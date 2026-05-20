import os
import re

import cv2

from core.OCR import (
    BODY_PATTERN,
    PLATE_PATTERN,
    VALID_REGION_CODES,
    _body_score,
    _candidate_score,
    _normalize_candidate,
    _prepare_variants,
    _region_score,
    _repair_candidate,
    _repair_region_code,
)


_PADDLE_OCR = None


def _get_paddle_ocr():
    global _PADDLE_OCR

    if _PADDLE_OCR is not None:
        return _PADDLE_OCR

    # Avoid a startup delay from repeated network host checks. Models are still
    # cached locally by PaddleX after the first download.
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "BOS")

    try:
        from paddleocr import PaddleOCR as PaddleOCRLib
    except Exception as exc:
        raise RuntimeError(
            "PaddleOCR backend selected, but the 'paddleocr' package is not installed."
        ) from exc

    try:
        _PADDLE_OCR = PaddleOCRLib(
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name="en_PP-OCRv5_mobile_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except TypeError:
        # Backward-compatible fallback for older PaddleOCR versions.
        _PADDLE_OCR = PaddleOCRLib(
            use_angle_cls=False,
            lang="en",
            det=True,
            rec=True,
            cls=False,
            show_log=False,
        )

    return _PADDLE_OCR


def _ensure_bgr(image):
    if image is None:
        return image
    if len(image.shape) == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if len(image.shape) == 3 and image.shape[2] == 1:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return image


def _extract_texts(result):
    texts = []
    if result is None:
        return texts

    if isinstance(result, dict):
        res = result.get("res", result)

        if isinstance(res, dict):
            rec_texts = res.get("rec_texts")
            rec_scores = res.get("rec_scores")
            if isinstance(rec_texts, list):
                if not isinstance(rec_scores, list):
                    rec_scores = [0.0] * len(rec_texts)
                for text, score in zip(rec_texts, rec_scores):
                    if isinstance(text, str):
                        texts.append((text, float(score or 0.0)))
                return texts

            rec_text = res.get("rec_text")
            rec_score = res.get("rec_score")
            if isinstance(rec_text, str):
                texts.append((rec_text, float(rec_score or 0.0)))
                return texts

        return texts

    if isinstance(result, (list, tuple)):
        for item in result:
            texts.extend(_extract_texts(item))
        return texts

    json_method = getattr(result, "json", None)
    if callable(json_method):
        try:
            texts.extend(_extract_texts(json_method()))
        except Exception:
            pass

    res_attr = getattr(result, "res", None)
    if isinstance(res_attr, dict):
        texts.extend(_extract_texts({"res": res_attr}))

    return texts


def _predict_texts(recognizer, variant_img):
    variant_img = _ensure_bgr(variant_img)

    try:
        output = recognizer.predict(variant_img)
        texts = _extract_texts(output)
        if texts:
            return texts
    except Exception:
        pass

    try:
        output = recognizer.ocr(variant_img)
    except Exception:
        return []

    texts = []
    for line in output or []:
        if not isinstance(line, (list, tuple)):
            continue
        for item in line:
            if (
                isinstance(item, (list, tuple))
                and len(item) >= 2
                and isinstance(item[1], (list, tuple))
                and len(item[1]) >= 2
            ):
                text = item[1][0]
                score = item[1][1]
                if isinstance(text, str):
                    texts.append((text, float(score or 0.0)))
    return texts


def _read_body_candidates(plate_img, recognizer, fast_mode=False):
    height, width = plate_img.shape[:2]
    if width == 0 or height == 0:
        return []

    split = max(1, int(width * 0.78))
    body_img = plate_img[:, :split]
    variants = _prepare_variants(body_img, fast_mode=fast_mode)
    best_candidates = []

    def add_candidate(value, score):
        for existing_value, existing_score in best_candidates:
            if existing_value == value and existing_score >= score:
                return
        best_candidates.append((value, score))

    for _, variant_img in variants:
        for text, confidence in _predict_texts(recognizer, variant_img):
            normalized = _normalize_candidate(text)
            if len(normalized) >= 6:
                normalized = normalized[:6]
            if BODY_PATTERN.fullmatch(normalized):
                add_candidate(normalized, _body_score(normalized, confidence))

    best_candidates.sort(key=lambda item: item[1], reverse=True)
    return best_candidates[:5]


def _read_region_candidates(plate_img, recognizer, fast_mode=False):
    height, width = plate_img.shape[:2]
    if width == 0 or height == 0:
        return []

    left = min(width - 1, max(1, int(width * 0.76)))
    right = min(width, max(left + 1, int(width * 0.94)))
    region_img = plate_img[:, left:right]
    variants = _prepare_variants(region_img, fast_mode=fast_mode)
    best_candidates = []

    def add_candidate(value, score):
        if not value.isdigit() or len(value) not in {2, 3}:
            return
        for existing_value, existing_score in best_candidates:
            if existing_value == value and existing_score >= score:
                return
        best_candidates.append((value, score))

    for _, variant_img in variants:
        for text, confidence in _predict_texts(recognizer, variant_img):
            digits = re.sub(r"\D", "", text)
            if digits:
                add_candidate(digits, _region_score(digits, confidence))

    best_candidates.sort(key=lambda item: item[1], reverse=True)
    return best_candidates[:5]


def recognize_plate_paddle(plate_img, fast_mode=False):
    if plate_img is None or plate_img.size == 0:
        return "", None

    recognizer = _get_paddle_ocr()
    variants = _prepare_variants(plate_img, fast_mode=fast_mode)
    best_candidate = ""
    best_score = -1.0
    best_variant_image = variants[0][1] if variants else None
    body_pool = {}
    region_pool = {}

    def add_to_pool(pool, key, score):
        if not key:
            return
        stats = pool.setdefault(key, {"best": -1.0, "hits": 0})
        stats["best"] = max(stats["best"], score)
        stats["hits"] += 1

    def pool_rank(item):
        _, stats = item
        return stats["best"] + stats["hits"] * 1.5

    for _, variant_img in variants:
        texts = _predict_texts(recognizer, variant_img)
        normalized_parts = []

        for text, confidence in texts:
            candidate = _normalize_candidate(text)
            if not candidate:
                continue

            normalized_parts.append((candidate, confidence))

            for repaired_candidate in _repair_candidate(candidate):
                for region_fixed_candidate in _repair_region_code(repaired_candidate):
                    score = _candidate_score(region_fixed_candidate, confidence)
                    if len(region_fixed_candidate) >= 6 and BODY_PATTERN.fullmatch(region_fixed_candidate[:6]):
                        add_to_pool(
                            body_pool,
                            region_fixed_candidate[:6],
                            _body_score(region_fixed_candidate[:6], confidence),
                        )
                    if PLATE_PATTERN.fullmatch(region_fixed_candidate):
                        add_to_pool(
                            region_pool,
                            region_fixed_candidate[6:],
                            _region_score(region_fixed_candidate[6:], confidence),
                        )
                    if score > best_score:
                        best_candidate = region_fixed_candidate
                        best_score = score
                        best_variant_image = variant_img

        if len(normalized_parts) > 1:
            combined = _normalize_candidate("".join(part[0] for part in normalized_parts))
            combined_confidence = sum(part[1] for part in normalized_parts) / len(normalized_parts)

            for repaired_candidate in _repair_candidate(combined):
                for region_fixed_candidate in _repair_region_code(repaired_candidate):
                    score = _candidate_score(region_fixed_candidate, combined_confidence)
                    if len(region_fixed_candidate) >= 6 and BODY_PATTERN.fullmatch(region_fixed_candidate[:6]):
                        add_to_pool(
                            body_pool,
                            region_fixed_candidate[:6],
                            _body_score(region_fixed_candidate[:6], combined_confidence),
                        )
                    if PLATE_PATTERN.fullmatch(region_fixed_candidate):
                        add_to_pool(
                            region_pool,
                            region_fixed_candidate[6:],
                            _region_score(region_fixed_candidate[6:], combined_confidence),
                        )
                    if score > best_score:
                        best_candidate = region_fixed_candidate
                        best_score = score
                        best_variant_image = variant_img

    body_candidates = _read_body_candidates(plate_img, recognizer, fast_mode=fast_mode)
    region_candidates = _read_region_candidates(plate_img, recognizer, fast_mode=fast_mode)

    if PLATE_PATTERN.fullmatch(best_candidate) and best_score >= 32.0:
        return best_candidate, best_variant_image

    for body, score in body_candidates:
        add_to_pool(body_pool, body, score)
    for region, score in region_candidates:
        add_to_pool(region_pool, region, score)

    body_bases = [
        (body, stats["best"] + stats["hits"] * 1.5)
        for body, stats in sorted(body_pool.items(), key=pool_rank, reverse=True)[:5]
    ]
    region_bases = [
        (region, stats["best"] + stats["hits"] * 1.5)
        for region, stats in sorted(region_pool.items(), key=pool_rank, reverse=True)[:5]
    ]

    seen = set()
    for body, body_score in body_bases:
        if not BODY_PATTERN.fullmatch(body):
            continue
        for region, region_score in region_bases:
            candidate = body + region
            if candidate in seen or not PLATE_PATTERN.fullmatch(candidate):
                continue
            seen.add(candidate)
            score = body_score + region_score + 4.0
            if region in VALID_REGION_CODES:
                score += 6.0
            if score > best_score:
                best_candidate = candidate
                best_score = score

    if len(best_candidate) < 6 or not PLATE_PATTERN.fullmatch(best_candidate):
        return "", best_variant_image

    return best_candidate, best_variant_image

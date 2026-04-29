import re

import cv2
import easyocr

from core.helper import fix_plate


reader = easyocr.Reader(["en"])
ALLOWED_CHARS = "ABCEHKMOPTXY0123456789"
ALLOWED_LETTERS = "ABCEHKMOPTXY"
PLATE_PATTERN = re.compile(r"^[ABCEHKMOPTXY][0-9]{3}[ABCEHKMOPTXY]{2}[0-9]{2,3}$")
BODY_PATTERN = re.compile(r"^[ABCEHKMOPTXY][0-9]{3}[ABCEHKMOPTXY]{2}$")
VALID_REGION_CODES = {
    "01", "02", "03", "04", "05", "06", "07", "08", "09", "10",
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "21",
    "22", "23", "24", "25", "26", "27", "28", "29", "30", "31",
    "32", "33", "34", "35", "36", "37", "38", "39", "40", "41",
    "42", "43", "44", "45", "46", "47", "48", "49", "50", "51",
    "52", "53", "54", "55", "56", "57", "58", "59", "60", "61",
    "62", "63", "64", "65", "66", "67", "68", "69", "70", "71",
    "72", "73", "74", "75", "76", "77", "78", "79", "80", "81",
    "82", "83", "86", "87", "89", "90", "92", "93", "94", "95",
    "96", "97", "98", "99", "102", "113", "116", "121", "123", "124",
    "125", "126", "134", "136", "138", "142", "147", "150", "152", "154",
    "159", "161", "163", "164", "173", "174", "177", "178", "186", "190",
    "193", "196", "197", "198", "199", "702", "716", "750", "761", "763",
    "774", "777", "790", "797", "799",
}
REGION_DIGIT_ALTERNATIVES = {
    "0": {"0", "8"},
    "1": {"1", "7"},
    "2": {"2", "7"},
    "3": {"3", "8"},
    "4": {"4"},
    "5": {"5", "6"},
    "6": {"6", "5"},
    "7": {"7", "1", "2"},
    "8": {"8", "3", "0"},
    "9": {"9", "6"},
}
DIGIT_SLOT_REPLACEMENTS = {
    "O": "0",
    "Q": "0",
    "D": "0",
    "B": "8",
    "S": "5",
    "G": "6",
    "Z": "2",
    "T": "1",
    "I": "1",
    "L": "1",
    "A": "1",
    "M": "1",
    "Y": "1",
}


def _normalize_candidate(text):
    candidate = re.sub(r"[^A-Za-z0-9]", "", text).upper()
    if not candidate or candidate == "RUS":
        return ""

    candidate = fix_plate(candidate)
    return "".join(char for char in candidate if char in ALLOWED_CHARS)


def _candidate_score(candidate, confidence):
    if not candidate:
        return -1.0

    score = float(confidence) * 10.0
    length = len(candidate)

    if 6 <= length <= 9:
        score += 2.0
    else:
        score -= abs(8 - length) * 0.7

    if len(candidate) == 9:
        score += 3.0

    if PLATE_PATTERN.fullmatch(candidate):
        score += 20.0
    else:
        if candidate[0] in ALLOWED_LETTERS:
            score += 1.5
        if length >= 4 and candidate[1:4].isdigit():
            score += 2.5
        if length >= 6 and all(char in ALLOWED_LETTERS for char in candidate[4:6]):
            score += 2.5
        if length >= 8 and candidate[6:].isdigit():
            score += 2.5

    return score


def _body_score(candidate, confidence):
    if not candidate:
        return -1.0

    score = float(confidence) * 10.0
    if BODY_PATTERN.fullmatch(candidate):
        score += 18.0
    else:
        score -= abs(6 - len(candidate)) * 0.8

    return score


def _region_score(candidate, confidence):
    if not candidate:
        return -1.0

    score = float(confidence) * 10.0
    if candidate in VALID_REGION_CODES:
        score += 14.0
    elif len(candidate) in {2, 3} and candidate.isdigit():
        score += 4.0
    else:
        score -= abs(3 - len(candidate)) * 1.2

    return score


def _repair_candidate(candidate):
    repaired = []

    def add_unique(value):
        if value not in repaired:
            repaired.append(value)

    add_unique(candidate)

    if len(candidate) >= 7:
        coerced = list(candidate)
        for index in range(min(len(coerced), 9)):
            if index in {1, 2, 3, 6, 7, 8}:
                if coerced[index].isdigit():
                    continue
                coerced[index] = DIGIT_SLOT_REPLACEMENTS.get(coerced[index], coerced[index])
        add_unique("".join(coerced))

    for current in list(repaired):
        if (
            len(current) == 7
            and current[0] in ALLOWED_LETTERS
            and current[1:3].isdigit()
            and all(char in ALLOWED_LETTERS for char in current[3:5])
            and current[5:].isdigit()
        ):
            add_unique(current[:3] + current[2] + current[3:])

        if (
            len(current) == 7
            and current[0] in ALLOWED_LETTERS
            and current[1:4].isdigit()
            and all(char in ALLOWED_LETTERS for char in current[4:6])
            and current[6].isdigit()
        ):
            add_unique(current[:7] + current[6])
            add_unique(current[:6] + "1" + current[6])

    return repaired


def _repair_region_code(candidate):
    if len(candidate) == 10 and BODY_PATTERN.fullmatch(candidate[:6]) and candidate[6:].isdigit():
        body = candidate[:6]
        region4 = candidate[6:]
        repaired = []
        if region4[1:] in VALID_REGION_CODES:
            repaired.append(body + region4[1:])
        if region4[:3] in VALID_REGION_CODES:
            repaired.append(body + region4[:3])
        if region4[2:] in VALID_REGION_CODES:
            repaired.append(body + region4[2:])
        if repaired:
            return repaired

    if not PLATE_PATTERN.fullmatch(candidate):
        return {candidate}

    body = candidate[:6]
    region = candidate[6:]
    if region in VALID_REGION_CODES:
        return [candidate]

    repaired = []

    if len(region) == 3:
        if region in VALID_REGION_CODES:
            return [candidate]

        if region[1:] in VALID_REGION_CODES:
            repaired.append(body + region[1:])

        for index, char in enumerate(region):
            for replacement in REGION_DIGIT_ALTERNATIVES.get(char, {char}):
                fixed_region = region[:index] + replacement + region[index + 1:]
                if fixed_region in VALID_REGION_CODES:
                    repaired.append(body + fixed_region)

    if not repaired:
        return [candidate]

    unique_repaired = []
    for value in repaired:
        if value not in unique_repaired:
            unique_repaired.append(value)
    return unique_repaired


def _prepare_variants(plate_img, fast_mode=False):
    gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)

    height, width = gray.shape[:2]
    if width == 0 or height == 0:
        return [("empty", gray)]

    baseline_scale = min(4.0, max(3.0, 320.0 / width))
    baseline_enlarged = cv2.resize(gray, None, fx=baseline_scale, fy=baseline_scale, interpolation=cv2.INTER_CUBIC)
    baseline_blur = cv2.GaussianBlur(baseline_enlarged, (3, 3), 0)
    baseline_otsu = cv2.threshold(baseline_blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    baseline_otsu_inv = cv2.threshold(baseline_blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    scale = min(7.0, max(4.0, 480.0 / width))
    enlarged = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(8, 8)).apply(enlarged)
    basic_blur = cv2.GaussianBlur(enlarged, (3, 3), 0)
    denoised = cv2.fastNlMeansDenoising(clahe, None, 10, 7, 21)
    denoised_soft = cv2.bilateralFilter(clahe, 9, 50, 50)
    sharpened = cv2.addWeighted(
        denoised,
        1.8,
        cv2.GaussianBlur(denoised, (0, 0), 1.5),
        -0.8,
        0,
    )
    blackhat = cv2.morphologyEx(
        sharpened,
        cv2.MORPH_BLACKHAT,
        cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
    )
    enhanced = cv2.add(sharpened, blackhat)
    enhanced_soft = cv2.addWeighted(
        denoised_soft,
        1.6,
        cv2.GaussianBlur(denoised_soft, (0, 0), 2.0),
        -0.6,
        0,
    )

    otsu = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    otsu_inv = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    basic_otsu = cv2.threshold(basic_blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    basic_otsu_inv = cv2.threshold(basic_blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    otsu_soft = cv2.threshold(enhanced_soft, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    otsu_inv_soft = cv2.threshold(enhanced_soft, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    adaptive = cv2.adaptiveThreshold(
        enhanced,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        35,
        9,
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    morph = cv2.morphologyEx(otsu_inv, cv2.MORPH_CLOSE, kernel)

    variants = [
        ("baseline_gray", baseline_enlarged),
        ("baseline_otsu", baseline_otsu),
        ("baseline_otsu_inv", baseline_otsu_inv),
        ("gray", enlarged),
        ("clahe", clahe),
        ("basic_otsu", basic_otsu),
        ("basic_otsu_inv", basic_otsu_inv),
        ("enhanced", enhanced),
        ("enhanced_soft", enhanced_soft),
        ("otsu", otsu),
        ("otsu_inv", otsu_inv),
        ("otsu_soft", otsu_soft),
        ("otsu_inv_soft", otsu_inv_soft),
        ("adaptive", adaptive),
        ("morph", morph),
    ]

    if fast_mode:
        return [
            ("baseline_gray", baseline_enlarged),
            ("baseline_otsu", baseline_otsu),
            ("gray", enlarged),
            ("enhanced", enhanced),
            ("otsu", otsu),
        ]

    return variants


def _collect_parts(detections, allowlist):
    parts = []

    for bbox, text, confidence in detections:
        candidate = re.sub(rf"[^{allowlist}]", "", text.upper())
        if not candidate:
            continue

        center_x = sum(point[0] for point in bbox) / len(bbox)
        parts.append((center_x, candidate, confidence))

    return parts


def _read_body_candidates(plate_img, fast_mode=False):
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
        detections = reader.readtext(
            variant_img,
            allowlist=ALLOWED_CHARS,
            detail=1,
            paragraph=False,
            contrast_ths=0.02,
            adjust_contrast=0.9,
        )
        parts = _collect_parts(detections, ALLOWED_CHARS)

        for _, candidate, confidence in parts:
            normalized = _normalize_candidate(candidate)
            if len(normalized) >= 6:
                normalized = normalized[:6]
            if BODY_PATTERN.fullmatch(normalized):
                add_candidate(normalized, _body_score(normalized, confidence))

        if len(parts) > 1:
            combined = "".join(part[1] for part in sorted(parts, key=lambda item: item[0]))
            normalized = _normalize_candidate(combined)
            if len(normalized) >= 6:
                normalized = normalized[:6]
            avg_confidence = sum(part[2] for part in parts) / len(parts)
            if BODY_PATTERN.fullmatch(normalized):
                add_candidate(normalized, _body_score(normalized, avg_confidence))

    best_candidates.sort(key=lambda item: item[1], reverse=True)
    return best_candidates[:5]


def _read_region_candidates(plate_img, fast_mode=False):
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
        detections = reader.readtext(
            variant_img,
            allowlist="0123456789",
            detail=1,
            paragraph=False,
            contrast_ths=0.02,
            adjust_contrast=0.9,
        )
        parts = _collect_parts(detections, "0123456789")

        for _, candidate, confidence in parts:
            add_candidate(candidate, _region_score(candidate, confidence))

        if len(parts) > 1:
            combined = "".join(part[1] for part in sorted(parts, key=lambda item: item[0]))
            avg_confidence = sum(part[2] for part in parts) / len(parts)
            add_candidate(combined, _region_score(combined, avg_confidence))

    best_candidates.sort(key=lambda item: item[1], reverse=True)
    return best_candidates[:5]


def recognize_plate(plate_img, fast_mode=False):
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
        detections = reader.readtext(
            variant_img,
            allowlist=ALLOWED_CHARS,
            detail=1,
            paragraph=False,
            contrast_ths=0.02,
            adjust_contrast=0.9,
        )

        normalized_parts = []

        for bbox, text, confidence in detections:
            candidate = _normalize_candidate(text)
            if not candidate:
                continue

            center_x = sum(point[0] for point in bbox) / len(bbox)
            normalized_parts.append((center_x, candidate, confidence))

            for repaired_candidate in _repair_candidate(candidate):
                for region_fixed_candidate in _repair_region_code(repaired_candidate):
                    score = _candidate_score(region_fixed_candidate, confidence)
                    if len(region_fixed_candidate) >= 6 and BODY_PATTERN.fullmatch(region_fixed_candidate[:6]):
                        add_to_pool(body_pool, region_fixed_candidate[:6], _body_score(region_fixed_candidate[:6], confidence))
                    if PLATE_PATTERN.fullmatch(region_fixed_candidate):
                        add_to_pool(region_pool, region_fixed_candidate[6:], _region_score(region_fixed_candidate[6:], confidence))
                    if score > best_score:
                        best_candidate = region_fixed_candidate
                        best_score = score
                        best_variant_image = variant_img

        if len(normalized_parts) > 1:
            combined = "".join(part[1] for part in sorted(normalized_parts, key=lambda item: item[0]))
            combined_confidence = sum(part[2] for part in normalized_parts) / len(normalized_parts)
            combined = _normalize_candidate(combined)

            for repaired_candidate in _repair_candidate(combined):
                for region_fixed_candidate in _repair_region_code(repaired_candidate):
                    score = _candidate_score(region_fixed_candidate, combined_confidence)
                    if len(region_fixed_candidate) >= 6 and BODY_PATTERN.fullmatch(region_fixed_candidate[:6]):
                        add_to_pool(body_pool, region_fixed_candidate[:6], _body_score(region_fixed_candidate[:6], combined_confidence))
                    if PLATE_PATTERN.fullmatch(region_fixed_candidate):
                        add_to_pool(region_pool, region_fixed_candidate[6:], _region_score(region_fixed_candidate[6:], combined_confidence))
                    if score > best_score:
                        best_candidate = region_fixed_candidate
                        best_score = score
                        best_variant_image = variant_img

    body_candidates = _read_body_candidates(plate_img, fast_mode=fast_mode)
    region_candidates = _read_region_candidates(plate_img, fast_mode=fast_mode)

    if PLATE_PATTERN.fullmatch(best_candidate) and best_score >= 32.0:
        return best_candidate, best_variant_image

    for body, score in body_candidates:
        add_to_pool(body_pool, body, score)
    for region, score in region_candidates:
        add_to_pool(region_pool, region, score)

    body_bases = []
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
            if (
                PLATE_PATTERN.fullmatch(best_candidate)
                and body == best_candidate[:6]
                and len(best_candidate[6:]) == 3
                and len(region) == 2
                and best_candidate[7:] == region
                and best_score >= 30.0
            ):
                continue
            seen.add(candidate)
            score = body_score + region_score + 4.0
            if region in VALID_REGION_CODES:
                score += 6.0
            if score > best_score:
                best_candidate = candidate
                best_score = score

    if len(best_candidate) < 6:
        return "", best_variant_image

    if not PLATE_PATTERN.fullmatch(best_candidate):
        print(f"Номер {best_candidate} не полностью соответствует формату")

    return best_candidate, best_variant_image

import re

import cv2
import easyocr

from core.helper import fix_plate


reader = easyocr.Reader(["en"])
ALLOWED_CHARS = "ABCEHKMOPTXY0123456789"
ALLOWED_LETTERS = "ABCEHKMOPTXY"
PLATE_PATTERN = re.compile(r"^[ABCEHKMOPTXY][0-9]{3}[ABCEHKMOPTXY]{2}[0-9]{2,3}$")
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


def _repair_candidate(candidate):
    repaired = []

    def add_unique(value):
        if value not in repaired:
            repaired.append(value)

    if len(candidate) >= 1 and candidate[0] == "O":
        add_unique("B" + candidate[1:])

    add_unique(candidate)

    if len(candidate) >= 7:
        coerced = list(candidate)
        for index in range(min(len(coerced), 9)):
            if index in {1, 2, 3, 6, 7, 8} and not coerced[index].isdigit():
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
    if not PLATE_PATTERN.fullmatch(candidate):
        return {candidate}

    body = candidate[:6]
    region = candidate[6:]
    if region in VALID_REGION_CODES:
        return [candidate]

    repaired = []

    if len(region) == 3:
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


def _prepare_variants(plate_img):
    gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)

    height, width = gray.shape[:2]
    if width == 0 or height == 0:
        return [("empty", gray)]

    scale = min(7.0, max(4.0, 480.0 / width))
    enlarged = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(8, 8)).apply(enlarged)
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

    return [
        ("enhanced", enhanced),
        ("enhanced_soft", enhanced_soft),
        ("otsu", otsu),
        ("otsu_inv", otsu_inv),
        ("otsu_soft", otsu_soft),
        ("otsu_inv_soft", otsu_inv_soft),
        ("adaptive", adaptive),
        ("morph", morph),
    ]


def recognize_plate(plate_img):
    variants = _prepare_variants(plate_img)
    best_candidate = ""
    best_score = -1.0
    best_variant_image = variants[0][1] if variants else None

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
                    if score > best_score:
                        best_candidate = region_fixed_candidate
                        best_score = score
                        best_variant_image = variant_img

    if len(best_candidate) < 6:
        return "", best_variant_image

    if not PLATE_PATTERN.fullmatch(best_candidate):
        print(f"Номер {best_candidate} не полностью соответствует формату")

    return best_candidate, best_variant_image

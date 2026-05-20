# Меняется одной строкой:
OCR_BACKEND = "easyocr"  # "easyocr", "crnn" или "paddleocr"


def get_ocr_backend():
    return OCR_BACKEND


def set_ocr_backend(name):
    global OCR_BACKEND
    normalized = (name or "").strip().lower()
    if normalized not in {"easyocr", "crnn", "paddleocr"}:
        raise ValueError(f"Unsupported OCR backend: {name}")
    OCR_BACKEND = normalized


def recognize_plate(plate_img, fast_mode=False):
    if OCR_BACKEND == "easyocr":
        from core.OCR import recognize_plate as recognize_plate_easyocr

        return recognize_plate_easyocr(plate_img, fast_mode=fast_mode)

    if OCR_BACKEND == "crnn":
        from core.CRNN import recognize_plate_crnn

        return recognize_plate_crnn(plate_img, fast_mode=fast_mode)

    if OCR_BACKEND == "paddleocr":
        from core.PaddleOCR import recognize_plate_paddle

        return recognize_plate_paddle(plate_img, fast_mode=fast_mode)

    raise ValueError(f"Unsupported OCR backend: {OCR_BACKEND}")

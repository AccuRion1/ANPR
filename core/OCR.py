import easyocr
import re
import cv2

from core.helper import fix_plate


reader = easyocr.Reader(['en'])

# ================================
# распознавание номера
# ================================

def recognize_plate(plate_img):

    gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2)
    gray = cv2.GaussianBlur(gray, (5,5), 0)
    _, thresh = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY)

    detections = reader.readtext(thresh)

    best_text = ""

    for detection in detections:
        candidate = re.sub(r'[^A-Za-z0-9]', '', detection[1])
        if candidate.lower() == "rus":
            continue
        if len(candidate) > len(best_text):
            best_text = candidate

    plate_number = best_text.upper()
    plate_number = fix_plate(plate_number)

    allowed_letters = "ABCEHKMOPTXY0123456789"
    plate_number = ''.join([c for c in plate_number if c in allowed_letters])

    if len(plate_number) < 6:
        return "", thresh   # ← ВАЖНО

    pattern = r'^[ABCEHKMOPTXY][0-9]{3}[ABCEHKMOPTXY]{2}[0-9]{2,3}$'
    if not re.match(pattern, plate_number):
        print(f"Номер {plate_number} не полностью соответствует формату")

    return plate_number, thresh
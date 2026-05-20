import cv2

from core.access_control import check_access
from core.OCR import PLATE_PATTERN
from core.plate_recognizer import get_ocr_backend, recognize_plate
from core.YOLOmodel import detect_plates


def _to_display_status(decision):
    if decision == "разрешен":
        return "ALLOWED"
    if decision == "запрещен":
        return "DENIED"
    return "UNREADABLE"


def _box_in_roi(box, roi):
    if roi is None:
        return True

    rx1, ry1, rx2, ry2 = roi
    x1, y1, x2, y2 = box
    center_x = (x1 + x2) // 2
    center_y = (y1 + y2) // 2
    return rx1 <= center_x <= rx2 and ry1 <= center_y <= ry2


def process_frame(
    frame,
    camera_name="Основная камера",
    direction="въезд",
    realtime=False,
    max_plates=None,
    return_details=False,
    roi=None,
):
    def build_operator_alert(plate_number, access_result, plate_found):
        if not plate_found:
            return "Требуется проверка оператором: номерной знак не обнаружен."
        if not plate_number:
            return "Требуется проверка оператором: номер не распознан или не соответствует формату."
        if not PLATE_PATTERN.fullmatch(plate_number):
            return "Требуется проверка оператором: распознанный номер не соответствует формату."
        if access_result and access_result.get("reason") == "РЅРѕРјРµСЂ РЅРµ РЅР°Р№РґРµРЅ":
            return "Требуется проверка оператором: номер отсутствует в базе данных."
        return ""

    if frame is None:
        empty_details = {
            "plate_number": None,
            "decision": None,
            "display_status": "UNREADABLE",
            "plate_crop": None,
            "processed_plate": None,
            "access_result": None,
            "operator_alert": "Требуется проверка оператором: кадр не получен.",
            "roi": roi,
            "ocr_backend": get_ocr_backend(),
        }
        return (None, None, empty_details) if return_details else (None, None)

    boxes = detect_plates(
        frame,
        max_plates=max_plates if max_plates is not None else (1 if realtime else None),
        realtime=realtime,
    )
    boxes = [box for box in boxes if _box_in_roi(box, roi)]

    display_frame = frame.copy() if realtime else (frame * 0.35).astype("uint8")
    detected_plate = None
    details = {
        "plate_number": None,
        "decision": None,
        "display_status": "UNREADABLE",
        "plate_crop": None,
        "processed_plate": None,
        "access_result": None,
        "operator_alert": "",
        "roi": roi,
        "ocr_backend": get_ocr_backend(),
    }

    if roi is not None:
        rx1, ry1, rx2, ry2 = roi
        cv2.rectangle(display_frame, (rx1, ry1), (rx2, ry2), (255, 255, 0), 2)
        cv2.putText(
            display_frame,
            "ROI",
            (rx1, max(25, ry1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 0),
            2,
        )

    for (x1, y1, x2, y2) in boxes:
        frame_height, frame_width = frame.shape[:2]
        pad_x = max(10, int((x2 - x1) * 0.14))
        pad_y = max(6, int((y2 - y1) * 0.20))

        crop_x1 = max(0, x1 - pad_x)
        crop_y1 = max(0, y1 - pad_y)
        crop_x2 = min(frame_width, x2 + pad_x)
        crop_y2 = min(frame_height, y2 + pad_y)

        plate = frame[crop_y1:crop_y2, crop_x1:crop_x2]
        if plate.size == 0:
            continue

        plate_number, processed_plate = recognize_plate(plate, fast_mode=realtime)

        access_result = None
        status_text = "не распознан"
        box_color = (0, 255, 255)

        if plate_number:
            access_result = check_access(
                plate_number=plate_number,
                camera_name=camera_name,
                direction=direction,
            )
            status_text = access_result["decision"]
            box_color = (0, 255, 0) if status_text == "разрешен" else (0, 0, 255)
            if detected_plate is None:
                detected_plate = plate_number

        if not realtime:
            display_frame[y1:y2, x1:x2] = frame[y1:y2, x1:x2]
        cv2.rectangle(display_frame, (x1, y1), (x2, y2), box_color, 2)

        display_plate = plate_number or "UNREADABLE"
        display_status = _to_display_status(status_text)

        cv2.putText(
            display_frame,
            display_plate,
            (x1, max(25, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            box_color,
            2,
        )

        cv2.putText(
            display_frame,
            display_status,
            (x1, min(frame_height - 10, y2 + 30)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            box_color,
            2,
        )

        if details["plate_crop"] is None:
            details = {
                "plate_number": plate_number,
                "decision": status_text if plate_number else None,
                "display_status": display_status,
                "plate_crop": plate.copy(),
                "processed_plate": processed_plate.copy() if processed_plate is not None else None,
                "access_result": access_result,
                "operator_alert": build_operator_alert(plate_number, access_result, True),
                "roi": roi,
                "ocr_backend": get_ocr_backend(),
            }

    if details["plate_crop"] is None:
        details["operator_alert"] = build_operator_alert(None, None, False)

    if return_details:
        return display_frame, detected_plate, details
    return display_frame, detected_plate


def handle_plate_number(plate_number, camera_name="Основная камера", direction="въезд"):
    if not plate_number:
        return None
    result = check_access(
        plate_number=plate_number,
        camera_name=camera_name,
        direction=direction,
    )
    return result["decision"]

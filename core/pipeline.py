import cv2

from core.YOLOmodel import detect_plates
from core.OCR import recognize_plate
#from core.preprocessing import straighten_plate
from core.access_control import check_access


def process_frame(frame, camera_name="Основная камера", direction="въезд"):

    boxes = detect_plates(frame)

    dark_frame = (frame * 0.35).astype("uint8")

    for (x1, y1, x2, y2) in boxes:

        frame_height, frame_width = frame.shape[:2]
        pad_x = max(10, int((x2 - x1) * 0.14))
        pad_y = max(6, int((y2 - y1) * 0.20))

        crop_x1 = max(0, x1 - pad_x)
        crop_y1 = max(0, y1 - pad_y)
        crop_x2 = min(frame_width, x2 + pad_x)
        crop_y2 = min(frame_height, y2 + pad_y)

        plate = frame[crop_y1:crop_y2, crop_x1:crop_x2]

        #plate = straighten_plate(plate)

        # получаем и текст, и обработанное изображение
        plate_number, processed_plate = recognize_plate(plate)

        # 🔥 показать обработанный номер
        if processed_plate is not None:
            cv2.imshow(f"Processed Plate", processed_plate)

        status_text = "НЕ РАСПОЗНАН"
        box_color = (0, 255, 255)

        if plate_number:
            access_result = check_access(
                plate_number=plate_number,
                camera_name=camera_name,
                direction=direction,
            )
            status_text = access_result["decision"]#.upper()
            box_color = (0, 255, 0) if access_result["decision"] == "разрешен" else (0, 0, 255)

        dark_frame[y1:y2, x1:x2] = frame[y1:y2, x1:x2]

        cv2.rectangle(dark_frame, (x1, y1), (x2, y2), box_color, 2)

        display_status = status_text
        display_plate = plate_number or "UNREADABLE"

        if status_text == "разрешен":
            display_status = "ALLOWED"
        elif status_text == "запрещен":
            display_status = "DENIED"

        cv2.putText(
            dark_frame,
            display_plate,
            (x1, y1-10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            box_color,
            2
        )

        cv2.putText(
            dark_frame,
            display_status,
            (x1, y2 + 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            box_color,
            2
        )

    return dark_frame

def handle_plate_number(plate_number, camera_name="Основная камера", direction="въезд"):
    if not plate_number:
        return None
    result = check_access(
        plate_number=plate_number,
        camera_name=camera_name,
        direction=direction,
    )
    return result["decision"]

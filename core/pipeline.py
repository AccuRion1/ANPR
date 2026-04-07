import cv2

from core.YOLOmodel import detect_plates
from core.OCR import recognize_plate
#from core.preprocessing import straighten_plate
from core.access_control import check_access


def process_frame(frame, camera_name="main_camera", direction="entry"):

    boxes = detect_plates(frame)

    dark_frame = (frame * 0.35).astype("uint8")

    for (x1, y1, x2, y2) in boxes:

        plate = frame[y1:y2, x1:x2]

        #plate = straighten_plate(plate)

        # получаем и текст, и обработанное изображение
        plate_number, processed_plate = recognize_plate(plate)

        # 🔥 показать обработанный номер
        if processed_plate is not None:
            cv2.imshow(f"Processed Plate", processed_plate)

        status_text = "UNREADABLE"
        box_color = (0, 255, 255)

        if plate_number:
            access_result = check_access(
                plate_number=plate_number,
                camera_name=camera_name,
                direction=direction,
            )
            status_text = access_result["decision"].upper()
            box_color = (0, 255, 0) if access_result["decision"] == "allowed" else (0, 0, 255)

        dark_frame[y1:y2, x1:x2] = frame[y1:y2, x1:x2]

        cv2.rectangle(dark_frame, (x1, y1), (x2, y2), box_color, 2)

        cv2.putText(
            dark_frame,
            plate_number or "UNREADABLE",
            (x1, y1-10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            box_color,
            2
        )

        cv2.putText(
            dark_frame,
            status_text,
            (x1, y2 + 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            box_color,
            2
        )

    return dark_frame

def handle_plate_number(plate_number, camera_name="main_camera", direction="entry"):
    if not plate_number:
        return None
    result = check_access(
        plate_number=plate_number,
        camera_name=camera_name,
        direction=direction,
    )
    return result["decision"]
    return "Разрешен" if ok else "Запрещен"

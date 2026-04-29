from pathlib import Path
from ultralytics import YOLO

base_dir = Path(__file__).resolve().parent.parent
model_path = base_dir / 'models' / 'yolov8_plate.pt'

yolo_model = YOLO(str(model_path))

def detect_plates(frame, max_plates=None, realtime=False):
    imgsz = 512 if realtime else 640
    results = yolo_model.predict(frame, imgsz=imgsz, verbose=False)
    boxes = []

    for result in results:
        for box in result.boxes.xyxy:
            x1, y1, x2, y2 = map(int, box)
            boxes.append((x1, y1, x2, y2))

    boxes.sort(key=lambda item: (item[2] - item[0]) * (item[3] - item[1]), reverse=True)

    if max_plates is not None:
        boxes = boxes[:max_plates]

    return boxes

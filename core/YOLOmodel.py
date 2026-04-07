from ultralytics import YOLO


yolo_model = YOLO("models/yolov8_plate.pt")

def detect_plates(frame):
    results = yolo_model(frame)
    boxes = []

    for result in results:
        for box in result.boxes.xyxy:
            x1, y1, x2, y2 = map(int, box)
            boxes.append((x1, y1, x2, y2))

    return boxes
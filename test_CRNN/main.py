python test_CRNN/main.py --source test_images/video1.mp4 --process-fps 2 --display-fps 30import argparse
from pathlib import Path
import cv2
import time
import torch

from CRNN import load_char_set, load_model, recognize_plate
from YOLOmodel import detect_plates


def draw_plate_box(frame, box, text):
    x1, y1, x2, y2 = box
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(
        frame,
        text,
        (x1, max(y1 - 10, 15)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )


def load_models():
    base_dir = Path(__file__).resolve().parent.parent
    char_set_path = base_dir / 'models' / 'recognition' / 'char_set.json'
    model_path = base_dir / 'models' / 'recognition' / 'crnn_plate.pth'

    _, idx_to_char = load_char_set(char_set_path)
    num_classes = len(idx_to_char) - 1
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    model = load_model(model_path, num_classes, device)
    return model, idx_to_char, device


def process_image(source_path, model, idx_to_char, device, max_plates=1):
    image = cv2.imread(str(source_path))
    if image is None:
        raise FileNotFoundError(f'Unable to load image: {source_path}')

    boxes = detect_plates(image, max_plates=max_plates, realtime=False)
    if not boxes:
        print('No plates detected')
    else:
        for box in boxes:
            x1, y1, x2, y2 = box
            plate_img = image[y1:y2, x1:x2]
            text, score = recognize_plate(plate_img, model, idx_to_char, device)
            draw_plate_box(image, box, f'{text} ({score:.2f})')
            print(f'Plate: {text}, score={score:.4f}')

    cv2.imshow('Result', image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def process_video(source_path, model, idx_to_char, device, max_plates=1, process_fps=2, display_fps=30):
    cap = cv2.VideoCapture(str(source_path))
    if not cap.isOpened():
        raise FileNotFoundError(f'Unable to open video: {source_path}')

    source_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    process_every_n = max(1, int(round(source_fps / process_fps)))
    frame_index = 0
    last_time = time.time()
    fps = 0.0
    last_boxes = []
    last_texts = []

    wait_ms = max(1, int(round(1000.0 / display_fps)))

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_index += 1
        output_frame = frame.copy()

        if frame_index % process_every_n == 0:
            last_boxes = detect_plates(frame, max_plates=max_plates, realtime=True)
            last_texts = []
            for box in last_boxes:
                x1, y1, x2, y2 = box
                plate_img = frame[y1:y2, x1:x2]
                text, score = recognize_plate(plate_img, model, idx_to_char, device)
                last_texts.append((text, score))
                draw_plate_box(output_frame, box, f'{text} ({score:.2f})')
                print(f'Frame {frame_index}: Plate={text}, score={score:.4f}')
        else:
            for box, (text, score) in zip(last_boxes, last_texts):
                draw_plate_box(output_frame, box, f'{text} ({score:.2f})')

        now = time.time()
        fps = 0.9 * fps + 0.1 * (1.0 / max(now - last_time, 1e-6)) if frame_index > 1 else 0.0
        last_time = now

        cv2.putText(output_frame, f'FPS: {fps:.1f}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        cv2.imshow('Video', output_frame)

        if cv2.waitKey(wait_ms) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description='YOLO + CRNN demo without database')
    parser.add_argument('--source', required=True, help='Path to image or video file')
    parser.add_argument('--max-plates', type=int, default=1, help='Maximum plates to recognize per frame')
    parser.add_argument('--process-fps', type=int, default=2, help='Processing FPS for video')
    parser.add_argument('--display-fps', type=int, default=30, help='Playback FPS for video display')
    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.exists():
        raise FileNotFoundError(f'Source file not found: {source_path}')

    model, idx_to_char, device = load_models()

    if source_path.suffix.lower() in ['.mp4', '.avi', '.mov', '.mkv', '.wmv']:
        process_video(
            source_path,
            model,
            idx_to_char,
            device,
            max_plates=args.max_plates,
            process_fps=args.process_fps,
            display_fps=args.display_fps,
        )
    else:
        process_image(source_path, model, idx_to_char, device, max_plates=args.max_plates)


if __name__ == '__main__':
    main()

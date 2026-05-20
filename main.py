import threading
import time

import cv2

from core.pipeline import process_frame
from core.plate_recognizer import get_ocr_backend


def process_image(path, camera_name="Изображение", direction="въезд"):
    image = cv2.imread(path)
    frame, _ = process_frame(image, camera_name=camera_name, direction=direction)
    cv2.imshow("Result", frame)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def _resize_for_realtime(frame, max_width=960):
    if frame is None:
        return frame

    height, width = frame.shape[:2]
    if width <= max_width:
        return frame

    scale = max_width / float(width)
    return cv2.resize(frame, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)


def _draw_fps(frame, fps_value, mode_label):
    cv2.putText(
        frame,
        f"{mode_label} FPS: {fps_value:.1f}",
        (15, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2,
    )
    return frame


class AsyncFrameProcessor:
    def __init__(self, camera_name, direction):
        self.camera_name = camera_name
        self.direction = direction
        self._lock = threading.Lock()
        self._pending_frame = None
        self._latest_result = None
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def submit(self, frame):
        with self._lock:
            self._pending_frame = frame.copy()

    def get_latest_result(self):
        with self._lock:
            return self._latest_result

    def stop(self):
        self._running = False
        self._thread.join(timeout=2.0)

    def _worker(self):
        while self._running:
            frame = None

            with self._lock:
                if self._pending_frame is not None:
                    frame = self._pending_frame
                    self._pending_frame = None

            if frame is None:
                time.sleep(0.002)
                continue

            processed_frame, detected_plate = process_frame(
                frame,
                camera_name=self.camera_name,
                direction=self.direction,
                realtime=True,
                max_plates=1,
            )

            with self._lock:
                self._latest_result = {
                    "frame": processed_frame,
                    "detected_plate": detected_plate,
                    "timestamp": time.perf_counter(),
                }


def process_video(path, camera_name="Видео", direction="въезд", target_display_fps=20, process_fps=None):
    if process_fps is None:
        process_fps = 8 if get_ocr_backend() == "crnn" else 2

    cap = cv2.VideoCapture(path)
    source_fps = cap.get(cv2.CAP_PROP_FPS)
    source_fps = source_fps if source_fps and source_fps > 0 else 25.0
    process_every_n_frames = max(1, int(round(source_fps / float(process_fps))))
    processor = AsyncFrameProcessor(camera_name, direction)

    frame_index = 0
    last_shown_time = time.perf_counter()
    current_fps = 0.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_index += 1
            frame = _resize_for_realtime(frame)

            if frame_index % process_every_n_frames == 0:
                processor.submit(frame)

            latest_result = processor.get_latest_result()
            display_frame = latest_result["frame"].copy() if latest_result is not None else frame.copy()

            now = time.perf_counter()
            delta = now - last_shown_time
            if delta > 0:
                current_fps = 1.0 / delta
            last_shown_time = now

            display_frame = _draw_fps(display_frame, current_fps, "Display")
            cv2.imshow("Video", display_frame)

            wait_ms = max(1, int(1000 / max(target_display_fps, 1)))
            if cv2.waitKey(wait_ms) & 0xFF == 27:
                break
    finally:
        processor.stop()
        cap.release()
        cv2.destroyAllWindows()


def process_camera(camera_index=0, camera_name="Веб-камера 0", direction="въезд", process_fps=None):
    if process_fps is None:
        process_fps = 8 if get_ocr_backend() == "crnn" else 2

    cap = cv2.VideoCapture(camera_index)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    source_fps = cap.get(cv2.CAP_PROP_FPS)
    source_fps = source_fps if source_fps and source_fps > 0 else 25.0
    process_every_n_frames = max(1, int(round(source_fps / float(process_fps))))
    processor = AsyncFrameProcessor(camera_name, direction)

    frame_index = 0
    last_shown_time = time.perf_counter()
    current_fps = 0.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_index += 1
            frame = _resize_for_realtime(frame)

            if frame_index % process_every_n_frames == 0:
                processor.submit(frame)

            latest_result = processor.get_latest_result()
            display_frame = latest_result["frame"].copy() if latest_result is not None else frame.copy()

            now = time.perf_counter()
            delta = now - last_shown_time
            if delta > 0:
                current_fps = 1.0 / delta
            last_shown_time = now

            display_frame = _draw_fps(display_frame, current_fps, "Display")
            cv2.imshow("Camera", display_frame)

            if cv2.waitKey(1) & 0xFF == 27:
                break
    finally:
        processor.stop()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    mode = input("Выберите режим (image / video / camera): ")

    if mode == "image":
        process_image("test_images/car9.jpg", camera_name="Изображение", direction="выезд")
    elif mode == "video":
        process_video("test_images/video1.mp4", camera_name="Видео", direction="въезд")
    elif mode == "camera":
        process_camera(camera_name="Веб-камера 0", direction="въезд")

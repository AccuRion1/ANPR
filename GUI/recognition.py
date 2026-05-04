import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import cv2
from PIL import Image, ImageTk

from core.database import get_active_camera
from core.pipeline import process_frame
from imitation.gate import GateSimulator


def _resize_for_realtime(frame, max_width=960):
    if frame is None:
        return None

    height, width = frame.shape[:2]
    if width <= max_width:
        return frame

    scale = max_width / float(width)
    return cv2.resize(frame, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)


def _frame_to_tk(frame, max_size):
    if frame is None:
        return None

    if len(frame.shape) == 2:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
    else:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    image = Image.fromarray(rgb_frame)
    image.thumbnail(max_size)
    return ImageTk.PhotoImage(image=image)


def _pretty_decision(decision):
    if decision == "разрешен":
        return "Разрешен"
    if decision == "запрещен":
        return "Запрещен"
    return "Не распознан"


class _BaseMonitorFrame:
    def __init__(self, parent):
        self.frame = tk.Frame(parent)
        self.frame.columnconfigure(0, weight=3)
        self.frame.columnconfigure(1, weight=1)
        self.frame.rowconfigure(1, weight=1)

        self._lock = threading.Lock()
        self._capture_thread = None
        self._process_thread = None
        self._video_running = False
        self._cap = None
        self._source_kind = None
        self._source_value = None
        self._camera_name = "Источник"
        self._direction = "въезд"
        self._process_interval = 0.4
        self._latest_raw_frame = None
        self._latest_display_frame = None
        self._latest_details = None
        self._status_text = "Ожидание запуска"
        self._last_processed_at = 0.0
        self._roi = None
        self._static_mode = False

        self.gate = GateSimulator(open_seconds=10, on_state_change=self._on_gate_state_changed)

        controls = tk.Frame(self.frame)
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 5))
        self.build_controls(controls)

        left_panel = tk.LabelFrame(self.frame, text="Наблюдение")
        left_panel.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(0, weight=1)

        self.image_label = tk.Label(left_panel, bg="#202020")
        self.image_label.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        right_panel = tk.LabelFrame(self.frame, text="Распознавание")
        right_panel.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=10)

        self.camera_value = tk.Label(right_panel, anchor="w", justify="left", font=("Arial", 11))
        self.direction_value = tk.Label(right_panel, anchor="w", justify="left", font=("Arial", 11))
        self.plate_value = tk.Label(right_panel, anchor="w", justify="left", font=("Arial", 18, "bold"), fg="#0a58ca")
        self.decision_value = tk.Label(right_panel, anchor="w", justify="left", font=("Arial", 12, "bold"))
        self.status_value = tk.Label(right_panel, anchor="w", justify="left", wraplength=280)
        self.gate_value = tk.Label(right_panel, anchor="w", justify="left", font=("Arial", 12, "bold"))
        self.roi_value = tk.Label(right_panel, anchor="w", justify="left", wraplength=280)

        tk.Label(right_panel, text="Камера:", anchor="w").pack(fill="x", padx=10, pady=(10, 0))
        self.camera_value.pack(fill="x", padx=10)
        tk.Label(right_panel, text="Направление:", anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        self.direction_value.pack(fill="x", padx=10)
        tk.Label(right_panel, text="Номер:", anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        self.plate_value.pack(fill="x", padx=10)
        tk.Label(right_panel, text="Решение:", anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        self.decision_value.pack(fill="x", padx=10)
        tk.Label(right_panel, text="Состояние потока:", anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        self.status_value.pack(fill="x", padx=10)
        tk.Label(right_panel, text="Шлагбаум:", anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        self.gate_value.pack(fill="x", padx=10)
        tk.Label(right_panel, text="Зона распознавания:", anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        self.roi_value.pack(fill="x", padx=10)

        crop_frame = tk.LabelFrame(right_panel, text="Фрагмент номера")
        crop_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.crop_label = tk.Label(crop_frame, text="Нет данных")
        self.crop_label.pack(fill="both", expand=True, padx=8, pady=8)

        self._refresh_ui()

    def build_controls(self, parent):
        pass

    def _set_status(self, text):
        with self._lock:
            self._status_text = text

    def _on_gate_state_changed(self, state):
        if self.frame.winfo_exists():
            self.frame.after(0, lambda: self.gate_value.config(text=state))

    def _format_roi_text(self):
        if self._roi is None:
            return "Не выбрана"
        x1, y1, x2, y2 = self._roi
        return f"x1={x1}, y1={y1}, x2={x2}, y2={y2}"

    def select_roi(self):
        with self._lock:
            frame = self._latest_raw_frame.copy() if self._latest_raw_frame is not None else None

        if frame is None:
            messagebox.showinfo("Зона распознавания", "Сначала запустите наблюдение или загрузите изображение.")
            return

        roi = cv2.selectROI("Выберите зону распознавания", frame, showCrosshair=True, fromCenter=False)
        cv2.destroyWindow("Выберите зону распознавания")

        x, y, w, h = roi
        if w <= 0 or h <= 0:
            self._set_status("Выбор зоны отменен.")
            return

        self._roi = (int(x), int(y), int(x + w), int(y + h))
        self._set_status("Зона распознавания обновлена.")

        if self._static_mode:
            self._reprocess_static_frame()

    def clear_roi(self):
        self._roi = None
        self._set_status("Зона распознавания сброшена.")
        if self._static_mode:
            self._reprocess_static_frame()

    def start_stream(self, source_value, source_kind, camera_name, direction):
        self.stop_stream()
        self._source_value = source_value
        self._source_kind = source_kind
        self._camera_name = camera_name or "Источник"
        self._direction = (direction or "въезд").strip().lower()
        self._video_running = True
        self._latest_raw_frame = None
        self._latest_display_frame = None
        self._latest_details = None
        self._last_processed_at = 0.0
        self._static_mode = False
        self._set_status("Подключение к источнику...")

        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._capture_thread.start()
        self._process_thread.start()

    def load_image(self, file_path, camera_name="Изображение", direction="въезд"):
        self.stop_stream()
        image = cv2.imread(file_path)
        if image is None:
            messagebox.showerror("Ошибка", "Не удалось открыть изображение.")
            return

        self._camera_name = camera_name
        self._direction = direction
        self._latest_raw_frame = image
        self._static_mode = True
        self._set_status(f"Изображение: {os.path.basename(file_path)}")
        self._reprocess_static_frame()

    def _reprocess_static_frame(self):
        if self._latest_raw_frame is None:
            return

        frame, _, details = process_frame(
            self._latest_raw_frame.copy(),
            camera_name=self._camera_name,
            direction=self._direction,
            realtime=False,
            max_plates=1,
            return_details=True,
            roi=self._roi,
        )

        self._latest_display_frame = frame
        self._latest_details = details

        access_result = details.get("access_result") if details else None
        if access_result and access_result.get("decision") == "разрешен" and not access_result.get("is_duplicate"):
            self.gate.request_open(authorized_plate=details.get("plate_number"))

    def stop_stream(self):
        self._video_running = False

        if self._cap is not None:
            self._cap.release()
            self._cap = None

        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1.0)
        if self._process_thread and self._process_thread.is_alive():
            self._process_thread.join(timeout=1.0)

        self._capture_thread = None
        self._process_thread = None

    def stop(self):
        self.stop_stream()
        self.gate.shutdown()

    def _open_capture(self):
        if self._source_kind == "rtsp":
            cap = cv2.VideoCapture(self._source_value, cv2.CAP_FFMPEG)
        else:
            cap = cv2.VideoCapture(self._source_value)

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _capture_loop(self):
        while self._video_running:
            if self._cap is None or not self._cap.isOpened():
                self._cap = self._open_capture()
                if not self._cap.isOpened():
                    self._set_status("Не удалось открыть поток. Повторная попытка...")
                    time.sleep(2.0)
                    continue
                self._set_status("Поток подключен")

            ret, frame = self._cap.read()
            if not ret:
                if self._source_kind == "video":
                    self._set_status("Видео завершено")
                    self._video_running = False
                    break

                self._set_status("Поток потерян. Переподключение...")
                self._cap.release()
                self._cap = None
                time.sleep(0.5)
                continue

            frame = _resize_for_realtime(frame)
            with self._lock:
                self._latest_raw_frame = frame.copy()

        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _process_loop(self):
        while self._video_running:
            snapshot = None
            with self._lock:
                if self._latest_raw_frame is not None:
                    snapshot = self._latest_raw_frame.copy()

            if snapshot is None:
                time.sleep(0.03)
                continue

            now = time.perf_counter()
            if now - self._last_processed_at < self._process_interval:
                time.sleep(0.01)
                continue

            self._last_processed_at = now
            processed_frame, _, details = process_frame(
                snapshot,
                camera_name=self._camera_name,
                direction=self._direction,
                realtime=True,
                max_plates=1,
                return_details=True,
                roi=self._roi,
            )

            access_result = details.get("access_result") if details else None
            if access_result and access_result.get("decision") == "разрешен" and not access_result.get("is_duplicate"):
                self.gate.request_open(authorized_plate=details.get("plate_number"))

            with self._lock:
                self._latest_display_frame = processed_frame
                self._latest_details = details

    def _refresh_ui(self):
        if self.frame.winfo_exists():
            with self._lock:
                display_frame = self._latest_display_frame.copy() if self._latest_display_frame is not None else None
                raw_frame = self._latest_raw_frame.copy() if self._latest_raw_frame is not None else None
                details = dict(self._latest_details) if self._latest_details else None
                status_text = self._status_text
                camera_name = self._camera_name
                direction = self._direction

            frame_to_show = display_frame if display_frame is not None else raw_frame
            if frame_to_show is not None:
                video_image = _frame_to_tk(frame_to_show, (900, 620))
                self.image_label.config(image=video_image, text="")
                self.image_label.image = video_image
            else:
                self.image_label.config(image="", text="Нет видеопотока", fg="white")
                self.image_label.image = None

            plate_text = "Не найден"
            decision_text = "Не распознан"
            crop_frame = None

            if details:
                plate_text = details.get("plate_number") or "Не найден"
                access_result = details.get("access_result")
                if access_result:
                    decision_text = _pretty_decision(access_result.get("decision"))
                    if access_result.get("incident_description"):
                        status_text = f"{status_text}\nИнцидент: {access_result['incident_description']}"
                crop_frame = details.get("plate_crop")

            self.camera_value.config(text=camera_name or "Не указана")
            self.direction_value.config(text=(direction or "не задан").capitalize())
            self.plate_value.config(text=plate_text)
            self.decision_value.config(
                text=decision_text,
                fg="#198754" if decision_text == "Разрешен" else "#dc3545" if decision_text == "Запрещен" else "#6c757d",
            )
            self.status_value.config(text=status_text)
            self.gate_value.config(text=self.gate.get_state())
            self.roi_value.config(text=self._format_roi_text())

            if crop_frame is not None and crop_frame.size:
                crop_image = _frame_to_tk(crop_frame, (260, 120))
                self.crop_label.config(image=crop_image, text="")
                self.crop_label.image = crop_image
            else:
                self.crop_label.config(image="", text="Нет данных")
                self.crop_label.image = None

            self.frame.after(50, self._refresh_ui)


class RecognitionFrame(_BaseMonitorFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.start_observation()

    def build_controls(self, parent):
        tk.Button(parent, text="Переподключить поток", command=self.start_observation).pack(side=tk.LEFT, padx=5)
        tk.Button(parent, text="Выбрать зону", command=self.select_roi).pack(side=tk.LEFT, padx=5)
        tk.Button(parent, text="Сбросить зону", command=self.clear_roi).pack(side=tk.LEFT, padx=5)
        tk.Button(parent, text="Открыть шлагбаум", command=lambda: self.gate.request_open()).pack(side=tk.LEFT, padx=5)

    def start_observation(self):
        camera = get_active_camera()
        if camera is None:
            self._set_status("В таблице cameras нет активной камеры.")
            return

        camera_url = camera.get("url")
        if not camera_url:
            self._set_status("У активной камеры не заполнен URL.")
            return

        self.start_stream(
            source_value=camera_url,
            source_kind="rtsp",
            camera_name=camera.get("name") or "Камера",
            direction=camera.get("direction") or "въезд",
        )


class LoadFrame(_BaseMonitorFrame):
    def build_controls(self, parent):
        tk.Button(parent, text="Загрузить изображение", command=self.select_image).pack(side=tk.LEFT, padx=5)
        tk.Button(parent, text="Загрузить видео", command=self.select_video).pack(side=tk.LEFT, padx=5)
        tk.Button(parent, text="Выбрать зону", command=self.select_roi).pack(side=tk.LEFT, padx=5)
        tk.Button(parent, text="Сбросить зону", command=self.clear_roi).pack(side=tk.LEFT, padx=5)
        tk.Button(parent, text="Открыть шлагбаум", command=lambda: self.gate.request_open()).pack(side=tk.LEFT, padx=5)

    def select_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp")])
        if not file_path:
            return
        self.load_image(file_path, camera_name="Загруженное изображение", direction="въезд")

    def select_video(self):
        file_path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv")])
        if not file_path:
            return
        self.start_stream(
            source_value=file_path,
            source_kind="video",
            camera_name="Видео",
            direction="въезд",
        )

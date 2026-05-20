import os
import threading
import time
from datetime import datetime

import cv2
from PyQt5.QtCore import QTimer, Qt, QSize
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QFileDialog,
    QHeaderView,
    QGroupBox,
)

from auth.auth_service import get_current_user, session_manager
from core.database import (
    DATETIME_DISPLAY_FORMAT,
    add_guest_plate,
    add_registered_plate,
    delete_guest_plate,
    delete_registered_plate,
    get_active_camera,
    get_active_cameras,
    get_access_events,
    get_all_guest_plates,
    get_all_registered_plates_with_owners,
    get_employees_for_select,
    get_guest_plate_by_number,
    get_incidents,
    get_registered_plate_by_number,
    update_guest_plate,
    update_registered_plate,
    get_all_cameras,
    add_camera,
    update_camera,
    delete_camera,
    get_camera_by_name,
)
from core.pipeline import process_frame
from core.plate_recognizer import get_ocr_backend
from imitation.gate import GateSimulator


def _cv_frame_to_qpixmap(frame, max_size=None):
    if frame is None:
        return QPixmap()

    if len(frame.shape) == 2:
        rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
    else:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    height, width = rgb.shape[:2]
    bytes_per_line = 3 * width
    qimage = QImage(rgb.data, width, height, bytes_per_line, QImage.Format_RGB888)
    pixmap = QPixmap.fromImage(qimage)
    if max_size:
        return pixmap.scaled(max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return pixmap


def _pretty_decision(decision):
    if decision == "разрешен":
        return "Разрешен"
    if decision == "запрещен":
        return "Запрещен"
    return "Не распознан"


class BaseMonitorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._lock = threading.Lock()
        self._capture_thread = None
        self._process_thread = None
        self._video_running = False
        self._cap = None
        self._source_kind = None
        self._source_value = None
        self._camera_name = "Источник"
        self._direction = "въезд"
        self._camera_location = ""
        self._process_interval = 0.12 if get_ocr_backend() == "crnn" else 0.35
        self._latest_raw_frame = None
        self._latest_raw_timestamp = 0.0
        self._latest_display_frame = None
        self._latest_display_timestamp = 0.0
        self._latest_details = None
        self._status_text = "Ожидание запуска"
        self._last_processed_at = 0.0
        self._roi = None
        self._static_mode = False
        self.gate = GateSimulator(open_seconds=10, on_state_change=self._on_gate_state_changed)

        self._build_ui()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_ui)
        self._refresh_timer.start(40)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        control_box = QGroupBox("Управление")
        control_layout = QHBoxLayout()
        self.build_controls(control_layout)
        control_box.setLayout(control_layout)
        layout.addWidget(control_box)

        content_layout = QHBoxLayout()
        layout.addLayout(content_layout)

        self.video_display = QLabel("Нет видеопотока")
        self.video_display.setStyleSheet("background:#202020; color:#fff; border:1px solid #444;")
        self.video_display.setAlignment(Qt.AlignCenter)
        self.video_display.setMinimumSize(640, 360)
        self.video_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout.addWidget(self.video_display, 3)

        info_box = QGroupBox("Инфопанель")
        info_layout = QVBoxLayout()
        info_box.setLayout(info_layout)
        content_layout.addWidget(info_box, 1)

        self.camera_value = QLabel("-")
        self.direction_value = QLabel("-")
        self.location_value = QLabel("-")
        self.plate_value = QLabel("Не найден")
        self.plate_value.setStyleSheet("font-size: 18px; font-weight: bold; color: #0a58ca;")
        self.decision_value = QLabel("Не распознан")
        self.status_value = QLabel(self._status_text)
        self.status_value.setWordWrap(True)
        self.operator_alert_value = QLabel("Нет")
        self.operator_alert_value.setWordWrap(True)
        self.operator_alert_value.setStyleSheet("color: #dc3545; font-weight: bold;")
        self.gate_value = QLabel(self.gate.get_state())
        self.roi_value = QLabel(self._format_roi_text())
        self.roi_value.setWordWrap(True)
        self.crop_preview = QLabel("Нет данных")
        self.crop_preview.setAlignment(Qt.AlignCenter)
        self.crop_preview.setStyleSheet("background:#fafafa; border:1px solid #ddd;")
        self.crop_preview.setMinimumSize(260, 120)

        info_layout.addWidget(QLabel("Камера:"))
        info_layout.addWidget(self.camera_value)
        info_layout.addWidget(QLabel("Местоположение:"))
        info_layout.addWidget(self.location_value)
        info_layout.addWidget(QLabel("Направление:"))
        info_layout.addWidget(self.direction_value)
        info_layout.addWidget(QLabel("Номер:"))
        info_layout.addWidget(self.plate_value)
        info_layout.addWidget(QLabel("Решение:"))
        info_layout.addWidget(self.decision_value)
        info_layout.addWidget(QLabel("Состояние потока:"))
        info_layout.addWidget(self.status_value)
        info_layout.addWidget(QLabel("Уведомление оператору:"))
        info_layout.addWidget(self.operator_alert_value)
        info_layout.addWidget(QLabel("Шлагбаум:"))
        info_layout.addWidget(self.gate_value)
        info_layout.addWidget(QLabel("Зона распознавания:"))
        info_layout.addWidget(self.roi_value)
        info_layout.addWidget(QLabel("Фрагмент номера:"))
        info_layout.addWidget(self.crop_preview)

        info_layout.addStretch(1)

    def build_controls(self, layout):
        raise NotImplementedError

    def _set_status(self, text):
        with self._lock:
            self._status_text = text

    def _on_gate_state_changed(self, state):
        self.gate_value.setText(state)

    def _format_roi_text(self):
        if self._roi is None:
            return "Не выбрана"
        x1, y1, x2, y2 = self._roi
        return f"x1={x1}, y1={y1}, x2={x2}, y2={y2}"

    def select_roi(self):
        with self._lock:
            frame = self._latest_raw_frame.copy() if self._latest_raw_frame is not None else None

        if frame is None:
            QMessageBox.information(self, "Зона распознавания", "Сначала запустите наблюдение или загрузите изображение.")
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

    def start_stream(self, source_value, source_kind, camera_name, direction, camera_location=None):
        self.stop_stream()
        self._source_value = source_value
        self._source_kind = source_kind
        self._camera_name = camera_name or "Источник"
        self._camera_location = camera_location or ""
        self._direction = (direction or "въезд").strip().lower()
        self._video_running = True
        self._latest_raw_frame = None
        self._latest_raw_timestamp = 0.0
        self._latest_display_frame = None
        self._latest_display_timestamp = 0.0
        self._latest_details = None
        self._last_processed_at = 0.0
        self._static_mode = False
        self._process_interval = 0.12 if get_ocr_backend() == "crnn" else 0.35
        self._set_status("Подключение к источнику...")

        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._capture_thread.start()
        self._process_thread.start()

    def load_image(self, file_path, camera_name="Изображение", direction="въезд"):
        self.stop_stream()
        image = cv2.imread(file_path)
        if image is None:
            QMessageBox.critical(self, "Ошибка", "Не удалось открыть изображение.")
            return

        self._camera_name = camera_name
        self._camera_location = ""
        self._direction = direction
        self._latest_raw_frame = image
        self._latest_raw_timestamp = time.perf_counter()
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
        self._latest_display_timestamp = time.perf_counter()
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

            frame = self._resize_for_realtime(frame)
            with self._lock:
                self._latest_raw_frame = frame.copy()
                self._latest_raw_timestamp = time.perf_counter()

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
                time.sleep(0.02)
                continue

            now = time.perf_counter()
            if now - self._last_processed_at < self._process_interval:
                time.sleep(0.005)
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
                self._latest_display_timestamp = time.perf_counter()
                self._latest_details = details

    def _refresh_ui(self):
        with self._lock:
            display_frame = self._latest_display_frame.copy() if self._latest_display_frame is not None else None
            raw_frame = self._latest_raw_frame.copy() if self._latest_raw_frame is not None else None
            raw_ts = self._latest_raw_timestamp
            display_ts = self._latest_display_timestamp
            details = dict(self._latest_details) if self._latest_details else None
            status_text = self._status_text
            camera_name = self._camera_name
            direction = self._direction

        frame_to_show = display_frame
        if raw_frame is not None and (frame_to_show is None or (raw_ts - display_ts) > 0.2):
            frame_to_show = raw_frame

        if frame_to_show is not None:
            video_pixmap = _cv_frame_to_qpixmap(frame_to_show, QSize(900, 620))
            self.video_display.setPixmap(video_pixmap)
            self.video_display.setText("")
        else:
            self.video_display.setPixmap(QPixmap())
            self.video_display.setText("Нет видеопотока")

        plate_text = "Не найден"
        decision_text = "Не распознан"
        crop_frame = None
        operator_alert = ""

        if details:
            plate_text = details.get("plate_number") or "Не найден"
            access_result = details.get("access_result")
            if access_result:
                decision_text = _pretty_decision(access_result.get("decision"))
                if access_result.get("incident_description"):
                    status_text = f"{status_text}\nИнцидент: {access_result['incident_description']}"
            crop_frame = details.get("plate_crop")
            operator_alert = details.get("operator_alert") or ""

        self.camera_value.setText(camera_name or "Не указана")
        self.location_value.setText(self._camera_location or "Не указана")
        self.direction_value.setText((direction or "не задан").capitalize())
        self.plate_value.setText(plate_text)
        self.decision_value.setText(decision_text)
        self.decision_value.setStyleSheet(
            "color: #198754;" if decision_text == "Разрешен" else "color: #dc3545;" if decision_text == "Запрещен" else "color: #6c757d;"
        )
        self.status_value.setText(status_text)
        self.operator_alert_value.setText(operator_alert or "Нет")
        self.gate_value.setText(self.gate.get_state())
        self.roi_value.setText(self._format_roi_text())

        if crop_frame is not None and getattr(crop_frame, "size", 0):
            crop_pixmap = _cv_frame_to_qpixmap(crop_frame, QSize(260, 120))
            self.crop_preview.setPixmap(crop_pixmap)
            self.crop_preview.setText("")
        else:
            self.crop_preview.setPixmap(QPixmap())
            self.crop_preview.setText("Нет данных")

    def _resize_for_realtime(self, frame, max_width=960):
        if frame is None:
            return None
        height, width = frame.shape[:2]
        if width <= max_width:
            return frame
        scale = max_width / float(width)
        return cv2.resize(frame, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)


class RecognitionPage(BaseMonitorPage):
    def __init__(self, parent=None):
        self._camera_lookup = {}
        self.camera_combo = QComboBox()
        super().__init__(parent)
        self.refresh_camera_list()
        self.start_observation()

    def build_controls(self, layout):
        layout.addWidget(QLabel("Камера:"))
        layout.addWidget(self.camera_combo)
        layout.addWidget(self._make_button("Подключить", self.start_observation))
        layout.addWidget(self._make_button("Обновить камеры", self.refresh_camera_list))
        layout.addWidget(self._make_button("Выбрать зону", self.select_roi))
        layout.addWidget(self._make_button("Сбросить зону", self.clear_roi))
        layout.addWidget(self._make_button("Открыть шлагбаум", lambda: self.gate.request_open()))

    def _make_button(self, text, callback):
        button = QPushButton(text)
        button.clicked.connect(callback)
        return button

    def refresh_camera_list(self):
        cameras = get_active_cameras()
        self._camera_lookup = {camera["name"]: camera for camera in cameras}
        self.camera_combo.clear()
        self.camera_combo.addItems(list(self._camera_lookup.keys()))

    def start_observation(self):
        selected_name = self.camera_combo.currentText().strip()
        camera = self._camera_lookup.get(selected_name) if selected_name else None
        if camera is None:
            camera = get_active_camera()
            if camera:
                self.camera_combo.setCurrentText(camera.get("name", ""))

        if camera is None:
            self._set_status("В таблице cameras нет активной камеры.")
            return

        camera_url = camera.get("url")
        if not camera_url:
            self._set_status("У выбранной камеры не заполнен URL.")
            return

        self.start_stream(
            source_value=camera_url,
            source_kind="rtsp",
            camera_name=camera.get("name") or "Камера",
            direction=camera.get("direction") or "въезд",
            camera_location=camera.get("location") or "",
        )


class LoadPage(BaseMonitorPage):
    def build_controls(self, layout):
        layout.addWidget(self._make_button("Загрузить изображение", self.select_image))
        layout.addWidget(self._make_button("Загрузить видео", self.select_video))
        layout.addWidget(self._make_button("Выбрать зону", self.select_roi))
        layout.addWidget(self._make_button("Сбросить зону", self.clear_roi))
        layout.addWidget(self._make_button("Открыть шлагбаум", lambda: self.gate.request_open()))

    def _make_button(self, text, callback):
        button = QPushButton(text)
        button.clicked.connect(callback)
        return button

    def select_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите изображение", filter="Image files (*.jpg *.jpeg *.png *.bmp)")
        if not file_path:
            return
        self.load_image(file_path, camera_name="Загруженное изображение", direction="въезд")

    def select_video(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите видео", filter="Video files (*.mp4 *.avi *.mov *.mkv)")
        if not file_path:
            return
        self.start_stream(
            source_value=file_path,
            source_kind="video",
            camera_name="Видео",
            direction="въезд",
        )


class EventsPanel(QWidget):
    def __init__(self, parent=None, columns=None, headings=None, fetcher=None):
        super().__init__(parent)
        self.fetcher = fetcher
        self._build_ui(columns, headings)
        self.refresh_rows()

    def _build_ui(self, columns, headings):
        layout = QVBoxLayout(self)
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Поиск:"))
        self.search_edit = QLineEdit()
        self.search_edit.textChanged.connect(self.refresh_rows)
        search_layout.addWidget(self.search_edit)
        clear_button = QPushButton("Очистить")
        clear_button.clicked.connect(lambda: self.search_edit.clear())
        search_layout.addWidget(clear_button)
        layout.addLayout(search_layout)

        self.table = QTableWidget(0, len(columns), self)
        self.table.setHorizontalHeaderLabels(headings)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

    def refresh_rows(self):
        self.table.setRowCount(0)
        rows = self.fetcher(search=self.search_edit.text().strip())
        for row in rows:
            row_index = self.table.rowCount()
            self.table.insertRow(row_index)
            for column, value in enumerate(row):
                item = QTableWidgetItem(str(value) if value is not None else "")
                self.table.setItem(row_index, column, item)


class EventsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        events_panel = EventsPanel(
            self,
            columns=("plate", "time", "camera", "direction", "access_level", "access"),
            headings=("Номер ТС", "Время события", "Видеокамера", "Направление", "Уровень доступа", "Доступ"),
            fetcher=get_access_events,
        )
        incidents_panel = EventsPanel(
            self,
            columns=("plate", "time", "camera", "description"),
            headings=("Номер ТС", "Время инцидента", "Видеокамера", "Описание"),
            fetcher=get_incidents,
        )

        tabs.addTab(events_panel, "Журнал событий")
        tabs.addTab(incidents_panel, "Журнал инцидентов")


class PlatesPanel(QWidget):
    def __init__(self, parent=None, panel_type="registered"):
        super().__init__(parent)
        self.panel_type = panel_type
        self.selected_plate = None
        self._build_ui()
        self.refresh_rows()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        add_button = QPushButton("Добавить номер")
        add_button.clicked.connect(self.add_dialog)
        refresh_button = QPushButton("Обновить")
        refresh_button.clicked.connect(self.refresh_rows)
        self.edit_button = QPushButton("Редактировать")
        self.edit_button.clicked.connect(self.edit_selected)
        self.edit_button.setEnabled(False)
        self.delete_button = QPushButton("Удалить")
        self.delete_button.clicked.connect(self.delete_selected)
        self.delete_button.setEnabled(False)

        controls.addWidget(add_button)
        controls.addWidget(refresh_button)
        controls.addWidget(self.edit_button)
        controls.addWidget(self.delete_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Поиск:"))
        self.search_edit = QLineEdit()
        self.search_edit.textChanged.connect(self.refresh_rows)
        search_layout.addWidget(self.search_edit)
        clear_button = QPushButton("Очистить")
        clear_button.clicked.connect(lambda: self.search_edit.clear())
        search_layout.addWidget(clear_button)
        layout.addLayout(search_layout)

        self.table = QTableWidget(0, 5 if self.panel_type == "guest" else 4, self)
        if self.panel_type == "registered":
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(["Номер ТС", "Владелец", "Статус", "На территории"])
        else:
            self.table.setColumnCount(5)
            self.table.setHorizontalHeaderLabels(["Номер ТС", "Время начала", "Время окончания", "Статус", "На территории"])

        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)

    def _on_selection_changed(self):
        selected_items = self.table.selectedItems()
        self.selected_plate = selected_items[0].text() if selected_items else None
        enabled = bool(self.selected_plate)
        self.edit_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)

    def refresh_rows(self):
        self.table.setRowCount(0)
        search_value = self.search_edit.text().strip()
        if self.panel_type == "registered":
            rows = get_all_registered_plates_with_owners(search=search_value)
        else:
            rows = get_all_guest_plates(search=search_value)

        for row in rows:
            row_index = self.table.rowCount()
            self.table.insertRow(row_index)
            for column, value in enumerate(row):
                self.table.setItem(row_index, column, QTableWidgetItem(str(value) if value is not None else ""))

    def add_dialog(self):
        if self.panel_type == "registered":
            self._open_registered_dialog("Добавить зарегистрированный номер")
        else:
            self._open_guest_dialog("Добавить гостевой номер")

    def edit_selected(self):
        if not self.selected_plate:
            QMessageBox.critical(self, "Ошибка", "Сначала выберите номер.")
            return
        if self.panel_type == "registered":
            data = get_registered_plate_by_number(self.selected_plate)
            if not data:
                QMessageBox.critical(self, "Ошибка", "Не удалось загрузить запись.")
                return
            self._open_registered_dialog("Редактировать зарегистрированный номер", initial_data=data)
        else:
            data = get_guest_plate_by_number(self.selected_plate)
            if not data:
                QMessageBox.critical(self, "Ошибка", "Не удалось загрузить запись.")
                return
            self._open_guest_dialog("Редактировать гостевой номер", initial_data=data)

    def delete_selected(self):
        if not self.selected_plate:
            QMessageBox.critical(self, "Ошибка", "Сначала выберите номер.")
            return
        if self.panel_type == "registered":
            confirm = QMessageBox.question(self, "Подтверждение", f"Удалить зарегистрированный номер {self.selected_plate}?", QMessageBox.Yes | QMessageBox.No)
            if confirm != QMessageBox.Yes:
                return
            if delete_registered_plate(self.selected_plate):
                self.selected_plate = None
                self.refresh_rows()
        else:
            confirm = QMessageBox.question(self, "Подтверждение", f"Удалить гостевой номер {self.selected_plate}?", QMessageBox.Yes | QMessageBox.No)
            if confirm != QMessageBox.Yes:
                return
            if delete_guest_plate(self.selected_plate):
                self.selected_plate = None
                self.refresh_rows()

    def _open_registered_dialog(self, title, initial_data=None):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setFixedSize(480, 320)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        plate_entry = QLineEdit()
        form.addRow("Номер ТС:", plate_entry)

        employees = get_employees_for_select()
        owner_names = ["Не выбран"] + [employee["full_name"] for employee in employees]
        owner_combo = QComboBox()
        owner_combo.addItems(owner_names)
        form.addRow("Сотрудник:", owner_combo)

        status_combo = QComboBox()
        status_combo.addItems(["Активен", "Неактивен"])
        form.addRow("Статус:", status_combo)

        territory_combo = QComboBox()
        territory_combo.addItems(["Да", "Нет"])
        form.addRow("На территории:", territory_combo)

        if initial_data:
            plate_entry.setText(initial_data["plate_number"])
            owner_combo.setCurrentText(next((name for name in owner_names if name == initial_data.get("owner_name")), "Не выбран"))
            status_combo.setCurrentText("Активен" if initial_data.get("status") else "Неактивен")
            territory_combo.setCurrentText("Да" if initial_data.get("on_territory") else "Нет")

        layout.addLayout(form)
        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(lambda: self._save_registered(dialog, plate_entry, owner_combo, employees, status_combo, territory_combo, initial_data))
        layout.addWidget(save_button)
        dialog.exec_()

    def _save_registered(self, dialog, plate_entry, owner_combo, employees, status_combo, territory_combo, initial_data):
        plate_number = plate_entry.text().strip().upper()
        if not plate_number:
            QMessageBox.critical(self, "Ошибка", "Введите номер ТС.")
            return

        owner_name = owner_combo.currentText().strip()
        owner_id = next((employee["id"] for employee in employees if employee["full_name"] == owner_name), None)
        status = status_combo.currentText() == "Активен"
        on_territory = territory_combo.currentText() == "Да"

        if initial_data:
            ok = update_registered_plate(initial_data["plate_number"], plate_number, owner_id, status, on_territory)
        else:
            ok = add_registered_plate(plate_number, owner_id, status, on_territory)

        if not ok:
            QMessageBox.critical(self, "Ошибка", "Не удалось сохранить зарегистрированный номер.")
            return

        dialog.accept()
        self.refresh_rows()

    def _open_guest_dialog(self, title, initial_data=None):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setFixedSize(480, 380)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        plate_entry = QLineEdit()
        form.addRow("Номер ТС:", plate_entry)

        start_entry = QLineEdit()
        start_entry.setPlaceholderText(DATETIME_DISPLAY_FORMAT)
        form.addRow("Время начала:", start_entry)

        end_entry = QLineEdit()
        end_entry.setPlaceholderText(DATETIME_DISPLAY_FORMAT)
        form.addRow("Время окончания:", end_entry)

        status_combo = QComboBox()
        status_combo.addItems(["Активен", "Неактивен"])
        form.addRow("Статус:", status_combo)

        territory_combo = QComboBox()
        territory_combo.addItems(["Да", "Нет"])
        form.addRow("На территории:", territory_combo)

        if initial_data:
            plate_entry.setText(initial_data["plate_number"])
            start_entry.setText(initial_data["start_time"])
            end_entry.setText(initial_data["end_time"])
            status_combo.setCurrentText("Активен" if initial_data.get("status") else "Неактивен")
            territory_combo.setCurrentText("Да" if initial_data.get("on_territory") else "Нет")

        layout.addLayout(form)
        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(lambda: self._save_guest(dialog, plate_entry, start_entry, end_entry, status_combo, territory_combo, initial_data))
        layout.addWidget(save_button)
        dialog.exec_()

    def _save_guest(self, dialog, plate_entry, start_entry, end_entry, status_combo, territory_combo, initial_data):
        plate_number = plate_entry.text().strip().upper()
        start_time = start_entry.text().strip()
        end_time = end_entry.text().strip()
        if not plate_number or not start_time or not end_time:
            QMessageBox.critical(self, "Ошибка", "Заполните номер и временной интервал.")
            return

        try:
            datetime.strptime(start_time, DATETIME_DISPLAY_FORMAT)
            datetime.strptime(end_time, DATETIME_DISPLAY_FORMAT)
        except ValueError:
            QMessageBox.critical(self, "Ошибка", f"Время нужно вводить в формате {DATETIME_DISPLAY_FORMAT}.")
            return

        status = status_combo.currentText() == "Активен"
        on_territory = territory_combo.currentText() == "Да"

        if initial_data:
            ok = update_guest_plate(
                initial_data["plate_number"],
                plate_number,
                start_time,
                end_time,
                status,
                on_territory,
            )
        else:
            ok = add_guest_plate(plate_number, start_time, end_time, status, on_territory)

        if not ok:
            QMessageBox.critical(self, "Ошибка", "Не удалось сохранить гостевой номер.")
            return

        dialog.accept()
        self.refresh_rows()


class PlatesPage(QWidget):
    """Management page: left content area with tables and right vertical buttons to switch topics.

    Left side shows either the plates tables (registered/guest) or the cameras table.
    Right side has vertical buttons: 'Номера' then 'Камеры'.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)

        # Left: stacked content area
        self.left_stack = QStackedWidget()

        # Plates tab widget (registered + guest)
        plates_tab = QTabWidget()
        self.registered_panel = PlatesPanel(self, panel_type="registered")
        self.guest_panel = PlatesPanel(self, panel_type="guest")
        plates_tab.addTab(self.registered_panel, "Зарегистрированные номера")
        plates_tab.addTab(self.guest_panel, "Гостевые номера")

        # Cameras panel (will be shown as the second page)
        self.cameras_panel = None

        self.left_stack.addWidget(plates_tab)

        layout.addWidget(self.left_stack, 3)

        # Right: vertical buttons to switch topics
        right_box = QVBoxLayout()
        right_box.setSpacing(8)
        right_box.addStretch(1)

        self.btn_numbers = QPushButton("Номера")
        self.btn_numbers.clicked.connect(self.show_numbers)
        right_box.addWidget(self.btn_numbers)

        self.btn_cameras = QPushButton("Камеры")
        self.btn_cameras.clicked.connect(self.show_cameras)
        right_box.addWidget(self.btn_cameras)

        right_box.addStretch(10)

        right_widget = QWidget()
        right_widget.setLayout(right_box)
        layout.addWidget(right_widget, 1)

    def show_numbers(self):
        self.left_stack.setCurrentIndex(0)

    def show_cameras(self):
        # Lazily create cameras panel
        if self.cameras_panel is None:
            self.cameras_panel = CamerasPanel(self)
            self.left_stack.addWidget(self.cameras_panel)
        self.left_stack.setCurrentWidget(self.cameras_panel)


class CamerasPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_name = None
        self._build_ui()
        self.refresh_rows()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # top controls (left side behavior is preserved)
        controls = QHBoxLayout()
        add_btn = QPushButton("Добавить Камеру")
        add_btn.clicked.connect(self.add_dialog)
        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self.refresh_rows)
        edit_btn = QPushButton("Редактировать")
        edit_btn.clicked.connect(self.edit_selected)
        delete_btn = QPushButton("Удалить")
        delete_btn.clicked.connect(self.delete_selected)

        self.edit_btn = edit_btn
        self.delete_btn = delete_btn
        self.edit_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)

        controls.addWidget(add_btn)
        controls.addWidget(refresh_btn)
        controls.addWidget(edit_btn)
        controls.addWidget(delete_btn)
        controls.addStretch(1)
        layout.addLayout(controls)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Поиск:"))
        self.search_edit = QLineEdit()
        self.search_edit.textChanged.connect(self.refresh_rows)
        search_layout.addWidget(self.search_edit)
        clear_button = QPushButton("Очистить")
        clear_button.clicked.connect(lambda: self.search_edit.clear())
        search_layout.addWidget(clear_button)
        layout.addLayout(search_layout)

        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["Название", "URL", "Местоположение", "Направление", "Статус"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)

    def _on_selection_changed(self):
        items = self.table.selectedItems()
        self.selected_name = items[0].text() if items else None
        enabled = bool(self.selected_name)
        self.edit_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)

    def refresh_rows(self):
        self.table.setRowCount(0)
        rows = get_all_cameras(search=self.search_edit.text().strip())
        for row in rows:
            idx = self.table.rowCount()
            self.table.insertRow(idx)
            for c, val in enumerate(row):
                self.table.setItem(idx, c, QTableWidgetItem(str(val) if val is not None else ""))

    def add_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Добавить камеру")
        dialog.setFixedSize(480, 320)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        name_edit = QLineEdit()
        url_edit = QLineEdit()
        location_edit = QLineEdit()
        direction_edit = QLineEdit()
        status_combo = QComboBox()
        status_combo.addItems(["Активен", "Неактивен"])

        form.addRow("Название:", name_edit)
        form.addRow("URL:", url_edit)
        form.addRow("Местоположение:", location_edit)
        form.addRow("Направление:", direction_edit)
        form.addRow("Статус:", status_combo)

        layout.addLayout(form)
        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(lambda: self._save_camera(dialog, name_edit, url_edit, location_edit, direction_edit, status_combo))
        layout.addWidget(save_btn)
        dialog.exec_()

    def _save_camera(self, dialog, name_edit, url_edit, location_edit, direction_edit, status_combo):
        name = name_edit.text().strip()
        url = url_edit.text().strip()
        location = location_edit.text().strip()
        direction = direction_edit.text().strip()
        status = status_combo.currentText() == "Активен"
        if not name or not url:
            QMessageBox.critical(self, "Ошибка", "Введите название и URL.")
            return
        ok = add_camera(name, url, location, direction, status)
        if not ok:
            QMessageBox.critical(self, "Ошибка", "Не удалось добавить камеру.")
            return
        dialog.accept()
        self.refresh_rows()

    def edit_selected(self):
        if not self.selected_name:
            QMessageBox.critical(self, "Ошибка", "Сначала выберите камеру.")
            return
        data = get_camera_by_name(self.selected_name)
        if not data:
            QMessageBox.critical(self, "Ошибка", "Не удалось загрузить запись.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Редактировать камеру")
        dialog.setFixedSize(480, 320)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        name_edit = QLineEdit(data.get("name") or "")
        url_edit = QLineEdit(data.get("url") or "")
        location_edit = QLineEdit(data.get("location") or "")
        direction_edit = QLineEdit(data.get("direction") or "")
        status_combo = QComboBox()
        status_combo.addItems(["Активен", "Неактивен"])
        status_combo.setCurrentText("Активен" if data.get("status") else "Неактивен")

        form.addRow("Название:", name_edit)
        form.addRow("URL:", url_edit)
        form.addRow("Местоположение:", location_edit)
        form.addRow("Направление:", direction_edit)
        form.addRow("Статус:", status_combo)

        layout.addLayout(form)
        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(lambda: self._update_camera(dialog, data.get("name"), name_edit, url_edit, location_edit, direction_edit, status_combo))
        layout.addWidget(save_btn)
        dialog.exec_()

    def _update_camera(self, dialog, original_name, name_edit, url_edit, location_edit, direction_edit, status_combo):
        name = name_edit.text().strip()
        url = url_edit.text().strip()
        location = location_edit.text().strip()
        direction = direction_edit.text().strip()
        status = status_combo.currentText() == "Активен"
        if not name or not url:
            QMessageBox.critical(self, "Ошибка", "Введите название и URL.")
            return
        ok = update_camera(original_name, name, url, location, direction, status)
        if not ok:
            QMessageBox.critical(self, "Ошибка", "Не удалось сохранить камеру.")
            return
        dialog.accept()
        self.refresh_rows()

    def delete_selected(self):
        if not self.selected_name:
            QMessageBox.critical(self, "Ошибка", "Сначала выберите камеру.")
            return
        confirm = QMessageBox.question(self, "Подтверждение", f"Удалить камеру {self.selected_name}?", QMessageBox.Yes | QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        if delete_camera(self.selected_name):
            self.selected_name = None
            self.refresh_rows()
        else:
            QMessageBox.critical(self, "Ошибка", "Не удалось удалить камеру.")


class QtMainWindow(QMainWindow):
    def __init__(self, session_id):
        super().__init__()
        self.session_id = session_id
        user = get_current_user(session_id)
        if not user:
            QMessageBox.critical(self, "Ошибка", "Сессия истекла")
            self.close()
            return

        self.username = user["username"]
        self.role = user["role"]
        self.setWindowTitle("NikolaAutoNPR")
        self.resize(1280, 820)

        self._build_ui()
        self.current_page = None
        self.show_recognition()

    def _build_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        header_layout = QHBoxLayout()
        title_label = QLabel("NikolaAutoNPR")
        title_label.setStyleSheet("font-size: 22px; font-weight: bold;")
        header_layout.addWidget(title_label)

        header_layout.addStretch(1)
        self.user_button = QPushButton(f"{self.username} | {self.role}")
        self.user_button.clicked.connect(self.logout)
        header_layout.addWidget(self.user_button)
        main_layout.addLayout(header_layout)

        nav_layout = QHBoxLayout()
        self.recognition_button = QPushButton("Наблюдение")
        self.recognition_button.clicked.connect(self.show_recognition)
        self.load_button = QPushButton("Загрузить")
        self.load_button.clicked.connect(self.show_load)
        self.events_button = QPushButton("Журнал событий")
        self.events_button.clicked.connect(self.show_events)
        self.plates_button = QPushButton("Управление")
        self.plates_button.clicked.connect(self.show_plates)

        for button in (self.recognition_button, self.load_button, self.events_button, self.plates_button):
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(36)
            nav_layout.addWidget(button)

        main_layout.addLayout(nav_layout)

        self.stack = QStackedWidget(self)
        main_layout.addWidget(self.stack, 1)

        self.recognition_page = RecognitionPage(self)
        self.load_page = LoadPage(self)
        self.events_page = EventsPage(self)
        self.plates_page = PlatesPage(self)

        self.stack.addWidget(self.recognition_page)
        self.stack.addWidget(self.load_page)
        self.stack.addWidget(self.events_page)
        self.stack.addWidget(self.plates_page)

    def _cleanup_current(self):
        if self.current_page is not None:
            stop_method = getattr(self.current_page, "stop", None)
            if callable(stop_method):
                stop_method()

    def show_recognition(self):
        self._cleanup_current()
        self.stack.setCurrentWidget(self.recognition_page)
        self.current_page = self.recognition_page

    def show_load(self):
        self._cleanup_current()
        self.stack.setCurrentWidget(self.load_page)
        self.current_page = self.load_page

    def show_events(self):
        self._cleanup_current()
        self.stack.setCurrentWidget(self.events_page)
        self.current_page = self.events_page

    def show_plates(self):
        self._cleanup_current()
        self.stack.setCurrentWidget(self.plates_page)
        self.current_page = self.plates_page

    def logout(self):
        session_manager.destroy_session(self.session_id)
        self.close()

    def closeEvent(self, event):
        self._cleanup_current()
        super().closeEvent(event)


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    login = QtMainWindow("test_session")
    login.show()
    sys.exit(app.exec_())

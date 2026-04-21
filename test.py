import sys
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QLabel, QFileDialog, QVBoxLayout, QTextEdit
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import QTimer
import cv2
from main import process_frame

class PlateApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Распознавание номеров")
        self.setGeometry(100, 100, 800, 600)

        # UI элементы
        self.layout = QVBoxLayout()
        self.image_label = QLabel("Здесь будет изображение")
        self.image_label.setFixedSize(640, 480)
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)

        self.btn_load = QPushButton("Выбрать изображение")
        self.btn_camera = QPushButton("Запустить вебкамеру")

        self.layout.addWidget(self.image_label)
        self.layout.addWidget(self.result_text)
        self.layout.addWidget(self.btn_load)
        self.layout.addWidget(self.btn_camera)
        self.setLayout(self.layout)

        # Сигналы кнопок
        self.btn_load.clicked.connect(self.load_image)
        self.btn_camera.clicked.connect(self.start_camera)

        # Таймер для видео
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.cap = None

    def load_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выбрать изображение", "", "Images (*.png *.jpg *.jpeg)")
        if file_path:
            frame = cv2.imread(file_path)
            processed = process_frame(frame)
            self.show_frame(processed)

    def start_camera(self):
        if self.cap is None:
            self.cap = cv2.VideoCapture(0)
            self.timer.start(30)  # обновление каждые 30 мс

    def update_frame(self):
        ret, frame = self.cap.read()
        if ret:
            processed = process_frame(frame)
            self.show_frame(processed)
        else:
            self.cap.release()
            self.timer.stop()
            self.cap = None

    def show_frame(self, frame):
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.image_label.setPixmap(QPixmap.fromImage(qt_image))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PlateApp()
    window.show()
    sys.exit(app.exec_())
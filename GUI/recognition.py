import tkinter as tk
from tkinter import filedialog, messagebox
import cv2
from PIL import Image, ImageTk
from core.pipeline import process_frame
import threading
import time


class RecognitionFrame:
    def __init__(self, parent):
        self.frame = tk.Frame(parent)
        self.video_thread = None
        self.video_running = False
        self.cap = None
        
        # Кнопки
        button_frame = tk.Frame(self.frame)
        button_frame.pack(pady=10)
        
        tk.Button(button_frame, text="Загрузить изображение", command=self.select_image).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Загрузить видео", command=self.select_video).pack(side=tk.LEFT, padx=5)
        #tk.Button(button_frame, text="Остановить видео", command=self.stop_video).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Открыть шлагбаум", command=self.open_barrier).pack(side=tk.LEFT, padx=5)
        
        # Изображение и информация
        self.image_label = tk.Label(self.frame)
        self.image_label.pack(pady=10)
        
        # Найденный номер
        self.plate_label = tk.Label(self.frame, text="", font=("Arial", 14, "bold"), fg="blue")
        self.plate_label.pack(pady=5)
        
        self.result_label = tk.Label(self.frame, text="", font=("Arial", 10))
        self.result_label.pack(pady=5)

    def select_image(self):
        """Загрузка и обработка изображения."""
        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.jpeg *.png")])
        if not file_path:
            return

        try:
            image = cv2.imread(file_path)
            result_frame, detected_plate = process_frame(image, camera_name="тест", direction="въезд")

            result_rgb = cv2.cvtColor(result_frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(result_rgb)
            img.thumbnail((600, 400))
            imgtk = ImageTk.PhotoImage(image=img)
            self.image_label.config(image=imgtk)
            self.image_label.image = imgtk

            # Показываем найденный номер
            if detected_plate:
                self.plate_label.config(text=f"Найден номер: {detected_plate}", fg="green")
            else:
                self.plate_label.config(text="Номер не найден", fg="red")
            
            #self.result_label.config(text="Обработка завершена")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обработать изображение: {e}")

    def select_video(self):
        """Загрузка и обработка видео."""
        file_path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv")])
        if not file_path:
            return

        if self.video_running:
            self.stop_video()

        self.cap = cv2.VideoCapture(file_path)
        if not self.cap.isOpened():
            messagebox.showerror("Ошибка", "Не удалось открыть видео файл")
            return

        self.video_running = True
        self.video_thread = threading.Thread(target=self.process_video)
        self.video_thread.daemon = True
        self.video_thread.start()
        
        self.result_label.config(text="Обработка видео запущена...")

    def process_video(self):
        """Обработка видео в отдельном потоке."""
        try:
            while self.video_running and self.cap.isOpened():
                ret, frame = self.cap.read()
                if not ret:
                    break

                # Обрабатываем кадр
                result_frame, detected_plate = process_frame(frame, camera_name="тест", direction="въезд")

                # Обновляем найденный номер
                if detected_plate:
                    self.plate_label.config(text=f"Найден номер: {detected_plate}", fg="green")
                else:
                    self.plate_label.config(text="Номер не найден", fg="red")

                # Показываем обработанный кадр
                result_rgb = cv2.cvtColor(result_frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(result_rgb)
                img.thumbnail((600, 400))
                imgtk = ImageTk.PhotoImage(image=img)
                
                # Обновляем изображение в GUI (в главном потоке)
                self.frame.after(0, lambda: self.update_image(imgtk))

                # Небольшая задержка для плавного воспроизведения
                time.sleep(0.1)

            self.cap.release()
            self.frame.after(0, lambda: self.result_label.config(text="Обработка видео завершена"))
            
        except Exception as e:
            self.frame.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка обработки видео: {e}"))
        finally:
            self.video_running = False

    def update_image(self, imgtk):
        """Обновление изображения в GUI."""
        self.image_label.config(image=imgtk)
        self.image_label.image = imgtk

    def stop_video(self):
        """Остановка обработки видео."""
        self.video_running = False
        if self.cap:
            self.cap.release()
        self.result_label.config(text="Обработка видео остановлена")

    def open_barrier(self):
        """Открывает шлагбаум"""
        messagebox.showinfo("Шлагбаум", "Сигнал открытия отправлен")

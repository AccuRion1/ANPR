import tkinter as tk
from tkinter import filedialog, messagebox
import cv2
from PIL import Image, ImageTk
from core.pipeline import process_frame


class RecognitionFrame:
    def __init__(self, parent):
        self.frame = tk.Frame(parent)
        
        tk.Button(self.frame, text="Выбрать изображение", command=self.select_image).pack(pady=10)
        
        self.result_label = tk.Label(self.frame, text="")
        self.result_label.pack(pady=10)
        
        self.image_label = tk.Label(self.frame)
        self.image_label.pack()

    def select_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.jpeg *.png")])
        if not file_path:
            return

        try:
            image = cv2.imread(file_path)
            result_frame = process_frame(image, camera_name="GUI", direction="въезд")

            result_rgb = cv2.cvtColor(result_frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(result_rgb)
            img.thumbnail((600, 400))
            imgtk = ImageTk.PhotoImage(image=img)
            self.image_label.config(image=imgtk)
            self.image_label.image = imgtk

            self.result_label.config(text="Обработка завершена")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обработать изображение: {e}")

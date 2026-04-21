import tkinter as tk
from tkinter import messagebox
from auth.auth_service import get_current_user, session_manager
from GUI.recognition import RecognitionFrame
from GUI.events_log import EventsLogFrame
from GUI.plates_table import PlatesTableFrame


class MainWindow:
    def __init__(self, root, session_id):
        self.root = root
        self.session_id = session_id
        self.root.title("Система контроля доступа")
        self.root.geometry("900x700")

        user = get_current_user(session_id)
        if not user:
            messagebox.showerror("Ошибка", "Сессия истекла")
            root.destroy()
            return

        self.role = user['role']
        self.current_frame = None

        # Верхняя панель с информацией и меню
        top_frame = tk.Frame(root, bg="#f0f0f0", height=60)
        top_frame.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(top_frame, text=f"Роль: {self.role}", bg="#f0f0f0", font=("Arial", 10)).pack(side=tk.LEFT, padx=10)

        # Меню кнопки
        menu_frame = tk.Frame(top_frame, bg="#f0f0f0")
        menu_frame.pack(side=tk.RIGHT, padx=10)

        tk.Button(menu_frame, text="Распознавание", command=self.show_recognition, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(menu_frame, text="Основная", command=self.show_main, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(menu_frame, text="Открыть шлагбаум", command=self.open_barrier, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(menu_frame, text="Журнал событий", command=self.show_events, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(menu_frame, text="Номера", command=self.show_plates, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(menu_frame, text="Выход", command=self.logout, width=10).pack(side=tk.LEFT, padx=5)

        # Основная область контента
        self.content_frame = tk.Frame(root)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Показываем основной экран по умолчанию
        self.show_main()

    def clear_content(self):
        """Очищает область контента."""
        if self.current_frame:
            self.current_frame.frame.pack_forget()

    def show_main(self):
        """Показывает основной экран."""
        self.clear_content()
        main_frame = tk.Frame(self.content_frame)
        main_frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(main_frame, text="Добро пожаловать в систему контроля доступа", font=("Arial", 16)).pack(pady=50)
        self.current_frame = type('obj', (object,), {'frame': main_frame})()

    def show_recognition(self):
        """Показывает модуль распознавания."""
        self.clear_content()
        self.current_frame = RecognitionFrame(self.content_frame)
        self.current_frame.frame.pack(fill=tk.BOTH, expand=True)

    def show_events(self):
        """Показывает журнал событий."""
        self.clear_content()
        self.current_frame = EventsLogFrame(self.content_frame)
        self.current_frame.frame.pack(fill=tk.BOTH, expand=True)

    def show_plates(self):
        """Показывает таблицу номеров."""
        self.clear_content()
        self.current_frame = PlatesTableFrame(self.content_frame)
        self.current_frame.frame.pack(fill=tk.BOTH, expand=True)

    def open_barrier(self):
        """Открывает шлагбаум (заглушка)."""
        messagebox.showinfo("Шлагбаум", "🚪 Сигнал открытия отправлен")

    def logout(self):
        """Выход из системы."""
        session_manager.destroy_session(self.session_id)
        self.root.destroy()
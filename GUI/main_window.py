import tkinter as tk
from tkinter import messagebox

from auth.auth_service import get_current_user, session_manager
from GUI.events_log import EventsLogFrame
from GUI.plates_table import PlatesTableFrame
from GUI.recognition import LoadFrame, RecognitionFrame


class MainWindow:
    def __init__(self, root, session_id):
        self.root = root
        self.session_id = session_id
        self.root.title("NikolaAutoNPR")
        self.root.geometry("1280x820")

        user = get_current_user(session_id)
        if not user:
            messagebox.showerror("Ошибка", "Сессия истекла")
            root.destroy()
            return

        self.username = user["username"]
        self.role = user["role"]
        self.current_frame = None

        top_frame = tk.Frame(root, bg="#f0f0f0", height=60)
        top_frame.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(top_frame, text="", font=("Arial", 20), bg="#f0f0f0").pack(side=tk.LEFT, padx=10)

        menu_frame = tk.Frame(top_frame, bg="#f0f0f0")
        menu_frame.pack(side=tk.LEFT, padx=10, expand=True)

        tk.Button(menu_frame, text="Наблюдение", command=self.show_recognition, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(menu_frame, text="Загрузить", command=self.show_load, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(menu_frame, text="Журнал событий", command=self.show_events, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(menu_frame, text="Номера", command=self.show_plates, width=15).pack(side=tk.LEFT, padx=5)

        user_frame = tk.Frame(top_frame, bg="#f0f0f0")
        user_frame.pack(side=tk.RIGHT, padx=10)

        tk.Button(
            user_frame,
            text=f"{self.username}\n{self.role}",
            command=self.show_user_menu,
            width=15,
            relief=tk.FLAT,
            bg="#e0e0e0",
        ).pack(side=tk.RIGHT, padx=5)

        self.content_frame = tk.Frame(root)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.show_recognition()

    def show_user_menu(self):
        popup = tk.Toplevel(self.root)
        popup.wm_overrideredirect(True)

        x = self.root.winfo_x() + self.root.winfo_width() - 200
        y = self.root.winfo_y() + 60
        popup.geometry(f"150x60+{x}+{y}")

        frame = tk.Frame(popup, bg="white", relief=tk.RAISED, borderwidth=1)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Button(
            frame,
            text="Сменить пользователя",
            command=lambda: [popup.destroy(), self.logout()],
            width=20,
            relief=tk.FLAT,
        ).pack(pady=5)

        def close_popup(_event=None):
            try:
                popup.destroy()
            except tk.TclError:
                pass

        popup.bind("<FocusOut>", close_popup)
        popup.focus()

    def clear_content(self):
        if not self.current_frame:
            return

        if hasattr(self.current_frame, "stop"):
            self.current_frame.stop()

        if hasattr(self.current_frame, "frame") and self.current_frame.frame.winfo_exists():
            self.current_frame.frame.destroy()

        self.current_frame = None

    def show_recognition(self):
        self.clear_content()
        self.current_frame = RecognitionFrame(self.content_frame)
        self.current_frame.frame.pack(fill=tk.BOTH, expand=True)

    def show_load(self):
        self.clear_content()
        self.current_frame = LoadFrame(self.content_frame)
        self.current_frame.frame.pack(fill=tk.BOTH, expand=True)

    def show_events(self):
        self.clear_content()
        self.current_frame = EventsLogFrame(self.content_frame)
        self.current_frame.frame.pack(fill=tk.BOTH, expand=True)

    def show_plates(self):
        self.clear_content()
        self.current_frame = PlatesTableFrame(self.content_frame)
        self.current_frame.frame.pack(fill=tk.BOTH, expand=True)

    def logout(self):
        session_manager.destroy_session(self.session_id)
        self.root.destroy()

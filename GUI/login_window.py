import tkinter as tk
from tkinter import messagebox
from auth.auth_service import authenticate_user
from GUI.main_window import MainWindow

class LoginWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Вход в систему")
        self.root.geometry("300x200")

        tk.Label(root, text="Логин:").pack(pady=5)
        self.login_entry = tk.Entry(root)
        self.login_entry.pack(pady=5)

        tk.Label(root, text="Пароль:").pack(pady=5)
        self.password_entry = tk.Entry(root, show="*")
        self.password_entry.pack(pady=5)

        tk.Button(root, text="Войти", command=self.login).pack(pady=20)

    def login(self):
        login = self.login_entry.get()
        password = self.password_entry.get()

        session_id = authenticate_user(login, password)
        if session_id:
            self.root.destroy()
            main_root = tk.Tk()
            MainWindow(main_root, session_id)
            main_root.mainloop()
        else:
            messagebox.showerror("Ошибка", "Неверный логин или пароль")
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from core.database import get_all_plates_with_owners, add_plate


class PlatesTableFrame:
    def __init__(self, parent):
        self.frame = tk.Frame(parent)
        
        button_frame = tk.Frame(self.frame)
        button_frame.pack(pady=10)
        
        tk.Button(button_frame, text="Добавить номер", command=self.add_plate_dialog).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Обновить", command=self.refresh_plates).pack(side=tk.LEFT, padx=5)
        
        # Таблица с скроллбаром
        self.tree_frame = tk.Frame(self.frame)
        self.tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.tree = ttk.Treeview(
            self.tree_frame,
            columns=("Номер", "Статус", "Тип доступа", "Владелец"),
            height=20
        )
        
        self.tree.heading("#0", text="ID")
        self.tree.heading("Номер", text="Номер автомобиля")
        self.tree.heading("Статус", text="Статус")
        self.tree.heading("Тип доступа", text="Тип доступа")
        self.tree.heading("Владелец", text="Владелец")
        
        self.tree.column("#0", width=30)
        self.tree.column("Номер", width=150)
        self.tree.column("Статус", width=100)
        self.tree.column("Тип доступа", width=100)
        self.tree.column("Владелец", width=150)
        
        scrollbar = ttk.Scrollbar(self.tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.refresh_plates()

    def refresh_plates(self):
        """Обновляет список номеров."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        plates = get_all_plates_with_owners()
        for idx, plate in enumerate(plates):
            self.tree.insert("", "end", text=str(idx+1), values=plate)

    def add_plate_dialog(self):
        """Открывает диалог для добавления номера."""
        window = tk.Toplevel(self.frame)
        window.title("Добавить номер")
        window.geometry("400x300")
        
        tk.Label(window, text="Номер автомобиля:").pack(pady=5)
        plate_entry = tk.Entry(window)
        plate_entry.pack(pady=5)
        
        tk.Label(window, text="ID владельца (или оставить пусто):").pack(pady=5)
        owner_entry = tk.Entry(window)
        owner_entry.pack(pady=5)
        
        tk.Label(window, text="Статус:").pack(pady=5)
        status_var = tk.StringVar(value="активный")
        status_combo = ttk.Combobox(window, textvariable=status_var, values=["активный", "неактивный"], state="readonly")
        status_combo.pack(pady=5)
        
        tk.Label(window, text="Тип доступа:").pack(pady=5)
        access_var = tk.StringVar(value="полный")
        access_combo = ttk.Combobox(window, textvariable=access_var, values=["полный", "ограниченный", "запрещен"], state="readonly")
        access_combo.pack(pady=5)
        
        def save():
            plate = plate_entry.get().strip()
            owner = owner_entry.get().strip()
            status = status_var.get()
            access = access_var.get()
            
            if not plate:
                messagebox.showerror("Ошибка", "Введите номер автомобиля")
                return
            
            owner_id = int(owner) if owner else None
            if add_plate(plate, owner_id, status, access):
                messagebox.showinfo("Успех", "Номер добавлен")
                window.destroy()
                self.refresh_plates()
            else:
                messagebox.showerror("Ошибка", "Не удалось добавить номер")
        
        tk.Button(window, text="Добавить", command=save).pack(pady=20)

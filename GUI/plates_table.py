import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from core.database import get_all_plates_with_owners, add_plate, update_plate, delete_plate, get_plate_by_number


class PlatesTableFrame:
    def __init__(self, parent):
        self.frame = tk.Frame(parent)
        self.selected_plate = None
        
        # Кнопки над таблицей
        button_frame = tk.Frame(self.frame)
        button_frame.pack(pady=10)
        
        tk.Button(button_frame, text="Добавить номер", command=self.add_plate_dialog).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Обновить", command=self.refresh_plates).pack(side=tk.LEFT, padx=5)
        
        # Кнопка редактирования (будет активна при выборе номера)
        self.edit_button = tk.Button(button_frame, text="Редактировать", command=self.edit_selected_plate, state=tk.DISABLED)
        self.edit_button.pack(side=tk.LEFT, padx=5)
        
        self.delete_button = tk.Button(button_frame, text="Удалить", command=self.delete_selected_plate, state=tk.DISABLED)
        self.delete_button.pack(side=tk.LEFT, padx=5)
        
        # Таблица с скроллбаром
        self.tree_frame = tk.Frame(self.frame)
        self.tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.tree = ttk.Treeview(
            self.tree_frame,
            columns=("Номер", "Статус", "Тип доступа", "Владелец"),
            height=20
        )
        
        self.tree.heading("#0", text="№")
        self.tree.heading("Номер", text="Номер автомобиля")
        self.tree.heading("Статус", text="Статус")
        self.tree.heading("Тип доступа", text="Тип доступа")
        self.tree.heading("Владелец", text="Владелец")
        
        self.tree.column("#0", width=30)
        self.tree.column("Номер", width=150)
        self.tree.column("Статус", width=100)
        self.tree.column("Тип доступа", width=100)
        self.tree.column("Владелец", width=150)
        
        # Привязываем клик на строку
        self.tree.bind("<<TreeviewSelect>>", self.on_plate_selected)
        
        scrollbar = ttk.Scrollbar(self.tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.refresh_plates()

    def on_plate_selected(self, event):
        """Обработчик выбора строки в таблице."""
        selection = self.tree.selection()
        if selection:
            item_id = selection[0]
            values = self.tree.item(item_id, 'values')
            self.selected_plate = values[0]  # Номер автомобиля (первый элемент в values)
            self.edit_button.config(state=tk.NORMAL)
            self.delete_button.config(state=tk.NORMAL)
        else:
            self.selected_plate = None
            self.edit_button.config(state=tk.DISABLED)
            self.delete_button.config(state=tk.DISABLED)

    def refresh_plates(self):
        """Обновляет список номеров."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        plates = get_all_plates_with_owners()
        for idx, plate in enumerate(plates, 1):
            self.tree.insert("", "end", text=str(idx), values=plate)

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

    def edit_selected_plate(self):
        """Редактирует выбранный номер."""
        if not self.selected_plate:
            messagebox.showerror("Ошибка", "Выберите номер для редактирования")
            return
        
        plate_data = get_plate_by_number(self.selected_plate)
        if not plate_data:
            messagebox.showerror("Ошибка", "Не удалось загрузить данные номера")
            return
        
        window = tk.Toplevel(self.frame)
        window.title("Редактировать номер")
        window.geometry("400x300")
        
        tk.Label(window, text="Номер автомобиля:").pack(pady=5)
        plate_entry = tk.Entry(window)
        plate_entry.insert(0, plate_data['plate_number'])
        plate_entry.pack(pady=5)
        
        tk.Label(window, text="ID владельца:").pack(pady=5)
        owner_entry = tk.Entry(window)
        owner_entry.insert(0, str(plate_data['owner_id']) if plate_data['owner_id'] else "")
        owner_entry.pack(pady=5)
        
        tk.Label(window, text="Статус:").pack(pady=5)
        status_var = tk.StringVar(value=plate_data['status'])
        status_combo = ttk.Combobox(window, textvariable=status_var, values=["активный", "неактивный"], state="readonly")
        status_combo.pack(pady=5)
        
        tk.Label(window, text="Тип доступа:").pack(pady=5)
        access_var = tk.StringVar(value=plate_data['access_type'])
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
            if update_plate(plate, owner_id, status, access):
                messagebox.showinfo("Успех", "Номер обновлен")
                window.destroy()
                self.refresh_plates()
            else:
                messagebox.showerror("Ошибка", "Не удалось обновить номер")
        
        tk.Button(window, text="Сохранить", command=save).pack(pady=20)

    def delete_selected_plate(self):
        """Удаляет выбранный номер."""
        if not self.selected_plate:
            messagebox.showerror("Ошибка", "Выберите номер для удаления")
            return
        
        if messagebox.askyesno("Подтверждение", f"Удалить номер {self.selected_plate}?"):
            if delete_plate(self.selected_plate):
                messagebox.showinfo("Успех", "Номер удален")
                self.refresh_plates()
            else:
                messagebox.showerror("Ошибка", "Не удалось удалить номер")

import tkinter as tk
from tkinter import ttk, messagebox

from core.database import (
    add_plate,
    delete_plate,
    get_all_plates_with_owners,
    get_plate_by_number,
    update_plate,
)


def _status_to_bool(value):
    return value == "Активен"


def _territory_to_bool(value):
    return value == "Да"


class PlatesTableFrame:
    def __init__(self, parent):
        self.frame = tk.Frame(parent)
        self.selected_plate = None

        controls = tk.Frame(self.frame)
        controls.pack(fill="x", padx=10, pady=(10, 5))

        tk.Button(controls, text="Добавить номер", command=self.add_plate_dialog).pack(side=tk.LEFT, padx=5)
        tk.Button(controls, text="Обновить", command=self.refresh_plates).pack(side=tk.LEFT, padx=5)

        self.edit_button = tk.Button(controls, text="Редактировать", command=self.edit_selected_plate, state=tk.DISABLED)
        self.edit_button.pack(side=tk.LEFT, padx=5)

        self.delete_button = tk.Button(controls, text="Удалить", command=self.delete_selected_plate, state=tk.DISABLED)
        self.delete_button.pack(side=tk.LEFT, padx=5)

        search_frame = tk.Frame(self.frame)
        search_frame.pack(fill="x", padx=10, pady=(0, 10))

        tk.Label(search_frame, text="Поиск:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_plates())
        tk.Entry(search_frame, textvariable=self.search_var).pack(side=tk.LEFT, fill="x", expand=True, padx=(8, 8))
        tk.Button(search_frame, text="Очистить", command=lambda: self.search_var.set("")).pack(side=tk.LEFT)

        tree_frame = tk.Frame(self.frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("plate", "owner", "status", "access", "territory"),
            show="headings",
            height=20,
        )

        self.tree.heading("plate", text="Номер ТС")
        self.tree.heading("owner", text="Владелец")
        self.tree.heading("status", text="Статус")
        self.tree.heading("access", text="Уровень доступа")
        self.tree.heading("territory", text="На территории")

        self.tree.column("plate", width=120, anchor="center")
        self.tree.column("owner", width=220, anchor="w")
        self.tree.column("status", width=120, anchor="center")
        self.tree.column("access", width=150, anchor="center")
        self.tree.column("territory", width=120, anchor="center")

        self.tree.bind("<<TreeviewSelect>>", self.on_plate_selected)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.refresh_plates()

    def on_plate_selected(self, _event):
        selection = self.tree.selection()
        if not selection:
            self.selected_plate = None
            self.edit_button.config(state=tk.DISABLED)
            self.delete_button.config(state=tk.DISABLED)
            return

        values = self.tree.item(selection[0], "values")
        self.selected_plate = values[0]
        self.edit_button.config(state=tk.NORMAL)
        self.delete_button.config(state=tk.NORMAL)

    def refresh_plates(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        search_value = self.search_var.get().strip()
        for plate in get_all_plates_with_owners(search=search_value):
            self.tree.insert("", "end", values=plate)

    def _open_plate_dialog(self, title, initial_data=None):
        is_edit = initial_data is not None

        window = tk.Toplevel(self.frame)
        window.title(title)
        window.geometry("420x360")
        window.resizable(False, False)

        tk.Label(window, text="Номер ТС:").pack(pady=(12, 4))
        plate_entry = tk.Entry(window)
        plate_entry.pack(pady=4, fill="x", padx=20)

        tk.Label(window, text="Владелец (ID сотрудника):").pack(pady=(8, 4))
        owner_entry = tk.Entry(window)
        owner_entry.pack(pady=4, fill="x", padx=20)

        tk.Label(window, text="Статус:").pack(pady=(8, 4))
        status_var = tk.StringVar(value="Активен")
        ttk.Combobox(
            window,
            textvariable=status_var,
            values=["Активен", "Неактивен"],
            state="readonly",
        ).pack(pady=4, fill="x", padx=20)

        tk.Label(window, text="Уровень доступа:").pack(pady=(8, 4))
        access_var = tk.StringVar(value="Сотрудник")
        ttk.Combobox(
            window,
            textvariable=access_var,
            values=["Сотрудник", "Гость"],
            state="normal",
        ).pack(pady=4, fill="x", padx=20)

        tk.Label(window, text="На территории:").pack(pady=(8, 4))
        territory_var = tk.StringVar(value="Нет")
        ttk.Combobox(
            window,
            textvariable=territory_var,
            values=["Да", "Нет"],
            state="readonly",
        ).pack(pady=4, fill="x", padx=20)

        if initial_data:
            plate_entry.insert(0, initial_data["plate_number"])
            owner_entry.insert(0, str(initial_data["owner_id"]) if initial_data["owner_id"] else "")
            status_var.set("Активен" if initial_data["status"] else "Неактивен")
            access_var.set(initial_data["access_level"] or "Сотрудник")
            territory_var.set("Да" if initial_data["on_territory"] else "Нет")

        def save():
            plate_number = plate_entry.get().strip().upper()
            owner_raw = owner_entry.get().strip()
            access_level = access_var.get().strip()

            if not plate_number:
                messagebox.showerror("Ошибка", "Введите номер ТС.")
                return

            if not access_level:
                messagebox.showerror("Ошибка", "Введите уровень доступа.")
                return

            try:
                owner_id = int(owner_raw) if owner_raw else None
            except ValueError:
                messagebox.showerror("Ошибка", "ID владельца должен быть числом.")
                return

            status = _status_to_bool(status_var.get())
            on_territory = _territory_to_bool(territory_var.get())

            if is_edit:
                ok = update_plate(
                    initial_data["plate_number"],
                    plate_number,
                    owner_id,
                    status,
                    access_level,
                    on_territory,
                )
            else:
                ok = add_plate(
                    plate_number,
                    owner_id,
                    status,
                    access_level,
                    on_territory,
                )

            if not ok:
                messagebox.showerror("Ошибка", "Не удалось сохранить запись. Проверьте номер и владельца.")
                return

            window.destroy()
            self.refresh_plates()

        tk.Button(window, text="Сохранить", command=save).pack(pady=20)

    def add_plate_dialog(self):
        self._open_plate_dialog("Добавить номер")

    def edit_selected_plate(self):
        if not self.selected_plate:
            messagebox.showerror("Ошибка", "Сначала выберите номер.")
            return

        plate_data = get_plate_by_number(self.selected_plate)
        if not plate_data:
            messagebox.showerror("Ошибка", "Не удалось загрузить выбранную запись.")
            return

        self._open_plate_dialog("Редактировать номер", initial_data=plate_data)

    def delete_selected_plate(self):
        if not self.selected_plate:
            messagebox.showerror("Ошибка", "Сначала выберите номер.")
            return

        if not messagebox.askyesno("Подтверждение", f"Удалить номер {self.selected_plate}?"):
            return

        if delete_plate(self.selected_plate):
            self.selected_plate = None
            self.refresh_plates()
            self.edit_button.config(state=tk.DISABLED)
            self.delete_button.config(state=tk.DISABLED)
        else:
            messagebox.showerror("Ошибка", "Не удалось удалить номер.")

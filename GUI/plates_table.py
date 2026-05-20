from datetime import datetime
import tkinter as tk
from tkinter import messagebox, ttk

from core.database import (
    DATETIME_DISPLAY_FORMAT,
    add_guest_plate,
    add_registered_plate,
    delete_guest_plate,
    delete_registered_plate,
    get_all_guest_plates,
    get_all_registered_plates_with_owners,
    get_employees_for_select,
    get_guest_plate_by_number,
    get_registered_plate_by_number,
    update_guest_plate,
    update_registered_plate,
)


def _status_to_bool(value):
    return value == "Активен"


def _territory_to_bool(value):
    return value == "Да"


class _BasePanel:
    def __init__(self, parent, title):
        self.frame = tk.Frame(parent)
        self.title = title
        self.selected_plate = None

        controls = tk.Frame(self.frame)
        controls.pack(fill="x", padx=10, pady=(10, 5))

        tk.Button(controls, text="Добавить номер", command=self.add_dialog).pack(side=tk.LEFT, padx=5)
        tk.Button(controls, text="Обновить", command=self.refresh_rows).pack(side=tk.LEFT, padx=5)

        self.edit_button = tk.Button(controls, text="Редактировать", command=self.edit_selected, state=tk.DISABLED)
        self.edit_button.pack(side=tk.LEFT, padx=5)

        self.delete_button = tk.Button(controls, text="Удалить", command=self.delete_selected, state=tk.DISABLED)
        self.delete_button.pack(side=tk.LEFT, padx=5)

        search_frame = tk.Frame(self.frame)
        search_frame.pack(fill="x", padx=10, pady=(0, 10))

        tk.Label(search_frame, text="Поиск:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_rows())
        tk.Entry(search_frame, textvariable=self.search_var).pack(side=tk.LEFT, fill="x", expand=True, padx=(8, 8))
        tk.Button(search_frame, text="Очистить", command=lambda: self.search_var.set("")).pack(side=tk.LEFT)

        tree_frame = tk.Frame(self.frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tree = ttk.Treeview(tree_frame, show="headings", height=20)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def on_select(self, _event):
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

    def refresh_rows(self):
        raise NotImplementedError

    def add_dialog(self):
        raise NotImplementedError

    def edit_selected(self):
        raise NotImplementedError

    def delete_selected(self):
        raise NotImplementedError


class RegisteredPlatesPanel(_BasePanel):
    def __init__(self, parent):
        super().__init__(parent, "Зарегистрированные номера")
        self.tree.configure(columns=("plate", "owner", "status", "territory"))
        self.tree.heading("plate", text="Номер ТС")
        self.tree.heading("owner", text="Владелец")
        self.tree.heading("status", text="Статус")
        self.tree.heading("territory", text="На территории")
        self.tree.column("plate", width=140, anchor="center")
        self.tree.column("owner", width=260, anchor="w")
        self.tree.column("status", width=120, anchor="center")
        self.tree.column("territory", width=120, anchor="center")
        self.refresh_rows()

    def refresh_rows(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for row in get_all_registered_plates_with_owners(search=self.search_var.get().strip()):
            self.tree.insert("", "end", values=row)

    def _open_dialog(self, title, initial_data=None):
        is_edit = initial_data is not None
        employees = get_employees_for_select()
        employee_names = ["Не выбран"] + [employee["full_name"] for employee in employees]
        employee_name_to_id = {employee["full_name"]: employee["id"] for employee in employees}
        employee_id_to_name = {employee["id"]: employee["full_name"] for employee in employees}

        window = tk.Toplevel(self.frame)
        window.title(title)
        window.geometry("460x320")
        window.resizable(False, False)

        tk.Label(window, text="Номер ТС:").pack(pady=(12, 4))
        plate_entry = tk.Entry(window)
        plate_entry.pack(pady=4, fill="x", padx=20)

        tk.Label(window, text="Сотрудник:").pack(pady=(8, 4))
        owner_var = tk.StringVar(value="Не выбран")
        ttk.Combobox(window, textvariable=owner_var, values=employee_names, state="readonly").pack(
            pady=4, fill="x", padx=20
        )

        tk.Label(window, text="Статус:").pack(pady=(8, 4))
        status_var = tk.StringVar(value="Активен")
        ttk.Combobox(window, textvariable=status_var, values=["Активен", "Неактивен"], state="readonly").pack(
            pady=4, fill="x", padx=20
        )

        tk.Label(window, text="На территории:").pack(pady=(8, 4))
        territory_var = tk.StringVar(value="Нет")
        ttk.Combobox(window, textvariable=territory_var, values=["Да", "Нет"], state="readonly").pack(
            pady=4, fill="x", padx=20
        )

        if initial_data:
            plate_entry.insert(0, initial_data["plate_number"])
            owner_var.set(employee_id_to_name.get(initial_data["owner_id"], "Не выбран"))
            status_var.set("Активен" if initial_data["status"] else "Неактивен")
            territory_var.set("Да" if initial_data["on_territory"] else "Нет")

        def save():
            plate_number = plate_entry.get().strip().upper()
            if not plate_number:
                messagebox.showerror("Ошибка", "Введите номер ТС.")
                return

            owner_name = owner_var.get().strip()
            owner_id = employee_name_to_id.get(owner_name) if owner_name != "Не выбран" else None
            status = _status_to_bool(status_var.get())
            on_territory = _territory_to_bool(territory_var.get())

            if is_edit:
                ok = update_registered_plate(initial_data["plate_number"], plate_number, owner_id, status, on_territory)
            else:
                ok = add_registered_plate(plate_number, owner_id, status, on_territory)

            if not ok:
                messagebox.showerror("Ошибка", "Не удалось сохранить зарегистрированный номер.")
                return

            window.destroy()
            self.refresh_rows()

        tk.Button(window, text="Сохранить", command=save).pack(pady=20)

    def add_dialog(self):
        self._open_dialog("Добавить зарегистрированный номер")

    def edit_selected(self):
        if not self.selected_plate:
            messagebox.showerror("Ошибка", "Сначала выберите номер.")
            return
        data = get_registered_plate_by_number(self.selected_plate)
        if not data:
            messagebox.showerror("Ошибка", "Не удалось загрузить запись.")
            return
        self._open_dialog("Редактировать зарегистрированный номер", initial_data=data)

    def delete_selected(self):
        if not self.selected_plate:
            messagebox.showerror("Ошибка", "Сначала выберите номер.")
            return
        if not messagebox.askyesno("Подтверждение", f"Удалить зарегистрированный номер {self.selected_plate}?"):
            return
        if delete_registered_plate(self.selected_plate):
            self.selected_plate = None
            self.refresh_rows()
            self.edit_button.config(state=tk.DISABLED)
            self.delete_button.config(state=tk.DISABLED)
        else:
            messagebox.showerror("Ошибка", "Не удалось удалить номер.")


class GuestPlatesPanel(_BasePanel):
    def __init__(self, parent):
        super().__init__(parent, "Гостевые номера")
        self.tree.configure(columns=("plate", "start", "end", "status", "territory"))
        self.tree.heading("plate", text="Номер ТС")
        self.tree.heading("start", text="Время начала")
        self.tree.heading("end", text="Время окончания")
        self.tree.heading("status", text="Статус")
        self.tree.heading("territory", text="На территории")
        self.tree.column("plate", width=140, anchor="center")
        self.tree.column("start", width=170, anchor="center")
        self.tree.column("end", width=170, anchor="center")
        self.tree.column("status", width=120, anchor="center")
        self.tree.column("territory", width=120, anchor="center")
        self.refresh_rows()

    def refresh_rows(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for row in get_all_guest_plates(search=self.search_var.get().strip()):
            self.tree.insert("", "end", values=row)

    def _open_dialog(self, title, initial_data=None):
        is_edit = initial_data is not None

        window = tk.Toplevel(self.frame)
        window.title(title)
        window.geometry("460x380")
        window.resizable(False, False)

        tk.Label(window, text="Номер ТС:").pack(pady=(12, 4))
        plate_entry = tk.Entry(window)
        plate_entry.pack(pady=4, fill="x", padx=20)

        tk.Label(window, text=f"Время начала (2026-01-01 00:00:00):").pack(pady=(8, 4))
        start_entry = tk.Entry(window)
        start_entry.pack(pady=4, fill="x", padx=20)

        tk.Label(window, text=f"Время окончания (2026-01-01 00:00:00):").pack(pady=(8, 4))
        end_entry = tk.Entry(window)
        end_entry.pack(pady=4, fill="x", padx=20)

        tk.Label(window, text="Статус:").pack(pady=(8, 4))
        status_var = tk.StringVar(value="Активен")
        ttk.Combobox(window, textvariable=status_var, values=["Активен", "Неактивен"], state="readonly").pack(
            pady=4, fill="x", padx=20
        )

        tk.Label(window, text="На территории:").pack(pady=(8, 4))
        territory_var = tk.StringVar(value="Нет")
        ttk.Combobox(window, textvariable=territory_var, values=["Да", "Нет"], state="readonly").pack(
            pady=4, fill="x", padx=20
        )

        if initial_data:
            plate_entry.insert(0, initial_data["plate_number"])
            start_entry.insert(0, initial_data["start_time"])
            end_entry.insert(0, initial_data["end_time"])
            status_var.set("Активен" if initial_data["status"] else "Неактивен")
            territory_var.set("Да" if initial_data["on_territory"] else "Нет")

        def save():
            plate_number = plate_entry.get().strip().upper()
            start_time = start_entry.get().strip()
            end_time = end_entry.get().strip()
            if not plate_number or not start_time or not end_time:
                messagebox.showerror("Ошибка", "Заполните номер и временной интервал.")
                return

            try:
                datetime.strptime(start_time, DATETIME_DISPLAY_FORMAT)
                datetime.strptime(end_time, DATETIME_DISPLAY_FORMAT)
            except ValueError:
                messagebox.showerror("Ошибка", f"Время нужно вводить в формате {DATETIME_DISPLAY_FORMAT}.")
                return

            status = _status_to_bool(status_var.get())
            on_territory = _territory_to_bool(territory_var.get())

            if is_edit:
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
                messagebox.showerror("Ошибка", "Не удалось сохранить гостевой номер.")
                return

            window.destroy()
            self.refresh_rows()

        tk.Button(window, text="Сохранить", command=save).pack(pady=20)

    def add_dialog(self):
        self._open_dialog("Добавить гостевой номер")

    def edit_selected(self):
        if not self.selected_plate:
            messagebox.showerror("Ошибка", "Сначала выберите номер.")
            return
        data = get_guest_plate_by_number(self.selected_plate)
        if not data:
            messagebox.showerror("Ошибка", "Не удалось загрузить запись.")
            return
        self._open_dialog("Редактировать гостевой номер", initial_data=data)

    def delete_selected(self):
        if not self.selected_plate:
            messagebox.showerror("Ошибка", "Сначала выберите номер.")
            return
        if not messagebox.askyesno("Подтверждение", f"Удалить гостевой номер {self.selected_plate}?"):
            return
        if delete_guest_plate(self.selected_plate):
            self.selected_plate = None
            self.refresh_rows()
            self.edit_button.config(state=tk.DISABLED)
            self.delete_button.config(state=tk.DISABLED)
        else:
            messagebox.showerror("Ошибка", "Не удалось удалить номер.")


class PlatesTableFrame:
    def __init__(self, parent):
        self.frame = tk.Frame(parent)

        notebook = ttk.Notebook(self.frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.registered_panel = RegisteredPlatesPanel(notebook)
        self.guest_panel = GuestPlatesPanel(notebook)

        notebook.add(self.registered_panel.frame, text="Зарегистрированные номера")
        notebook.add(self.guest_panel.frame, text="Гостевые номера")

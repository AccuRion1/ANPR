import tkinter as tk
from tkinter import ttk

from core.database import get_access_events, get_incidents


class EventsLogFrame:
    def __init__(self, parent):
        self.frame = tk.Frame(parent)
        self.mode = "events"

        header = tk.Frame(self.frame)
        header.pack(fill="x", padx=10, pady=(10, 5))

        self.title_label = tk.Label(header, text="Журнал событий", font=("Arial", 14, "bold"))
        self.title_label.pack(side=tk.LEFT)

        tk.Button(header, text="События", command=lambda: self.set_mode("events")).pack(side=tk.RIGHT, padx=5)
        tk.Button(header, text="Инциденты", command=lambda: self.set_mode("incidents")).pack(side=tk.RIGHT, padx=5)

        search_frame = tk.Frame(self.frame)
        search_frame.pack(fill="x", padx=10, pady=(0, 10))

        tk.Label(search_frame, text="Поиск:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_rows())
        self.search_entry = tk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill="x", expand=True, padx=(8, 8))
        tk.Button(search_frame, text="Очистить", command=self.clear_search).pack(side=tk.LEFT)

        tree_frame = tk.Frame(self.frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tree = ttk.Treeview(tree_frame, show="headings", height=20)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.set_mode("events")

    def clear_search(self):
        self.search_var.set("")

    def set_mode(self, mode):
        self.mode = mode
        self._configure_columns()
        self.refresh_rows()

    def _configure_columns(self):
        for column in self.tree["columns"]:
            self.tree.heading(column, text="")

        if self.mode == "events":
            self.title_label.config(text="Журнал событий")
            columns = ("plate", "time", "camera", "direction", "access_level", "access")
            self.tree.configure(columns=columns)
            self.tree.heading("plate", text="Номер ТС")
            self.tree.heading("time", text="Время события")
            self.tree.heading("camera", text="Видеокамера")
            self.tree.heading("direction", text="Направление")
            self.tree.heading("access_level", text="Уровень доступа")
            self.tree.heading("access", text="Доступ")
            self.tree.column("plate", width=120, anchor="center")
            self.tree.column("time", width=160, anchor="center")
            self.tree.column("camera", width=170, anchor="w")
            self.tree.column("direction", width=100, anchor="center")
            self.tree.column("access_level", width=140, anchor="center")
            self.tree.column("access", width=100, anchor="center")
        else:
            self.title_label.config(text="Журнал инцидентов")
            columns = ("plate", "time", "camera", "description")
            self.tree.configure(columns=columns)
            self.tree.heading("plate", text="Номер ТС")
            self.tree.heading("time", text="Время инцидента")
            self.tree.heading("camera", text="Видеокамера")
            self.tree.heading("description", text="Описание")
            self.tree.column("plate", width=120, anchor="center")
            self.tree.column("time", width=170, anchor="center")
            self.tree.column("camera", width=170, anchor="w")
            self.tree.column("description", width=420, anchor="w")

    def refresh_rows(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        search_value = self.search_var.get().strip()
        rows = (
            get_access_events(limit=200, search=search_value)
            if self.mode == "events"
            else get_incidents(limit=200, search=search_value)
        )

        for row in rows:
            self.tree.insert("", "end", values=row)

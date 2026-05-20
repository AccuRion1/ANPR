import tkinter as tk
from tkinter import ttk

from core.database import get_access_events, get_incidents


class _BaseLogPanel:
    def __init__(self, parent):
        self.frame = tk.Frame(parent)

        search_frame = tk.Frame(self.frame)
        search_frame.pack(fill="x", padx=10, pady=(10, 10))

        tk.Label(search_frame, text="Поиск:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_rows())
        tk.Entry(search_frame, textvariable=self.search_var).pack(side=tk.LEFT, fill="x", expand=True, padx=(8, 8))
        tk.Button(search_frame, text="Очистить", command=lambda: self.search_var.set("")).pack(side=tk.LEFT)

        tree_frame = tk.Frame(self.frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tree = ttk.Treeview(tree_frame, show="headings", height=20)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def refresh_rows(self):
        raise NotImplementedError


class EventsPanel(_BaseLogPanel):
    def __init__(self, parent):
        super().__init__(parent)
        self.tree.configure(columns=("plate", "time", "camera", "direction", "access_level", "access"))
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
        self.refresh_rows()

    def refresh_rows(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        search_value = self.search_var.get().strip()
        rows = get_access_events(limit=200, search=search_value)

        for row in rows:
            self.tree.insert("", "end", values=row)


class IncidentsPanel(_BaseLogPanel):
    def __init__(self, parent):
        super().__init__(parent)
        self.tree.configure(columns=("plate", "time", "camera", "description"))
        self.tree.heading("plate", text="Номер ТС")
        self.tree.heading("time", text="Время инцидента")
        self.tree.heading("camera", text="Видеокамера")
        self.tree.heading("description", text="Описание")
        self.tree.column("plate", width=120, anchor="center")
        self.tree.column("time", width=170, anchor="center")
        self.tree.column("camera", width=170, anchor="w")
        self.tree.column("description", width=420, anchor="w")
        self.refresh_rows()

    def refresh_rows(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        search_value = self.search_var.get().strip()
        rows = get_incidents(limit=200, search=search_value)

        for row in rows:
            self.tree.insert("", "end", values=row)


class EventsLogFrame:
    def __init__(self, parent):
        self.frame = tk.Frame(parent)

        notebook = ttk.Notebook(self.frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.events_panel = EventsPanel(notebook)
        self.incidents_panel = IncidentsPanel(notebook)

        notebook.add(self.events_panel.frame, text="Журнал событий")
        notebook.add(self.incidents_panel.frame, text="Журнал инцидентов")

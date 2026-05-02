import tkinter as tk
from tkinter import ttk

from core.database import get_access_events


class EventsLogFrame:
    def __init__(self, parent):
        self.frame = tk.Frame(parent)

        header = tk.Frame(self.frame)
        header.pack(fill="x", padx=10, pady=(10, 5))

        tk.Label(header, text="Журнал событий", font=("Arial", 14, "bold")).pack(side=tk.LEFT)

        search_frame = tk.Frame(self.frame)
        search_frame.pack(fill="x", padx=10, pady=(0, 10))

        tk.Label(search_frame, text="Поиск:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_events())
        self.search_entry = tk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill="x", expand=True, padx=(8, 8))
        tk.Button(search_frame, text="Очистить", command=self.clear_search).pack(side=tk.LEFT)

        tree_frame = tk.Frame(self.frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("plate", "time", "camera", "direction", "access_level", "access"),
            show="headings",
            height=20,
        )

        self.tree.heading("plate", text="Номер ТС")
        self.tree.heading("time", text="Время события")
        self.tree.heading("camera", text="Видеокамера")
        self.tree.heading("direction", text="Направление")
        self.tree.heading("access_level", text="Уровень доступа")
        self.tree.heading("access", text="Доступ")

        self.tree.column("plate", width=120, anchor="center")
        self.tree.column("time", width=160, anchor="center")
        self.tree.column("camera", width=180, anchor="w")
        self.tree.column("direction", width=100, anchor="center")
        self.tree.column("access_level", width=140, anchor="center")
        self.tree.column("access", width=100, anchor="center")

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.refresh_events()

    def clear_search(self):
        self.search_var.set("")

    def refresh_events(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        search_value = self.search_var.get().strip()
        events = get_access_events(limit=200, search=search_value)

        for event in events:
            self.tree.insert("", "end", values=event)

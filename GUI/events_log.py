import tkinter as tk
from tkinter import ttk
from core.database import get_access_events


class EventsLogFrame:
    def __init__(self, parent):
        self.frame = tk.Frame(parent)
        
        tk.Label(self.frame, text="Журнал событий").pack(pady=10)
        
        # Таблица с скроллбаром
        self.tree_frame = tk.Frame(self.frame)
        self.tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.tree = ttk.Treeview(
            self.tree_frame,
            columns=("Номер", "Камера", "Направление", "Решение", "Причина", "Дата"),
            height=20
        )
        
        self.tree.heading("#0", text="ID")
        self.tree.heading("Номер", text="Номер автомобиля")
        self.tree.heading("Камера", text="Камера")
        self.tree.heading("Направление", text="Направление")
        self.tree.heading("Решение", text="Решение")
        self.tree.heading("Причина", text="Причина")
        self.tree.heading("Дата", text="Дата и время")
        
        self.tree.column("#0", width=30)
        self.tree.column("Номер", width=120)
        self.tree.column("Камера", width=100)
        self.tree.column("Направление", width=100)
        self.tree.column("Решение", width=80)
        self.tree.column("Причина", width=100)
        self.tree.column("Дата", width=150)
        
        scrollbar = ttk.Scrollbar(self.tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.refresh_events()

    def refresh_events(self):
        """Обновляет список событий."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        events = get_access_events(limit=100)
        for idx, event in enumerate(events):
            self.tree.insert("", "end", text=str(idx+1), values=event)

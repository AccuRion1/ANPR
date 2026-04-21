import uuid
from typing import Dict, Optional

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Dict] = {}  # session_id -> {'user_id': int, 'role': str}

    def create_session(self, user_id: int, role: str) -> str:
        """Создает новую сессию и возвращает session_id."""
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {'user_id': user_id, 'role': role}
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Получает данные сессии по session_id."""
        return self.sessions.get(session_id)

    def destroy_session(self, session_id: str):
        """Удаляет сессию."""
        self.sessions.pop(session_id, None)

# Глобальный менеджер сессий
session_manager = SessionManager()
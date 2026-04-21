from typing import Optional, Dict
from core.database import conn
from auth.password_utils import verify_password
from auth.session import session_manager

def authenticate_user(login: str, password: str) -> Optional[str]:
    """Аутентифицирует пользователя и возвращает session_id если успешно."""
    cursor = conn.cursor()
    query = """
    SELECT u.id, u.password, r.role
    FROM users u
    JOIN roles r ON u.role_id = r.id
    WHERE u.login = %s
    """
    cursor.execute(query, (login,))
    row = cursor.fetchone()
    cursor.close()

    if row and verify_password(password, row[1]):
        user_id, _, role = row
        session_id = session_manager.create_session(user_id, role)
        return session_id
    return None

def get_current_user(session_id: str) -> Optional[Dict]:
    """Получает текущего пользователя по session_id."""
    return session_manager.get_session(session_id)
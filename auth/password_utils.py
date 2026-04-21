import bcrypt

def hash_password(password: str) -> str:
    """Хеширует пароль с солью."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Проверяет пароль против хеша."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


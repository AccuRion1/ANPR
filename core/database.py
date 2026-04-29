import os

import psycopg2


conn = psycopg2.connect(
    dbname=os.getenv("DB_NAME", "plates"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "201720122004"),
    host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", "5432"),
    client_encoding="UTF8",
)
conn.autocommit = True


def get_registered_plate(plate_number):
    cursor = conn.cursor()
    query = """
    SELECT id, "Номер автомобиля", "Владелец", "Статус", "Тип доступа"
    FROM registered_plates
    WHERE "Номер автомобиля" = %s
    """

    cursor.execute(query, (plate_number,))
    row = cursor.fetchone()
    cursor.close()

    if row is None:
        return None

    return {
        "id": row[0],
        "plate_number": row[1],
        "owner_id": row[2],
        "status": row[3],
        "access_type": row[4],
    }


def save_access_event(plate_number, camera_name, direction, decision, reason):
    cursor = conn.cursor()
    query = """
    INSERT INTO access_events ("Номер автомобиля", "Камера", "Направление", "Решение", "Причина")
    VALUES (%s, %s, %s, %s, %s)
    """

    cursor.execute(
        query,
        (plate_number, camera_name, direction, decision, reason),
    )
    cursor.close()


def get_vehicle_on_territory(plate_id):
    cursor = conn.cursor()
    query = """
    SELECT "id", "Номер автомобиля", "Время въезда"
    FROM vehicles_on_territory
    WHERE "Номер автомобиля" = %s
    """

    cursor.execute(query, (plate_id,))
    row = cursor.fetchone()
    cursor.close()

    if row is None:
        return None

    return {
        "id": row[0],
        "plate_id": row[1],
        "entry_time": row[2],
    }


def add_vehicle_on_territory(plate_id):
    cursor = conn.cursor()
    query = """
    INSERT INTO vehicles_on_territory ("Номер автомобиля")
    VALUES (%s)
    """

    cursor.execute(query, (plate_id,))
    cursor.close()


def remove_vehicle_from_territory(plate_id):
    cursor = conn.cursor()
    query = """
    DELETE FROM vehicles_on_territory
    WHERE "Номер автомобиля" = %s
    """

    cursor.execute(query, (plate_id,))
    cursor.close()


def check_plate_in_db(plate_number):
    return get_registered_plate(plate_number) is not None


def get_access_events(limit=100):
    """Получает журнал событий из БД."""
    cursor = conn.cursor()
    query = """
    SELECT "Номер автомобиля", "Камера", "Направление", "Решение", "Причина", 
           TO_CHAR("Время события", 'YYYY-MM-DD HH24:MI:SS') AS "Время события"
    FROM access_events
    ORDER BY "Время события" DESC
    LIMIT %s
    """
    cursor.execute(query, (limit,))
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_all_plates_with_owners():
    """Получает все номера с ФИ владельца из таблицы employees."""
    cursor = conn.cursor()
    query = """
    SELECT rp."Номер автомобиля", rp."Статус", rp."Тип доступа", 
           COALESCE(e."Фамилия" || ' ' || e."Имя", 'Неизвестно') AS owner_name
    FROM registered_plates rp
    LEFT JOIN employees e ON rp."Владелец" = e."id"
    ORDER BY rp."Номер автомобиля"
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()
    return rows


def add_plate(plate_number, owner_id, status, access_type):
    """Добавляет новый номер в БД."""
    cursor = conn.cursor()
    query = """
    INSERT INTO registered_plates ("Номер автомобиля", "Владелец", "Статус", "Тип доступа")
    VALUES (%s, %s, %s, %s)
    """
    try:
        cursor.execute(query, (plate_number, owner_id, status, access_type))
        cursor.close()
        return True
    except Exception as e:
        cursor.close()
        return False


def update_plate(plate_number, owner_id, status, access_type):
    """Обновляет существующий номер в БД."""
    cursor = conn.cursor()
    query = """
    UPDATE registered_plates
    SET "Владелец" = %s, "Статус" = %s, "Тип доступа" = %s
    WHERE "Номер автомобиля" = %s
    """
    try:
        cursor.execute(query, (owner_id, status, access_type, plate_number))
        cursor.close()
        return True
    except Exception as e:
        cursor.close()
        return False


def delete_plate(plate_number):
    """Удаляет номер из БД."""
    cursor = conn.cursor()
    query = """
    DELETE FROM registered_plates
    WHERE "Номер автомобиля" = %s
    """
    try:
        cursor.execute(query, (plate_number,))
        cursor.close()
        return True
    except Exception as e:
        cursor.close()
        return False


def get_plate_by_number(plate_number):
    """Получает данные номера по номеру автомобиля."""
    cursor = conn.cursor()
    query = """
    SELECT "Номер автомобиля", "Владелец", "Статус", "Тип доступа"
    FROM registered_plates
    WHERE "Номер автомобиля" = %s
    """
    cursor.execute(query, (plate_number,))
    row = cursor.fetchone()
    cursor.close()
    
    if row is None:
        return None
    
    return {
        "plate_number": row[0],
        "owner_id": row[1],
        "status": row[2],
        "access_type": row[3],
    }

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


def _fetchone(query, params=()):
    cursor = conn.cursor()
    cursor.execute(query, params)
    row = cursor.fetchone()
    cursor.close()
    return row


def _fetchall(query, params=()):
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    cursor.close()
    return rows


def _execute(query, params=()):
    cursor = conn.cursor()
    cursor.execute(query, params)
    cursor.close()


def get_registered_plate(plate_number):
    row = _fetchone(
        """
        SELECT
            rp.id,
            rp."Номер ТС",
            rp."Владелец",
            rp."Статус",
            rp."Уровень доступа",
            rp."На территории",
            COALESCE(e."Фамилия" || ' ' || e."Имя", 'Неизвестно') AS owner_name
        FROM registered_plates rp
        LEFT JOIN employees e ON rp."Владелец" = e.id
        WHERE rp."Номер ТС" = %s
        """,
        (plate_number,),
    )

    if row is None:
        return None

    return {
        "id": row[0],
        "plate_number": row[1],
        "owner_id": row[2],
        "status": row[3],
        "access_level": row[4],
        "on_territory": row[5],
        "owner_name": row[6],
    }


def update_plate_territory_state(plate_id, on_territory):
    _execute(
        """
        UPDATE registered_plates
        SET "На территории" = %s
        WHERE id = %s
        """,
        (on_territory, plate_id),
    )


def check_plate_in_db(plate_number):
    return get_registered_plate(plate_number) is not None


def get_camera_by_name(camera_name):
    if not camera_name:
        return None

    row = _fetchone(
        """
        SELECT id, "Название", URL, "Местоположение", "Направление", "Статус"
        FROM cameras
        WHERE "Название" = %s
        """,
        (camera_name,),
    )

    if row is None:
        return None

    return {
        "id": row[0],
        "name": row[1],
        "url": row[2],
        "location": row[3],
        "direction": row[4],
        "status": row[5],
    }


def get_active_camera(direction=None):
    params = []
    query = """
    SELECT id, "Название", URL, "Местоположение", "Направление", "Статус"
    FROM cameras
    WHERE "Статус" = TRUE
    """

    if direction:
        query += ' AND LOWER("Направление") = LOWER(%s)'
        params.append(direction)

    query += " ORDER BY id LIMIT 1"
    row = _fetchone(query, tuple(params))

    if row is None:
        return None

    return {
        "id": row[0],
        "name": row[1],
        "url": row[2],
        "location": row[3],
        "direction": row[4],
        "status": row[5],
    }


def get_active_cameras():
    rows = _fetchall(
        """
        SELECT id, "Название", URL, "Местоположение", "Направление", "Статус"
        FROM cameras
        WHERE "Статус" = TRUE
        ORDER BY id
        """
    )

    return [
        {
            "id": row[0],
            "name": row[1],
            "url": row[2],
            "location": row[3],
            "direction": row[4],
            "status": row[5],
        }
        for row in rows
    ]


def save_access_event(plate_id, camera_id, direction, access_level, access_granted):
    _execute(
        """
        INSERT INTO events ("Номер ТС", "Видеокамера", "Направление", "Уровень доступа", "Доступ")
        VALUES (%s, %s, %s, %s, %s)
        """,
        (plate_id, camera_id, direction, access_level, access_granted),
    )


def get_access_events(limit=100, search=""):
    params = []
    query = """
    SELECT
        COALESCE(rp."Номер ТС", 'Неизвестно') AS plate_number,
        TO_CHAR(e."Время события", 'YYYY-MM-DD HH24:MI:SS') AS event_time,
        COALESCE(c."Название", 'Неизвестно') AS camera_name,
        e."Направление",
        COALESCE(e."Уровень доступа", 'Неизвестно') AS access_level,
        CASE
            WHEN e."Доступ" = TRUE THEN 'Разрешен'
            ELSE 'Запрещен'
        END AS access_value
    FROM events e
    LEFT JOIN registered_plates rp ON e."Номер ТС" = rp.id
    LEFT JOIN cameras c ON e."Видеокамера" = c.id
    """

    if search:
        query += """
        WHERE
            rp."Номер ТС" ILIKE %s
            OR c."Название" ILIKE %s
            OR e."Направление" ILIKE %s
            OR COALESCE(e."Уровень доступа", '') ILIKE %s
        """
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern, pattern])

    query += """
    ORDER BY e."Время события" DESC
    LIMIT %s
    """
    params.append(limit)

    return _fetchall(query, tuple(params))


def get_all_plates_with_owners(search=""):
    params = []
    query = """
    SELECT
        rp."Номер ТС",
        COALESCE(e."Фамилия" || ' ' || e."Имя", 'Неизвестно') AS owner_name,
        CASE
            WHEN rp."Статус" = TRUE THEN 'Активен'
            ELSE 'Неактивен'
        END AS status_name,
        COALESCE(rp."Уровень доступа", 'Не указан') AS access_level,
        CASE
            WHEN rp."На территории" = TRUE THEN 'Да'
            ELSE 'Нет'
        END AS on_territory_name
    FROM registered_plates rp
    LEFT JOIN employees e ON rp."Владелец" = e.id
    """

    if search:
        query += """
        WHERE
            rp."Номер ТС" ILIKE %s
            OR COALESCE(e."Фамилия" || ' ' || e."Имя", '') ILIKE %s
            OR COALESCE(rp."Уровень доступа", '') ILIKE %s
        """
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])

    query += ' ORDER BY rp."Номер ТС"'
    return _fetchall(query, tuple(params))


def add_plate(plate_number, owner_id, status, access_level, on_territory=False):
    try:
        _execute(
            """
            INSERT INTO registered_plates ("Номер ТС", "Владелец", "Статус", "Уровень доступа", "На территории")
            VALUES (%s, %s, %s, %s, %s)
            """,
            (plate_number, owner_id, status, access_level, on_territory),
        )
        return True
    except Exception:
        return False


def update_plate(original_plate_number, plate_number, owner_id, status, access_level, on_territory):
    try:
        _execute(
            """
            UPDATE registered_plates
            SET
                "Номер ТС" = %s,
                "Владелец" = %s,
                "Статус" = %s,
                "Уровень доступа" = %s,
                "На территории" = %s
            WHERE "Номер ТС" = %s
            """,
            (plate_number, owner_id, status, access_level, on_territory, original_plate_number),
        )
        return True
    except Exception:
        return False


def delete_plate(plate_number):
    try:
        _execute(
            """
            DELETE FROM registered_plates
            WHERE "Номер ТС" = %s
            """,
            (plate_number,),
        )
        return True
    except Exception:
        return False


def get_plate_by_number(plate_number):
    row = _fetchone(
        """
        SELECT "Номер ТС", "Владелец", "Статус", "Уровень доступа", "На территории"
        FROM registered_plates
        WHERE "Номер ТС" = %s
        """,
        (plate_number,),
    )

    if row is None:
        return None

    return {
        "plate_number": row[0],
        "owner_id": row[1],
        "status": row[2],
        "access_level": row[3],
        "on_territory": row[4],
    }

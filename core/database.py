import os
from datetime import datetime

import psycopg2


DATETIME_DISPLAY_FORMAT = "%Y-%m-%d %H:%M"

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


def _execute_returning_id(query, params=()):
    cursor = conn.cursor()
    cursor.execute(query, params)
    row = cursor.fetchone()
    cursor.close()
    return row[0] if row else None


def _build_owner_name(last_name, first_name, middle_name):
    parts = [last_name or "", first_name or "", middle_name or ""]
    full_name = " ".join(part.strip() for part in parts if part and part.strip())
    return full_name or "Неизвестно"


def _format_dt(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.strftime(DATETIME_DISPLAY_FORMAT)


def _parse_dt(value):
    if isinstance(value, datetime):
        return value
    return datetime.strptime(value, DATETIME_DISPLAY_FORMAT)


def get_plate_id(plate_number):
    row = _fetchone('SELECT id FROM plates WHERE "Номер ТС" = %s', (plate_number,))
    return row[0] if row else None


def get_or_create_plate_id(plate_number):
    existing_id = get_plate_id(plate_number)
    if existing_id is not None:
        return existing_id

    return _execute_returning_id(
        'INSERT INTO plates ("Номер ТС") VALUES (%s) RETURNING id',
        (plate_number,),
    )


def _cleanup_orphan_plate(plate_id):
    counts = _fetchone(
        """
        SELECT
            (SELECT COUNT(*) FROM registered_plates WHERE "Номер ТС" = %s),
            (SELECT COUNT(*) FROM guest_plates WHERE "Номер ТС" = %s),
            (SELECT COUNT(*) FROM events WHERE "ID ТС" = %s)
        """,
        (plate_id, plate_id, plate_id),
    )
    if counts and counts[0] == 0 and counts[1] == 0 and counts[2] == 0:
        _execute("DELETE FROM plates WHERE id = %s", (plate_id,))


def get_registered_plate(plate_number):
    row = _fetchone(
        """
        SELECT
            rp.id,
            p.id,
            p."Номер ТС",
            rp."Владелец",
            rp."Статус",
            rp."На территории",
            e."Фамилия",
            e."Имя",
            e."Отчество"
        FROM registered_plates rp
        JOIN plates p ON rp."Номер ТС" = p.id
        LEFT JOIN employees e ON rp."Владелец" = e.id
        WHERE p."Номер ТС" = %s
        """,
        (plate_number,),
    )

    if row is None:
        return None

    return {
        "record_id": row[0],
        "plate_id": row[1],
        "plate_number": row[2],
        "owner_id": row[3],
        "status": row[4],
        "on_territory": row[5],
        "owner_name": _build_owner_name(row[6], row[7], row[8]),
        "access_level": "Сотрудник",
        "kind": "registered",
    }


def get_guest_plate(plate_number):
    row = _fetchone(
        """
        SELECT
            gp.id,
            p.id,
            p."Номер ТС",
            gp."Время начала",
            gp."Время окончания",
            gp."Статус",
            gp."На территории"
        FROM guest_plates gp
        JOIN plates p ON gp."Номер ТС" = p.id
        WHERE p."Номер ТС" = %s
        """,
        (plate_number,),
    )

    if row is None:
        return None

    return {
        "record_id": row[0],
        "plate_id": row[1],
        "plate_number": row[2],
        "start_time": row[3],
        "end_time": row[4],
        "status": row[5],
        "on_territory": row[6],
        "access_level": "Гость",
        "kind": "guest",
    }


def update_registered_plate_territory_state(record_id, on_territory):
    _execute(
        """
        UPDATE registered_plates
        SET "На территории" = %s
        WHERE id = %s
        """,
        (on_territory, record_id),
    )


def update_guest_plate_territory_state(record_id, on_territory):
    _execute(
        """
        UPDATE guest_plates
        SET "На территории" = %s
        WHERE id = %s
        """,
        (on_territory, record_id),
    )


def check_plate_in_db(plate_number):
    return get_registered_plate(plate_number) is not None or get_guest_plate(plate_number) is not None


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


def get_all_cameras(search=""):
    params = []
    query = '''
    SELECT id, "Название", URL, "Местоположение", "Направление", "Статус"
    FROM cameras
    '''

    if search:
        query += '''
        WHERE
            "Название" ILIKE %s
            OR URL ILIKE %s
            OR "Местоположение" ILIKE %s
            OR "Направление" ILIKE %s
        '''
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern, pattern])

    query += ' ORDER BY id'
    rows = _fetchall(query, tuple(params))

    result = []
    for row in rows:
        result.append((row[1], row[2], row[3], row[4], 'Активен' if row[5] else 'Неактивен'))
    return result


def add_camera(name, url, location, direction, status=True):
    try:
        _execute(
            '''
            INSERT INTO cameras ("Название", URL, "Местоположение", "Направление", "Статус")
            VALUES (%s, %s, %s, %s, %s)
            ''',
            (name, url, location, direction, status),
        )
        return True
    except Exception:
        return False


def update_camera(original_name, name, url, location, direction, status):
    current = get_camera_by_name(original_name)
    if current is None:
        return False
    try:
        _execute(
            '''
            UPDATE cameras
            SET "Название" = %s, URL = %s, "Местоположение" = %s, "Направление" = %s, "Статус" = %s
            WHERE id = %s
            ''',
            (name, url, location, direction, status, current["id"]),
        )
        return True
    except Exception:
        return False


def delete_camera(name):
    current = get_camera_by_name(name)
    if current is None:
        return False
    try:
        _execute('DELETE FROM cameras WHERE id = %s', (current["id"],))
        return True
    except Exception:
        return False


def save_access_event(plate_number, plate_id, camera_id, direction, access_level, access_granted):
    return _execute_returning_id(
        """
        INSERT INTO events ("Номер ТС", "ID ТС", "Видеокамера", "Направление", "Уровень доступа", "Доступ")
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (plate_number, plate_id, camera_id, direction, access_level, access_granted),
    )


def save_incident(plate_number, event_id, camera_id, description):
    return _execute_returning_id(
        """
        INSERT INTO incidents ("Номер ТС", "ID события", "Видеокамера", "Описание")
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (plate_number, event_id, camera_id, description),
    )


def get_access_events(limit=100, search=""):
    params = []
    query = """
    SELECT
        COALESCE(e."Номер ТС", p."Номер ТС", 'Неизвестно') AS plate_number,
        TO_CHAR(e."Время события", 'YYYY-MM-DD HH24:MI:SS') AS event_time,
        COALESCE(c."Название", 'Неизвестно') AS camera_name,
        COALESCE(e."Направление", 'Не указано') AS direction,
        COALESCE(e."Уровень доступа", 'Неизвестно') AS access_level,
        CASE
            WHEN e."Доступ" = TRUE THEN 'Разрешен'
            ELSE 'Запрещен'
        END AS access_value
    FROM events e
    LEFT JOIN plates p ON e."ID ТС" = p.id
    LEFT JOIN cameras c ON e."Видеокамера" = c.id
    """

    if search:
        query += """
        WHERE
            COALESCE(e."Номер ТС", p."Номер ТС", '') ILIKE %s
            OR COALESCE(c."Название", '') ILIKE %s
            OR COALESCE(e."Направление", '') ILIKE %s
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


def get_incidents(limit=100, search=""):
    params = []
    query = """
    SELECT
        COALESCE(i."Номер ТС", e."Номер ТС", p."Номер ТС", 'Неизвестно') AS plate_number,
        TO_CHAR(i."Время инциндента", 'YYYY-MM-DD HH24:MI:SS') AS incident_time,
        COALESCE(c."Название", 'Неизвестно') AS camera_name,
        COALESCE(i."Описание", 'Без описания') AS description
    FROM incidents i
    LEFT JOIN events e ON i."ID события" = e.id
    LEFT JOIN plates p ON e."ID ТС" = p.id
    LEFT JOIN cameras c ON i."Видеокамера" = c.id
    """

    if search:
        query += """
        WHERE
            COALESCE(i."Номер ТС", e."Номер ТС", p."Номер ТС", '') ILIKE %s
            OR COALESCE(c."Название", '') ILIKE %s
            OR COALESCE(i."Описание", '') ILIKE %s
        """
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])

    query += """
    ORDER BY i."Время инциндента" DESC
    LIMIT %s
    """
    params.append(limit)
    return _fetchall(query, tuple(params))


def get_all_registered_plates_with_owners(search=""):
    params = []
    query = """
    SELECT
        p."Номер ТС",
        CASE
            WHEN e.id IS NULL THEN 'Неизвестно'
            ELSE TRIM(COALESCE(e."Фамилия", '') || ' ' || COALESCE(e."Имя", '') || ' ' || COALESCE(e."Отчество", ''))
        END AS owner_name,
        CASE
            WHEN rp."Статус" = TRUE THEN 'Активен'
            ELSE 'Неактивен'
        END AS status_name,
        CASE
            WHEN rp."На территории" = TRUE THEN 'Да'
            ELSE 'Нет'
        END AS on_territory_name
    FROM registered_plates rp
    JOIN plates p ON rp."Номер ТС" = p.id
    LEFT JOIN employees e ON rp."Владелец" = e.id
    """

    if search:
        query += """
        WHERE
            p."Номер ТС" ILIKE %s
            OR TRIM(COALESCE(e."Фамилия", '') || ' ' || COALESCE(e."Имя", '') || ' ' || COALESCE(e."Отчество", '')) ILIKE %s
        """
        pattern = f"%{search}%"
        params.extend([pattern, pattern])

    query += ' ORDER BY p."Номер ТС"'
    return _fetchall(query, tuple(params))


def get_all_guest_plates(search=""):
    params = []
    query = """
    SELECT
        p."Номер ТС",
        TO_CHAR(gp."Время начала", 'YYYY-MM-DD HH24:MI') AS start_time,
        TO_CHAR(gp."Время окончания", 'YYYY-MM-DD HH24:MI') AS end_time,
        CASE
            WHEN gp."Статус" = TRUE THEN 'Активен'
            ELSE 'Неактивен'
        END AS status_name,
        CASE
            WHEN gp."На территории" = TRUE THEN 'Да'
            ELSE 'Нет'
        END AS on_territory_name
    FROM guest_plates gp
    JOIN plates p ON gp."Номер ТС" = p.id
    """

    if search:
        query += """
        WHERE
            p."Номер ТС" ILIKE %s
            OR TO_CHAR(gp."Время начала", 'YYYY-MM-DD HH24:MI') ILIKE %s
            OR TO_CHAR(gp."Время окончания", 'YYYY-MM-DD HH24:MI') ILIKE %s
        """
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])

    query += ' ORDER BY gp."Время окончания" DESC'
    return _fetchall(query, tuple(params))


def get_employees_for_select(search=""):
    params = []
    query = """
    SELECT
        id,
        TRIM(COALESCE("Фамилия", '') || ' ' || COALESCE("Имя", '') || ' ' || COALESCE("Отчество", '')) AS full_name
    FROM employees
    """

    if search:
        query += """
        WHERE TRIM(COALESCE("Фамилия", '') || ' ' || COALESCE("Имя", '') || ' ' || COALESCE("Отчество", '')) ILIKE %s
        """
        params.append(f"%{search}%")

    query += " ORDER BY full_name"
    rows = _fetchall(query, tuple(params))
    return [{"id": row[0], "full_name": row[1] or f"Сотрудник #{row[0]}"} for row in rows]


def add_registered_plate(plate_number, owner_id, status, on_territory=False):
    try:
        plate_id = get_or_create_plate_id(plate_number)
        _execute(
            """
            INSERT INTO registered_plates ("Номер ТС", "Владелец", "Статус", "На территории")
            VALUES (%s, %s, %s, %s)
            """,
            (plate_id, owner_id, status, on_territory),
        )
        return True
    except Exception:
        return False


def update_registered_plate(original_plate_number, plate_number, owner_id, status, on_territory):
    current = get_registered_plate(original_plate_number)
    if current is None:
        return False

    try:
        new_plate_id = get_or_create_plate_id(plate_number)
        _execute(
            """
            UPDATE registered_plates
            SET
                "Номер ТС" = %s,
                "Владелец" = %s,
                "Статус" = %s,
                "На территории" = %s
            WHERE id = %s
            """,
            (new_plate_id, owner_id, status, on_territory, current["record_id"]),
        )
        if current["plate_id"] != new_plate_id:
            _cleanup_orphan_plate(current["plate_id"])
        return True
    except Exception:
        return False


def delete_registered_plate(plate_number):
    current = get_registered_plate(plate_number)
    if current is None:
        return False

    try:
        _execute("DELETE FROM registered_plates WHERE id = %s", (current["record_id"],))
        _cleanup_orphan_plate(current["plate_id"])
        return True
    except Exception:
        return False


def get_registered_plate_by_number(plate_number):
    record = get_registered_plate(plate_number)
    if record is None:
        return None
    return {
        "plate_number": record["plate_number"],
        "owner_id": record["owner_id"],
        "status": record["status"],
        "on_territory": record["on_territory"],
    }


def add_guest_plate(plate_number, start_time, end_time, status, on_territory=False):
    try:
        plate_id = get_or_create_plate_id(plate_number)
        _execute(
            """
            INSERT INTO guest_plates ("Номер ТС", "Время начала", "Время окончания", "Статус", "На территории")
            VALUES (%s, %s, %s, %s, %s)
            """,
            (plate_id, _parse_dt(start_time), _parse_dt(end_time), status, on_territory),
        )
        return True
    except Exception:
        return False


def update_guest_plate(original_plate_number, plate_number, start_time, end_time, status, on_territory):
    current = get_guest_plate(original_plate_number)
    if current is None:
        return False

    try:
        new_plate_id = get_or_create_plate_id(plate_number)
        _execute(
            """
            UPDATE guest_plates
            SET
                "Номер ТС" = %s,
                "Время начала" = %s,
                "Время окончания" = %s,
                "Статус" = %s,
                "На территории" = %s
            WHERE id = %s
            """,
            (
                new_plate_id,
                _parse_dt(start_time),
                _parse_dt(end_time),
                status,
                on_territory,
                current["record_id"],
            ),
        )
        if current["plate_id"] != new_plate_id:
            _cleanup_orphan_plate(current["plate_id"])
        return True
    except Exception:
        return False


def delete_guest_plate(plate_number):
    current = get_guest_plate(plate_number)
    if current is None:
        return False

    try:
        _execute("DELETE FROM guest_plates WHERE id = %s", (current["record_id"],))
        _cleanup_orphan_plate(current["plate_id"])
        return True
    except Exception:
        return False


def get_guest_plate_by_number(plate_number):
    record = get_guest_plate(plate_number)
    if record is None:
        return None
    return {
        "plate_number": record["plate_number"],
        "start_time": _format_dt(record["start_time"]),
        "end_time": _format_dt(record["end_time"]),
        "status": record["status"],
        "on_territory": record["on_territory"],
    }


# Совместимость со старыми импортами
def get_all_plates_with_owners(search=""):
    return get_all_registered_plates_with_owners(search=search)


def add_plate(plate_number, owner_id, status, on_territory=False):
    return add_registered_plate(plate_number, owner_id, status, on_territory)


def update_plate(original_plate_number, plate_number, owner_id, status, on_territory):
    return update_registered_plate(original_plate_number, plate_number, owner_id, status, on_territory)


def delete_plate(plate_number):
    return delete_registered_plate(plate_number)


def get_plate_by_number(plate_number):
    return get_registered_plate_by_number(plate_number)

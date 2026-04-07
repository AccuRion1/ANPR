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
    SELECT id, plate_number, owner_name, status, access_type
    FROM registered_plates
    WHERE plate_number = %s
    """

    cursor.execute(query, (plate_number,))
    row = cursor.fetchone()
    cursor.close()

    if row is None:
        return None

    return {
        "id": row[0],
        "plate_number": row[1],
        "owner_name": row[2],
        "status": row[3],
        "access_type": row[4],
    }


def save_access_event(plate_number, camera_name, direction, decision, reason):
    cursor = conn.cursor()
    query = """
    INSERT INTO access_events (plate_number, camera_name, direction, decision, reason)
    VALUES (%s, %s, %s, %s, %s)
    """

    cursor.execute(
        query,
        (plate_number, camera_name, direction, decision, reason),
    )
    cursor.close()


def check_plate_in_db(plate_number):
    return get_registered_plate(plate_number) is not None

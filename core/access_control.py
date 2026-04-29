import time

from core.database import (
    add_vehicle_on_territory,
    get_registered_plate,
    get_vehicle_on_territory,
    remove_vehicle_from_territory,
    save_access_event,
)


EVENT_COOLDOWN_SECONDS = 10
_recent_results = {}


def _make_cache_key(plate_number, camera_name, direction):
    return (plate_number, camera_name, direction)


def _get_recent_result(plate_number, camera_name, direction):
    key = _make_cache_key(plate_number, camera_name, direction)
    cached = _recent_results.get(key)

    if cached is None:
        return None

    if time.time() - cached["timestamp"] > EVENT_COOLDOWN_SECONDS:
        _recent_results.pop(key, None)
        return None

    result = dict(cached["result"])
    result["event_logged"] = False
    result["is_duplicate"] = True
    return result


def _remember_result(plate_number, camera_name, direction, result):
    key = _make_cache_key(plate_number, camera_name, direction)
    _recent_results[key] = {
        "timestamp": time.time(),
        "result": dict(result),
    }


def _build_result(plate_number, decision, reason, owner_id=None, status=None, access_type=None):
    return {
        "plate_number": plate_number,
        "decision": decision,
        "reason": reason,
        "owner_id": owner_id,
        "status": status,
        "access_type": access_type,
    }


def check_access(plate_number, camera_name="Основная камера", direction="въезд"):
    plate_number = (plate_number or "").strip().upper()
    direction = (direction or "въезд").strip().lower()
    camera_name = (camera_name or "Основная камера").strip()

    if not plate_number:
        return {
            "plate_number": "",
            "decision": "запрещен",
            "reason": "номер не распознан",
            "owner_id": None,
            "status": None,
            "access_type": None,
            "event_logged": False,
            "is_duplicate": False,
        }

    cached = _get_recent_result(plate_number, camera_name, direction)
    if cached is not None:
        return cached

    plate_record = get_registered_plate(plate_number)

    if plate_record is None:
        result = _build_result(
            plate_number=plate_number,
            decision="запрещен",
            reason="номер не найден",
        )
    else:
        status = (plate_record["status"] or "").strip().lower()
        access_type = (plate_record["access_type"] or "").strip().lower()
        owner_id = plate_record["owner_id"]

        if status != "активен":
            result = _build_result(
                plate_number=plate_number,
                decision="запрещен",
                reason=f"статус: {status or 'неактивен'}",
                owner_id=owner_id,
                status=plate_record["status"],
                access_type=plate_record["access_type"],
            )
        elif access_type not in {"сотрудник", "гость"}:
            result = _build_result(
                plate_number=plate_number,
                decision="запрещен",
                reason=f"тип доступа: {access_type or 'запрещен'}",
                owner_id=owner_id,
                status=plate_record["status"],
                access_type=plate_record["access_type"],
            )
        else:
            vehicle_on_territory = get_vehicle_on_territory(plate_record["id"])

            if direction == "въезд":
                if vehicle_on_territory is not None:
                    result = _build_result(
                        plate_number=plate_number,
                        decision="запрещен",
                        reason="автомобиль уже находится на территории",
                        owner_id=owner_id,
                        status=plate_record["status"],
                        access_type=plate_record["access_type"],
                    )
                else:
                    add_vehicle_on_territory(plate_record["id"])
                    result = _build_result(
                        plate_number=plate_number,
                        decision="разрешен",
                        reason="въезд разрешен",
                        owner_id=owner_id,
                        status=plate_record["status"],
                        access_type=plate_record["access_type"],
                    )
            elif direction == "выезд":
                if vehicle_on_territory is None:
                    result = _build_result(
                        plate_number=plate_number,
                        decision="запрещен",
                        reason="автомобиль отсутствует на территории",
                        owner_id=owner_id,
                        status=plate_record["status"],
                        access_type=plate_record["access_type"],
                    )
                else:
                    remove_vehicle_from_territory(plate_record["id"])
                    result = _build_result(
                        plate_number=plate_number,
                        decision="разрешен",
                        reason="выезд разрешен",
                        owner_id=owner_id,
                        status=plate_record["status"],
                        access_type=plate_record["access_type"],
                    )
            else:
                result = _build_result(
                    plate_number=plate_number,
                    decision="запрещен",
                    reason="неизвестное направление",
                    owner_id=owner_id,
                    status=plate_record["status"],
                    access_type=plate_record["access_type"],
                )

    save_access_event(
        plate_number=result["plate_number"],
        camera_name=camera_name,
        direction=direction,
        decision=result["decision"],
        reason=result["reason"],
    )

    result["event_logged"] = True
    result["is_duplicate"] = False
    _remember_result(plate_number, camera_name, direction, result)
    return result

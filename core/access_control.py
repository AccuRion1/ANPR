import time

from core.database import (
    get_active_camera,
    get_camera_by_name,
    get_registered_plate,
    save_access_event,
    update_plate_territory_state,
)


EVENT_COOLDOWN_SECONDS = 10
_recent_results = {}


def _normalize_direction(direction):
    normalized = (direction or "въезд").strip().lower()
    if normalized in {"entry", "in"}:
        return "въезд"
    if normalized in {"exit", "out"}:
        return "выезд"
    return normalized


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


def _build_result(
    plate_number,
    decision,
    reason,
    owner_id=None,
    owner_name=None,
    status=None,
    access_level=None,
    on_territory=None,
    camera_id=None,
    camera_name=None,
):
    return {
        "plate_number": plate_number,
        "decision": decision,
        "reason": reason,
        "owner_id": owner_id,
        "owner_name": owner_name,
        "status": status,
        "access_level": access_level,
        "on_territory": on_territory,
        "camera_id": camera_id,
        "camera_name": camera_name,
    }


def _resolve_camera(camera_name, direction):
    camera = get_camera_by_name(camera_name) if camera_name else None
    if camera is None:
        camera = get_active_camera(direction)
    return camera


def check_access(plate_number, camera_name="Основная камера", direction="въезд"):
    plate_number = (plate_number or "").strip().upper()
    direction = _normalize_direction(direction)
    camera_name = (camera_name or "Основная камера").strip()

    if not plate_number:
        return {
            "plate_number": "",
            "decision": "запрещен",
            "reason": "номер не распознан",
            "owner_id": None,
            "owner_name": None,
            "status": None,
            "access_level": None,
            "on_territory": None,
            "camera_id": None,
            "camera_name": camera_name,
            "event_logged": False,
            "is_duplicate": False,
        }

    cached = _get_recent_result(plate_number, camera_name, direction)
    if cached is not None:
        return cached

    camera = _resolve_camera(camera_name, direction)
    resolved_camera_name = camera["name"] if camera else camera_name
    camera_id = camera["id"] if camera else None

    plate_record = get_registered_plate(plate_number)

    if plate_record is None:
        result = _build_result(
            plate_number=plate_number,
            decision="запрещен",
            reason="номер не найден",
            access_level="Неизвестен",
            camera_id=camera_id,
            camera_name=resolved_camera_name,
        )
    else:
        is_active = bool(plate_record["status"])
        access_level = (plate_record["access_level"] or "").strip().lower()
        on_territory = bool(plate_record["on_territory"])

        base_kwargs = {
            "plate_number": plate_number,
            "owner_id": plate_record["owner_id"],
            "owner_name": plate_record["owner_name"],
            "status": plate_record["status"],
            "access_level": plate_record["access_level"],
            "on_territory": plate_record["on_territory"],
            "camera_id": camera_id,
            "camera_name": resolved_camera_name,
        }

        if not is_active:
            result = _build_result(
                decision="запрещен",
                reason="статус неактивен",
                **base_kwargs,
            )
        elif access_level not in {"сотрудник", "гость"}:
            result = _build_result(
                decision="запрещен",
                reason="уровень доступа запрещен",
                **base_kwargs,
            )
        elif direction == "въезд":
            if on_territory:
                result = _build_result(
                    decision="запрещен",
                    reason="автомобиль уже на территории",
                    **base_kwargs,
                )
            else:
                update_plate_territory_state(plate_record["id"], True)
                allowed_kwargs = dict(base_kwargs)
                allowed_kwargs["on_territory"] = True
                result = _build_result(
                    decision="разрешен",
                    reason="въезд разрешен",
                    **allowed_kwargs,
                )
        elif direction == "выезд":
            if not on_territory:
                result = _build_result(
                    decision="запрещен",
                    reason="автомобиль отсутствует на территории",
                    **base_kwargs,
                )
            else:
                update_plate_territory_state(plate_record["id"], False)
                allowed_kwargs = dict(base_kwargs)
                allowed_kwargs["on_territory"] = False
                result = _build_result(
                    decision="разрешен",
                    reason="выезд разрешен",
                    **allowed_kwargs,
                )
        else:
            result = _build_result(
                decision="запрещен",
                reason="неизвестное направление",
                **base_kwargs,
            )

    save_access_event(
        plate_id=plate_record["id"] if plate_record else None,
        camera_id=camera_id,
        direction=direction,
        access_level=result["access_level"] or "Неизвестен",
        access_granted=result["decision"] == "разрешен",
    )

    result["event_logged"] = True
    result["is_duplicate"] = False
    _remember_result(plate_number, resolved_camera_name, direction, result)
    return result

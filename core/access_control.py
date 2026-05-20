import time
from datetime import datetime

from core.database import (
    get_active_camera,
    get_camera_by_name,
    get_guest_plate,
    get_registered_plate,
    save_access_event,
    save_incident,
    update_guest_plate_territory_state,
    update_registered_plate_territory_state,
)
from imitation.gate import get_gate_runtime_state


EVENT_COOLDOWN_SECONDS = 10
NOISY_DENIAL_COOLDOWN_SECONDS = 4
_recent_results = {}
_recent_denials = {}


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


def _should_suppress_denial(camera_name, direction, reason, gate_open):
    key = (camera_name, direction, reason, gate_open)
    last_time = _recent_denials.get(key)
    now = time.time()
    if last_time is not None and now - last_time < NOISY_DENIAL_COOLDOWN_SECONDS:
        return True
    _recent_denials[key] = now
    return False


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
    event_id=None,
    incident_description=None,
    kind=None,
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
        "event_id": event_id,
        "incident_description": incident_description,
        "kind": kind,
    }


def _resolve_camera(camera_name, direction):
    camera = get_camera_by_name(camera_name) if camera_name else None
    if camera is None:
        camera = get_active_camera(direction)
    return camera


def _resolve_plate_record(plate_number):
    registered = get_registered_plate(plate_number)
    if registered is not None:
        return registered
    return get_guest_plate(plate_number)


def _evaluate_registered_access(record, direction, camera_id, camera_name):
    base_kwargs = {
        "plate_number": record["plate_number"],
        "owner_id": record["owner_id"],
        "owner_name": record["owner_name"],
        "status": record["status"],
        "access_level": record["access_level"],
        "on_territory": record["on_territory"],
        "camera_id": camera_id,
        "camera_name": camera_name,
        "kind": "registered",
    }

    is_active = bool(record["status"])
    on_territory = bool(record["on_territory"])

    if not is_active:
        return _build_result(decision="запрещен", reason="статус неактивен", **base_kwargs)

    if direction == "въезд":
        if on_territory:
            return _build_result(
                decision="запрещен",
                reason="автомобиль уже на территории",
                incident_description="Попытка повторного въезда автомобиля, который уже находится на территории",
                **base_kwargs,
            )

        update_registered_plate_territory_state(record["record_id"], True)
        allowed = dict(base_kwargs)
        allowed["on_territory"] = True
        return _build_result(decision="разрешен", reason="въезд разрешен", **allowed)

    if direction == "выезд":
        if not on_territory:
            return _build_result(
                decision="запрещен",
                reason="автомобиль отсутствует на территории",
                incident_description="Попытка выезда автомобиля, который не числится на территории",
                **base_kwargs,
            )

        update_registered_plate_territory_state(record["record_id"], False)
        allowed = dict(base_kwargs)
        allowed["on_territory"] = False
        return _build_result(decision="разрешен", reason="выезд разрешен", **allowed)

    return _build_result(decision="запрещен", reason="неизвестное направление", **base_kwargs)


def _evaluate_guest_access(record, direction, camera_id, camera_name):
    base_kwargs = {
        "plate_number": record["plate_number"],
        "owner_id": None,
        "owner_name": "Гостевой пропуск",
        "status": record["status"],
        "access_level": record["access_level"],
        "on_territory": record["on_territory"],
        "camera_id": camera_id,
        "camera_name": camera_name,
        "kind": "guest",
    }

    now = datetime.now()
    is_active = bool(record["status"])
    on_territory = bool(record["on_territory"])
    start_time = record["start_time"]
    end_time = record["end_time"]

    if not is_active:
        return _build_result(decision="запрещен", reason="гостевой пропуск неактивен", **base_kwargs)

    if direction == "въезд":
        if on_territory:
            return _build_result(
                decision="запрещен",
                reason="гостевой автомобиль уже на территории",
                incident_description="Попытка повторного въезда гостевого автомобиля, который уже находится на территории",
                **base_kwargs,
            )
        if now < start_time:
            return _build_result(decision="запрещен", reason="гостевой пропуск еще не активен", **base_kwargs)
        if now > end_time:
            return _build_result(decision="запрещен", reason="гостевой пропуск истек", **base_kwargs)

        update_guest_plate_territory_state(record["record_id"], True)
        allowed = dict(base_kwargs)
        allowed["on_territory"] = True
        return _build_result(decision="разрешен", reason="гостевой въезд разрешен", **allowed)

    if direction == "выезд":
        if not on_territory:
            return _build_result(
                decision="запрещен",
                reason="гостевой автомобиль отсутствует на территории",
                incident_description="Попытка выезда гостевого автомобиля, который не числится на территории",
                **base_kwargs,
            )

        update_guest_plate_territory_state(record["record_id"], False)
        allowed = dict(base_kwargs)
        allowed["on_territory"] = False
        return _build_result(decision="разрешен", reason="гостевой выезд разрешен", **allowed)

    return _build_result(decision="запрещен", reason="неизвестное направление", **base_kwargs)


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
            "event_id": None,
            "incident_description": None,
            "kind": None,
            "event_logged": False,
            "is_duplicate": False,
        }

    cached = _get_recent_result(plate_number, camera_name, direction)
    if cached is not None:
        return cached

    camera = _resolve_camera(camera_name, direction)
    resolved_camera_name = camera["name"] if camera else camera_name
    camera_id = camera["id"] if camera else None

    record = _resolve_plate_record(plate_number)
    gate_state = get_gate_runtime_state()

    if record is None:
        result = _build_result(
            plate_number=plate_number,
            decision="запрещен",
            reason="номер не найден",
            access_level="Неизвестен",
            camera_id=camera_id,
            camera_name=resolved_camera_name,
            kind=None,
        )
        plate_id = None
    elif record["kind"] == "registered":
        result = _evaluate_registered_access(record, direction, camera_id, resolved_camera_name)
        plate_id = record["plate_id"]
    else:
        result = _evaluate_guest_access(record, direction, camera_id, resolved_camera_name)
        plate_id = record["plate_id"]

    if gate_state["is_open"] and gate_state["authorized_plate"] and gate_state["authorized_plate"] != plate_number:
        if result["decision"] == "разрешен":
            result["reason"] = "проезд разрешен, цикл шлагбаума продлен"
        else:
            result["incident_description"] = (
                "Несанкционированный проезд: второй автомобиль во время открытого шлагбаума"
            )

    if result["decision"] != "разрешен":
        suppress_reason = result["reason"]
        if _should_suppress_denial(resolved_camera_name, direction, suppress_reason, gate_state["is_open"]):
            result["event_logged"] = False
            result["is_duplicate"] = True
            return result

    event_id = save_access_event(
        plate_number=plate_number,
        plate_id=plate_id,
        camera_id=camera_id,
        direction=direction,
        access_level=result["access_level"] or "Неизвестен",
        access_granted=result["decision"] == "разрешен",
    )
    result["event_id"] = event_id

    if result.get("incident_description"):
        save_incident(
            plate_number=plate_number,
            event_id=event_id,
            camera_id=camera_id,
            description=result["incident_description"],
        )

    result["event_logged"] = True
    result["is_duplicate"] = False
    _remember_result(plate_number, resolved_camera_name, direction, result)
    return result

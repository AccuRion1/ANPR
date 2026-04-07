import time

from core.database import get_registered_plate, save_access_event


EVENT_COOLDOWN_SECONDS = 5
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


def check_access(plate_number, camera_name="main_camera", direction="entry"):
    plate_number = (plate_number or "").strip().upper()
    direction = (direction or "entry").strip().lower()
    camera_name = (camera_name or "main_camera").strip()

    if not plate_number:
        return {
            "plate_number": "",
            "decision": "denied",
            "reason": "plate_not_recognized",
            "owner_name": None,
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
        result = {
            "plate_number": plate_number,
            "decision": "denied",
            "reason": "plate_not_found",
            "owner_name": None,
            "status": None,
            "access_type": None,
        }
    else:
        status = (plate_record["status"] or "").strip().lower()
        access_type = (plate_record["access_type"] or "").strip().lower()

        if status != "active":
            result = {
                "plate_number": plate_number,
                "decision": "denied",
                "reason": f"status_{status or 'inactive'}",
                "owner_name": plate_record["owner_name"],
                "status": plate_record["status"],
                "access_type": plate_record["access_type"],
            }
        elif access_type not in {"allowed", "guest"}:
            result = {
                "plate_number": plate_number,
                "decision": "denied",
                "reason": f"access_type_{access_type or 'denied'}",
                "owner_name": plate_record["owner_name"],
                "status": plate_record["status"],
                "access_type": plate_record["access_type"],
            }
        else:
            result = {
                "plate_number": plate_number,
                "decision": "allowed",
                "reason": "guest_access" if access_type == "guest" else "registered_plate",
                "owner_name": plate_record["owner_name"],
                "status": plate_record["status"],
                "access_type": plate_record["access_type"],
            }

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

import threading
import time


_shared_lock = threading.Lock()
_shared_state = {
    "opened_until": 0.0,
    "authorized_plate": None,
}


def mark_gate_open(authorized_plate=None, open_seconds=10):
    with _shared_lock:
        _shared_state["authorized_plate"] = authorized_plate
        _shared_state["opened_until"] = time.time() + float(open_seconds)


def clear_gate_state():
    with _shared_lock:
        _shared_state["authorized_plate"] = None
        _shared_state["opened_until"] = 0.0


def get_gate_runtime_state():
    with _shared_lock:
        is_open = _shared_state["opened_until"] > time.time()
        authorized_plate = _shared_state["authorized_plate"]

    if not is_open:
        return {"is_open": False, "authorized_plate": None}
    return {"is_open": True, "authorized_plate": authorized_plate}


class GateSimulator:
    def __init__(self, open_seconds=10, on_state_change=None):
        self.open_seconds = open_seconds
        self.on_state_change = on_state_change
        self._lock = threading.Lock()
        self._timer = None
        self._state = "Закрыт"

    def _notify(self):
        if self.on_state_change:
            self.on_state_change(self._state)

    def get_state(self):
        with self._lock:
            return self._state

    def request_open(self, authorized_plate=None):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()

            self._state = "Открыт"
            mark_gate_open(authorized_plate=authorized_plate, open_seconds=self.open_seconds)
            self._timer = threading.Timer(self.open_seconds, self.close)
            self._timer.daemon = True
            self._timer.start()

        self._notify()
        return True

    def close(self):
        with self._lock:
            self._state = "Закрыт"
            self._timer = None
            clear_gate_state()
        self._notify()

    def shutdown(self):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._state = "Закрыт"
            clear_gate_state()
        self._notify()

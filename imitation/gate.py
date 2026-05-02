import threading


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

    def _set_state(self, state):
        with self._lock:
            self._state = state
        self._notify()

    def get_state(self):
        with self._lock:
            return self._state

    def request_open(self):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()

            self._state = "Открыт"
            self._timer = threading.Timer(self.open_seconds, self.close)
            self._timer.daemon = True
            self._timer.start()

        self._notify()
        return True

    def close(self):
        with self._lock:
            self._state = "Закрыт"
            self._timer = None
        self._notify()

    def shutdown(self):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._state = "Закрыт"
        self._notify()

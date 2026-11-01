"""Журнал событий прогона для страницы Live: реплики, конец диалога, ошибки.
Потокобезопасный список; страница читает его раз в секунду."""
import threading


class EventLog:
    def __init__(self, limit: int = 5000):
        self._items: list[dict] = []
        self._lock = threading.Lock()
        self.limit = limit

    def emit(self, scenario: str, item: dict):
        with self._lock:
            self._items.append({"scenario": scenario, **item})
            if len(self._items) > self.limit:
                del self._items[: len(self._items) - self.limit]

    def items(self) -> list[dict]:
        with self._lock:
            return list(self._items)

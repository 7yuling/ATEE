import threading
from typing import Any


class AsyncReviewWorker:
    def __init__(self, core: Any, interval_seconds: int = 5, batch_size: int = 5):
        self.core = core
        self.interval_seconds = max(1, int(interval_seconds))
        self.batch_size = max(1, min(int(batch_size), 100))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="atee-async-ai-review-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def run_once(self) -> dict[str, Any]:
        result = self.core.process_async_reviews(limit=self.batch_size)
        self.last_result = result
        self.last_error = None if result.get("ok") else str(result.get("reason") or result.get("error") or "unknown")
        return result

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as error:
                self.last_error = str(error)[:160]
            self._stop.wait(self.interval_seconds)

import threading
from typing import Any


class AsyncReviewWorker:
    def __init__(self, core: Any, interval_seconds: int = 5, batch_size: int = 5):
        self.core = core
        self.interval_seconds = max(1, int(interval_seconds))
        self.batch_size = max(1, min(int(batch_size), 100))
        self.max_batch_size = 100
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
        result = self.core.process_async_reviews(limit=self._adaptive_batch_size())
        self.last_result = result
        self.last_error = None if result.get("ok") else str(result.get("reason") or result.get("error") or "unknown")
        return result

    def _loop(self) -> None:
        while not self._stop.is_set():
            wait_seconds = self.interval_seconds
            try:
                result = self.run_once()
                wait_seconds = self._adaptive_wait_seconds(result)
            except Exception as error:
                self.last_error = str(error)[:160]
            self._stop.wait(wait_seconds)

    def _adaptive_batch_size(self) -> int:
        queued = self._queued_jobs()
        if queued >= 1000:
            return self.max_batch_size
        if queued >= 200:
            return min(self.max_batch_size, max(self.batch_size, 50))
        if queued >= 50:
            return min(self.max_batch_size, max(self.batch_size, 25))
        if queued >= 10:
            return min(self.max_batch_size, max(self.batch_size, 10))
        return self.batch_size

    def _adaptive_wait_seconds(self, result: dict[str, Any]) -> int:
        if result.get("paused") and result.get("reason") == "llm_budget_exhausted":
            return max(self.interval_seconds, 60)
        queued = int((result.get("queue") or {}).get("queued") or self._queued_jobs())
        if queued >= 10:
            return 1
        if result.get("claimed"):
            return 1
        return self.interval_seconds

    def _queued_jobs(self) -> int:
        queue = getattr(self.core, "async_reviews", None)
        if not queue:
            return 0
        try:
            return int(queue.status().get("queued") or 0)
        except Exception:
            return 0

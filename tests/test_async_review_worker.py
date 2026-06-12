import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "core-service"))

from atee_core.async_review_worker import AsyncReviewWorker  # noqa: E402
from atee_core.config import AdminConfig  # noqa: E402
from atee_core.core import CoreService  # noqa: E402


class AsyncReviewWorkerTests(unittest.TestCase):
    def test_worker_scales_batch_with_backlog_and_waits_on_budget_pause(self):
        class FakeQueue:
            def __init__(self, queued):
                self.queued = queued

            def status(self):
                return {"queued": self.queued}

        class FakeCore:
            def __init__(self):
                self.async_reviews = FakeQueue(250)
                self.seen_limits = []

            def process_async_reviews(self, limit):
                self.seen_limits.append(limit)
                return {
                    "ok": True,
                    "claimed": 0,
                    "paused": True,
                    "reason": "llm_budget_exhausted",
                    "queue": {"queued": self.async_reviews.queued},
                }

        core = FakeCore()
        worker = AsyncReviewWorker(core, interval_seconds=5, batch_size=5)

        result = worker.run_once()

        self.assertTrue(result["paused"])
        self.assertEqual(core.seen_limits, [50])
        self.assertEqual(worker._adaptive_wait_seconds(result), 60)

    def test_worker_processes_due_ai_review_jobs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(
                    llm_mode="mock",
                    llm_provider="mock",
                    llm_model="atee-local-mock-v1",
                    async_review_worker_enabled=True,
                    async_review_worker_interval_seconds=1,
                    async_review_worker_batch_size=2,
                ),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            queued = core.check(
                {
                    "method": "POST",
                    "path": "/comment",
                    "event_type": "comment_create",
                    "body": {"text": "normal comment"},
                }
            )
            self.assertEqual(queued["route"]["route"], "async_agent")
            self.assertEqual(core.admin_async_reviews(status="pending")["count"], 1)

            worker = AsyncReviewWorker(core, interval_seconds=1, batch_size=2)
            try:
                worker.start()
                deadline = time.time() + 3
                completed = {"count": 0}
                while time.time() < deadline:
                    completed = core.admin_async_reviews(status="completed")
                    if completed["count"] == 1:
                        break
                    time.sleep(0.05)
            finally:
                worker.stop()

            self.assertEqual(completed["count"], 1)
            self.assertEqual(core.admin_async_reviews(status="pending")["count"], 0)
            self.assertFalse(worker.last_error)
            self.assertEqual((worker.last_result or {}).get("claimed"), 1)


if __name__ == "__main__":
    unittest.main()

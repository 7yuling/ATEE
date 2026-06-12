import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AsyncAIReviewWorkerSmokeScriptTests(unittest.TestCase):
    def test_fake_worker_smoke_covers_budget_and_circuit_without_leaking_provider_details(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "async-worker.md"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/async-ai-review-worker-smoke.py",
                    "--report",
                    str(report_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            payload = json.loads(completed.stdout)
            report = report_path.read_text(encoding="utf-8")
            scenarios = {item["name"]: item for item in payload["scenarios"]}

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["mode"], "fake")
            self.assertFalse(payload["live_used"])
            self.assertEqual(scenarios["budget_exhaustion_pauses_pending"]["provider_calls"], 1)
            self.assertEqual(scenarios["budget_exhaustion_pauses_pending"]["completed"], 1)
            self.assertEqual(scenarios["budget_exhaustion_pauses_pending"]["dead_letter"], 0)
            self.assertEqual(scenarios["budget_exhaustion_pauses_pending"]["queue"]["pending"], 1)
            self.assertEqual(scenarios["provider_failure_circuit_breaker"]["provider_calls"], 3)
            self.assertTrue(scenarios["provider_failure_circuit_breaker"]["circuit"]["open"])
            self.assertIn("ATEE Async AI Review Worker Smoke Report", report)
            for leaked in ["async-worker-key-", "127.0.0.1", "/v1", "worker.sqlite3"]:
                self.assertNotIn(leaked, completed.stdout)
                self.assertNotIn(leaked, report)

    def test_live_mode_requires_remote_provider_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text('{"llm_mode": "mock"}\n', encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/async-ai-review-worker-smoke.py",
                    "--include-live",
                    "--config",
                    str(config_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)
            payload = json.loads(completed.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["mode"], "live")
            self.assertEqual(payload["reason"], "remote_llm_not_configured")


if __name__ == "__main__":
    unittest.main()

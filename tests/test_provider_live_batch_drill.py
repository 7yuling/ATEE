import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProviderLiveBatchDrillScriptTests(unittest.TestCase):
    def test_fake_batch_drill_uses_local_provider_by_default(self):
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/provider-live-batch-drill.py",
                "--attempts",
                "3",
                "--budget-cents",
                "3",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "fake")
        self.assertFalse(payload["live_used"])
        self.assertEqual(payload["provider_calls"], 3)
        self.assertEqual(payload["reason_counts"]["provider_json_decision"], 3)
        self.assertGreaterEqual(payload["latency_ms"]["min"], 0)

    def test_report_output_is_sanitized(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "live-batch.md"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/provider-live-batch-drill.py",
                    "--attempts",
                    "4",
                    "--budget-cents",
                    "2",
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
            self.assertEqual(payload["report_path"], str(report_path))
            self.assertIn("ATEE Provider Live Batch Drill Report", report)
            self.assertIn("llm_budget_exhausted", report)
            self.assertNotIn("local-live-batch-", completed.stdout)
            self.assertNotIn("local-live-batch-", report)
            self.assertNotIn("127.0.0.1", report)
            self.assertNotIn("/v1", report)

    def test_live_mode_has_small_attempt_safety_cap(self):
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/provider-live-batch-drill.py",
                "--include-live",
                "--attempts",
                "4",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("capped at 3 attempts", completed.stderr)


if __name__ == "__main__":
    unittest.main()

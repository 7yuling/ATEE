import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProviderBudgetDrillScriptTests(unittest.TestCase):
    def test_budget_drill_stops_remote_calls_after_budget_is_exhausted(self):
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/provider-budget-drill.py",
                "--attempts",
                "5",
                "--budget-cents",
                "2",
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
        self.assertEqual(payload["attempts"], 5)
        self.assertEqual(payload["budget_cents"], 2)
        self.assertEqual(payload["provider_calls"], 2)
        self.assertEqual(payload["reason_counts"]["provider_json_decision"], 2)
        self.assertEqual(payload["reason_counts"]["llm_budget_exhausted"], 3)
        self.assertEqual(payload["budget"]["daily_remaining_cents"], 0)
        self.assertTrue(payload["api_key_configured"])

    def test_budget_drill_report_is_sanitized(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "budget-drill.md"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/provider-budget-drill.py",
                    "--attempts",
                    "4",
                    "--budget-cents",
                    "1",
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
            self.assertIn("ATEE Provider Budget Drill Report", report)
            self.assertIn("llm_budget_exhausted", report)
            self.assertNotIn("local-drill-", completed.stdout)
            self.assertNotIn("local-drill-", report)
            self.assertNotIn("127.0.0.1", report)
            self.assertNotIn("/v1", report)


if __name__ == "__main__":
    unittest.main()

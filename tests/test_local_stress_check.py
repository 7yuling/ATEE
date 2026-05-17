import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LocalStressCheckScriptTests(unittest.TestCase):
    def test_request_mode_reports_expected_count(self):
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/local-stress-check.py",
                "--requests",
                "24",
                "--workers",
                "3",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        summary = json.loads(completed.stdout)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["mode"], "requests")
        self.assertEqual(summary["requests"], 24)
        self.assertEqual(summary["target_requests"], 24)
        self.assertGreater(summary["throughput_rps"], 0)

    def test_duration_mode_writes_sanitized_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "local-stress-report.md"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/local-stress-check.py",
                    "--duration-seconds",
                    "0.2",
                    "--max-requests",
                    "24",
                    "--workers",
                    "3",
                    "--target-rps",
                    "20",
                    "--report",
                    str(report_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "duration")
            self.assertEqual(summary["max_requests"], 24)
            self.assertEqual(summary["target_rps"], 20.0)
            self.assertGreater(summary["requests"], 0)
            self.assertEqual(summary["report_path"], str(report_path))

            report = report_path.read_text(encoding="utf-8")
            self.assertIn("ATEE Local Stress Report", report)
            self.assertIn("Target rps: 20.0", report)
            self.assertIn("Security Notes", report)
            self.assertNotIn("sk-", report)
            self.assertNotIn("config/secrets", report)
            self.assertNotIn("proxy.example", report)


if __name__ == "__main__":
    unittest.main()

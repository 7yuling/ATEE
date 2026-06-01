import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BackupRestoreDrillScriptTests(unittest.TestCase):
    def test_backup_restore_drill_restores_state_and_excludes_secrets(self):
        completed = subprocess.run(
            [sys.executable, "scripts/backup-restore-drill.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["archive"]["contains_config"])
        self.assertTrue(payload["archive"]["contains_sqlite"])
        self.assertTrue(payload["archive"]["contains_logs"])
        self.assertFalse(payload["archive"]["contains_secrets"])
        self.assertFalse(payload["archive"]["contains_excluded_marker"])
        self.assertEqual(payload["restore"]["persisted_records"], payload["source"]["persisted_records"])
        self.assertEqual(payload["restore"]["pending_appeals"], payload["source"]["pending_appeals"])
        self.assertTrue(payload["restore"]["target_placeholder_secret_preserved"])
        self.assertFalse(payload["restore"]["source_secret_restored"])

    def test_backup_restore_drill_report_is_sanitized(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "backup-restore.md"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/backup-restore-drill.py",
                    "--report",
                    str(report_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            payload = json.loads(completed.stdout)
            report = report_path.read_text(encoding="utf-8")
            self.assertEqual(payload["report_path"], str(report_path))
            self.assertIn("ATEE Backup Restore Drill Report", report)
            self.assertIn("config/secrets is intentionally excluded", report)
            self.assertNotIn("excluded-backup-drill-marker", completed.stdout)
            self.assertNotIn("excluded-backup-drill-marker", report)
            self.assertNotIn(str(Path(temp_dir)), report)
            self.assertNotIn("source-install", report)
            self.assertNotIn("target-install", report)

    def test_backup_restore_drill_has_python_fallback_for_linux(self):
        env = os.environ.copy()
        env["PATH"] = ""
        completed = subprocess.run(
            [sys.executable, "scripts/backup-restore-drill.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=env,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["archive"]["contains_config"])
        self.assertTrue(payload["archive"]["contains_sqlite"])
        self.assertTrue(payload["archive"]["contains_logs"])
        self.assertFalse(payload["archive"]["contains_secrets"])
        self.assertTrue(payload["restore"]["target_placeholder_secret_preserved"])


if __name__ == "__main__":
    unittest.main()

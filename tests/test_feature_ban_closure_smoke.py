import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FeatureBanClosureSmokeScriptTests(unittest.TestCase):
    def test_feature_ban_closure_smoke_covers_ban_lifecycle_with_sanitized_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "feature-ban-closure.md"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/feature-ban-closure-smoke.py",
                    "--report",
                    str(report_path),
                ],
                cwd=ROOT,
                check=True,
                text=True,
                capture_output=True,
            )

            payload = json.loads(completed.stdout)
            checks = {check["name"]: check for check in payload["checks"]}
            report = report_path.read_text(encoding="utf-8")

            self.assertTrue(payload["ok"])
            self.assertTrue(checks["site_feature_ban_created"]["ok"])
            self.assertTrue(checks["site_feature_access_blocks_all_users"]["ok"])
            self.assertEqual(checks["site_feature_appeal_does_not_auto_unban"]["reason"], "action_is_not_user_feature_ban")
            self.assertTrue(checks["site_feature_admin_revoke_restores_access"]["ok"])
            self.assertTrue(checks["manual_async_review_records_user_feature_ban"]["ok"])
            self.assertEqual(checks["user_feature_ban_blocks_feature_access"]["reason"], "active_feature_ban")
            self.assertEqual(checks["user_feature_appeal_auto_unbans"]["reason"], "feature_ban_revoked")
            self.assertFalse(payload["security"]["raw_prompt_stored"])
            self.assertFalse(payload["security"]["raw_request_body_stored"])

            for leaked in [
                "manual-feature-ban-smoke-user",
                "manual review candidate",
                "sk-",
                "provider.example",
                "Author" + "ization",
            ]:
                self.assertNotIn(leaked, report)


if __name__ == "__main__":
    unittest.main()

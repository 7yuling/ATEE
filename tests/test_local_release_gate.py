import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LocalReleaseGateTests(unittest.TestCase):
    def test_quick_gate_runs_sanitized_release_checks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "local-release-gate.md"
            env = os.environ.copy()
            env.setdefault("ATEE_LLM_API_KEY", "atee-release-gate-placeholder-key")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/local-release-gate.py",
                    "--quick",
                    "--report",
                    str(report_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
                env=env,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            payload = json.loads(completed.stdout)
            report = report_path.read_text(encoding="utf-8")
            steps = {step["name"]: step for step in payload["steps"]}

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["mode"], "quick")
            for name in (
                "config_preflight",
                "python_compile",
                "unit_tests",
                "agent_ai_full_flow_smoke",
                "async_ai_review_worker_smoke",
                "sensitive_scan",
            ):
                self.assertIn(name, steps)
                self.assertTrue(steps[name]["ok"], name)
            self.assertGreaterEqual(steps["unit_tests"].get("tests_ran", 0), 1)
            self.assertEqual(steps["sensitive_scan"]["findings_count"], 0)
            self.assertIn("ATEE Local Release Gate Report", report)
            for leaked in [
                ("local" + "-agent-flow-"),
                ("async" + "-worker-key-"),
                ("budget" + "-drill-secret"),
                ("local" + "-live-batch-"),
                ("127" + ".0.0.1:" + "10808"),
                ("api" + ".deepseek" + ".com"),
                ("deepseek" + "_api_key"),
                "sk-",
            ]:
                self.assertNotIn(leaked, completed.stdout)
                self.assertNotIn(leaked, report)


if __name__ == "__main__":
    unittest.main()

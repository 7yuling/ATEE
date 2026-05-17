import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AgentAIFullFlowSmokeScriptTests(unittest.TestCase):
    def test_fake_full_flow_smoke_is_sanitized_and_uses_one_provider_call(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "agent-flow.md"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/agent-ai-full-flow-smoke.py",
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
            step_status = {step["name"]: step["ok"] for step in payload["steps"]}

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["mode"], "fake")
            self.assertFalse(payload["live_used"])
            self.assertEqual(payload["final"]["provider_calls"], 1)
            self.assertEqual(payload["final"]["budget"]["daily_spend_cents"], 1)
            self.assertFalse(payload["final"]["circuit"]["open"])
            self.assertTrue(step_status["low_risk_read_skip"])
            self.assertTrue(step_status["sync_agent_ai_review"])
            self.assertTrue(step_status["fast_path_attack_block"])
            self.assertTrue(step_status["appeal_submit"])
            self.assertTrue(step_status["admin_appeal_review"])
            self.assertTrue(step_status["ledger_recent"])
            self.assertIn("ATEE Agent AI Full-Flow Smoke Report", report)
            for leaked in ["local-agent-flow-", "127.0.0.1", "/v1", "flow.sqlite3"]:
                self.assertNotIn(leaked, completed.stdout)
                self.assertNotIn(leaked, report)

    def test_live_mode_requires_remote_provider_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text('{"llm_mode": "mock"}\n', encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/agent-ai-full-flow-smoke.py",
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

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProviderFaultDrillScriptTests(unittest.TestCase):
    def test_bad_proxy_drill_is_sanitized_and_does_not_require_live_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config" / "config.json"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                json.dumps(
                    {
                        "llm_mode": "openai_compatible",
                        "llm_provider": "drill-provider",
                        "llm_model": "drill-model",
                        "llm_api_base": "https://provider.example/v1",
                        "llm_api_key_env": "ATEE_PROVIDER_DRILL_TEST_KEY",
                        "remote_soft_timeout_ms": 100,
                        "remote_hard_timeout_ms": 1000,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            env = dict(os.environ)
            env["ATEE_PROVIDER_DRILL_TEST_KEY"] = "test-secret-value"

            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/provider-fault-drill.py",
                    "--config",
                    str(config_path),
                    "--bad-proxy-url",
                    "http://127.0.0.1:9",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotIn("test-secret-value", completed.stdout)
            payload = json.loads(completed.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["bad_proxy"]["ok"])
            self.assertEqual(payload["bad_proxy"]["fourth_request_reason"], "llm_circuit_open")
            self.assertTrue(payload["live"]["skipped"])

    def test_report_output_is_markdown_and_sanitized(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "config" / "config.json"
            report_path = temp_path / "reports" / "provider-drill.md"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                json.dumps(
                    {
                        "llm_mode": "openai_compatible",
                        "llm_provider": "drill-provider",
                        "llm_model": "drill-model",
                        "llm_api_base": "https://provider.example/v1",
                        "llm_api_key_env": "ATEE_PROVIDER_DRILL_TEST_KEY",
                        "remote_soft_timeout_ms": 100,
                        "remote_hard_timeout_ms": 1000,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            env = dict(os.environ)
            env["ATEE_PROVIDER_DRILL_TEST_KEY"] = "test-secret-value"

            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/provider-fault-drill.py",
                    "--config",
                    str(config_path),
                    "--bad-proxy-url",
                    "http://127.0.0.1:9",
                    "--report",
                    str(report_path),
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            report = report_path.read_text(encoding="utf-8")
            self.assertEqual(payload["report_path"], str(report_path))
            self.assertIn("# ATEE Provider Fault Drill Report", report)
            self.assertIn("llm_circuit_open", report)
            self.assertNotIn("test-secret-value", report)
            self.assertNotIn("127.0.0.1:9", report)
            self.assertNotIn("provider.example", report)


if __name__ == "__main__":
    unittest.main()

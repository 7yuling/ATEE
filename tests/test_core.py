import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "core-service"))

from atee_core.config import AdminConfig
from atee_core.config import ConfigStore
from atee_core.core import CoreService
from atee_core.ip_resolver import TrustedRealIpResolver
from atee_core.models import RequestContext
from atee_core.prompt_packet import PromptPacketCompiler
from atee_core.tool_gateway import ToolGateway


class AteeCoreTests(unittest.TestCase):
    def test_unconfigured_proxy_disables_ip_ban(self):
        resolver = TrustedRealIpResolver([])
        result = resolver.resolve({"X-Forwarded-For": "1.2.3.4"}, "10.0.0.5")
        self.assertEqual(result["client_ip"], "10.0.0.5")
        self.assertFalse(result["can_ip_ban"])
        self.assertEqual(result["ip_trust_status"], "untrusted_proxy_unknown")

    def test_trusted_proxy_uses_header_priority(self):
        resolver = TrustedRealIpResolver(["10.0.0.0/8"])
        result = resolver.resolve(
            {
                "CF-Connecting-IP": "203.0.113.10",
                "X-Forwarded-For": "198.51.100.1, 198.51.100.2",
            },
            "10.1.2.3",
        )
        self.assertEqual(result["client_ip"], "203.0.113.10")
        self.assertTrue(result["can_ip_ban"])

    def test_fast_path_blocks_xss_before_agent_route(self):
        core = CoreService()
        result = core.check(
            {
                "method": "POST",
                "path": "/comment",
                "event_type": "comment_create",
                "body": {"text": "<script>alert(1)</script>"},
                "remote_addr": "198.51.100.8",
            }
        )
        self.assertEqual(result["route"]["route"], "fast_path_block")
        self.assertEqual(result["fast_path"]["rule_id"], "FP_XSS_001")
        self.assertFalse(result["fast_path"]["llm_called"])

    def test_prompt_packet_redacts_sensitive_fields(self):
        ctx = RequestContext(
            method="POST",
            path="/login",
            headers={"Authorization": "Bearer secret", "X-Trace": "ok"},
            body={"password": "secret", "name": "alice"},
            remote_addr="203.0.113.4",
            user_id="alice",
        )
        packet = PromptPacketCompiler().compile(
            ctx,
            {"client_ip": "203.0.113.4"},
            {"action": "pass", "rule_id": None},
            {"route": "sync_agent", "event_type": "login"},
        )
        self.assertNotIn("Authorization", packet["headers"])
        self.assertIn("[REDACTED]", packet["body_summary"]["preview"])
        self.assertIsNotNone(packet["user_hash"])

    def test_prompt_packet_redacts_chinese_sensitive_fields(self):
        ctx = RequestContext(
            method="POST",
            path="/register",
            headers={"X-Trace": "ok"},
            body={"用户密码": "secret", "手机号": "13800138000", "昵称": "小明"},
            remote_addr="203.0.113.4",
            user_id="小明",
        )
        packet = PromptPacketCompiler().compile(
            ctx,
            {"client_ip": "203.0.113.4"},
            {"action": "pass", "rule_id": None},
            {"route": "sync_agent", "event_type": "register"},
        )
        preview = packet["body_summary"]["preview"]
        self.assertIn("[REDACTED]", preview)
        self.assertNotIn("secret", preview)
        self.assertNotIn("13800138000", preview)
        self.assertIn("标准敏感字段", packet["privacy_note"])

    def test_runtime_status_has_chinese_display(self):
        core = CoreService()
        status = core.runtime_status()
        self.assertEqual(status["display"]["locale"], "zh-CN")
        self.assertEqual(status["display"]["runtime_mode_zh"], "观察模式")

    def test_onboarding_steps_are_chinese(self):
        core = CoreService()
        guide = core.onboarding_steps()
        self.assertEqual(guide["locale"], "zh-CN")
        self.assertGreaterEqual(len(guide["steps"]), 6)
        self.assertIn("真实 IP", " ".join(step["title_zh"] for step in guide["steps"]))

    def test_tool_gateway_rejects_ip_ban_without_trusted_real_ip(self):
        gateway = ToolGateway()
        decision = {
            "selected_action": "ip_ban_short",
            "duration_seconds": 60,
            "scores": {
                "final_confidence": 0.95,
                "evidence_score": 0.90,
                "behavior_score": 0.80,
            },
        }
        result = gateway.validate(decision, {"can_ip_ban": False}, AdminConfig(runtime_mode="auto"))
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "ip_ban_requires_trusted_real_ip_and_admin_enablement")

    def test_observe_mode_records_would_have_action(self):
        core = CoreService(AdminConfig(runtime_mode="observe"))
        result = core.check(
            {
                "method": "POST",
                "path": "/login",
                "event_type": "login",
                "body": {"text": "normal login"},
                "agent_decision": {"selected_action": "challenge", "ai_confidence": 0.95},
            }
        )
        self.assertEqual(result["tool_gateway"]["effective_action"], "would_have_action")
        self.assertFalse(result["action_result"]["executed"])

    def test_appeal_duplicate_and_rate_limit(self):
        core = CoreService()
        first = core.appeal({"punishment_id": "p1", "reason": "please review"})
        second = core.appeal({"punishment_id": "p1", "reason": "again"})
        self.assertEqual(first["status"], 202)
        self.assertEqual(second["status"], 429)
        self.assertEqual(len(core.appeals.appeals), 1)

    def test_config_store_creates_and_loads_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            store = ConfigStore(config_path)
            config = store.load()
            self.assertTrue(config_path.exists())
            config.runtime_mode = "auto"
            config.trusted_proxy_cidrs = ["10.0.0.0/8"]
            store.save(config)
            loaded = store.load()
            self.assertEqual(loaded.runtime_mode, "auto")
            self.assertEqual(loaded.trusted_proxy_cidrs, ["10.0.0.0/8"])

    def test_core_persists_runtime_mode_and_pause(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            core = CoreService(config_path=config_path)
            core.set_mode({"mode": "auto"})
            core.pause_agent({"paused": True})

            restarted = CoreService(config_path=config_path)
            status = restarted.runtime_status()
            self.assertEqual(status["runtime_mode"], "auto")
            self.assertTrue(status["agent_paused"])
            self.assertEqual(status["config"]["config_path"], str(config_path))

    def test_update_config_rebuilds_real_ip_resolver(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(config_path=Path(temp_dir) / "config.json")
            result = core.update_config({"trusted_proxy_cidrs": ["10.0.0.0/8"], "auto_ip_ban_enabled": True})
            self.assertEqual(result["changed"]["trusted_proxy_cidrs"], ["10.0.0.0/8"])
            check = core.check(
                {
                    "method": "POST",
                    "path": "/login",
                    "event_type": "login",
                    "remote_addr": "10.1.2.3",
                    "headers": {"CF-Connecting-IP": "203.0.113.8"},
                }
            )
            self.assertEqual(check["real_ip"]["client_ip"], "203.0.113.8")


if __name__ == "__main__":
    unittest.main()

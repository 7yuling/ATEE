import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "core-service"))

from atee_core.config import AdminConfig
from atee_core.config import ConfigStore
from atee_core.core import CoreService
from atee_core.ip_resolver import TrustedRealIpResolver
from atee_core.llm_gateway import RemoteLLMGateway
from atee_core.models import RequestContext
from atee_core.prompt_packet import PromptPacketCompiler
from atee_core.secret_store import load_secret_file
from atee_core.secret_store import write_encrypted_secret_file
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
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(config_path=Path(temp_dir) / "config" / "config.json")
            first = core.appeal({"punishment_id": "p1", "reason": "please review"})
            second = core.appeal({"punishment_id": "p1", "reason": "again"})
            self.assertEqual(first["status"], 202)
            self.assertEqual(second["status"], 429)
            self.assertEqual(len(core.appeals.appeals), 1)

    def test_appeals_survive_core_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config" / "config.json"
            core = CoreService(config_path=config_path)
            first = core.appeal({"punishment_id": "persist-p1", "reason": "please review"})

            self.assertEqual(first["status"], 202)
            restarted = CoreService(config_path=config_path)
            self.assertEqual(restarted.runtime_status()["pending_appeals"], 1)
            duplicate = restarted.appeal({"punishment_id": "persist-p1", "reason": "again"})
            self.assertEqual(duplicate["status"], 200)
            self.assertEqual(len(restarted.appeals.appeals), 1)

    def test_admin_can_review_pending_appeal_and_persist_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config" / "config.json"
            core = CoreService(config_path=config_path)
            core.appeal({"punishment_id": "review-p1", "reason": "please review"})

            pending = core.admin_appeals(status="pending")
            reviewed = core.review_appeal(
                {
                    "punishment_id": "review-p1",
                    "resolution": "approved",
                    "admin_note": "同意复核，撤销请在动作页处理。",
                }
            )
            restarted = CoreService(config_path=config_path)
            approved = restarted.admin_appeals(status="approved")

            self.assertEqual(pending["count"], 1)
            self.assertTrue(reviewed["ok"])
            self.assertEqual(reviewed["appeal"]["status"], "approved")
            self.assertEqual(restarted.runtime_status()["pending_appeals"], 0)
            self.assertEqual(approved["count"], 1)
            self.assertEqual(approved["appeals"][0]["punishment_id"], "review-p1")

    def test_actions_survive_core_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config" / "config.json"
            config = AdminConfig(runtime_mode="auto")
            core = CoreService(config=config, config_path=config_path)
            result = core.check(
                {
                    "method": "POST",
                    "path": "/comment",
                    "event_type": "comment_create",
                    "body": {"text": "<script>alert(1)</script>"},
                }
            )

            self.assertTrue(result["action_result"]["executed"])
            self.assertEqual(len(core.executor.actions), 1)
            restarted = CoreService(config=config, config_path=config_path)
            self.assertEqual(restarted.runtime_status()["actions_executed"], 1)
            self.assertEqual(restarted.executor.actions[0]["action"], "challenge")

    def test_admin_can_list_revoke_and_cleanup_actions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config" / "config.json"
            core = CoreService(config=AdminConfig(runtime_mode="auto"), config_path=config_path)
            executed = core.check(
                {
                    "method": "POST",
                    "path": "/comment",
                    "event_type": "comment_create",
                    "body": {"text": "<script>alert(1)</script>"},
                }
            )
            action_id = executed["action_result"]["record"]["id"]

            active = core.admin_actions(status="active")
            revoked = core.revoke_action({"action_id": action_id, "reason": "管理员复核撤销"})
            revoked_list = core.admin_actions(status="revoked")
            expired_record = core.executor.execute(
                {
                    "duration_seconds": -1,
                    "target_scope": {"type": "request"},
                },
                {"executed": True, "effective_action": "challenge"},
            )
            cleanup = core.cleanup_expired_actions()
            expired = core.admin_actions(status="expired")

            self.assertEqual(active["count"], 1)
            self.assertTrue(revoked["ok"])
            self.assertEqual(revoked["action"]["status"], "revoked")
            self.assertEqual(revoked_list["count"], 1)
            self.assertTrue(expired_record["executed"])
            self.assertEqual(cleanup["expired_marked"], 1)
            self.assertEqual(expired["count"], 1)

    def test_config_store_creates_and_loads_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            store = ConfigStore(config_path)
            config = store.load()
            self.assertTrue(config_path.exists())
            config.runtime_mode = "auto"
            config.trusted_proxy_cidrs = ["10.0.0.0/8"]
            config.llm_api_base = "https://provider.example/v1"
            config.llm_api_key_file = "config/secrets/provider.dpapi.json"
            config.llm_proxy_url = "http://proxy.example:1080"
            config.admin_auth_enabled = True
            config.admin_token_file = "config/secrets/admin-token.txt"
            store.save(config)
            loaded = store.load()
            self.assertEqual(loaded.runtime_mode, "auto")
            self.assertEqual(loaded.trusted_proxy_cidrs, ["10.0.0.0/8"])
            self.assertEqual(loaded.llm_api_key_file, "config/secrets/provider.dpapi.json")
            self.assertEqual(loaded.llm_proxy_url, "http://proxy.example:1080")
            self.assertTrue(loaded.admin_auth_enabled)
            self.assertEqual(loaded.admin_token_file, "config/secrets/admin-token.txt")

            public = store.public_payload(loaded)
            self.assertNotIn("llm_api_base", public)
            self.assertNotIn("llm_api_key_file", public)
            self.assertNotIn("llm_proxy_url", public)
            self.assertNotIn("admin_token_file", public)
            self.assertTrue(public["llm_api_base_configured"])
            self.assertTrue(public["llm_api_key_file_configured"])
            self.assertFalse(public["llm_api_key_env_configured"])
            self.assertTrue(public["llm_proxy_configured"])
            self.assertTrue(public["admin_token_file_configured"])

    def test_core_resolves_relative_secret_files_from_project_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_path = project_root / "config" / "config.json"
            key_file = project_root / "config" / "secrets" / "provider.key"
            key_file.parent.mkdir(parents=True)
            key_file.write_text("test-secret", encoding="utf-8")

            core = CoreService(
                config=AdminConfig(
                    llm_mode="openai_compatible",
                    llm_provider="deepseek",
                    llm_model="deepseek-v4-pro",
                    llm_api_base="https://provider.example/v1",
                    llm_api_key_file="config/secrets/provider.key",
                ),
                config_path=config_path,
            )

            self.assertTrue(core.runtime_status()["llm_gateway"]["api_key_configured"])

    def test_admin_auth_uses_env_or_secret_file_without_exposing_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_name = "ATEE_ADMIN_AUTH_TEST_TOKEN"
            os.environ[env_name] = "test-admin-token"
            try:
                core = CoreService(
                    config=AdminConfig(admin_auth_enabled=True, admin_token_env=env_name),
                    config_path=Path(temp_dir) / "config" / "config.json",
                )
                self.assertTrue(core.admin_authorized({"Authorization": "Bearer test-admin-token"}))
                self.assertTrue(core.admin_authorized({"X-ATEE-Admin-Token": "test-admin-token"}))
                self.assertFalse(core.admin_authorized({"Authorization": "Bearer wrong"}))
                status = core.runtime_status()["admin_auth"]
                self.assertTrue(status["enabled"])
                self.assertTrue(status["token_configured"])
                self.assertNotIn("test-admin-token", json.dumps(status))
            finally:
                os.environ.pop(env_name, None)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            token_file = root / "config" / "secrets" / "admin-token.txt"
            token_file.parent.mkdir(parents=True)
            token_file.write_text("file-admin-token\n", encoding="utf-8")
            core = CoreService(
                config=AdminConfig(
                    admin_auth_enabled=True,
                    admin_token_env="ATEE_MISSING_ADMIN_TEST_TOKEN",
                    admin_token_file="config/secrets/admin-token.txt",
                ),
                config_path=root / "config" / "config.json",
            )
            self.assertTrue(core.admin_authorized({"Authorization": "Bearer file-admin-token"}))
            self.assertFalse(core.admin_authorized({}))

    def test_admin_mutations_record_actor_summary_without_tokens(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config" / "config.json"
            core = CoreService(config_path=config_path)
            actor = core.admin_actor_from_headers(
                {
                    "X-ATEE-Admin-Id": "ops.alice@example.com",
                    "Authorization": "Bearer should-not-be-recorded",
                    "X-Real-IP": "203.0.113.77",
                },
                remote_addr="127.0.0.1",
            )
            core.update_config({"runtime_mode": "degraded"}, actor=actor)
            core.pause_agent({"paused": True}, actor=actor)

            summaries = "\n".join(record["summary"] for record in core.ledger_recent(limit=5)["records"])

            self.assertIn("admin_actor_id=ops.alice@example.com", summaries)
            self.assertIn("admin_actor_hash=sha256:", summaries)
            self.assertIn("admin_source_hash=sha256:", summaries)
            self.assertIn("changed_keys=runtime_mode", summaries)
            self.assertIn("agent_paused=True", summaries)
            self.assertNotIn("should-not-be-recorded", summaries)
            self.assertNotIn("203.0.113.77", summaries)

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

    def test_sqlite_ledger_persists_agent_decisions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config" / "config.json"
            core = CoreService(config_path=config_path)
            result = core.check(
                {
                    "method": "POST",
                    "path": "/login",
                    "event_type": "login",
                    "body": {"text": "normal login"},
                }
            )

            self.assertEqual(result["ledger_record"]["event_type"], "agent_decision")
            status = core.runtime_status()["ledger"]
            self.assertTrue(status["sqlite_enabled"])
            self.assertEqual(status["persisted_records"], 1)
            self.assertTrue((Path(temp_dir) / "data" / "atee_ledger.sqlite3").exists())

    def test_sqlite_ledger_does_not_persist_low_risk_skip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(config_path=Path(temp_dir) / "config" / "config.json")
            result = core.check({"method": "GET", "path": "/public"})

            self.assertEqual(result["route"]["route"], "skip")
            status = core.runtime_status()["ledger"]
            self.assertEqual(status["aggregates"], 1)
            self.assertEqual(status["persisted_records"], 0)

    def test_ledger_recent_survives_core_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config" / "config.json"
            core = CoreService(config_path=config_path)
            core.check(
                {
                    "method": "POST",
                    "path": "/comment",
                    "event_type": "comment_create",
                    "body": {"text": "normal comment"},
                }
            )

            restarted = CoreService(config_path=config_path)
            recent = restarted.ledger_recent(limit=5)
            self.assertTrue(recent["ok"])
            self.assertEqual(recent["status"]["persisted_records"], 1)
            self.assertEqual(recent["records"][0]["event_type"], "agent_decision")
            self.assertEqual(recent["records"][0]["endpoint_type"], "comment_create")

    def test_update_config_rebuilds_real_ip_resolver(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(config_path=Path(temp_dir) / "config.json")
            result = core.update_config(
                {
                    "runtime_mode": "degraded",
                    "trusted_proxy_cidrs": ["10.0.0.0/8"],
                    "auto_ip_ban_enabled": True,
                    "agent_paused": True,
                    "locale": "zh-CN",
                    "appeal_paths": ["/appeal", "/security/appeal"],
                    "llm_api_base": "https://provider.example/v1",
                }
            )
            self.assertEqual(result["changed"]["runtime_mode"], "degraded")
            self.assertEqual(result["changed"]["locale"], "zh-CN")
            self.assertTrue(result["changed"]["agent_paused"])
            self.assertEqual(result["changed"]["appeal_paths"], ("/appeal", "/security/appeal"))
            self.assertNotIn("llm_api_base", result["changed"])
            self.assertTrue(result["changed"]["llm_api_base_configured"])
            self.assertEqual(core.runtime_status()["runtime_mode"], "degraded")
            self.assertTrue(core.runtime_status()["agent_paused"])
            self.assertNotIn("llm_api_base", core.runtime_status()["config"])
            self.assertTrue(core.runtime_status()["config"]["llm_api_base_configured"])
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

    def test_update_config_stores_api_key_value_only_in_runtime_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_name = "ATEE_TEST_RUNTIME_ONLY_API_KEY"
            os.environ.pop(env_name, None)
            try:
                config_path = Path(temp_dir) / "config.json"
                core = CoreService(config_path=config_path)
                result = core.update_config(
                    {
                        "llm_api_key_env": env_name,
                        "llm_api_key_value": "test-runtime-key",
                    }
                )

                self.assertEqual(os.environ.get(env_name), "test-runtime-key")
                self.assertTrue(result["changed"]["llm_api_key_env_configured"])
                self.assertNotIn("llm_api_key_value", json.dumps(result, ensure_ascii=False))
                self.assertTrue(core.runtime_status()["config"]["llm_api_key_env_configured"])
                persisted = config_path.read_text(encoding="utf-8")
                self.assertIn(env_name, persisted)
                self.assertNotIn("test-runtime-key", persisted)
                self.assertNotIn("llm_api_key_value", persisted)
            finally:
                os.environ.pop(env_name, None)

    def test_mock_llm_gateway_allows_normal_request(self):
        gateway = RemoteLLMGateway(AdminConfig())
        result = gateway.review(
            {"body_summary": {"preview": "普通登录", "signals": []}, "endpoint_type": "login"},
            {"route": "sync_agent", "event_type": "login"},
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["llm_called"])
        self.assertEqual(result["agent_decision"]["selected_action"], "allow")
        self.assertFalse(result["raw_prompt_stored"])

    def test_core_uses_llm_gateway_for_sync_request(self):
        core = CoreService()
        result = core.check(
            {
                "method": "POST",
                "path": "/login",
                "event_type": "login",
                "body": {"text": "普通登录"},
            }
        )
        self.assertIsNotNone(result["llm_gateway"])
        self.assertTrue(result["llm_gateway"]["llm_called"])
        self.assertEqual(result["decision"]["selected_action"], "allow")

    def test_mock_llm_gateway_flags_chinese_spam_as_rule_hint(self):
        core = CoreService()
        result = core.check(
            {
                "method": "POST",
                "path": "/comment",
                "event_type": "comment_create",
                "body": {"text": "广告 刷屏 诈骗"},
            }
        )
        self.assertEqual(result["route"]["route"], "async_agent")
        self.assertEqual(result["decision"]["selected_action"], "rule_hint")
        self.assertEqual(result["llm_gateway"]["reason"], "mock_suspicious_content")

    def test_openai_compatible_gateway_requires_key_without_leaking_secret(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_key_file = Path(temp_dir) / "missing.key"
            gateway = RemoteLLMGateway(
                AdminConfig(
                    llm_mode="openai_compatible",
                    llm_provider="deepseek",
                    llm_model="deepseek-v4-pro",
                    llm_api_base="https://provider.example/v1",
                    llm_api_key_file=str(missing_key_file),
                )
            )

            result = gateway.review({"body_summary": {"preview": "hello"}}, {"route": "sync_agent", "event_type": "login"})
            self.assertFalse(result["ok"])
            self.assertFalse(result["llm_called"])
            self.assertEqual(result["reason"], "missing_api_key")
            self.assertTrue(gateway.status()["api_base_configured"])
            self.assertFalse(gateway.status()["api_key_configured"])

    def test_openai_compatible_gateway_parses_provider_json_without_leaking_key(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps({"selected_action": "challenge", "ai_confidence": 0.81})
                                }
                            }
                        ]
                    }
                ).encode("utf-8")

        with tempfile.TemporaryDirectory() as temp_dir:
            dummy_key = "test-secret-value"
            key_file = Path(temp_dir) / "provider.key"
            key_file.write_text(dummy_key, encoding="utf-8")
            captured: dict[str, object] = {}

            def fake_urlopen(request, timeout):
                captured["url"] = request.full_url
                captured["headers"] = dict(request.header_items())
                captured["body"] = json.loads(request.data.decode("utf-8"))
                captured["timeout"] = timeout
                return FakeResponse()

            gateway = RemoteLLMGateway(
                AdminConfig(
                    llm_mode="openai_compatible",
                    llm_provider="deepseek",
                    llm_model="deepseek-v4-pro",
                    llm_api_base="https://provider.example/v1",
                    llm_api_key_file=str(key_file),
                )
            )
            with patch("urllib.request.urlopen", fake_urlopen):
                result = gateway.review(
                    {"method": "POST", "path": "/login", "body_summary": {"preview": "hello", "signals": []}},
                    {"route": "sync_agent", "event_type": "login"},
                )
                public_text = json.dumps(
                    {"result": result, "status": gateway.status(), "test": gateway.test_connection()},
                    ensure_ascii=False,
                )

            self.assertTrue(result["ok"])
            self.assertEqual(captured["url"], "https://provider.example/v1/chat/completions")
            self.assertEqual(captured["body"]["model"], "deepseek-v4-pro")
            self.assertEqual(result["agent_decision"]["selected_action"], "challenge")
            self.assertEqual(result["agent_decision"]["ai_confidence"], 0.81)
            self.assertNotIn(dummy_key, public_text)

    def test_openai_compatible_gateway_uses_configured_proxy(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps({"selected_action": "allow", "ai_confidence": 0.61})
                                }
                            }
                        ]
                    }
                ).encode("utf-8")

        class FakeOpener:
            def open(self, request, timeout):
                captured["url"] = request.full_url
                captured["timeout"] = timeout
                return FakeResponse()

        with tempfile.TemporaryDirectory() as temp_dir:
            key_file = Path(temp_dir) / "provider.key"
            key_file.write_text("test-secret-value", encoding="utf-8")
            captured: dict[str, object] = {}

            def fake_build_opener(*handlers):
                captured["handler_count"] = len(handlers)
                return FakeOpener()

            gateway = RemoteLLMGateway(
                AdminConfig(
                    llm_mode="openai_compatible",
                    llm_provider="deepseek",
                    llm_model="deepseek-v4-pro",
                    llm_api_base="https://provider.example/v1",
                    llm_api_key_file=str(key_file),
                    llm_proxy_url="http://proxy.example:1080",
                )
            )
            with patch("urllib.request.build_opener", fake_build_opener):
                result = gateway.review(
                    {"method": "POST", "path": "/login", "body_summary": {"preview": "hello", "signals": []}},
                    {"route": "sync_agent", "event_type": "login"},
                )

            self.assertTrue(result["ok"])
            self.assertEqual(captured["url"], "https://provider.example/v1/chat/completions")
            self.assertEqual(captured["handler_count"], 1)
            self.assertTrue(gateway.status()["proxy_configured"])

    def test_openai_compatible_gateway_enforces_daily_budget(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps({"selected_action": "allow", "ai_confidence": 0.61})
                                }
                            }
                        ]
                    }
                ).encode("utf-8")

        with tempfile.TemporaryDirectory() as temp_dir:
            key_file = Path(temp_dir) / "provider.key"
            key_file.write_text("test-secret", encoding="utf-8")
            captured = {"calls": 0}

            def fake_urlopen(request, timeout):
                captured["calls"] += 1
                return FakeResponse()

            gateway = RemoteLLMGateway(
                AdminConfig(
                    llm_mode="openai_compatible",
                    llm_provider="deepseek",
                    llm_model="deepseek-v4-pro",
                    llm_api_base="https://provider.example/v1",
                    llm_api_key_file=str(key_file),
                    llm_daily_budget_cents=1,
                )
            )
            with patch("urllib.request.urlopen", fake_urlopen):
                first = gateway.review(
                    {"method": "POST", "path": "/login", "body_summary": {"preview": "hello", "signals": []}},
                    {"route": "sync_agent", "event_type": "login"},
                )
                second = gateway.review(
                    {"method": "POST", "path": "/login", "body_summary": {"preview": "hello", "signals": []}},
                    {"route": "sync_agent", "event_type": "login"},
                )

            budget = gateway.status()["budget"]
            self.assertTrue(first["ok"])
            self.assertFalse(second["ok"])
            self.assertEqual(second["reason"], "llm_budget_exhausted")
            self.assertEqual(captured["calls"], 1)
            self.assertEqual(budget["daily_spend_cents"], 1)
            self.assertEqual(budget["daily_remaining_cents"], 0)

    def test_openai_compatible_gateway_opens_failure_circuit_after_timeouts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            key_file = Path(temp_dir) / "provider.key"
            key_file.write_text("test-secret", encoding="utf-8")
            captured = {"calls": 0}

            def fake_urlopen(request, timeout):
                captured["calls"] += 1
                raise TimeoutError("provider timed out")

            gateway = RemoteLLMGateway(
                AdminConfig(
                    llm_mode="openai_compatible",
                    llm_provider="deepseek",
                    llm_model="deepseek-v4-pro",
                    llm_api_base="https://provider.example/v1",
                    llm_api_key_file=str(key_file),
                )
            )
            with patch("urllib.request.urlopen", fake_urlopen):
                results = [
                    gateway.review(
                        {"method": "POST", "path": "/login", "body_summary": {"preview": "hello", "signals": []}},
                        {"route": "sync_agent", "event_type": "login"},
                    )
                    for _ in range(3)
                ]
                circuit_result = gateway.review(
                    {"method": "POST", "path": "/login", "body_summary": {"preview": "hello", "signals": []}},
                    {"route": "sync_agent", "event_type": "login"},
                )

            self.assertEqual([item["reason"] for item in results], ["provider_timeout"] * 3)
            self.assertEqual(circuit_result["reason"], "llm_circuit_open")
            self.assertEqual(captured["calls"], 3)
            self.assertTrue(gateway.status()["circuit"]["open"])
            self.assertEqual(gateway.status()["circuit"]["consecutive_failures"], 3)

    def test_openai_compatible_gateway_rejects_public_http_base(self):
        gateway = RemoteLLMGateway(
            AdminConfig(
                llm_mode="openai_compatible",
                llm_provider="deepseek",
                llm_model="deepseek-v4-pro",
                llm_api_base="http://provider.example/v1",
                llm_api_key_env="ATEE_MISSING_TEST_KEY",
            )
        )

        result = gateway.review({"body_summary": {"preview": "hello"}}, {"route": "sync_agent", "event_type": "login"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "insecure_api_base_requires_https")

    @unittest.skipUnless(sys.platform == "win32", "DPAPI encryption is Windows-only")
    def test_dpapi_secret_file_round_trips_without_plaintext(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            secret = "test-secret-value"
            encrypted_path = Path(temp_dir) / "provider.dpapi.json"

            write_encrypted_secret_file(secret, encrypted_path)

            stored_text = encrypted_path.read_text(encoding="utf-8")
            self.assertNotIn(secret, stored_text)
            self.assertEqual(load_secret_file(encrypted_path), secret)


if __name__ == "__main__":
    unittest.main()

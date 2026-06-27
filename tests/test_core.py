import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from time import monotonic
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
    def _execute_user_feature_ban(
        self,
        core: CoreService,
        user_id: str = "feature-user",
        feature_scope: str = "comments",
        duration_seconds: int = 3600,
        site_id: int | None = None,
    ) -> dict:
        user_hash = core.packet_compiler._hash(user_id)
        target_scope = {
            "type": "user_feature",
            "user_hash": user_hash,
            "feature": feature_scope,
        }
        if site_id:
            target_scope["site_id"] = site_id
        return core.executor.execute(
            {
                "selected_action": "feature_ban",
                "duration_seconds": duration_seconds,
                "target_scope": target_scope,
            },
            {"executed": True, "effective_action": "feature_ban"},
        )

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

    def test_fast_path_blocks_ssrf_metadata_before_agent_route(self):
        core = CoreService()
        result = core.check(
            {
                "method": "POST",
                "path": "/fetch",
                "body": {"url": "http://169.254.169.254/latest/meta-data/"},
            }
        )
        self.assertEqual(result["route"]["route"], "fast_path_block")
        self.assertEqual(result["fast_path"]["rule_id"], "FP_SSRF_001")

    def test_fast_path_blocks_ssrf_localhost_before_agent_route(self):
        core = CoreService()
        result = core.check(
            {
                "method": "POST",
                "path": "/fetch",
                "body": {"url": "http://127.0.0.1:8787/health"},
            }
        )
        self.assertEqual(result["route"]["route"], "fast_path_block")
        self.assertEqual(result["fast_path"]["rule_id"], "FP_SSRF_001")

    def test_fast_path_blocks_single_extension_upload(self):
        core = CoreService()
        result = core.check(
            {
                "method": "POST",
                "path": "/upload",
                "event_type": "upload",
                "body": {"filename": "shell.php", "content_type": "application/octet-stream"},
            }
        )
        self.assertEqual(result["route"]["route"], "fast_path_block")
        self.assertEqual(result["fast_path"]["rule_id"], "FP_UPLOAD_001")

    def test_fast_path_blocks_webshell_signature_before_upload_rule(self):
        core = CoreService()
        result = core.check(
            {
                "method": "POST",
                "path": "/upload",
                "event_type": "upload",
                "body": {"filename": "a.aspx", "body": 'eval(Request.Item["pass"])'},
            }
        )
        self.assertEqual(result["route"]["route"], "fast_path_block")
        self.assertEqual(result["fast_path"]["rule_id"], "FP_WEBSHELL_001")

    def test_fast_path_does_not_rate_limit_normal_get_batch(self):
        core = CoreService(config=AdminConfig(trusted_proxy_cidrs=["203.0.113.0/24"]))
        routes = []
        for _ in range(90):
            result = core.check(
                {
                    "method": "GET",
                    "path": "/api/orders",
                    "headers": {"X-Forwarded-For": "198.51.100.77"},
                },
                remote_addr="203.0.113.10",
            )
            routes.append(result["route"]["route"])
        self.assertNotIn("fast_path_block", routes)

    def test_fast_path_still_rate_limits_login_burst(self):
        core = CoreService(config=AdminConfig(trusted_proxy_cidrs=["203.0.113.0/24"]))
        routes = []
        for _ in range(70):
            result = core.check(
                {
                    "method": "POST",
                    "path": "/login",
                    "event_type": "login",
                    "body": {"username": "demo", "password": "wrong"},
                },
                remote_addr="198.51.100.99",
            )
            routes.append(result["route"]["route"])
        self.assertIn("fast_path_block", routes)

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
        self.assertIn("details_zh", guide["steps"][0])
        self.assertIn("安全情况处理总流程", " ".join(step["title_zh"] for step in guide["steps"]))

    def test_environment_preflight_reports_actionable_checks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(config_path=Path(temp_dir) / "config" / "config.json")
            report = core.environment_preflight()
            check_ids = {item["id"] for item in report["checks"]}

            self.assertIn("python_runtime", check_ids)
            self.assertIn("config_file", check_ids)
            self.assertIn("ledger_writable", check_ids)
            self.assertIn("llm_gateway_config", check_ids)
            self.assertEqual(report["summary"]["total"], len(report["checks"]))
            self.assertNotIn("api_key_value", json.dumps(report, ensure_ascii=False).lower())

    def test_integration_plan_generates_http_api_mapping(self):
        core = CoreService()
        plan = core.integration_plan(
            {
                "site_name": "Dining Hall",
                "site_url": "https://dining.example/app",
                "site_type": "论坛/社区",
                "adapter_type": "HTTP API",
                "core_url": "https://atee.example/core/",
                "appeal_path": "security/appeal",
                "protected_features": ["comments", "uploads"],
            }
        )
        endpoints = {item["core_endpoint"] for item in plan["endpoint_mappings"]}
        payload_urls = {item["url"].rsplit("/", 1)[-1] for item in plan["payload_examples"].values()}

        self.assertTrue(plan["ok"])
        self.assertEqual(plan["site"]["appeal_path"], "/security/appeal")
        self.assertEqual(plan["site"]["protected_features"], ["comments", "uploads"])
        self.assertEqual(endpoints, {"/v1/check", "/v1/event", "/v1/feature-access", "/v1/appeal"})
        self.assertEqual(payload_urls, {"check", "event", "feature-access", "appeal"})
        self.assertEqual(len(plan["verification_requests"]), 4)
        self.assertFalse(plan["payload_examples"]["check"]["json"]["body"].get("password"))

    def test_integration_plan_defaults_truncates_and_redacts_sensitive_fields(self):
        core = CoreService()
        plan = core.integration_plan(
            {
                "site_name": "x" * 120,
                "site_url": "Authorization Bearer secret",
                "adapter_type": "HTTP API",
                "core_url": "https://core.example/v1?admin_token=secret",
                "protected_features": "comments,api_key=secret," + ("u" * 80),
            }
        )
        public_text = json.dumps(plan, ensure_ascii=False).lower()

        self.assertTrue(plan["ok"])
        self.assertEqual(len(plan["site"]["name"]), 80)
        self.assertEqual(plan["site"]["url"], "https://target.example")
        self.assertEqual(plan["core_url"], "http://127.0.0.1:8787")
        self.assertEqual(plan["site"]["protected_features"], ["comments", "u" * 40])
        for marker in ("authorization", "api_key", "admin_token", "proxy_url", "secret"):
            self.assertNotIn(marker, public_text)

    def test_integration_plan_rejects_non_http_api_adapter_without_examples(self):
        core = CoreService()
        plan = core.integration_plan({"adapter_type": "Node/Express Adapter"})

        self.assertFalse(plan["ok"])
        self.assertEqual(plan["status"], 422)
        self.assertEqual(plan["reason"], "unsupported_adapter_type")
        self.assertEqual(plan["payload_examples"], {})
        self.assertEqual(plan["verification_requests"], [])

    def test_managed_site_scan_records_action_inventory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(config_path=Path(temp_dir) / "config" / "config.json")
            site = core.register_site(
                {
                    "name": "staging-forum",
                    "base_url": "https://staging.example/app",
                    "environment": "staging",
                    "allowed_domains": ["staging.example"],
                    "auth_mode": "storage_state",
                    "session_state_ref": "config/sessions/staging.json",
                }
            )
            scan = core.create_site_scan(
                {
                    "site_id": site["site"]["id"],
                    "start_url": "https://staging.example/app",
                    "allow_high_risk_actions": True,
                    "actions": [
                        {
                            "page_url": "https://staging.example/app",
                            "action_type": "delete",
                            "risk_level": "critical",
                            "label": "Delete post",
                            "selector": "#deletePost",
                            "suggested_feature_scope": "posts_delete",
                        },
                        {
                            "page_url": "https://staging.example/app",
                            "action_type": "search",
                            "risk_level": "low",
                            "label": "Search",
                            "selector": "#search",
                        },
                    ],
                }
            )
            sites = core.admin_sites()
            scans = core.admin_site_scans(site_id=site["site"]["id"])
            critical_actions = core.admin_site_actions(site_id=site["site"]["id"], risk_level="critical")
            search_actions = core.admin_site_actions(action_type="search")

            self.assertTrue(site["ok"])
            self.assertEqual(site["site"]["allowed_domains"], ["staging.example"])
            self.assertTrue(scan["ok"])
            self.assertEqual(scan["scan"]["summary"]["actions"], 2)
            self.assertEqual(scan["scan"]["summary"]["high_risk_actions"], 1)
            self.assertEqual(sites["sites"][0]["scan_count"], 1)
            self.assertEqual(sites["sites"][0]["action_count"], 2)
            self.assertEqual(scans["count"], 1)
            self.assertEqual(critical_actions["count"], 1)
            self.assertEqual(critical_actions["actions"][0]["recommended_test_type"], "approval_regression")
            self.assertTrue(critical_actions["actions"][0]["requires_admin_review"])
            self.assertEqual(search_actions["count"], 1)

    def test_site_scan_auto_matches_feature_map_and_path_rules(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(config_path=Path(temp_dir) / "config" / "config.json")
            site = core.register_site(
                {
                    "name": "forum",
                    "base_url": "https://forum.example/",
                    "allowed_domains": ["forum.example"],
                }
            )

            scan = core.create_site_scan(
                {
                    "site_id": site["site"]["id"],
                    "actions": [
                        {
                            "page_url": "https://forum.example/topic/1",
                            "action_type": "submit",
                            "risk_level": "high",
                            "label": "Post comment",
                            "selector": "#comment-submit",
                            "form_method": "POST",
                            "form_action": "/api/comments",
                        },
                        {
                            "page_url": "https://forum.example/topic/1",
                            "action_type": "search",
                            "risk_level": "medium",
                            "label": "Search",
                            "selector": "#search",
                        },
                    ],
                }
            )
            updated_site = core.admin_sites()["sites"][0]
            actions = core.admin_site_actions(site_id=site["site"]["id"])["actions"]
            comment_action = next(action for action in actions if action["selector"] == "#comment-submit")
            search_action = next(action for action in actions if action["selector"] == "#search")
            path_rules = updated_site["site_proxy"]["path_rules"]

            self.assertTrue(scan["ok"])
            self.assertEqual(scan["auto_mapping"]["features"], ["comments"])
            self.assertEqual(updated_site["site_proxy"]["feature_map"]["#comment-submit"], "comments")
            self.assertIn({"methods": ["POST"], "path": "/api/comments", "feature_scope": "comments"}, path_rules)
            self.assertEqual(comment_action["metadata"]["atee_auto_match"]["status"], "applied")
            self.assertEqual(search_action["metadata"]["atee_auto_match"]["status"], "unapplied")

    def test_site_feature_ban_applies_target_admin_template_without_leaking_session(self):
        class FakeResponse:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with tempfile.TemporaryDirectory() as temp_dir:
            session_path = Path(temp_dir) / "config" / "sessions" / "admin.json"
            session_path.parent.mkdir(parents=True, exist_ok=True)
            session_path.write_text(json.dumps({"headers": {"Cookie": "admin_session=super-secret"}}), encoding="utf-8")
            core = CoreService(config_path=Path(temp_dir) / "config" / "config.json")
            site = core.register_site(
                {
                    "name": "forum",
                    "base_url": "https://forum.example/",
                    "protected_features": ["comments"],
                    "site_proxy": {
                        "admin_session_enabled": True,
                        "admin_session_ref": "config/sessions/admin.json",
                        "admin_action_templates": {
                            "comments": {
                                "method": "POST",
                                "path": "/admin/feature-ban",
                                "body_template": {
                                    "feature": "{feature_scope}",
                                    "reason": "{reason}",
                                    "action_id": "{action_id}",
                                },
                                "success_status": [204],
                            }
                        },
                    },
                }
            )

            with patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
                result = core.create_site_feature_ban(
                    {"site_id": site["site"]["id"], "feature_scope": "comments", "reason": "spam wave"}
                )
            request = urlopen.call_args.args[0]
            public_text = json.dumps(result, ensure_ascii=False).lower()

            self.assertTrue(result["ok"])
            self.assertEqual(result["site_admin_action"]["status"], "applied")
            self.assertEqual(request.full_url, "https://forum.example/admin/feature-ban")
            self.assertIn('"feature": "comments"', request.data.decode("utf-8"))
            self.assertNotIn("super-secret", public_text)

    def test_site_feature_ban_keeps_atee_ban_when_target_admin_apply_fails(self):
        class FakeResponse:
            status = 500

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with tempfile.TemporaryDirectory() as temp_dir:
            session_path = Path(temp_dir) / "config" / "sessions" / "admin.json"
            session_path.parent.mkdir(parents=True, exist_ok=True)
            session_path.write_text(json.dumps({"headers": {"Cookie": "admin_session=super-secret"}}), encoding="utf-8")
            core = CoreService(config_path=Path(temp_dir) / "config" / "config.json")
            site = core.register_site(
                {
                    "name": "forum",
                    "base_url": "https://forum.example/",
                    "site_proxy": {
                        "admin_session_enabled": True,
                        "admin_session_ref": "config/sessions/admin.json",
                        "admin_action_templates": {
                            "comments": {"method": "POST", "path": "/admin/feature-ban", "success_status": [204]}
                        },
                    },
                }
            )

            with patch("urllib.request.urlopen", return_value=FakeResponse()):
                result = core.create_site_feature_ban({"site_id": site["site"]["id"], "feature_scope": "comments"})
            access = core.feature_access({"site_id": site["site"]["id"], "user_id": "u1", "feature_scope": "comments"})

            self.assertTrue(result["ok"])
            self.assertEqual(result["site_admin_action"]["status"], "failed")
            self.assertEqual(result["site_admin_action"]["reason"], "target_admin_action_rejected")
            self.assertFalse(access["allowed"])
            self.assertEqual(access["reason"], "active_site_feature_ban")

    def test_site_scan_records_first_scanner_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(config_path=Path(temp_dir) / "config" / "config.json")
            site = core.register_site(
                {
                    "name": "offline-local",
                    "base_url": "http://127.0.0.1:65534/",
                    "environment": "dev",
                }
            )
            scanner_result = {
                "ok": True,
                "status": "failed",
                "actions": [],
                "errors": [
                    {
                        "url": "http://127.0.0.1:65534/",
                        "error": "page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:65534/",
                    }
                ],
            }

            with patch.object(core, "_run_page_action_scan", return_value=scanner_result):
                scan = core.create_site_scan({"site_id": site["site"]["id"]})
            scans = core.admin_site_scans(site_id=site["site"]["id"])

            self.assertFalse(scan["ok"])
            self.assertEqual(scan["status"], 502)
            self.assertEqual(scan["scan"]["status"], "failed")
            self.assertIn("ERR_CONNECTION_REFUSED", scan["scan"]["error_untrusted_text"])
            self.assertNotIn("http://127.0.0.1:65534", scan["scan"]["error_untrusted_text"])
            self.assertEqual(scans["scans"][0]["error_untrusted_text"], scan["scan"]["error_untrusted_text"])

    def test_production_high_risk_site_scan_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(config_path=Path(temp_dir) / "config" / "config.json")
            site = core.register_site(
                {
                    "name": "prod-site",
                    "base_url": "https://prod.example/",
                    "environment": "production",
                }
            )

            blocked = core.create_site_scan(
                {
                    "site_id": site["site"]["id"],
                    "allow_high_risk_actions": True,
                    "actions": [{"action_type": "delete", "risk_level": "critical", "label": "Delete"}],
                }
            )
            confirmed = core.create_site_scan(
                {
                    "site_id": site["site"]["id"],
                    "allow_high_risk_actions": True,
                    "production_confirmed": True,
                    "actions": [{"action_type": "delete", "risk_level": "critical", "label": "Delete"}],
                }
            )

            self.assertFalse(blocked["ok"])
            self.assertEqual(blocked["status"], 409)
            self.assertEqual(blocked["reason"], "production_high_risk_scan_requires_confirmation")
            self.assertTrue(confirmed["ok"])
            self.assertEqual(core.admin_site_actions(risk_level="critical")["count"], 1)

    def test_read_only_blocks_managed_site_mutations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(runtime_mode="read_only"),
                config_path=Path(temp_dir) / "config" / "config.json",
            )

            site = core.register_site({"name": "blocked", "base_url": "https://blocked.example"})
            scan = core.create_site_scan({"site_id": 1, "actions": [{"label": "Search"}]})

            self.assertFalse(site["ok"])
            self.assertEqual(site["status"], 423)
            self.assertFalse(scan["ok"])
            self.assertEqual(scan["status"], 423)

    def test_security_flow_rehearsal_returns_sanitized_steps(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(llm_mode="mock", llm_provider="mock", llm_model="atee-local-mock-v1"),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            report = core.security_flow_rehearsal(actor={"id": "ops", "id_hash": "sha256:abc", "source_hash": "sha256:def"})
            step_ids = {item["id"] for item in report["flow_steps"]}
            public_text = json.dumps(report, ensure_ascii=False)

            self.assertTrue(report["ok"])
            self.assertEqual(report["summary"]["total"], len(report["flow_steps"]))
            self.assertIn("preflight", step_ids)
            self.assertIn("safe_request", step_ids)
            self.assertIn("fast_path", step_ids)
            self.assertIn("async_queue", step_ids)
            self.assertIn("appeal", step_ids)
            self.assertIn("llm_gateway", step_ids)
            self.assertIn("ledger", step_ids)
            self.assertNotIn("records", report)
            self.assertEqual(core.admin_appeals(status="pending")["count"], 0)
            self.assertNotIn("ledger_record", public_text)
            self.assertNotIn("api_key", public_text.lower())
            self.assertNotIn("Authorization", public_text)

    def test_read_only_blocks_security_flow_rehearsal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(runtime_mode="read_only"),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            report = core.security_flow_rehearsal()

            self.assertFalse(report["ok"])
            self.assertEqual(report["status"], 423)
            self.assertEqual(report["reason"], "read_only_mode_blocks_security_flow")
            self.assertEqual(core.ledger_recent(limit=5)["status"]["persisted_records"], 0)

    def test_agent_chat_mock_does_not_store_prompt_or_secret(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(config_path=Path(temp_dir) / "config" / "config.json")
            result = core.agent_chat(
                {
                    "message": "如何配置 AI API 和紧急恢复？",
                    "site_type": "论坛/社区",
                    "adapter_type": "HTTP API",
                },
                actor={"id": "ops", "id_hash": "sha256:abc", "source_hash": "sha256:def"},
            )
            public_text = json.dumps(result, ensure_ascii=False)

            self.assertTrue(result["ok"])
            self.assertEqual(result["reason"], "mock_chat")
            self.assertFalse(result["raw_prompt_stored"])
            self.assertIn("reply_zh", result)
            self.assertNotIn("sk-", public_text)

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

    def test_read_only_blocks_appeal_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config" / "config.json"
            core = CoreService(config=AdminConfig(runtime_mode="read_only"), config_path=config_path)
            core.appeal({"punishment_id": "read-only-review", "reason": "please review"})

            reviewed = core.review_appeal(
                {
                    "punishment_id": "read-only-review",
                    "resolution": "approved",
                    "admin_note": "should be blocked",
                }
            )
            pending = core.admin_appeals(status="pending")

            self.assertFalse(reviewed["ok"])
            self.assertEqual(reviewed["status"], 423)
            self.assertEqual(reviewed["reason"], "read_only_mode_blocks_appeal_review")
            self.assertEqual(pending["count"], 1)

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

    def test_feature_access_blocks_active_user_feature_ban_with_punishment_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(runtime_mode="auto"),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            action = self._execute_user_feature_ban(core, user_id="low-risk-user", feature_scope="comments")

            access = core.feature_access({"user_id": "low-risk-user", "feature_scope": "comments"})
            unrelated = core.feature_access({"user_id": "low-risk-user", "feature_scope": "uploads"})

            self.assertFalse(access["allowed"])
            self.assertEqual(access["reason"], "active_feature_ban")
            self.assertEqual(access["punishment_id"], f"action:{action['record']['id']}")
            self.assertEqual(access["active_action"]["punishment_id"], f"action:{action['record']['id']}")
            self.assertEqual(access["active_action"]["target_scope"]["feature"], "comments")
            self.assertTrue(unrelated["allowed"])
            self.assertNotIn("low-risk-user", json.dumps(access, ensure_ascii=False))

    def test_approved_feature_ban_appeal_auto_unbans_action(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(runtime_mode="auto"),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            action = self._execute_user_feature_ban(core, user_id="appeal-user", feature_scope="comments")
            punishment_id = f"action:{action['record']['id']}"
            appeal = core.appeal({"punishment_id": punishment_id, "reason": "please review"})

            reviewed = core.review_appeal(
                {"punishment_id": punishment_id, "resolution": "approved", "admin_note": "low risk"},
                actor={"id": "ops", "id_hash": "sha256:ops", "source_hash": "sha256:src"},
            )
            access = core.feature_access({"user_id": "appeal-user", "feature_scope": "comments"})
            revoked = core.admin_actions(status="revoked")

            self.assertEqual(appeal["status"], 202)
            self.assertTrue(reviewed["ok"])
            self.assertTrue(reviewed["auto_unban"]["executed"])
            self.assertEqual(reviewed["auto_unban"]["reason"], "feature_ban_revoked")
            self.assertTrue(access["allowed"])
            self.assertEqual(access["reason"], "no_active_feature_ban")
            self.assertEqual(revoked["count"], 1)
            self.assertEqual(revoked["actions"][0]["punishment_id"], punishment_id)

    def test_rejected_feature_ban_appeal_does_not_unban_action(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(runtime_mode="auto"),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            action = self._execute_user_feature_ban(core, user_id="reject-user", feature_scope="comments")
            punishment_id = f"action:{action['record']['id']}"
            core.appeal({"punishment_id": punishment_id, "reason": "please review"})

            reviewed = core.review_appeal({"punishment_id": punishment_id, "resolution": "rejected"})
            access = core.feature_access({"user_id": "reject-user", "feature_scope": "comments"})

            self.assertTrue(reviewed["ok"])
            self.assertFalse(reviewed["auto_unban"]["executed"])
            self.assertEqual(reviewed["auto_unban"]["reason"], "appeal_not_approved")
            self.assertFalse(access["allowed"])
            self.assertEqual(core.admin_actions(status="active")["count"], 1)

    def test_async_ai_feature_ban_targets_site_user_feature(self):
        class FakeResponse:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        with tempfile.TemporaryDirectory() as temp_dir:
            session_path = Path(temp_dir) / "config" / "sessions" / "admin.json"
            session_path.parent.mkdir(parents=True, exist_ok=True)
            session_path.write_text(json.dumps({"headers": {"Cookie": "admin_session=async-secret"}}), encoding="utf-8")
            core = CoreService(
                config=AdminConfig(runtime_mode="auto", llm_mode="mock"),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            site = core.register_site(
                {
                    "name": "upload-site",
                    "base_url": "https://upload.example/",
                    "protected_features": ["uploads"],
                    "site_proxy": {
                        "admin_session_enabled": True,
                        "admin_session_ref": "config/sessions/admin.json",
                        "admin_action_templates": {
                            "uploads": {
                                "method": "POST",
                                "path": "/admin/feature-ban",
                                "body_template": {"user_hash": "{user_hash}", "feature": "{feature_scope}"},
                                "success_status": [204],
                            }
                        },
                    },
                }
            )
            queued = core.event(
                {
                    "method": "POST",
                    "path": "/upload",
                    "site_id": site["site"]["id"],
                    "user_id": "upload-user",
                    "event_type": "upload",
                    "feature_scope": "uploads",
                    "body": {"text": "spam upload payload"},
                }
            )
            llm_result = {
                "ok": True,
                "llm_called": True,
                "reason": "test_feature_ban",
                "agent_decision": {"selected_action": "feature_ban", "ai_confidence": 0.92},
            }

            with patch.object(core.llm_gateway, "review", return_value=llm_result), patch(
                "urllib.request.urlopen", return_value=FakeResponse()
            ) as urlopen:
                processed = core.process_async_reviews(limit=1)
            action = core.admin_actions(status="active")["actions"][0]
            completed = core.admin_async_reviews(status="completed")
            access = core.feature_access({"site_id": site["site"]["id"], "user_id": "upload-user", "feature_scope": "uploads"})
            public_text = json.dumps(completed, ensure_ascii=False).lower()

            self.assertEqual(queued["route"]["route"], "async_agent")
            self.assertEqual(processed["processed"][0]["effective_action"], "feature_ban")
            self.assertEqual(action["target_scope"]["type"], "user_feature")
            self.assertEqual(action["target_scope"]["site_id"], site["site"]["id"])
            self.assertEqual(action["target_scope"]["feature"], "uploads")
            self.assertEqual(completed["jobs"][0]["result"]["site_admin_action"]["status"], "applied")
            self.assertIn('"feature": "uploads"', urlopen.call_args.args[0].data.decode("utf-8"))
            self.assertNotIn("async-secret", public_text)
            self.assertFalse(access["allowed"])
            self.assertEqual(access["reason"], "active_feature_ban")

    def test_feature_ban_without_user_or_feature_downgrades_to_challenge(self):
        core = CoreService(config=AdminConfig(runtime_mode="auto"))
        result = core.check(
            {
                "method": "POST",
                "path": "/login",
                "event_type": "login",
                "body": {"text": "spam login attempt"},
                "agent_decision": {"selected_action": "feature_ban", "ai_confidence": 0.95},
            }
        )

        self.assertEqual(result["decision"]["selected_action"], "challenge")
        self.assertIn("feature_ban:missing_user_or_feature", result["decision"]["reason_codes"])
        self.assertEqual(result["action_result"]["record"]["action"], "challenge")

    def test_site_feature_ban_blocks_all_users_and_is_not_auto_unbanned_by_user_appeal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(runtime_mode="auto"),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            site = core.register_site(
                {
                    "name": "managed",
                    "base_url": "https://managed.example",
                    "protected_features": ["uploads"],
                    "page_guard_enabled": True,
                }
            )["site"]
            fuse = core.create_site_feature_ban(
                {"site_id": site["id"], "feature_scope": "uploads", "duration_seconds": 3600, "reason": "confirmed spike"}
            )
            punishment_id = f"action:{fuse['action_result']['record']['id']}"
            user_one = core.feature_access({"site_id": site["id"], "user_id": "one", "feature_scope": "uploads"})
            user_two = core.feature_access({"site_id": site["id"], "user_id": "two", "feature_scope": "uploads"})
            core.appeal({"punishment_id": punishment_id, "reason": "please review"})

            reviewed = core.review_appeal({"punishment_id": punishment_id, "resolution": "approved"})
            still_blocked = core.feature_access({"site_id": site["id"], "user_id": "one", "feature_scope": "uploads"})
            revoked = core.revoke_action({"action_id": fuse["action_result"]["record"]["id"], "reason": "incident over"})
            restored = core.feature_access({"site_id": site["id"], "user_id": "one", "feature_scope": "uploads"})

            self.assertTrue(fuse["ok"])
            self.assertFalse(user_one["allowed"])
            self.assertFalse(user_two["allowed"])
            self.assertEqual(user_one["reason"], "active_site_feature_ban")
            self.assertIsNone(user_one["punishment_id"])
            self.assertEqual(reviewed["auto_unban"]["reason"], "action_is_not_user_feature_ban")
            self.assertFalse(still_blocked["allowed"])
            self.assertTrue(revoked["ok"])
            self.assertTrue(restored["allowed"])

    def test_admin_sites_returns_global_fuse_suggestion_after_repeated_user_feature_bans(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(runtime_mode="auto"),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            site = core.register_site(
                {
                    "name": "managed",
                    "base_url": "https://managed.example",
                    "protected_features": ["comments"],
                    "global_fuse_policy": {"threshold": 3, "window_seconds": 3600},
                }
            )["site"]
            for index in range(3):
                self._execute_user_feature_ban(core, user_id=f"user-{index}", feature_scope="comments", site_id=site["id"])

            sites = core.admin_sites()

            self.assertEqual(sites["global_fuse_suggestions"][0]["site_id"], site["id"])
            self.assertEqual(sites["global_fuse_suggestions"][0]["feature_scope"], "comments")
            self.assertEqual(sites["global_fuse_suggestions"][0]["active_user_bans"], 3)

    def test_approved_appeal_with_invalid_or_non_feature_action_keeps_review_saved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(runtime_mode="auto"),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            challenge = core.executor.execute(
                {"duration_seconds": 60, "target_scope": {"type": "request", "hash": "challenge"}},
                {"executed": True, "effective_action": "challenge"},
            )
            invalid_id = "action:not-a-number"
            non_feature_id = f"action:{challenge['record']['id']}"
            core.appeal({"punishment_id": invalid_id, "reason": "invalid"})
            core.appeal({"punishment_id": non_feature_id, "reason": "not feature"})

            invalid_review = core.review_appeal({"punishment_id": invalid_id, "resolution": "approved"})
            non_feature_review = core.review_appeal({"punishment_id": non_feature_id, "resolution": "approved"})

            self.assertTrue(invalid_review["ok"])
            self.assertEqual(invalid_review["auto_unban"]["reason"], "invalid_action_punishment_id")
            self.assertTrue(non_feature_review["ok"])
            self.assertEqual(non_feature_review["auto_unban"]["reason"], "action_is_not_feature_ban")
            self.assertEqual(core.admin_appeals(status="approved")["count"], 2)
            self.assertEqual(core.admin_actions(status="active")["count"], 1)

    def test_read_only_blocks_admin_action_mutations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config" / "config.json"
            core = CoreService(config=AdminConfig(runtime_mode="read_only"), config_path=config_path)
            active_record = core.executor.execute(
                {"duration_seconds": 60, "target_scope": {"type": "request", "hash": "active"}},
                {"executed": True, "effective_action": "challenge"},
            )["record"]
            core.executor.execute(
                {"duration_seconds": -1, "target_scope": {"type": "request", "hash": "expired"}},
                {"executed": True, "effective_action": "challenge"},
            )

            listed = core.admin_actions(status="active")
            expired_before_cleanup = core.admin_actions(status="expired")
            revoked = core.revoke_action({"action_id": active_record["id"], "reason": "read only check"})
            cleanup = core.cleanup_expired_actions()

            self.assertEqual(listed["count"], 2)
            self.assertEqual(expired_before_cleanup["count"], 0)
            self.assertFalse(revoked["ok"])
            self.assertEqual(revoked["status"], 423)
            self.assertEqual(revoked["reason"], "read_only_mode_blocks_action_revoke")
            self.assertFalse(cleanup["ok"])
            self.assertEqual(cleanup["status"], 423)
            self.assertEqual(cleanup["reason"], "read_only_mode_blocks_action_cleanup")
            self.assertEqual(core.admin_actions(status="active")["count"], 2)

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

    def test_admin_captcha_register_login_session_and_accounts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(admin_auth_enabled=True),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            captcha = core.admin_captcha()
            left, right = [int(part.strip()) for part in captcha["question"].split("=")[0].split("+")]
            registered = core.register_admin(
                {
                    "username": "ops@example.com",
                    "password": "strong-pass-1",
                    "captcha_id": captcha["captcha_id"],
                    "captcha_answer": str(left + right),
                }
            )
            login_captcha = core.admin_captcha()
            left, right = [int(part.strip()) for part in login_captcha["question"].split("=")[0].split("+")]
            logged_in = core.login_admin(
                {
                    "username": "ops@example.com",
                    "password": "strong-pass-1",
                    "captcha_id": login_captcha["captcha_id"],
                    "captcha_answer": str(left + right),
                },
                remote_addr="203.0.113.5",
            )
            actor = core.admin_actor_from_headers({"Authorization": f"Bearer {logged_in['token']}"})
            accounts = core.admin_accounts()
            created = core.create_admin_account({"username": "backup", "password": "backup-pass-1"}, actor=actor)
            changed = core.change_admin_password(
                {"username": "backup", "new_password": "backup-pass-2"},
                actor=actor,
            )

            self.assertTrue(registered["ok"])
            self.assertTrue(logged_in["ok"])
            self.assertTrue(core.admin_authorized({"Authorization": f"Bearer {logged_in['token']}"}))
            self.assertEqual(actor["id"], "ops@example.com")
            self.assertEqual(accounts["count"], 1)
            self.assertTrue(created["ok"])
            self.assertTrue(changed["ok"])
            self.assertTrue(core.admin_auth_status()["accounts_configured"])
            self.assertNotIn("strong-pass-1", json.dumps(core.admin_accounts(), ensure_ascii=False))
            self.assertNotIn(logged_in["token"], json.dumps(core.runtime_status(), ensure_ascii=False))

    def test_admin_api_key_registry_masks_key_and_uses_runtime_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_name = "ATEE_TEST_MANAGED_PROVIDER_KEY"
            os.environ.pop(env_name, None)
            try:
                core = CoreService(config_path=Path(temp_dir) / "config" / "config.json")
                created = core.create_api_key(
                    {
                        "name": "provider",
                        "scope": "backend",
                        "env_name": env_name,
                        "key_value": "sk-live-secret-value",
                    }
                )
                listed = core.admin_api_keys()
                env_after_create = os.environ.get(env_name)
                deleted = core.delete_api_key(created["record"]["id"])
                listed_after_delete = core.admin_api_keys()
                persisted = (Path(temp_dir) / "data" / "atee_ledger.sqlite3").read_bytes()

                self.assertTrue(created["ok"])
                self.assertEqual(env_after_create, "sk-live-secret-value")
                self.assertEqual(core.config.llm_api_key_env, env_name)
                self.assertEqual(listed["count"], 1)
                self.assertIn("********", listed["keys"][0]["masked_key"])
                self.assertNotIn("sk-live-secret-value", json.dumps(listed, ensure_ascii=False))
                self.assertTrue(deleted["ok"])
                self.assertIsNone(os.environ.get(env_name))
                self.assertEqual(listed_after_delete["count"], 0)
                self.assertNotIn(b"sk-live-secret-value", persisted)
            finally:
                os.environ.pop(env_name, None)

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
                    "path": "/login",
                    "event_type": "login",
                    "body": {"text": "normal login"},
                }
            )

            restarted = CoreService(config_path=config_path)
            recent = restarted.ledger_recent(limit=5)
            self.assertTrue(recent["ok"])
            self.assertEqual(recent["status"]["persisted_records"], 1)
            self.assertEqual(recent["records"][0]["event_type"], "agent_decision")
            self.assertEqual(recent["records"][0]["endpoint_type"], "login")

    def test_ledger_recent_public_payload_hides_details(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config" / "config.json"
            core = CoreService(config_path=config_path)
            actor = core.admin_actor_from_headers(
                {"X-ATEE-Admin-Id": "ops.alice@example.com", "X-Real-IP": "203.0.113.77"},
                remote_addr="127.0.0.1",
            )
            core.update_config({"runtime_mode": "degraded"}, actor=actor)

            full = core.ledger_recent(limit=5, include_details=True)
            public = core.ledger_recent(limit=5, include_details=False)

            self.assertIn("summary", full["records"][0])
            self.assertIn("admin_actor_id=ops.alice@example.com", full["records"][0]["summary"])
            self.assertNotIn("summary", public["records"][0])
            self.assertNotIn("endpoint_type", public["records"][0])
            self.assertNotIn("ip_hash", public["records"][0])
            self.assertNotIn("rule_id", public["records"][0])
            self.assertNotIn("sqlite_path", public["status"])

    def test_ledger_recent_details_include_sanitized_behavior_and_core_scores(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config" / "config.json"
            core = CoreService(config_path=config_path)
            core.check(
                {
                    "method": "POST",
                    "path": "/login",
                    "event_type": "login",
                    "body": {"username": "alice", "password": "secret-password"},
                    "headers": {"Authorization": "Bearer hidden"},
                }
            )
            full = core.ledger_recent(limit=5, include_details=True)
            public = core.ledger_recent(limit=5, include_details=False)
            details = full["records"][0]["details"]
            public_text = json.dumps(public, ensure_ascii=False)
            details_text = json.dumps(details, ensure_ascii=False)

            self.assertEqual(details["request"]["path"], "/login")
            self.assertIn("[REDACTED]", details["request"]["body_summary"]["preview"])
            self.assertIn("final_confidence", details["core_scores"])
            self.assertIn("reason_codes", details["core_decision"])
            self.assertNotIn("Authorization", details_text)
            self.assertNotIn("secret-password", details_text)
            self.assertNotIn("details", public_text)

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

    def test_update_config_preserves_llm_budget_and_circuit_runtime_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(llm_daily_budget_cents=10),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            core.llm_gateway.daily_spend_cents = 4
            core.llm_gateway.consecutive_failures = 3
            core.llm_gateway.circuit_opened_until = monotonic() + 60
            old_gateway = core.llm_gateway

            core.update_config(
                {
                    "llm_daily_budget_cents": 6,
                    "llm_proxy_url": "http://proxy.example:1080",
                }
            )
            status = core.runtime_status()["llm_gateway"]

            self.assertIsNot(core.llm_gateway, old_gateway)
            self.assertEqual(status["budget"]["daily_budget_cents"], 6)
            self.assertEqual(status["budget"]["daily_spend_cents"], 4)
            self.assertEqual(status["budget"]["daily_remaining_cents"], 2)
            self.assertTrue(status["circuit"]["open"])
            self.assertEqual(status["circuit"]["consecutive_failures"], 3)
            self.assertGreater(status["circuit"]["remaining_ms"], 0)

    def test_llm_budget_and_circuit_runtime_state_survive_core_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config" / "config.json"
            core = CoreService(config_path=config_path)
            core.update_config(
                {
                    "llm_daily_budget_cents": 10,
                    "llm_api_base": "https://provider.example/v1",
                    "llm_api_key_env": "ATEE_TEST_PROVIDER_KEY",
                }
            )
            core.llm_gateway.daily_spend_cents = 4
            core.llm_gateway.consecutive_failures = 3
            core.llm_gateway.circuit_opened_until = monotonic() + 60
            core._save_llm_gateway_state()

            state_text = core._llm_gateway_state_path().read_text(encoding="utf-8")
            restarted = CoreService(config_path=config_path)
            status = restarted.runtime_status()["llm_gateway"]

            self.assertEqual(status["budget"]["daily_budget_cents"], 10)
            self.assertEqual(status["budget"]["daily_spend_cents"], 4)
            self.assertEqual(status["budget"]["daily_remaining_cents"], 6)
            self.assertTrue(status["circuit"]["open"])
            self.assertEqual(status["circuit"]["consecutive_failures"], 3)
            self.assertNotIn("provider.example", state_text)
            self.assertNotIn("ATEE_TEST_PROVIDER_KEY", state_text)

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

    def test_read_only_blocks_config_update_and_runtime_api_key_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_name = "ATEE_TEST_READ_ONLY_API_KEY"
            os.environ.pop(env_name, None)
            try:
                config_path = Path(temp_dir) / "config.json"
                core = CoreService(config=AdminConfig(runtime_mode="read_only"), config_path=config_path)
                result = core.update_config(
                    {
                        "runtime_mode": "auto",
                        "llm_api_base": "https://provider.example/v1",
                        "llm_api_key_env": env_name,
                        "llm_api_key_value": "blocked-runtime-key",
                    }
                )

                self.assertFalse(result["ok"])
                self.assertEqual(result["status"], 423)
                self.assertEqual(result["reason"], "read_only_mode_blocks_config_update")
                self.assertEqual(core.runtime_status()["runtime_mode"], "read_only")
                self.assertIsNone(os.environ.get(env_name))
                self.assertFalse(config_path.exists())
                self.assertNotIn("blocked-runtime-key", json.dumps(result, ensure_ascii=False))
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
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(config_path=Path(temp_dir) / "config" / "config.json")
            result = core.check(
                {
                    "method": "POST",
                    "path": "/comment",
                    "event_type": "comment_create",
                    "body": {"text": "广告 刷屏 诈骗"},
                }
            )
            self.assertEqual(result["route"]["route"], "async_agent")
            self.assertEqual(result["decision"]["selected_action"], "allow")
            self.assertEqual(result["llm_gateway"]["reason"], "async_review_queued")
            self.assertFalse(result["llm_gateway"]["llm_called"])

            processed = core.run_async_reviews({"limit": 5})
            completed = core.admin_async_reviews(status="completed")

            self.assertTrue(processed["ok"])
            self.assertEqual(processed["claimed"], 1)
            self.assertEqual(processed["processed"][0]["status"], "completed")
            self.assertEqual(completed["count"], 1)
            self.assertEqual(completed["jobs"][0]["result"]["decision"]["selected_action"], "rule_hint")
            self.assertEqual(completed["jobs"][0]["result"]["llm_gateway"]["reason"], "mock_suspicious_content")
            self.assertNotIn("packet", completed["jobs"][0])

    def test_async_review_retries_then_dead_letters_provider_failures(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_name = "ATEE_MISSING_ASYNC_TEST_KEY"
            os.environ.pop(env_name, None)
            core = CoreService(
                config=AdminConfig(
                    llm_mode="openai_compatible",
                    llm_provider="deepseek",
                    llm_model="test-model",
                    llm_api_base="https://provider.example/v1",
                    llm_api_key_env=env_name,
                ),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            core.async_reviews.retry_backoff_seconds = 0
            result = core.check(
                {
                    "method": "POST",
                    "path": "/comment",
                    "event_type": "comment_create",
                    "body": {"text": "normal comment"},
                }
            )

            first = core.run_async_reviews({"limit": 1})
            second = core.run_async_reviews({"limit": 1})
            third = core.run_async_reviews({"limit": 1})
            dead = core.admin_async_reviews(status="dead_letter")

            self.assertEqual(result["llm_gateway"]["reason"], "async_review_queued")
            self.assertEqual(first["processed"][0]["status"], "retry")
            self.assertEqual(second["processed"][0]["status"], "retry")
            self.assertEqual(third["processed"][0]["status"], "dead_letter")
            self.assertEqual(dead["count"], 1)
            self.assertEqual(dead["jobs"][0]["attempts"], 3)
            self.assertEqual(dead["jobs"][0]["last_error"], "missing_api_key")

    def test_async_review_processing_pauses_before_claim_when_budget_exhausted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(
                    llm_mode="openai_compatible",
                    llm_provider="deepseek",
                    llm_model="test-model",
                    llm_api_base="https://provider.example/v1",
                    llm_daily_budget_cents=1,
                ),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            core.llm_gateway.daily_spend_cents = 1
            queued = core.check(
                {
                    "method": "POST",
                    "path": "/comment",
                    "event_type": "comment_create",
                    "body": {"text": "normal comment"},
                }
            )

            processed = core.run_async_reviews({"limit": 5})
            pending = core.admin_async_reviews(status="pending")
            dead = core.admin_async_reviews(status="dead_letter")

            self.assertEqual(queued["llm_gateway"]["reason"], "async_review_queued")
            self.assertTrue(processed["ok"])
            self.assertTrue(processed["paused"])
            self.assertEqual(processed["reason"], "llm_budget_exhausted")
            self.assertEqual(processed["claimed"], 0)
            self.assertEqual(pending["count"], 1)
            self.assertEqual(pending["jobs"][0]["attempts"], 0)
            self.assertEqual(dead["count"], 0)

    def test_async_review_queue_applies_backpressure_at_max_depth(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(
                    llm_mode="mock",
                    async_review_queue_max_depth=1,
                ),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            first = core.check(
                {
                    "method": "POST",
                    "path": "/comment",
                    "event_type": "comment_create",
                    "body": {"text": "first comment"},
                }
            )
            second = core.check(
                {
                    "method": "POST",
                    "path": "/comment",
                    "event_type": "comment_create",
                    "body": {"text": "second comment"},
                }
            )
            pending = core.admin_async_reviews(status="pending")
            queue = core.runtime_status()["async_review"]

            self.assertEqual(first["llm_gateway"]["reason"], "async_review_queued")
            self.assertEqual(second["llm_gateway"]["reason"], "async_review_backpressure")
            self.assertEqual(second["decision"]["selected_action"], "allow")
            self.assertEqual(second["async_review_queue"]["active_depth"], 1)
            self.assertTrue(second["async_review_queue"]["backpressure"])
            self.assertEqual(pending["count"], 1)
            self.assertEqual(queue["max_depth"], 1)
            self.assertEqual(queue["available_depth"], 0)

    def test_manual_async_review_feature_ban_completes_job_and_records_action(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(runtime_mode="auto", llm_mode="mock"),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            queued = core.check(
                {
                    "method": "POST",
                    "path": "/comment",
                    "event_type": "comment_create",
                    "feature_scope": "comments",
                    "user_id": "user-123",
                    "body": {"text": "manual review candidate"},
                }
            )
            job_id = queued["async_review_job"]["id"]
            pending = core.admin_async_reviews(status="pending")

            result = core.manual_review_async_job(
                {
                    "job_id": job_id,
                    "duration_seconds": 7200,
                    "admin_note": "confirmed abuse pattern",
                },
                actor={"id": "ops", "id_hash": "sha256:ops", "source_hash": "sha256:src"},
            )
            completed = core.admin_async_reviews(status="completed")
            actions = core.admin_actions(status="active")["actions"]

            self.assertTrue(result["ok"])
            self.assertEqual(pending["jobs"][0]["user_hash"], queued["async_review_job"]["user_hash"])
            self.assertEqual(completed["count"], 1)
            self.assertEqual(completed["jobs"][0]["result"]["reviewer_action"], "feature_ban")
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0]["action"], "feature_ban")
            self.assertEqual(actions[0]["target_scope"]["type"], "user_feature")
            self.assertEqual(actions[0]["target_scope"]["user_hash"], queued["async_review_job"]["user_hash"])
            self.assertEqual(actions[0]["target_scope"]["feature"], "comments")
            self.assertIn("manual_async_review", result["ledger_record"]["summary"])
            self.assertNotIn("user-123", json.dumps(result, ensure_ascii=False))

    def test_read_only_blocks_manual_async_review_action(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(runtime_mode="read_only", llm_mode="mock"),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            queued = core.check(
                {
                    "method": "POST",
                    "path": "/comment",
                    "event_type": "comment_create",
                    "feature_scope": "comments",
                    "user_id": "user-123",
                    "body": {"text": "manual review candidate"},
                }
            )

            result = core.manual_review_async_job({"job_id": queued["async_review_job"]["id"]})

            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], 423)
            self.assertEqual(result["reason"], "read_only_mode_blocks_manual_review")
            self.assertEqual(core.admin_async_reviews(status="pending")["count"], 1)
            self.assertEqual(core.admin_actions(status="active")["count"], 0)

    def test_read_only_blocks_async_review_processing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            core = CoreService(
                config=AdminConfig(
                    runtime_mode="read_only",
                    llm_mode="mock",
                    llm_provider="mock",
                    llm_model="atee-local-mock-v1",
                ),
                config_path=Path(temp_dir) / "config" / "config.json",
            )
            queued = core.check(
                {
                    "method": "POST",
                    "path": "/comment",
                    "event_type": "comment_create",
                    "body": {"text": "normal comment"},
                }
            )
            processed = core.run_async_reviews({"limit": 1})
            pending = core.admin_async_reviews(status="pending")

            self.assertEqual(queued["route"]["route"], "async_agent")
            self.assertFalse(processed["ok"])
            self.assertEqual(processed["status"], 423)
            self.assertEqual(processed["reason"], "read_only_mode_blocks_async_review_processing")
            self.assertEqual(pending["count"], 1)

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

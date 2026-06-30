import json
import os
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "core-service"))

from atee_core.config import AdminConfig
from atee_core.core import CoreService
from atee_core import http_server


class AteeHttpE2ETests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_core = http_server.CORE
        http_server.CORE = CoreService(
            config=AdminConfig(llm_mode="mock", llm_provider="mock", llm_model="atee-local-mock-v1"),
            config_path=Path(self.temp_dir.name) / "config" / "config.json",
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), http_server.AteeHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        http_server.CORE = self.previous_core
        self.temp_dir.cleanup()

    def test_admin_console_and_security_workflow_over_http(self):
        html = self._text("GET", "/")
        admin_html = self._text("GET", "/admin/")
        admin_js = self._text("GET", "/admin/admin.js")
        page_guard_js = self._text("GET", "/page-guard/atee-page-guard.mjs")
        chunk_path = re.search(r'href="(/admin/admin-[^"]+\.js)"', html).group(1)
        chunk_status, chunk_headers, chunk_body = self._response("GET", chunk_path)
        admin_image_paths = [
            "/admin/admin-gothic-console-bg.png",
            "/admin/admin-admin-bg-wing-single.png",
            "/admin/admin-admin-bg-wing-wide.png",
        ]
        admin_image_responses = [self._binary_response("GET", path) for path in admin_image_paths]
        favicon_status = self._status("GET", "/favicon.ico")
        status = self._json("GET", "/v1/runtime/status")
        safe = self._json(
            "POST",
            "/v1/check",
            {"method": "GET", "path": "/posts/hello", "body": {"text": "普通浏览"}},
        )
        attack = self._json(
            "POST",
            "/v1/check",
            {
                "method": "POST",
                "path": "/comment",
                "event_type": "comment_create",
                "body": {"text": "<script>alert(1)</script>"},
            },
        )
        async_check = self._json(
            "POST",
            "/v1/check",
            {
                "method": "POST",
                "path": "/comment",
                "event_type": "comment_create",
                "body": {"text": "normal comment"},
            },
        )
        async_pending = self._json("GET", "/v1/admin/async-reviews?status=pending")
        async_run = self._json("POST", "/v1/admin/async-reviews/run", {"limit": 2})
        async_completed = self._json("GET", "/v1/admin/async-reviews?status=completed")
        feature_user = "http-feature-user"
        feature_scope = "comments"
        feature_user_hash = http_server.CORE.packet_compiler._hash(feature_user)
        feature_action = http_server.CORE.executor.execute(
            {
                "selected_action": "feature_ban",
                "duration_seconds": 3600,
                "target_scope": {
                    "type": "user_feature",
                    "user_hash": feature_user_hash,
                    "feature": feature_scope,
                },
            },
            {"executed": True, "effective_action": "feature_ban"},
        )
        feature_punishment_id = f"action:{feature_action['record']['id']}"
        feature_blocked = self._json(
            "POST",
            "/v1/feature-access",
            {"user_id": feature_user, "feature_scope": feature_scope},
        )
        feature_appeal = self._json(
            "POST",
            "/v1/appeal",
            {"punishment_id": feature_punishment_id, "reason": "feature ban appeal"},
        )
        feature_reviewed = self._json(
            "POST",
            "/v1/admin/appeals/review",
            {"punishment_id": feature_punishment_id, "resolution": "approved", "admin_note": "low risk"},
        )
        feature_allowed = self._json(
            "POST",
            "/v1/feature-access",
            {"user_id": feature_user, "feature_scope": feature_scope},
        )
        appeal = self._json("POST", "/v1/appeal", {"punishment_id": "http-e2e-p1", "reason": "please review"})
        pending = self._json("GET", "/v1/admin/appeals?status=pending")
        reviewed = self._json(
            "POST",
            "/v1/admin/appeals/review",
            {"punishment_id": "http-e2e-p1", "resolution": "approved", "admin_note": "reviewed"},
        )
        self._json("POST", "/v1/admin/mode", {"mode": "auto"})
        executed = self._json(
            "POST",
            "/v1/check",
            {
                "method": "POST",
                "path": "/comment",
                "event_type": "comment_create",
                "body": {"text": "<script>alert(1)</script>"},
            },
        )
        action_id = executed["action_result"]["record"]["id"]
        active = self._json("GET", "/v1/admin/actions?status=active")
        revoked = self._json("POST", "/v1/admin/actions/revoke", {"action_id": action_id, "reason": "reviewed"})
        security_flow = self._json("POST", "/v1/admin/security-flow/run", {})
        integration_plan = self._json(
            "POST",
            "/v1/admin/integration/plan",
            {
                "site_name": "http-e2e-site",
                "site_url": "https://http-e2e.example",
                "site_type": "API 服务",
                "adapter_type": "HTTP API",
                "core_url": self.base_url,
                "appeal_path": "/security/appeal",
                "protected_features": ["comments"],
            },
        )
        registered_site = self._json(
            "POST",
            "/v1/admin/sites",
            {
                "name": "http-e2e-managed-site",
                "base_url": "https://managed.example/app",
                "environment": "staging",
                "allowed_domains": ["managed.example"],
                "protected_features": ["uploads"],
                "page_guard_enabled": True,
            },
        )
        site_fuse = self._json(
            "POST",
            "/v1/admin/site-feature-bans",
            {
                "site_id": registered_site["site"]["id"],
                "feature_scope": "uploads",
                "duration_seconds": 3600,
                "reason": "http e2e fuse",
            },
        )
        site_global_blocked = self._json(
            "POST",
            "/v1/feature-access",
            {"site_id": registered_site["site"]["id"], "user_id": "global-user", "feature_scope": "uploads"},
        )
        site_fuse_revoked = self._json(
            "POST",
            "/v1/admin/actions/revoke",
            {"action_id": site_fuse["action_result"]["record"]["id"], "reason": "http e2e restore"},
        )
        site_global_restored = self._json(
            "POST",
            "/v1/feature-access",
            {"site_id": registered_site["site"]["id"], "user_id": "global-user", "feature_scope": "uploads"},
        )
        site_scan = self._json(
            "POST",
            "/v1/admin/site-scans",
            {
                "site_id": registered_site["site"]["id"],
                "start_url": "https://managed.example/app",
                "actions": [
                    {
                        "page_url": "https://managed.example/app",
                        "action_type": "delete",
                        "risk_level": "critical",
                        "label": "Delete account",
                        "selector": "#deleteAccount",
                    }
                ],
            },
        )
        managed_sites = self._json("GET", "/v1/admin/sites")
        site_scans = self._json("GET", f"/v1/admin/site-scans?site_id={registered_site['site']['id']}")
        site_actions = self._json("GET", "/v1/admin/site-actions?risk_level=critical")

        self.assertIn("ATEE 管理控制台", html)
        self.assertIn('src="/admin/admin.js"', admin_html)
        self.assertIn("/v1/admin/actions/revoke", admin_js)
        self.assertIn("/v1/admin/security-flow/run", admin_js)
        self.assertIn("/v1/admin/integration/plan", admin_js)
        self.assertIn("/v1/admin/sites", admin_js)
        self.assertIn("/v1/admin/site-scans", admin_js)
        self.assertIn("/v1/admin/site-actions", admin_js)
        self.assertIn("/v1/admin/site-feature-bans", admin_js)
        self.assertIn("startPageGuard", page_guard_js)
        self.assertIn("/v1/feature-access", page_guard_js)
        self.assertEqual(chunk_status, 200)
        self.assertIn("application/javascript", chunk_headers["Content-Type"])
        self.assertTrue(chunk_body)
        for image_status, image_headers, image_body in admin_image_responses:
            self.assertEqual(image_status, 200)
            self.assertEqual(image_headers["Content-Type"], "image/png")
            self.assertTrue(image_body.startswith(b"\x89PNG"))
        self.assertEqual(favicon_status, 204)
        self.assertEqual(status["display"]["locale"], "zh-CN")
        self.assertEqual(safe["route"]["route"], "skip")
        self.assertEqual(attack["route"]["route"], "fast_path_block")
        self.assertEqual(async_check["route"]["route"], "async_agent")
        self.assertEqual(async_check["llm_gateway"]["reason"], "async_review_queued")
        self.assertEqual(async_pending["count"], 1)
        self.assertEqual(async_run["claimed"], 1)
        self.assertEqual(async_completed["count"], 1)
        self.assertFalse(feature_blocked["allowed"])
        self.assertEqual(feature_blocked["punishment_id"], feature_punishment_id)
        self.assertEqual(feature_appeal["status"], 202)
        self.assertTrue(feature_reviewed["auto_unban"]["executed"])
        self.assertTrue(feature_allowed["allowed"])
        self.assertEqual(appeal["status"], 202)
        self.assertEqual(pending["count"], 1)
        self.assertTrue(reviewed["ok"])
        self.assertEqual(active["count"], 1)
        self.assertTrue(revoked["ok"])
        self.assertTrue(security_flow["ok"])
        self.assertGreaterEqual(len(security_flow["flow_steps"]), 7)
        self.assertNotIn("records", security_flow)
        self.assertTrue(integration_plan["ok"])
        self.assertEqual(
            {item["core_endpoint"] for item in integration_plan["endpoint_mappings"]},
            {"/v1/check", "/v1/event", "/v1/feature-access", "/v1/appeal"},
        )
        self.assertTrue(registered_site["ok"])
        self.assertEqual(registered_site["site"]["protected_features"], ["uploads"])
        self.assertTrue(registered_site["site"]["page_guard_enabled"])
        self.assertTrue(site_fuse["ok"])
        self.assertFalse(site_global_blocked["allowed"])
        self.assertEqual(site_global_blocked["reason"], "active_site_feature_ban")
        self.assertTrue(site_fuse_revoked["ok"])
        self.assertTrue(site_global_restored["allowed"])
        self.assertTrue(site_scan["ok"])
        self.assertEqual(site_scan["scan"]["summary"]["high_risk_actions"], 1)
        self.assertEqual(managed_sites["count"], 1)
        self.assertEqual(site_scans["count"], 1)
        self.assertEqual(site_actions["count"], 1)
        self.assertEqual(site_actions["actions"][0]["action_type"], "delete")

    def test_admin_console_csp_nonce_is_generated_per_response(self):
        status_one, headers_one, html_one = self._response("GET", "/")
        status_two, headers_two, html_two = self._response("GET", "/")

        nonce_one = re.search(r'<meta name="csp-nonce" content="([^"]+)">', html_one).group(1)
        nonce_two = re.search(r'<meta name="csp-nonce" content="([^"]+)">', html_two).group(1)
        csp_one = headers_one["Content-Security-Policy"]

        self.assertEqual(status_one, 200)
        self.assertEqual(status_two, 200)
        self.assertNotEqual("__ATEE_CSP_NONCE__", nonce_one)
        self.assertNotEqual(nonce_one, nonce_two)
        self.assertRegex(nonce_one, r"^[A-Za-z0-9+/]+={0,2}$")
        self.assertIn(f"'nonce-{nonce_one}'", csp_one)
        self.assertIn("script-src 'self'", csp_one)
        self.assertIn("style-src 'self'", csp_one)
        self.assertIn("style-src-elem 'self'", csp_one)
        self.assertIn("style-src-attr 'unsafe-inline'", csp_one)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", csp_one)
        self.assertNotIn("style-src 'self' 'unsafe-inline'", csp_one)

    def test_site_proxy_injects_guard_and_blocks_protected_writes(self):
        class TargetHandler(BaseHTTPRequestHandler):
            login_attempts = 0
            publish_attempts = 0
            admin_bans = 0
            admin_cookie = ""

            def do_GET(self):
                if self.path == "/":
                    body = (
                        "<html><head>"
                        "<script>fetch('/api/me')</script>"
                        "<script src=\"/assets/app.js\"></script>"
                        "<link rel=\"stylesheet\" href=\"/assets/app.css\">"
                        "</head><body>"
                        "<button id=\"login-btn\" onclick=\"location.href='/login'\">Login</button>"
                        "<a id=\"admin-link\" href=\"/admin\">Admin</a>"
                        "<form id=\"login-form\" method=\"post\" action=\"/api/login\"></form>"
                        "<button id=\"publish\">Publish</button>"
                        "</body></html>"
                    ).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/assets/app.js":
                    body = b"fetch('/api/admin/status'); history.pushState({}, '', '/admin');"
                    self.send_response(200)
                    self.send_header("Content-Type", "application/javascript")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/assets/app.css":
                    body = b"body{color:#111}"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/css")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/api/me":
                    body = b'{"ok":true,"id":"target-user"}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/api/admin/status":
                    body = b'{"ok":true,"target_admin_status":true}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/admin":
                    body = b"<html><body>target admin backend</body></html>"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(404)
                self.end_headers()

            def do_POST(self):
                if self.path == "/api/login":
                    TargetHandler.login_attempts += 1
                    body = b'{"ok":true,"target_login":true}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Set-Cookie", "session=target-user; Domain=127.0.0.1; Path=/; HttpOnly; SameSite=Lax")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/api/publish":
                    TargetHandler.publish_attempts += 1
                    body = b'{"ok":true,"published":true}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/admin/feature-ban":
                    TargetHandler.admin_bans += 1
                    TargetHandler.admin_cookie = self.headers.get("Cookie", "")
                    body = b'{"ok":true,"admin_ban":true}'
                    self.send_response(204)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    return
                self.send_response(404)
                self.end_headers()

            def log_message(self, format, *args):
                return

        target = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
        thread = threading.Thread(target=target.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = target.server_address
            target_base = f"http://{host}:{port}/"
            session_path = Path(self.temp_dir.name) / "config" / "sessions" / "target-admin.json"
            session_path.parent.mkdir(parents=True, exist_ok=True)
            session_path.write_text(json.dumps({"headers": {"Cookie": "target_admin=ok"}}), encoding="utf-8")
            registered = self._json(
                "POST",
                "/v1/admin/sites",
                {
                    "name": "proxy-target",
                    "base_url": target_base,
                    "environment": "staging",
                    "allowed_domains": [host],
                    "protected_features": ["login", "posts", "comments"],
                    "page_guard_enabled": True,
                    "site_proxy": {
                        "feature_map": {"#publish": "publishing"},
                        "path_rules": [
                            {"methods": ["POST"], "path": "/api/publish", "feature_scope": "publishing"}
                        ],
                        "admin_session_enabled": True,
                        "admin_session_ref": "config/sessions/target-admin.json",
                        "admin_action_templates": {
                            "publishing": {
                                "method": "POST",
                                "path": "/admin/feature-ban",
                                "body_template": {"feature": "{feature_scope}", "reason": "{reason}"},
                                "success_status": [204],
                            }
                        },
                    },
                },
            )
            site_id = registered["site"]["id"]
            observed_actions = self._json(
                "POST",
                f"/proxy/sites/{site_id}/v1/page-actions",
                {
                    "page_url": target_base,
                    "actions": [
                        {
                            "page_url": target_base,
                            "action_type": "submit",
                            "risk_level": "high",
                            "label": "Comment",
                            "selector": "#comment",
                            "form_method": "POST",
                            "form_action": "/api/comments",
                        }
                    ],
                },
            )
            allowed_login_status, allowed_login_headers, allowed_login = self._json_response(
                "POST",
                f"/proxy/sites/{site_id}/api/login",
                {"username": "target-user", "password": "target-password"},
            )
            site_fuse = self._json(
                "POST",
                "/v1/admin/site-feature-bans",
                {"site_id": site_id, "feature_scope": "login", "duration_seconds": 3600},
            )
            publish_fuse = self._json(
                "POST",
                "/v1/admin/site-feature-bans",
                {"site_id": site_id, "feature_scope": "publishing", "duration_seconds": 3600},
            )

            html = self._text("GET", f"/proxy/sites/{site_id}/")
            guard_js = self._text("GET", f"/proxy/sites/{site_id}/atee-runtime-guard.js")
            page_guard_js = self._text("GET", f"/proxy/sites/{site_id}/page-guard/atee-page-guard.mjs")
            proxied_app_js = self._text("GET", f"/proxy/sites/{site_id}/assets/app.js")
            proxied_me = self._json("GET", f"/proxy/sites/{site_id}/api/me")
            proxied_admin_status = self._json("GET", f"/proxy/sites/{site_id}/api/admin/status")
            target_admin = self._text("GET", f"/proxy/sites/{site_id}/admin")
            managed_sites = self._json("GET", "/v1/admin/sites")
            observed_site_actions = self._json("GET", f"/v1/admin/site-actions?site_id={site_id}&action_type=submit")
            feature_access = self._json(
                "POST",
                f"/proxy/sites/{site_id}/v1/feature-access",
                {"user_id": "proxy-user", "feature_scope": "login"},
            )
            blocked_login = self._json(
                "POST",
                f"/proxy/sites/{site_id}/api/login",
                {"username": "blocked", "password": "blocked"},
            )
            blocked_publish = self._json(
                "POST",
                f"/proxy/sites/{site_id}/api/publish",
                {"title": "blocked"},
            )

            self.assertTrue(registered["ok"])
            self.assertTrue(observed_actions["ok"])
            self.assertEqual(observed_actions["auto_mapping"]["features"], ["comments"])
            self.assertTrue(site_fuse["ok"])
            self.assertTrue(publish_fuse["ok"])
            self.assertEqual(publish_fuse["site_admin_action"]["status"], "applied")
            self.assertEqual(allowed_login_status, 200)
            self.assertTrue(allowed_login["target_login"])
            self.assertIn(f"Path=/proxy/sites/{site_id}/", allowed_login_headers["Set-Cookie"])
            self.assertNotIn("Domain=", allowed_login_headers["Set-Cookie"])
            self.assertEqual(registered["site"]["site_proxy"]["standard"], "atee_site_proxy_v1")
            self.assertEqual(registered["site"]["site_proxy"]["proxy_path"], f"/proxy/sites/{site_id}/")
            self.assertIn(f'src="/proxy/sites/{site_id}/atee-runtime-guard.js"', html)
            self.assertNotIn('type="module" src=', html)
            self.assertLess(
                html.index(f'src="/proxy/sites/{site_id}/atee-runtime-guard.js"'),
                html.index("fetch('/api/me')"),
            )
            self.assertIn(f'src="/proxy/sites/{site_id}/assets/app.js"', html)
            self.assertIn(f'href="/proxy/sites/{site_id}/assets/app.css"', html)
            self.assertIn(f'href="/proxy/sites/{site_id}/admin"', html)
            self.assertIn(f'action="/proxy/sites/{site_id}/api/login"', html)
            self.assertIn(f'"/proxy/sites/{site_id}/v1/feature-access"', guard_js)
            self.assertIn(f'"/proxy/sites/{site_id}/v1/page-actions"', guard_js)
            self.assertIn('"path": "/api/publish"', guard_js)
            self.assertIn('"#publish": "publishing"', guard_js)
            self.assertIn("mutationFeature", guard_js)
            self.assertIn("history.pushState", guard_js)
            self.assertNotIn('path.startsWith("/admin")', guard_js)
            self.assertIn("startPageGuard", page_guard_js)
            self.assertIn("fetch('/api/admin/status')", proxied_app_js)
            self.assertTrue(proxied_me["ok"])
            self.assertTrue(proxied_admin_status["target_admin_status"])
            self.assertIn("target admin backend", target_admin)
            self.assertEqual(managed_sites["sites"][0]["site_proxy"]["feature_map"]["#comment"], "comments")
            self.assertEqual(observed_site_actions["actions"][0]["metadata"]["atee_auto_match"]["status"], "applied")
            self.assertFalse(feature_access["allowed"])
            self.assertEqual(feature_access["reason"], "active_site_feature_ban")
            self.assertEqual(blocked_login["status"], 403)
            self.assertTrue(blocked_login["atee_blocked"])
            self.assertEqual(blocked_login["feature_scope"], "login")
            self.assertEqual(blocked_publish["status"], 403)
            self.assertTrue(blocked_publish["atee_blocked"])
            self.assertEqual(blocked_publish["feature_scope"], "publishing")
            self.assertEqual(TargetHandler.login_attempts, 1)
            self.assertEqual(TargetHandler.publish_attempts, 0)
            self.assertEqual(TargetHandler.admin_bans, 1)
            self.assertEqual(TargetHandler.admin_cookie, "target_admin=ok")
        finally:
            target.shutdown()
            target.server_close()
            thread.join(timeout=5)

    def test_admin_api_requires_token_when_enabled(self):
        env_name = "ATEE_HTTP_E2E_ADMIN_TOKEN"
        os.environ[env_name] = "http-e2e-admin-token"
        try:
            http_server.CORE.update_config({"admin_auth_enabled": True, "admin_token_env": env_name})

            unauthorized = self._json("GET", "/v1/admin/config")
            unauthorized_plan = self._json(
                "POST",
                "/v1/admin/integration/plan",
                {"site_name": "blocked", "adapter_type": "HTTP API"},
            )
            authorized = self._json(
                "GET",
                "/v1/admin/config",
                headers={"Authorization": "Bearer http-e2e-admin-token"},
            )
            authorized_plan = self._json(
                "POST",
                "/v1/admin/integration/plan",
                {"site_name": "authorized", "adapter_type": "HTTP API"},
                headers={"Authorization": "Bearer http-e2e-admin-token"},
            )
            mode = self._json(
                "POST",
                "/v1/admin/mode",
                {"mode": "degraded"},
                headers={
                    "Authorization": "Bearer http-e2e-admin-token",
                    "X-ATEE-Admin-Id": "ops-http",
                },
            )
            header_authorized = self._json(
                "GET",
                "/v1/admin/config",
                headers={"X-ATEE-Admin-Token": "http-e2e-admin-token"},
            )
            recent = self._json(
                "GET",
                "/v1/admin/ledger/recent?limit=5",
                headers={"Authorization": "Bearer http-e2e-admin-token"},
            )
            public_status = self._json("GET", "/v1/runtime/status")

            self.assertFalse(unauthorized["ok"])
            self.assertEqual(unauthorized["error"], "admin_auth_required")
            self.assertFalse(unauthorized_plan["ok"])
            self.assertEqual(unauthorized_plan["error"], "admin_auth_required")
            self.assertTrue(authorized["ok"])
            self.assertTrue(authorized_plan["ok"])
            self.assertTrue(mode["ok"])
            self.assertTrue(header_authorized["ok"])
            self.assertTrue(public_status["admin_auth"]["enabled"])
            self.assertTrue(any(record.get("event_type") == "admin_runtime_mode" for record in recent["records"]))
            self.assertTrue(all("summary" not in record for record in recent["records"]))
            self.assertTrue(all("ip_hash" not in record for record in recent["records"]))
            self.assertTrue(all("rule_id" not in record for record in recent["records"]))
            self.assertTrue(all("endpoint_type" not in record for record in recent["records"]))
            self.assertNotIn("sqlite_path", recent["status"])
            self.assertNotIn("http-e2e-admin-token", json.dumps(unauthorized))
            self.assertNotIn("http-e2e-admin-token", json.dumps(public_status))
            self.assertNotIn("http-e2e-admin-token", json.dumps(recent))
        finally:
            os.environ.pop(env_name, None)

    def test_captcha_admin_login_and_api_key_routes_over_http(self):
        env_name = "ATEE_HTTP_MANAGED_PROVIDER_KEY"
        os.environ.pop(env_name, None)
        try:
            captcha = self._json("GET", "/v1/auth/captcha")
            left, right = [int(part.strip()) for part in captcha["question"].split("=")[0].split("+")]
            registered = self._json(
                "POST",
                "/v1/auth/register",
                {
                    "username": "http-admin",
                    "password": "http-admin-pass",
                    "captcha_id": captcha["captcha_id"],
                    "captcha_answer": str(left + right),
                },
            )
            login_captcha = self._json("GET", "/v1/auth/captcha")
            left, right = [int(part.strip()) for part in login_captcha["question"].split("=")[0].split("+")]
            logged_in = self._json(
                "POST",
                "/v1/auth/login",
                {
                    "username": "http-admin",
                    "password": "http-admin-pass",
                    "captcha_id": login_captcha["captcha_id"],
                    "captcha_answer": str(left + right),
                },
            )
            token_headers = {"Authorization": f"Bearer {logged_in['token']}"}
            self._json("POST", "/v1/admin/config", {"admin_auth_enabled": True}, headers=token_headers)
            accounts = self._json("GET", "/v1/admin/accounts", headers=token_headers)
            created_key = self._json(
                "POST",
                "/v1/admin/api-keys",
                {
                    "name": "http-provider",
                    "scope": "backend",
                    "env_name": env_name,
                    "key_value": "sk-http-secret",
                },
                headers=token_headers,
            )
            listed = self._json("GET", "/v1/admin/api-keys", headers=token_headers)
            env_after_create = os.environ.get(env_name)
            deleted = self._json("DELETE", f"/v1/admin/api-keys/{created_key['record']['id']}", headers=token_headers)
            self._json(
                "POST",
                "/v1/check",
                {
                    "method": "POST",
                    "path": "/login",
                    "event_type": "login",
                    "body": {"username": "http-user", "password": "hidden-password"},
                },
            )
            ledger = self._json("GET", "/v1/admin/ledger/recent?limit=5&details=1", headers=token_headers)
            public_text = json.dumps({"accounts": accounts, "listed": listed, "ledger": ledger}, ensure_ascii=False)

            self.assertTrue(registered["ok"])
            self.assertTrue(logged_in["ok"])
            self.assertTrue(accounts["ok"])
            self.assertEqual(accounts["count"], 1)
            self.assertTrue(created_key["ok"])
            self.assertEqual(env_after_create, "sk-http-secret")
            self.assertEqual(listed["count"], 1)
            self.assertIn("********", listed["keys"][0]["masked_key"])
            self.assertTrue(deleted["ok"])
            self.assertIsNone(os.environ.get(env_name))
            self.assertTrue(any(record.get("details") is not None for record in ledger["records"]))
            self.assertNotIn("sk-http-secret", public_text)
            self.assertNotIn(logged_in["token"], public_text)
        finally:
            os.environ.pop(env_name, None)

    def test_http_load_smoke_handles_parallel_checks(self):
        payloads = [
            {"method": "GET", "path": f"/public/{index}", "body": {"text": "普通浏览"}}
            if index % 2 == 0
            else {"method": "POST", "path": "/comment", "event_type": "comment_create", "body": {"text": "正常评论"}}
            for index in range(40)
        ]

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda payload: self._json("POST", "/v1/check", payload), payloads))

        self.assertEqual(len(results), 40)
        self.assertTrue(all("route" in result for result in results))
        status = self._json("GET", "/v1/runtime/status")
        self.assertGreaterEqual(status["ledger"]["aggregates"], 1)
        self.assertGreaterEqual(status["ledger"]["persisted_records"], 1)

    def _json(self, method: str, path: str, payload: dict | None = None, headers: dict[str, str] | None = None) -> dict:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(headers or {})
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                return json.loads(error.read().decode("utf-8"))
            finally:
                error.close()

    def _json_response(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], dict]:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(headers or {})
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=request_headers,
            method=method,
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return int(response.status), dict(response.headers), json.loads(response.read().decode("utf-8"))

    def _text(self, method: str, path: str) -> str:
        request = urllib.request.Request(self.base_url + path, method=method)
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.read().decode("utf-8")

    def _response(self, method: str, path: str) -> tuple[int, dict[str, str], str]:
        request = urllib.request.Request(self.base_url + path, method=method)
        with urllib.request.urlopen(request, timeout=10) as response:
            return int(response.status), dict(response.headers), response.read().decode("utf-8")

    def _binary_response(self, method: str, path: str) -> tuple[int, dict[str, str], bytes]:
        request = urllib.request.Request(self.base_url + path, method=method)
        with urllib.request.urlopen(request, timeout=10) as response:
            return int(response.status), dict(response.headers), response.read()

    def _status(self, method: str, path: str) -> int:
        request = urllib.request.Request(self.base_url + path, method=method)
        with urllib.request.urlopen(request, timeout=10) as response:
            return int(response.status)


if __name__ == "__main__":
    unittest.main()

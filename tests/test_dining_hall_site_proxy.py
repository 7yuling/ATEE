import importlib.util
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "core-service"))

from atee_core import http_server  # noqa: E402
from atee_core.config import (  # noqa: E402
    AdminConfig,
    configured_appeal_paths,
    is_appeal_path,
)
from atee_core.core import CoreService  # noqa: E402
from atee_core.site_proxy import proxy_path_from_referer  # noqa: E402


SCRIPT_PATH = ROOT / "scripts" / "dining-hall-integration-smoke.py"
SPEC = importlib.util.spec_from_file_location("dining_hall_integration_smoke", SCRIPT_PATH)
dining_hall_smoke = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(dining_hall_smoke)


class DiningHallAppealPathConfigTests(unittest.TestCase):
    def test_site_api_appeal_paths_stay_target_owned(self):
        default_paths = configured_appeal_paths(AdminConfig())
        self.assertIn("/v1/appeal", default_paths)
        self.assertIn("/atee-appeal", default_paths)
        self.assertIn("/security/appeal", default_paths)
        self.assertIn("/.well-known/atee-appeal", default_paths)
        self.assertNotIn("/api/appeal", default_paths)
        self.assertNotIn("/api/appeal/submit", default_paths)

        config = AdminConfig(
            appeal_paths=("/api/appeal", "/api/appeal/submit", "/security/appeal"),
        )
        paths = configured_appeal_paths(config)

        self.assertIn("/v1/appeal", paths)
        self.assertIn("/security/appeal", paths)
        self.assertNotIn("/api/appeal", paths)
        self.assertNotIn("/api/appeal/submit", paths)
        self.assertFalse(is_appeal_path("/api/appeal", config))
        self.assertFalse(is_appeal_path("/api/appeal/submit", config))
        self.assertTrue(is_appeal_path("/security/appeal", config))


class DiningHallSiteProxyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_core = http_server.CORE
        http_server.CORE = CoreService(
            config=AdminConfig(runtime_mode="auto", llm_mode="mock", llm_provider="mock", llm_model="atee-local-mock-v1"),
            config_path=Path(self.temp_dir.name) / "config" / "config.json",
        )
        self.core_server = ThreadingHTTPServer(("127.0.0.1", 0), http_server.AteeHandler)
        self.core_thread = threading.Thread(target=self.core_server.serve_forever, daemon=True)
        self.core_thread.start()
        self.core_url = f"http://{self.core_server.server_address[0]}:{self.core_server.server_address[1]}"

    def tearDown(self):
        self.core_server.shutdown()
        self.core_server.server_close()
        self.core_thread.join(timeout=5)
        http_server.CORE = self.previous_core
        self.temp_dir.cleanup()

    def test_payload_uses_dining_hall_collision_safe_routes(self):
        payload = dining_hall_smoke.build_site_payload("http://127.0.0.1:5001/")
        rules = payload["site_proxy"]["path_rules"]

        self.assertEqual(payload["base_url"], "http://127.0.0.1:5001/")
        self.assertEqual(payload["allowed_domains"], ["127.0.0.1", "localhost"])
        self.assertEqual(payload["auth_mode"], "none")
        self.assertTrue(payload["page_guard_enabled"])
        self.assertTrue(payload["site_proxy"]["enabled"])
        self.assertFalse(payload["site_proxy"]["auto_apply_admin_actions"])
        self.assertIn("account_settings", payload["protected_features"])
        self.assertIn(
            {"methods": ["POST"], "path_regex": r"^/api/topics/\d+/pin$", "feature_scope": "admin_actions"},
            rules,
        )
        self.assertIn({"methods": ["PUT"], "path": "/api/me/password", "feature_scope": "account_settings"}, rules)

    def test_proxy_blocks_dining_hall_writes_before_target_and_preserves_target_appeal(self):
        class TargetHandler(BaseHTTPRequestHandler):
            attempts = {
                "topics": 0,
                "comments": 0,
                "delete_topics": 0,
                "pin": 0,
                "password": 0,
                "appeal": 0,
            }

            def do_GET(self):
                if self.path == "/":
                    body = (
                        "<html><head><title>Dining Hall</title></head><body>"
                        "<button id=\"btn-create\">Create topic</button>"
                        "<button id=\"send-btn\">Send</button>"
                        "<button onclick=\"location.href='/login'\">Login</button>"
                        "</body></html>"
                    ).encode("utf-8")
                    self._send(200, body, "text/html; charset=utf-8")
                    return
                if self.path == "/login":
                    self._send(200, b"<html>target login</html>", "text/html; charset=utf-8")
                    return
                self._send(404, b"not found", "text/plain")

            def do_POST(self):
                self._read_body()
                if self.path == "/api/topics":
                    TargetHandler.attempts["topics"] += 1
                    self._send_json({"ok": True, "target": "topics"})
                    return
                if self.path == "/api/topics/1/posts":
                    TargetHandler.attempts["comments"] += 1
                    self._send_json({"ok": True, "target": "comments"})
                    return
                if self.path == "/api/topics/1/pin":
                    TargetHandler.attempts["pin"] += 1
                    self._send_json({"ok": True, "target": "pin"})
                    return
                if self.path == "/api/appeal":
                    TargetHandler.attempts["appeal"] += 1
                    self._send_json({"ok": True, "target_appeal": True})
                    return
                self._send(404, b"not found", "text/plain")

            def do_PUT(self):
                self._read_body()
                if self.path == "/api/me/password":
                    TargetHandler.attempts["password"] += 1
                    self._send_json({"ok": True, "target": "password"})
                    return
                self._send(404, b"not found", "text/plain")

            def do_DELETE(self):
                self._read_body()
                if self.path == "/api/topics/1":
                    TargetHandler.attempts["delete_topics"] += 1
                    self._send_json({"ok": True, "target": "delete_topics"})
                    return
                self._send(404, b"not found", "text/plain")

            def _read_body(self):
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length > 0:
                    self.rfile.read(length)

            def _send_json(self, payload):
                body = json.dumps(payload).encode("utf-8")
                self._send(200, body, "application/json")

            def _send(self, status, body, content_type):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        target = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
        target_thread = threading.Thread(target=target.serve_forever, daemon=True)
        target_thread.start()
        try:
            target_url = f"http://{target.server_address[0]}:{target.server_address[1]}/"
            registered = self._json(
                "POST",
                "/v1/admin/sites",
                dining_hall_smoke.build_site_payload(target_url),
            )
            site_id = registered["site"]["id"]
            proxy_base = f"/proxy/sites/{site_id}"

            proxy_html = self._text("GET", f"{proxy_base}/")
            referer_login = self._text(
                "GET",
                "/login",
                headers={"Referer": f"{self.core_url}{proxy_base}/"},
            )
            appeal_response = self._json("POST", f"{proxy_base}/api/appeal", {"username": "target", "reason": "target flow"})
            pending_appeals = self._json("GET", "/v1/admin/appeals?status=pending")

            blocked_results = {}
            for feature, method, path, payload in dining_hall_smoke.PROTECTED_WRITE_CHECKS:
                self._json(
                    "POST",
                    "/v1/admin/site-feature-bans",
                    {"site_id": site_id, "feature_scope": feature, "duration_seconds": 600, "reason": "test"},
                )
                blocked_results[feature] = self._json(method, f"{proxy_base}{path}", payload)

            self.assertTrue(registered["ok"])
            self.assertIn(f'src="{proxy_base}/atee-runtime-guard.js"', proxy_html)
            self.assertIn("target login", referer_login)
            self.assertEqual(proxy_path_from_referer("/login", f"{self.core_url}{proxy_base}/"), f"{proxy_base}/login")
            self.assertTrue(appeal_response["target_appeal"])
            self.assertEqual(TargetHandler.attempts["appeal"], 1)
            self.assertEqual(pending_appeals["count"], 0)
            for feature, result in blocked_results.items():
                self.assertEqual(result["status"], 403)
                self.assertTrue(result["atee_blocked"])
                self.assertEqual(result["feature_scope"], feature)
            self.assertEqual(
                {key: value for key, value in TargetHandler.attempts.items() if key != "appeal"},
                {"topics": 0, "comments": 0, "delete_topics": 0, "pin": 0, "password": 0},
            )
        finally:
            target.shutdown()
            target.server_close()
            target_thread.join(timeout=5)

    def _json(self, method, path, payload=None, headers=None):
        status, text = self._request(method, path, payload, headers=headers)
        data = json.loads(text) if text else {}
        if isinstance(data, dict):
            data.setdefault("status", status)
        return data

    def _text(self, method, path, payload=None, headers=None):
        return self._request(method, path, payload, headers=headers)[1]

    def _request(self, method, path, payload=None, headers=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(f"{self.core_url}{path}", data=body, method=method)
        request.add_header("Accept", "application/json, text/html;q=0.9, */*;q=0.8")
        if payload is not None:
            request.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return int(response.status), response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            try:
                text = error.read().decode("utf-8")
            finally:
                error.close()
            return int(error.code), text


if __name__ == "__main__":
    unittest.main()

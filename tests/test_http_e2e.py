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
from http.server import ThreadingHTTPServer
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
        admin_js = self._text("GET", "/admin/admin.js")
        chunk_path = re.search(r'href="(/admin/admin-[^"]+\.js)"', html).group(1)
        chunk_status, chunk_headers, chunk_body = self._response("GET", chunk_path)
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

        self.assertIn("ATEE 管理控制台", html)
        self.assertIn("/v1/admin/actions/revoke", admin_js)
        self.assertEqual(chunk_status, 200)
        self.assertIn("application/javascript", chunk_headers["Content-Type"])
        self.assertTrue(chunk_body)
        self.assertEqual(favicon_status, 204)
        self.assertEqual(status["display"]["locale"], "zh-CN")
        self.assertEqual(safe["route"]["route"], "skip")
        self.assertEqual(attack["route"]["route"], "fast_path_block")
        self.assertEqual(async_check["route"]["route"], "async_agent")
        self.assertEqual(async_check["llm_gateway"]["reason"], "async_review_queued")
        self.assertEqual(async_pending["count"], 1)
        self.assertEqual(async_run["claimed"], 1)
        self.assertEqual(async_completed["count"], 1)
        self.assertEqual(appeal["status"], 202)
        self.assertEqual(pending["count"], 1)
        self.assertTrue(reviewed["ok"])
        self.assertEqual(active["count"], 1)
        self.assertTrue(revoked["ok"])

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

    def test_admin_api_requires_token_when_enabled(self):
        env_name = "ATEE_HTTP_E2E_ADMIN_TOKEN"
        os.environ[env_name] = "http-e2e-admin-token"
        try:
            http_server.CORE.update_config({"admin_auth_enabled": True, "admin_token_env": env_name})

            unauthorized = self._json("GET", "/v1/admin/config")
            authorized = self._json(
                "GET",
                "/v1/admin/config",
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
            self.assertTrue(authorized["ok"])
            self.assertTrue(mode["ok"])
            self.assertTrue(header_authorized["ok"])
            self.assertTrue(public_status["admin_auth"]["enabled"])
            summaries = "\n".join(record["summary"] for record in recent["records"])
            self.assertIn("admin_actor_id=ops-http", summaries)
            self.assertIn("admin_actor_hash=sha256:", summaries)
            self.assertNotIn("http-e2e-admin-token", json.dumps(unauthorized))
            self.assertNotIn("http-e2e-admin-token", json.dumps(public_status))
            self.assertNotIn("http-e2e-admin-token", json.dumps(recent))
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

    def _text(self, method: str, path: str) -> str:
        request = urllib.request.Request(self.base_url + path, method=method)
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.read().decode("utf-8")

    def _response(self, method: str, path: str) -> tuple[int, dict[str, str], str]:
        request = urllib.request.Request(self.base_url + path, method=method)
        with urllib.request.urlopen(request, timeout=10) as response:
            return int(response.status), dict(response.headers), response.read().decode("utf-8")

    def _status(self, method: str, path: str) -> int:
        request = urllib.request.Request(self.base_url + path, method=method)
        with urllib.request.urlopen(request, timeout=10) as response:
            return int(response.status)


if __name__ == "__main__":
    unittest.main()

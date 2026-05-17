import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProductionSmokeHandler(BaseHTTPRequestHandler):
    token = "prod-smoke-test-token-value"
    sso_actor = "ops.sso@example.com"
    ledger_records: list[dict] = []

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json({"ok": True})
            return
        if self.path == "/":
            self._text(
                (
                    '<!doctype html><title>ATEE 管理控制台</title>'
                    '<script type="module" src="/admin/admin.js"></script>'
                    '<link rel="modulepreload" href="/admin/admin-vendor.js">'
                    '<link rel="stylesheet" href="/admin/styles.css">'
                    "<div>ATEE</div>"
                ),
                "text/html; charset=utf-8",
                security_headers=True,
            )
            return
        if self.path == "/admin/admin.js" or self.path == "/admin/admin-vendor.js":
            self._text("export default {};", "application/javascript; charset=utf-8")
            return
        if self.path == "/admin/styles.css":
            self._text("body{color:#111827}", "text/css; charset=utf-8")
            return
        if self.path == "/v1/runtime/status":
            self._json({"display": {"locale": "zh-CN"}, "admin_auth": {"enabled": True}})
            return
        if self.path == "/v1/admin/config":
            if not self._authorized():
                self._json({"ok": False, "error": "admin_auth_required"}, status=401)
                return
            self._json({"ok": True, "config": {"admin_auth_enabled": True}})
            return
        if self.path.startswith("/v1/admin/ledger/recent"):
            if not self._authorized():
                self._json({"ok": False, "error": "admin_auth_required"}, status=401)
                return
            self._json({"ok": True, "records": self.ledger_records})
            return
        self._json({"error": "not_found"}, status=404)

    def do_POST(self) -> None:
        if self.path == "/v1/admin/break-glass/status":
            if not self._authorized():
                self._json({"ok": False, "error": "admin_auth_required"}, status=401)
                return
            self.__class__.ledger_records.append(
                {
                    "id": len(self.ledger_records) + 1,
                    "summary": (
                        f"valid_for_request=False admin_actor_id={self.sso_actor} "
                        "admin_actor_hash=sha256:1111222233334444 "
                        "admin_source_hash=sha256:aaaabbbbccccdddd"
                    ),
                }
            )
            self._json({"enabled": False, "valid_for_request": False})
            return
        self._json({"error": "not_found"}, status=404)

    def log_message(self, format: str, *args) -> None:
        return

    def _authorized(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {self.token}"

    def _json(self, payload: dict, status: int = 200) -> None:
        self._text(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8", status=status)

    def _text(self, text: str, content_type: str, status: int = 200, security_headers: bool = False) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; object-src 'none'")
        if security_headers:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)


class ProductionSmokeCheckTests(unittest.TestCase):
    def setUp(self):
        ProductionSmokeHandler.ledger_records = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ProductionSmokeHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_production_smoke_check_is_sanitized_and_verifies_sso_actor_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "production-smoke.md"
            env = os.environ.copy()
            env["ATEE_PROD_SMOKE_TOKEN"] = ProductionSmokeHandler.token
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "production-smoke-check.py"),
                    "--base-url",
                    self.base_url,
                    "--allow-http",
                    "--expect-admin-auth",
                    "--admin-token-env",
                    "ATEE_PROD_SMOKE_TOKEN",
                    "--verify-audit-actor",
                    "--audit-actor-id",
                    "browser-spoofed@example.com",
                    "--expected-audit-actor",
                    ProductionSmokeHandler.sso_actor,
                    "--report",
                    str(report_path),
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(completed.stdout)
            report = report_path.read_text(encoding="utf-8")

            self.assertTrue(payload["ok"])
            self.assertTrue(any(check["name"] == "audit_actor" and check["ok"] for check in payload["checks"]))
            self.assertNotIn(ProductionSmokeHandler.token, completed.stdout)
            self.assertNotIn(self.base_url, completed.stdout)
            self.assertNotIn("browser-spoofed@example.com", completed.stdout)
            self.assertNotIn(ProductionSmokeHandler.sso_actor, completed.stdout)
            self.assertIn("ATEE Production Smoke Check Report", report)
            self.assertNotIn(ProductionSmokeHandler.token, report)
            self.assertNotIn(self.base_url, report)
            self.assertNotIn("browser-spoofed@example.com", report)
            self.assertNotIn(ProductionSmokeHandler.sso_actor, report)


if __name__ == "__main__":
    unittest.main()

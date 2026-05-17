import json
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AdminTokenRotationSmokeHandler(BaseHTTPRequestHandler):
    active_token_file: Path | None = None
    sso_actor = "ops.rotation@example.test"
    ledger_records: list[dict] = []

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json({"ok": True})
            return
        if self.path == "/":
            self._text(
                (
                    "<!doctype html><title>ATEE</title>"
                    '<script type="module" src="/admin/admin.js"></script>'
                    '<link rel="modulepreload" href="/admin/admin-vendor.js">'
                    '<link rel="stylesheet" href="/admin/styles.css">'
                    "<div>ATEE</div>"
                ),
                "text/html; charset=utf-8",
                security_headers=True,
            )
            return
        if self.path in {"/admin/admin.js", "/admin/admin-vendor.js"}:
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
        return self.headers.get("Authorization") == f"Bearer {self._active_token()}"

    def _active_token(self) -> str:
        assert self.active_token_file is not None
        return self.active_token_file.read_text(encoding="utf-8").strip()

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


class AdminTokenRotationSmokeTests(unittest.TestCase):
    def setUp(self):
        AdminTokenRotationSmokeHandler.ledger_records = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), AdminTokenRotationSmokeHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        AdminTokenRotationSmokeHandler.active_token_file = None

    def test_admin_token_rotation_smoke_rotates_restarts_and_redacts(self):
        old_token = "old-admin-token-value-1234567890"
        spoofed_actor = "browser-rotation-spoof@example.test"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            env_file = temp_path / "atee-core.env"
            active_token_file = temp_path / "active-token.txt"
            report_path = temp_path / "rotation-smoke.md"
            restart_script = temp_path / "restart.py"
            env_file.write_text(f"ATEE_ADMIN_TOKEN={old_token}\nOTHER_SETTING=kept\n", encoding="utf-8")
            active_token_file.write_text(old_token, encoding="utf-8")
            restart_script.write_text(
                (
                    "import sys\n"
                    "from pathlib import Path\n"
                    "env_file = Path(sys.argv[1])\n"
                    "active_file = Path(sys.argv[2])\n"
                    "for line in env_file.read_text(encoding='utf-8').splitlines():\n"
                    "    if line.startswith('ATEE_ADMIN_TOKEN='):\n"
                    "        active_file.write_text(line.split('=', 1)[1], encoding='utf-8')\n"
                    "        raise SystemExit(0)\n"
                    "raise SystemExit(2)\n"
                ),
                encoding="utf-8",
            )
            AdminTokenRotationSmokeHandler.active_token_file = active_token_file
            restart_command = _command_line([sys.executable, str(restart_script), str(env_file), str(active_token_file)])

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "admin-token-rotation-smoke.py"),
                    "--env-file",
                    str(env_file),
                    "--base-url",
                    self.base_url,
                    "--allow-http",
                    "--expect-admin-auth",
                    "--verify-audit-actor",
                    "--audit-actor-id",
                    spoofed_actor,
                    "--expected-audit-actor",
                    AdminTokenRotationSmokeHandler.sso_actor,
                    "--restart-command",
                    restart_command,
                    "--report",
                    str(report_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(completed.stdout)
            report = report_path.read_text(encoding="utf-8")
            new_token = _read_env_value(env_file, "ATEE_ADMIN_TOKEN")

            self.assertTrue(payload["ok"])
            self.assertTrue(payload["rotation"]["ok"])
            self.assertTrue(payload["restart"]["ok"])
            self.assertTrue(payload["old_token_rejected"]["ok"])
            self.assertTrue(payload["smoke"]["ok"])
            self.assertTrue(any(check["name"] == "audit_actor" and check["ok"] for check in payload["smoke"]["checks"]))
            self.assertIsNotNone(new_token)
            self.assertNotEqual(old_token, new_token)
            self.assertEqual(new_token, active_token_file.read_text(encoding="utf-8").strip())
            self.assertIn("OTHER_SETTING=kept", env_file.read_text(encoding="utf-8"))
            self.assertIn("ATEE Admin Token Rotation Smoke Report", report)
            for leaked in [
                old_token,
                new_token,
                self.base_url,
                spoofed_actor,
                AdminTokenRotationSmokeHandler.sso_actor,
            ]:
                self.assertNotIn(leaked, completed.stdout)
                self.assertNotIn(leaked, report)


def _command_line(parts: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


def _read_env_value(path: Path, name: str) -> str | None:
    prefix = f"{name}="
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line.split("=", 1)[1].strip()
    return None


if __name__ == "__main__":
    unittest.main()

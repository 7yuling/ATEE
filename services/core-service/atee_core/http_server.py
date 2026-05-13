import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .core import CoreService


ROOT = Path(__file__).resolve().parents[3]
CORE = CoreService(config_path=ROOT / "config" / "config.json")
ADMIN_DIR = ROOT / "apps" / "admin-console"
ADMIN_INDEX = ADMIN_DIR / "index.html"
ADMIN_STYLES = ADMIN_DIR / "styles.css"
ADMIN_JS = ADMIN_DIR / "admin.js"


class AteeHandler(BaseHTTPRequestHandler):
    server_version = "ATEECore/0.1"

    def do_GET(self) -> None:
        if self.path in {"/", "/admin"}:
            self._send_html(ADMIN_INDEX.read_text(encoding="utf-8"))
            return
        if self.path == "/admin/styles.css":
            self._send_text(ADMIN_STYLES.read_text(encoding="utf-8"), "text/css; charset=utf-8")
            return
        if self.path == "/admin/admin.js":
            self._send_text(ADMIN_JS.read_text(encoding="utf-8"), "application/javascript; charset=utf-8")
            return
        if self.path == "/health":
            self._send_json({"ok": True})
            return
        if self.path == "/v1/runtime/status":
            self._send_json(CORE.runtime_status())
            return
        if self.path == "/v1/admin/config":
            self._send_json(CORE.config_status())
            return
        if self.path == "/v1/onboarding/steps":
            self._send_json(CORE.onboarding_steps())
            return
        self._send_json({"error": "not_found"}, status=404)

    def do_POST(self) -> None:
        payload = self._read_json()
        remote_addr = self.client_address[0] if self.client_address else "127.0.0.1"
        if self.path == "/v1/check":
            self._send_json(CORE.check(payload, remote_addr=remote_addr))
            return
        if self.path == "/v1/event":
            self._send_json(CORE.event(payload, remote_addr=remote_addr))
            return
        if self.path == "/v1/appeal":
            result = CORE.appeal(payload, remote_addr=remote_addr)
            self._send_json(result, status=int(result.get("status", 200)))
            return
        if self.path == "/v1/admin/mode":
            self._send_json(CORE.set_mode(payload))
            return
        if self.path == "/v1/admin/pause-agent":
            self._send_json(CORE.pause_agent(payload))
            return
        if self.path == "/v1/admin/config":
            self._send_json(CORE.update_config(payload))
            return
        if self.path == "/v1/admin/break-glass/status":
            self._send_json(CORE.break_glass_status(dict(self.headers.items())))
            return
        self._send_json({"error": "not_found"}, status=404)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, text: str, status: int = 200) -> None:
        self._send_text(text, "text/html; charset=utf-8", status=status)

    def _send_text(self, text: str, content_type: str, status: int = 200) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'self'")
        self.end_headers()
        self.wfile.write(body)


def run(host: str = "127.0.0.1", port: int = 8787) -> None:
    server = ThreadingHTTPServer((host, port), AteeHandler)
    print(f"ATEE Core Service running at http://{host}:{port}")
    server.serve_forever()

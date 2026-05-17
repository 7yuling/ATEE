import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ADAPTER_DIR = ROOT / "adapters" / "python-fastapi"
STATIC_DIR = Path(__file__).resolve().parent
if str(ADAPTER_DIR) not in sys.path:
    sys.path.insert(0, str(ADAPTER_DIR))

from atee_adapter import AteeThinAdapter, build_context  # noqa: E402


class DemoBusinessApp:
    def __init__(self, adapter: Any):
        self.adapter = adapter

    def login(self, body: dict[str, Any], headers: dict[str, str] | None = None, remote_addr: str = "127.0.0.1") -> dict[str, Any]:
        context = build_context(
            "POST",
            "/login",
            headers or {},
            {
                "username": str(body.get("username") or "")[:80],
                "password": str(body.get("password") or "")[:200],
            },
            remote_addr,
            "login",
        )
        security = self.adapter.check(context)
        return self._business_response("login", security, {"user": context["body"]["username"]})

    def comment(self, body: dict[str, Any], headers: dict[str, str] | None = None, remote_addr: str = "127.0.0.1") -> dict[str, Any]:
        context = build_context(
            "POST",
            "/comment",
            headers or {},
            {"text": str(body.get("text") or "")[:2000]},
            remote_addr,
            "comment_create",
        )
        security = self.adapter.event(context)
        return self._business_response("comment", security, {"text": context["body"]["text"]})

    def upload(self, body: dict[str, Any], headers: dict[str, str] | None = None, remote_addr: str = "127.0.0.1") -> dict[str, Any]:
        context = build_context(
            "POST",
            "/upload",
            headers or {},
            {
                "filename": str(body.get("filename") or "demo.txt")[:160],
                "text": str(body.get("text") or "")[:2000],
            },
            remote_addr,
            "file_upload",
        )
        security = self.adapter.event(context)
        return self._business_response("upload", security, {"filename": context["body"]["filename"]})

    def appeal(self, body: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "punishment_id": str(body.get("punishment_id") or "")[:160],
            "banned_ip_hash": str(body.get("banned_ip_hash") or "")[:160],
            "reason": str(body.get("reason") or "")[:2000],
        }
        result = self.adapter.appeal(payload)
        return {
            "ok": result.get("accepted", False),
            "demo_action": "appeal_submitted",
            "appeal": result,
        }

    def _business_response(self, action: str, security: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        action_result = security.get("action_result") or {}
        executed = bool(action_result.get("executed"))
        return {
            "ok": not executed,
            "demo_action": f"{action}_{'accepted' if not executed else 'held'}",
            "data": data,
            "security": self._security_summary(security),
            "core_response": security,
        }

    def _security_summary(self, security: dict[str, Any]) -> dict[str, Any]:
        gateway = security.get("tool_gateway") or {}
        action_result = security.get("action_result") or {}
        return {
            "route": (security.get("route") or {}).get("route"),
            "event_type": (security.get("route") or {}).get("event_type"),
            "selected_action": (security.get("decision") or {}).get("selected_action"),
            "effective_action": gateway.get("effective_action"),
            "executed": bool(action_result.get("executed")),
            "message_zh": (security.get("display") or {}).get("message_zh"),
        }


DEMO = DemoBusinessApp(AteeThinAdapter())


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "ATEEDemo/0.1"

    def do_GET(self) -> None:
        if self.path in {"/", "/demo"}:
            self._send_text((STATIC_DIR / "index.html").read_text(encoding="utf-8"), "text/html; charset=utf-8")
            return
        if self.path == "/demo/styles.css":
            self._send_text((STATIC_DIR / "styles.css").read_text(encoding="utf-8"), "text/css; charset=utf-8")
            return
        if self.path == "/demo/demo.js":
            self._send_text((STATIC_DIR / "demo.js").read_text(encoding="utf-8"), "application/javascript; charset=utf-8")
            return
        if self.path == "/assets/flow.svg":
            self._send_text((STATIC_DIR / "assets" / "flow.svg").read_text(encoding="utf-8"), "image/svg+xml; charset=utf-8")
            return
        if self.path == "/health":
            self._send_json({"ok": True, "service": "atee-demo-site"})
            return
        self._send_json({"error": "not_found"}, status=404)

    def do_POST(self) -> None:
        body = self._read_json()
        headers = dict(self.headers.items())
        remote_addr = self.client_address[0] if self.client_address else "127.0.0.1"
        if self.path == "/api/login":
            self._send_json(DEMO.login(body, headers, remote_addr))
            return
        if self.path == "/api/comment":
            self._send_json(DEMO.comment(body, headers, remote_addr))
            return
        if self.path == "/api/upload":
            self._send_json(DEMO.upload(body, headers, remote_addr))
            return
        if self.path == "/api/appeal":
            result = DEMO.appeal(body)
            status = int((result.get("appeal") or {}).get("status", 200))
            self._send_json(result, status=status)
            return
        self._send_json({"error": "not_found"}, status=404)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; base-uri 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, content_type: str, status: int = 200) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; base-uri 'self'")
        self.end_headers()
        self.wfile.write(body)


def run(host: str = "127.0.0.1", port: int = 8790) -> None:
    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"ATEE Demo Site running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()

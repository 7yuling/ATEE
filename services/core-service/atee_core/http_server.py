import base64
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .core import CoreService
from .async_review_worker import AsyncReviewWorker


ROOT = Path(__file__).resolve().parents[3]
CORE = CoreService(config_path=ROOT / "config" / "config.json")
ADMIN_DIR = ROOT / "apps" / "admin-console"
ADMIN_INDEX = ADMIN_DIR / "index.html"
ADMIN_STYLES = ADMIN_DIR / "styles.css"
ADMIN_JS = ADMIN_DIR / "admin.js"
ADMIN_ASSET_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".png": "image/png",
}


class AteeHandler(BaseHTTPRequestHandler):
    server_version = "ATEECore/0.1"

    def do_GET(self) -> None:
        if self._is_admin_api_path() and not self._ensure_admin_auth():
            return
        if self.path in {"/", "/admin", "/admin/"}:
            self._send_html(ADMIN_INDEX.read_text(encoding="utf-8"))
            return
        if self.path == "/favicon.ico":
            self._send_text("", "image/x-icon", status=204)
            return
        if self.path == "/admin/styles.css":
            self._send_text(ADMIN_STYLES.read_text(encoding="utf-8"), "text/css; charset=utf-8")
            return
        if self.path == "/admin/admin.js":
            self._send_text(ADMIN_JS.read_text(encoding="utf-8"), "application/javascript; charset=utf-8")
            return
        if self.path.startswith("/admin/"):
            self._send_admin_asset()
            return
        if self.path == "/health":
            self._send_json({"ok": True})
            return
        if self.path == "/v1/runtime/status":
            self._send_json(CORE.runtime_status())
            return
        if self.path == "/v1/auth/captcha":
            self._send_json(CORE.admin_captcha())
            return
        if self.path == "/v1/admin/config":
            self._send_json(CORE.config_status())
            return
        if self.path == "/v1/admin/accounts":
            self._send_json(CORE.admin_accounts())
            return
        if self.path.startswith("/v1/admin/api-keys"):
            include_revoked = self._query_value("include_revoked", "0") == "1"
            self._send_json(CORE.admin_api_keys(include_revoked=include_revoked))
            return
        if self.path == "/v1/admin/preflight":
            self._send_json(CORE.environment_preflight())
            return
        if self.path == "/v1/admin/llm/test":
            self._send_json(CORE.test_llm_gateway())
            return
        if self.path.startswith("/v1/admin/ledger/recent"):
            include_details = self._query_value("details", "0") == "1"
            self._send_json(CORE.ledger_recent(self._query_limit(default=20), include_details=include_details))
            return
        if self.path.startswith("/v1/admin/appeals"):
            self._send_json(CORE.admin_appeals(self._query_value("status", "pending"), self._query_limit(default=50)))
            return
        if self.path.startswith("/v1/admin/actions"):
            self._send_json(CORE.admin_actions(self._query_value("status", "active")))
            return
        if self.path.startswith("/v1/admin/async-reviews"):
            self._send_json(
                CORE.admin_async_reviews(
                    self._query_value("status", "pending"),
                    self._query_limit(default=50),
                )
            )
            return
        if self.path == "/v1/onboarding/steps":
            self._send_json(CORE.onboarding_steps())
            return
        self._send_json({"error": "not_found"}, status=404)

    def do_POST(self) -> None:
        if self._is_admin_api_path() and not self._ensure_admin_auth():
            return
        payload = self._read_json()
        remote_addr = self.client_address[0] if self.client_address else "127.0.0.1"
        if self.path == "/v1/auth/register":
            result = CORE.register_admin(payload)
            self._send_json(result, status=int(result.get("status", 200)))
            return
        if self.path == "/v1/auth/login":
            result = CORE.login_admin(payload, remote_addr=remote_addr)
            self._send_json(result, status=int(result.get("status", 200)))
            return
        if self.path == "/v1/check":
            self._send_json(CORE.check(payload, remote_addr=remote_addr))
            return
        if self.path == "/v1/event":
            self._send_json(CORE.event(payload, remote_addr=remote_addr))
            return
        if self.path == "/v1/feature-access":
            result = CORE.feature_access(payload)
            self._send_json(result, status=int(result.get("status", 200)))
            return
        if self.path == "/v1/appeal":
            result = CORE.appeal(payload, remote_addr=remote_addr)
            self._send_json(result, status=int(result.get("status", 200)))
            return
        if self.path == "/v1/admin/mode":
            self._send_json(CORE.set_mode(payload, actor=self._admin_actor()))
            return
        if self.path == "/v1/admin/pause-agent":
            self._send_json(CORE.pause_agent(payload, actor=self._admin_actor()))
            return
        if self.path == "/v1/admin/config":
            self._send_json(CORE.update_config(payload, actor=self._admin_actor()))
            return
        if self.path == "/v1/admin/accounts":
            result = CORE.create_admin_account(payload, actor=self._admin_actor())
            self._send_json(result, status=int(result.get("status", 200)))
            return
        if self.path == "/v1/admin/accounts/password":
            result = CORE.change_admin_password(payload, actor=self._admin_actor())
            self._send_json(result, status=int(result.get("status", 200)))
            return
        if self.path == "/v1/admin/api-keys":
            result = CORE.create_api_key(payload, actor=self._admin_actor())
            self._send_json(result, status=int(result.get("status", 200)))
            return
        if self.path == "/v1/admin/preflight":
            self._send_json(CORE.environment_preflight())
            return
        if self.path == "/v1/admin/security-flow/run":
            result = CORE.security_flow_rehearsal(actor=self._admin_actor())
            self._send_json(result, status=int(result.get("status", 200)))
            return
        if self.path == "/v1/admin/agent/chat":
            result = CORE.agent_chat(payload, actor=self._admin_actor())
            self._send_json(result, status=int(result.get("status", 200)))
            return
        if self.path == "/v1/admin/integration/plan":
            result = CORE.integration_plan(payload, actor=self._admin_actor())
            self._send_json(result, status=int(result.get("status", 200)))
            return
        if self.path == "/v1/admin/llm/test":
            self._send_json(CORE.test_llm_gateway())
            return
        if self.path == "/v1/admin/break-glass/status":
            self._send_json(CORE.break_glass_status(dict(self.headers.items()), actor=self._admin_actor()))
            return
        if self.path == "/v1/admin/appeals/review":
            result = CORE.review_appeal(payload, actor=self._admin_actor())
            self._send_json(result, status=int(result.get("status", 200)))
            return
        if self.path == "/v1/admin/actions/revoke":
            result = CORE.revoke_action(payload, actor=self._admin_actor())
            self._send_json(result, status=int(result.get("status", 200)))
            return
        if self.path == "/v1/admin/actions/cleanup-expired":
            self._send_json(CORE.cleanup_expired_actions(actor=self._admin_actor()))
            return
        if self.path == "/v1/admin/async-reviews/run":
            self._send_json(CORE.run_async_reviews(payload, actor=self._admin_actor()))
            return
        if self.path == "/v1/admin/async-reviews/manual-action":
            result = CORE.manual_review_async_job(payload, actor=self._admin_actor())
            self._send_json(result, status=int(result.get("status", 200)))
            return
        self._send_json({"error": "not_found"}, status=404)

    def do_DELETE(self) -> None:
        if self._is_admin_api_path() and not self._ensure_admin_auth():
            return
        path = urlsplit(self.path).path
        if path.startswith("/v1/admin/api-keys/"):
            _, _, raw_id = path.rpartition("/")
            try:
                key_id = int(raw_id)
            except ValueError:
                self._send_json({"ok": False, "status": 400, "reason": "api_key_id_required"}, status=400)
                return
            result = CORE.delete_api_key(key_id, actor=self._admin_actor())
            self._send_json(result, status=int(result.get("status", 200)))
            return
        self._send_json({"error": "not_found"}, status=404)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _is_admin_api_path(self) -> bool:
        return self.path == "/v1/admin" or self.path.startswith("/v1/admin/")

    def _ensure_admin_auth(self) -> bool:
        if CORE.admin_authorized(dict(self.headers.items())):
            return True
        self._send_json(CORE.admin_auth_challenge(), status=401)
        return False

    def _admin_actor(self) -> dict[str, str]:
        remote_addr = self.client_address[0] if self.client_address else ""
        return CORE.admin_actor_from_headers(dict(self.headers.items()), remote_addr=remote_addr)

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

    def _query_limit(self, default: int = 20) -> int:
        value = self._query_value("limit", "")
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def _query_value(self, name: str, default: str = "") -> str:
        if "?" not in self.path:
            return default
        query = self.path.split("?", 1)[1]
        for part in query.split("&"):
            key, _, value = part.partition("=")
            if key == name:
                return value
        return default

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", self._content_security_policy())
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, text: str, status: int = 200) -> None:
        nonce = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        self._send_text(
            text.replace("__ATEE_CSP_NONCE__", nonce),
            "text/html; charset=utf-8",
            status=status,
            csp_nonce=nonce,
        )

    def _send_text(self, text: str, content_type: str, status: int = 200, csp_nonce: str | None = None) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", self._content_security_policy(csp_nonce))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", self._content_security_policy())
        self.end_headers()
        self.wfile.write(body)

    def _send_admin_asset(self) -> None:
        path = unquote(urlsplit(self.path).path)
        relative_name = path.removeprefix("/admin/")
        asset_path = (ADMIN_DIR / relative_name).resolve()
        admin_root = ADMIN_DIR.resolve()
        content_type = ADMIN_ASSET_TYPES.get(asset_path.suffix.lower())
        if not content_type or not asset_path.is_relative_to(admin_root) or not asset_path.is_file():
            self._send_json({"error": "not_found"}, status=404)
            return
        self._send_bytes(asset_path.read_bytes(), content_type)

    def _content_security_policy(self, nonce: str | None = None) -> str:
        script_src = "script-src 'self'"
        style_src = "style-src 'self'"
        style_src_elem = "style-src-elem 'self'"
        if nonce:
            script_src += f" 'nonce-{nonce}'"
            style_src += f" 'nonce-{nonce}'"
            style_src_elem += f" 'nonce-{nonce}'"
        return (
            "default-src 'self'; "
            f"{script_src}; "
            f"{style_src}; "
            f"{style_src_elem}; "
            "style-src-attr 'unsafe-inline'; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'"
        )


def run(host: str = "127.0.0.1", port: int = 8787) -> None:
    server = ThreadingHTTPServer((host, port), AteeHandler)
    worker = None
    if CORE.config.async_review_worker_enabled:
        worker = AsyncReviewWorker(
            CORE,
            interval_seconds=CORE.config.async_review_worker_interval_seconds,
            batch_size=CORE.config.async_review_worker_batch_size,
        )
        worker.start()
    print(f"ATEE Core Service running at http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        if worker:
            worker.stop()
        server.server_close()

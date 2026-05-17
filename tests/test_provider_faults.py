import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "services" / "core-service"
sys.path.insert(0, str(CORE_PATH))

from atee_core.config import AdminConfig  # noqa: E402
from atee_core.core import CoreService  # noqa: E402


class ProviderFaultInjectionTests(unittest.TestCase):
    def test_fake_provider_success_redacts_request_body(self):
        with _FakeProvider("success") as provider, tempfile.TemporaryDirectory() as temp_dir:
            key_file = Path(temp_dir) / "provider.key"
            key_file.write_text("test-secret-value", encoding="utf-8")
            core = _core_for_provider(provider, key_file, temp_dir)

            result = core.check(_sensitive_login_payload())
            public_text = json.dumps({"result": result, "status": core.runtime_status()}, ensure_ascii=False)
            provider_payload = json.dumps(provider.bodies, ensure_ascii=False)

            self.assertTrue(result["llm_gateway"]["ok"])
            self.assertEqual(result["llm_gateway"]["reason"], "provider_json_decision")
            self.assertEqual(provider.calls, 1)
            self.assertNotIn("test-secret-value", public_text)
            self.assertNotIn("raw-user-password", public_text)
            self.assertNotIn("raw-user-password", provider_payload)
            self.assertIn("[REDACTED]", provider_payload)

    def test_provider_failures_open_circuit_and_skip_subsequent_remote_calls(self):
        with _FakeProvider("http_500") as provider, tempfile.TemporaryDirectory() as temp_dir:
            key_file = Path(temp_dir) / "provider.key"
            key_file.write_text("test-secret-value", encoding="utf-8")
            core = _core_for_provider(provider, key_file, temp_dir)

            results = [core.check(_sensitive_login_payload()) for _ in range(4)]
            reasons = [result["llm_gateway"]["reason"] for result in results]
            status = core.runtime_status()["llm_gateway"]
            public_text = json.dumps(
                {"results": results, "status": status, "recent": core.ledger_recent(limit=5)},
                ensure_ascii=False,
            )

            self.assertEqual(reasons[:3], ["provider_request_failed"] * 3)
            self.assertEqual(reasons[3], "llm_circuit_open")
            self.assertEqual(provider.calls, 3)
            self.assertTrue(status["circuit"]["open"])
            self.assertEqual(status["circuit"]["consecutive_failures"], 3)
            self.assertNotIn("test-secret-value", public_text)
            self.assertNotIn("raw-user-password", public_text)


class _FakeProvider:
    def __init__(self, mode: str):
        self.mode = mode
        self.calls = 0
        self.bodies: list[dict] = []
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}/v1"

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def _handler_class(self):
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw_body = self.rfile.read(length).decode("utf-8")
                with provider._lock:
                    provider.calls += 1
                    provider.bodies.append(json.loads(raw_body))

                if provider.mode == "http_500":
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b'{"error":"provider down"}')
                    return

                content = json.dumps({"selected_action": "challenge", "ai_confidence": 0.82})
                response = {"choices": [{"message": {"content": content}}]}
                data = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format, *args):
                return

        return Handler


def _core_for_provider(provider: _FakeProvider, key_file: Path, temp_dir: str) -> CoreService:
    return CoreService(
        config=AdminConfig(
            llm_mode="openai_compatible",
            llm_provider="fake-provider",
            llm_model="fake-model",
            llm_api_base=provider.base_url,
            llm_api_key_file=str(key_file),
            remote_soft_timeout_ms=100,
            remote_hard_timeout_ms=1000,
        ),
        config_path=Path(temp_dir) / "config" / "config.json",
    )


def _sensitive_login_payload() -> dict:
    return {
        "method": "POST",
        "path": "/login",
        "event_type": "login",
        "headers": {"Authorization": "Bearer raw-header-token"},
        "body": {
            "username": "alice",
            "password": "raw-user-password",
            "密钥": "raw-user-secret",
            "text": "普通登录",
        },
    }


if __name__ == "__main__":
    unittest.main()

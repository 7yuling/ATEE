import json
import os
import socket
import urllib.error
import urllib.request
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 25.0


class AteeThinAdapter:
    def __init__(self, core_url: str = "http://127.0.0.1:8787", timeout_seconds: float | None = None):
        self.core_url = core_url.rstrip("/")
        self.timeout_seconds = _adapter_timeout_seconds(timeout_seconds)

    def check(self, request_context: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/check", request_context)

    def event(self, request_context: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/event", request_context)

    def appeal(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/appeal", payload)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.core_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (TimeoutError, socket.timeout) as error:
            raise RuntimeError(f"ATEE Core request to {path} timed out after {self.timeout_seconds:g}s") from error
        except urllib.error.URLError as error:
            reason = getattr(error, "reason", error)
            raise RuntimeError(f"ATEE Core request to {path} failed: {reason}") from error


def _adapter_timeout_seconds(value: float | None = None) -> float:
    raw = os.environ.get("ATEE_ADAPTER_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)) if value is None else value
    try:
        timeout = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS
    return timeout if timeout > 0 else DEFAULT_TIMEOUT_SECONDS


def build_context(
    method: str,
    path: str,
    headers: dict[str, str],
    body: Any,
    remote_addr: str,
    event_type: str | None = None,
) -> dict[str, Any]:
    context = {
        "method": method,
        "path": path,
        "headers": headers,
        "body": body,
        "remote_addr": remote_addr,
    }
    if event_type:
        context["event_type"] = event_type
    return context

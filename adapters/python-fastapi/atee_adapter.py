import json
import urllib.request
from typing import Any


class AteeThinAdapter:
    def __init__(self, core_url: str = "http://127.0.0.1:8787"):
        self.core_url = core_url.rstrip("/")

    def check(self, request_context: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/check", request_context)

    def event(self, request_context: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/event", request_context)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.core_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))


def build_context(method: str, path: str, headers: dict[str, str], body: Any, remote_addr: str) -> dict[str, Any]:
    return {
        "method": method,
        "path": path,
        "headers": headers,
        "body": body,
        "remote_addr": remote_addr,
    }


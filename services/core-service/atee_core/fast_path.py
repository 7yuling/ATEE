from collections import defaultdict, deque
from time import time
from typing import Any

from .models import RequestContext


SKIP_EXTENSIONS = (
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
)

ATTACK_PATTERNS = {
    "FP_SQLI_001": ("union select", " or 1=1", "'or 1=1", "sleep("),
    "FP_XSS_001": ("<script", "onerror=", "javascript:"),
    "FP_PATH_001": ("../", "..\\", "/etc/passwd"),
    "FP_CMD_001": (";cat ", "&& whoami", "`whoami", "| bash"),
    "FP_SCAN_001": ("/.env", "/phpmyadmin", "/wp-admin"),
    "FP_UPLOAD_001": (".php.", ".phtml", "application/x-php"),
}


class FastPathRuleGate:
    def __init__(self, max_hits_per_minute: int = 60):
        self.max_hits_per_minute = max_hits_per_minute
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def evaluate(self, ctx: RequestContext, real_ip: dict[str, Any]) -> dict[str, Any]:
        path = ctx.path.lower()
        if ctx.method == "GET" and (path in ("/health", "/metrics") or path.endswith(SKIP_EXTENSIONS)):
            return self._result("skip", "FP_SKIP_001", "low-risk static or health path")

        haystack = self._haystack(ctx)
        for rule_id, patterns in ATTACK_PATTERNS.items():
            for pattern in patterns:
                if pattern in haystack:
                    return self._result("block_403", rule_id, "hard block pattern matched")

        if self._rate_limited(str(real_ip.get("client_ip")), path):
            return self._result("rate_limited", "FP_RATE_001", "short cooldown from high request rate")

        return self._result("pass", None, "no fast-path decision")

    def _rate_limited(self, client_ip: str, path: str) -> bool:
        now = time()
        key = (client_ip, path)
        hits = self._hits[key]
        while hits and now - hits[0] > 60:
            hits.popleft()
        hits.append(now)
        return len(hits) > self.max_hits_per_minute

    def _haystack(self, ctx: RequestContext) -> str:
        pieces = [ctx.path, str(ctx.query), self._summarize_body(ctx.body)]
        return " ".join(pieces).lower()

    def _summarize_body(self, body: Any) -> str:
        if body is None:
            return ""
        if isinstance(body, (dict, list, tuple)):
            return str(body)
        return str(body)[:4096]

    def _result(self, action: str, rule_id: str | None, reason: str) -> dict[str, Any]:
        return {
            "action": action,
            "rule_id": rule_id,
            "reason": reason,
            "llm_called": False,
        }


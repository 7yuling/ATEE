import ipaddress
import re
from collections import defaultdict, deque
from time import time
from typing import Any
from urllib.parse import urlsplit

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
    "FP_WEBSHELL_001": (
        "eval(request.",
        "eval(request[",
        "eval(request.item",
        "assert($_post",
        "base64_decode(",
        "runtime.getruntime().exec",
    ),
    "FP_UPLOAD_001": (".php.", ".phtml", "application/x-php"),
}

DANGEROUS_UPLOAD_EXTENSIONS = (
    ".php",
    ".phtml",
    ".jsp",
    ".jspx",
    ".asp",
    ".aspx",
    ".war",
    ".exe",
    ".dll",
    ".sh",
    ".bat",
)

LOW_RISK_GET_PATHS = {"/health", "/metrics", "/robots.txt"}
RATE_LIMITED_EVENT_TYPES = {"login", "admin_login", "register", "password_change", "api_key"}
RATE_LIMITED_PATH_MARKERS = ("/login", "/admin", "/auth", "/token")
SSRF_HOST_MARKERS = (
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "[::1]",
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.azure.com",
    "metadata.oraclecloud.com",
)
URL_RE = re.compile(r"https?://[^\s'\"<>)}\]]+", re.IGNORECASE)
FILENAME_RE = re.compile(r"filename['\"]?\s*[:=]\s*['\"]?([^'\",}\s]+)", re.IGNORECASE)


class FastPathRuleGate:
    def __init__(self, max_hits_per_minute: int = 60):
        self.max_hits_per_minute = max_hits_per_minute
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def evaluate(self, ctx: RequestContext, real_ip: dict[str, Any]) -> dict[str, Any]:
        path = ctx.path.lower()
        if ctx.method == "GET" and (path in LOW_RISK_GET_PATHS or path.endswith(SKIP_EXTENSIONS)):
            return self._result("skip", "FP_SKIP_001", "low-risk static or health path")

        haystack = self._haystack(ctx)
        if self._matches_ssrf(haystack):
            return self._result("block_403", "FP_SSRF_001", "server-side request forgery target matched")

        for rule_id, patterns in ATTACK_PATTERNS.items():
            for pattern in patterns:
                if pattern in haystack:
                    return self._result("block_403", rule_id, "hard block pattern matched")

        if self._matches_dangerous_upload(ctx, haystack):
            return self._result("block_403", "FP_UPLOAD_001", "dangerous upload extension matched")

        if self._should_rate_limit(ctx, path) and self._rate_limited(str(real_ip.get("client_ip")), path):
            return self._result("rate_limited", "FP_RATE_001", "short cooldown from high request rate")

        return self._result("pass", None, "no fast-path decision")

    def _matches_ssrf(self, haystack: str) -> bool:
        if any(marker in haystack for marker in SSRF_HOST_MARKERS):
            return True
        for raw_url in URL_RE.findall(haystack):
            try:
                host = urlsplit(raw_url).hostname
            except ValueError:
                continue
            if not host:
                continue
            try:
                ip = ipaddress.ip_address(host.strip("[]"))
            except ValueError:
                continue
            if ip.is_loopback or ip.is_link_local or ip.is_private:
                return True
        return False

    def _matches_dangerous_upload(self, ctx: RequestContext, haystack: str) -> bool:
        if "upload" not in ctx.path.lower() and "filename" not in haystack and "content_type" not in haystack:
            return False
        for filename in FILENAME_RE.findall(haystack):
            cleaned = filename.lower().split("\x00", 1)[0].rstrip(". ")
            if cleaned.endswith(DANGEROUS_UPLOAD_EXTENSIONS):
                return True
        return any(f"'{extension}'" in haystack or f'"{extension}"' in haystack for extension in DANGEROUS_UPLOAD_EXTENSIONS)

    def _should_rate_limit(self, ctx: RequestContext, path: str) -> bool:
        if ctx.method in {"GET", "HEAD", "OPTIONS"}:
            return False
        event_type = (ctx.event_type or "").strip().lower().replace("-", "_")
        return event_type in RATE_LIMITED_EVENT_TYPES or any(marker in path for marker in RATE_LIMITED_PATH_MARKERS)

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

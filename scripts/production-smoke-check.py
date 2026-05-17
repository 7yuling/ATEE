import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a sanitized ATEE production reverse-proxy smoke check.")
    parser.add_argument("--base-url", required=True, help="ATEE public base URL, for example https://atee.example.com")
    parser.add_argument("--allow-http", action="store_true", help="Allow http:// targets for local rehearsal only")
    parser.add_argument("--expect-admin-auth", action="store_true", help="Require /v1/admin/* to reject unauthenticated requests")
    parser.add_argument("--admin-token-env", default="ATEE_ADMIN_TOKEN", help="Environment variable containing the Admin Token")
    parser.add_argument("--verify-audit-actor", action="store_true", help="Write one safe admin audit probe and verify ledger attribution")
    parser.add_argument("--audit-actor-id", default="production-smoke-check", help="Client-side actor header sent during audit probe")
    parser.add_argument("--expected-audit-actor", help="Expected actor id after SSO/proxy rewriting")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--report", type=Path, help="Write a sanitized Markdown report")
    args = parser.parse_args()

    runner = SmokeRunner(args)
    summary = runner.run()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(_markdown_report(summary), encoding="utf-8")
        summary["report_path"] = str(args.report)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


class SmokeRunner:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.base_url = args.base_url.rstrip("/")
        self.parsed = urllib.parse.urlparse(self.base_url)
        self.token = os.environ.get(args.admin_token_env, "")
        self.checks: list[dict[str, Any]] = []

    def run(self) -> dict[str, Any]:
        self._check_target_scheme()
        self._check_health()
        html = self._check_admin_console()
        self._check_admin_assets(html)
        self._check_runtime_status()
        self._check_admin_auth()
        if self.args.verify_audit_actor:
            self._check_audit_actor()
        ok = all(check.get("ok") or check.get("skipped") for check in self.checks)
        return {
            "ok": ok,
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "target": {
                "scheme": self.parsed.scheme,
                "host_configured": bool(self.parsed.netloc),
                "https": self.parsed.scheme == "https",
            },
            "checks": self.checks,
        }

    def _record(self, name: str, ok: bool, **details: Any) -> None:
        self.checks.append({"name": name, "ok": bool(ok), **_sanitize(details)})

    def _skip(self, name: str, reason: str) -> None:
        self.checks.append({"name": name, "ok": False, "skipped": True, "reason": reason})

    def _check_target_scheme(self) -> None:
        ok = self.parsed.scheme == "https" or (self.args.allow_http and self.parsed.scheme == "http")
        self._record("target_scheme", ok, https=self.parsed.scheme == "https", local_http_allowed=bool(self.args.allow_http))

    def _check_health(self) -> None:
        status, _, body = self._request("GET", "/health")
        payload = _json_body(body)
        self._record("health", status == 200 and payload.get("ok") is True, status=status)

    def _check_admin_console(self) -> str:
        status, headers, body = self._request("GET", "/")
        csp = headers.get("Content-Security-Policy", "")
        security_headers_ok = True
        if not self.args.allow_http:
            security_headers_ok = (
                bool(headers.get("Strict-Transport-Security"))
                and headers.get("X-Content-Type-Options", "").lower() == "nosniff"
                and bool(headers.get("Referrer-Policy"))
            )
        ok = (
            status == 200
            and "ATEE" in body
            and "script-src 'self'" in csp
            and "object-src 'none'" in csp
            and security_headers_ok
        )
        self._record("admin_console", ok, status=status, security_headers_ok=security_headers_ok)
        return body

    def _check_admin_assets(self, html: str) -> None:
        assets = _admin_asset_paths(html)
        if not assets:
            self._record("admin_assets", False, asset_count=0)
            return
        failures = 0
        for asset in assets:
            status, headers, body = self._request("GET", asset)
            content_type = headers.get("Content-Type", "")
            if status != 200 or not body:
                failures += 1
                continue
            if asset.endswith(".js") and "javascript" not in content_type:
                failures += 1
            if asset.endswith(".css") and "text/css" not in content_type:
                failures += 1
        self._record("admin_assets", failures == 0, asset_count=len(assets), failures=failures)

    def _check_runtime_status(self) -> None:
        status, _, body = self._request("GET", "/v1/runtime/status")
        payload = _json_body(body)
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        ok = status == 200 and payload.get("display", {}).get("locale") == "zh-CN" and not _contains_secret(text)
        self._record(
            "runtime_status",
            ok,
            status=status,
            locale=payload.get("display", {}).get("locale"),
            secret_like_output=_contains_secret(text),
        )

    def _check_admin_auth(self) -> None:
        status, _, body = self._request("GET", "/v1/admin/config")
        payload = _json_body(body)
        rejects_without_token = status == 401 or payload.get("error") == "admin_auth_required"
        if self.args.expect_admin_auth:
            self._record("admin_auth_required", rejects_without_token, status=status)
        else:
            self._record("admin_auth_observed", True, rejects_without_token=rejects_without_token)

        if not self.token:
            reason = "admin_token_env_not_set" if self.args.expect_admin_auth else "admin_token_env_not_set_optional"
            self._skip("admin_auth_with_token", reason)
            return
        status, _, body = self._request("GET", "/v1/admin/config", headers=self._auth_headers())
        payload = _json_body(body)
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self._record("admin_auth_with_token", status == 200 and payload.get("ok") is True and self.token not in text, status=status)

    def _check_audit_actor(self) -> None:
        if not self.token:
            self._record("audit_actor", False, reason="admin_token_env_not_set")
            return
        expected_actor = self.args.expected_audit_actor or self.args.audit_actor_id
        headers = self._auth_headers()
        headers["X-ATEE-Admin-Id"] = self.args.audit_actor_id
        status, _, _ = self._request("POST", "/v1/admin/break-glass/status", headers=headers, payload={})
        ledger_status, _, ledger_body = self._request("GET", "/v1/admin/ledger/recent?limit=20", headers=self._auth_headers())
        ledger = _json_body(ledger_body)
        summaries = "\n".join(str(record.get("summary") or "") for record in ledger.get("records") or [])
        ok = (
            status == 200
            and ledger_status == 200
            and f"admin_actor_id={expected_actor}" in summaries
            and "admin_actor_hash=sha256:" in summaries
            and "admin_source_hash=sha256:" in summaries
            and self.token not in summaries
        )
        if self.args.expected_audit_actor and self.args.expected_audit_actor != self.args.audit_actor_id:
            ok = ok and f"admin_actor_id={self.args.audit_actor_id}" not in summaries
        self._record("audit_actor", ok, status=status, ledger_status=ledger_status, actor_matched=ok)

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def _request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, str], str]:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(headers or {})
        request = urllib.request.Request(self.base_url + path, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.args.timeout) as response:
                return int(response.status), dict(response.headers), response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            try:
                return int(error.code), dict(error.headers), error.read().decode("utf-8", errors="replace")
            finally:
                error.close()
        except (OSError, TimeoutError) as exc:
            return 0, {}, json.dumps({"error": exc.__class__.__name__})


def _admin_asset_paths(html: str) -> list[str]:
    paths = set(re.findall(r'(?:src|href)="(/admin/[^"]+\.(?:js|css))"', html))
    return sorted(paths)


def _json_body(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _contains_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items() if key not in {"token", "authorization", "base_url"}}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        sanitized = value
        for pattern in SECRET_PATTERNS:
            sanitized = pattern.sub("<redacted>", sanitized)
        return sanitized
    return value


def _markdown_report(summary: dict[str, Any]) -> str:
    target = summary.get("target") or {}
    lines = [
        "# ATEE Production Smoke Check Report",
        "",
        f"- Generated at: {summary.get('generated_at')}",
        f"- Overall ok: {summary.get('ok')}",
        f"- HTTPS: {target.get('https')}",
        f"- Host configured: {target.get('host_configured')}",
        "",
        "## Checks",
    ]
    for check in summary.get("checks") or []:
        state = "SKIPPED" if check.get("skipped") else ("OK" if check.get("ok") else "FAIL")
        lines.append(f"- {check.get('name')}: {state}")
    lines.extend(
        [
            "",
            "## Security Notes",
            "- This report intentionally omits the full target URL, Admin Token, authorization headers, and actor identifiers.",
            "- Use `--verify-audit-actor` only when writing one admin audit probe is acceptable.",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())

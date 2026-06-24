import argparse
import json
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "services" / "core-service"
sys.path.insert(0, str(CORE_PATH))

from atee_core.config import AdminConfig  # noqa: E402
from atee_core.core import CoreService  # noqa: E402
from atee_core import http_server  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a sanitized ATEE feature-ban closure smoke check.")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    summary = run_smoke()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(markdown_report(summary), encoding="utf-8")
        summary["report_path"] = str(args.report)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


def run_smoke() -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    checks: list[dict[str, Any]] = []
    previous_core = http_server.CORE
    with tempfile.TemporaryDirectory(prefix="atee-feature-ban-smoke-") as temp_dir:
        http_server.CORE = CoreService(
            config=AdminConfig(runtime_mode="auto", llm_mode="mock", llm_provider="mock", llm_model="atee-local-mock-v1"),
            config_path=Path(temp_dir) / "config" / "config.json",
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), http_server.AteeHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
            _run_flow(base_url, checks)
        except Exception as error:  # pragma: no cover - defensive report path
            checks.append({"name": "feature_ban_smoke_exception", "ok": False, "reason": type(error).__name__})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            http_server.CORE = previous_core

    passed = sum(1 for check in checks if check.get("ok"))
    return {
        "ok": passed == len(checks) and bool(checks),
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "mode": "local_http",
        "checks": checks,
        "totals": {"passed": passed, "total": len(checks)},
        "security": {
            "raw_prompt_stored": False,
            "raw_request_body_stored": False,
            "secrets_omitted": True,
        },
    }


def _run_flow(base_url: str, checks: list[dict[str, Any]]) -> None:
    site = _post(
        base_url,
        "/v1/admin/sites",
        {
            "name": "feature-ban-smoke-site",
            "base_url": "https://feature-ban-smoke.example",
            "environment": "staging",
            "allowed_domains": ["feature-ban-smoke.example"],
            "protected_features": ["uploads", "comments"],
            "page_guard_enabled": True,
        },
    )
    site_id = ((site.get("site") or {}).get("id"))
    _check(checks, "managed_site_registered", site.get("ok") and site_id, status=site.get("status", 200))

    site_fuse = _post(
        base_url,
        "/v1/admin/site-feature-bans",
        {
            "site_id": site_id,
            "feature_scope": "uploads",
            "duration_seconds": 3600,
            "reason": "feature ban closure smoke",
        },
    )
    site_action = ((site_fuse.get("action_result") or {}).get("record") or {})
    site_action_id = site_action.get("id")
    _check(
        checks,
        "site_feature_ban_created",
        site_fuse.get("ok") and site_action.get("action") == "feature_ban",
        status=site_fuse.get("status", 200),
        effective_action=site_action.get("action"),
        target_type=(site_action.get("target_scope") or {}).get("type"),
    )

    blocked_one = _feature_access(base_url, site_id, "site-user-one", "uploads")
    blocked_two = _feature_access(base_url, site_id, "site-user-two", "uploads")
    _check(
        checks,
        "site_feature_access_blocks_all_users",
        all(
            not item.get("allowed")
            and item.get("reason") == "active_site_feature_ban"
            and item.get("punishment_id") is None
            for item in (blocked_one, blocked_two)
        ),
        reason="active_site_feature_ban",
        blocked_count=sum(1 for item in (blocked_one, blocked_two) if not item.get("allowed")),
        punishment_id_omitted=blocked_one.get("punishment_id") is None and blocked_two.get("punishment_id") is None,
    )

    action_list = _get(base_url, "/v1/admin/actions?status=active")
    ledger = _get(base_url, "/v1/admin/ledger/recent?limit=20&details=1")
    _check(
        checks,
        "site_feature_ban_listed_and_ledgered",
        action_list.get("count", 0) >= 1 and ledger.get("count", len(ledger.get("records") or [])) >= 1,
        active_actions=action_list.get("count", 0),
        ledger_records=ledger.get("count", len(ledger.get("records") or [])),
    )

    site_punishment_id = f"action:{site_action_id}"
    _post(base_url, "/v1/appeal", {"punishment_id": site_punishment_id, "reason": "please review"})
    site_review = _post(
        base_url,
        "/v1/admin/appeals/review",
        {"punishment_id": site_punishment_id, "resolution": "approved", "admin_note": "reviewed"},
    )
    still_blocked = _feature_access(base_url, site_id, "site-user-one", "uploads")
    _check(
        checks,
        "site_feature_appeal_does_not_auto_unban",
        (site_review.get("auto_unban") or {}).get("reason") == "action_is_not_user_feature_ban"
        and not still_blocked.get("allowed"),
        reason=(site_review.get("auto_unban") or {}).get("reason"),
        still_blocked=not still_blocked.get("allowed"),
    )

    site_revoked = _post(
        base_url,
        "/v1/admin/actions/revoke",
        {"action_id": site_action_id, "reason": "feature ban closure smoke restore"},
    )
    site_restored = _feature_access(base_url, site_id, "site-user-one", "uploads")
    _check(
        checks,
        "site_feature_admin_revoke_restores_access",
        site_revoked.get("ok") and site_restored.get("allowed"),
        revoke_reason=site_revoked.get("reason", "revoked"),
        access_reason=site_restored.get("reason"),
    )

    queued = _post(
        base_url,
        "/v1/check",
        {
            "method": "POST",
            "path": "/comment",
            "event_type": "comment_create",
            "feature_scope": "comments",
            "user_id": "manual-feature-ban-smoke-user",
            "body": {"text": "manual review candidate"},
        },
    )
    job_id = (queued.get("async_review_job") or {}).get("id")
    _check(
        checks,
        "async_review_job_queued_for_manual_feature_ban",
        queued.get("route", {}).get("route") == "async_agent" and bool(job_id),
        route=(queued.get("route") or {}).get("route"),
    )

    manual = _post(
        base_url,
        "/v1/admin/async-reviews/manual-action",
        {"job_id": job_id, "duration_seconds": 7200, "admin_note": "confirmed abuse pattern"},
    )
    user_action = ((manual.get("action_result") or {}).get("record") or {})
    _check(
        checks,
        "manual_async_review_records_user_feature_ban",
        manual.get("ok")
        and user_action.get("action") == "feature_ban"
        and (user_action.get("target_scope") or {}).get("type") == "user_feature",
        status=manual.get("status", 200),
        effective_action=user_action.get("action"),
        target_type=(user_action.get("target_scope") or {}).get("type"),
    )

    user_blocked = _feature_access(base_url, None, "manual-feature-ban-smoke-user", "comments")
    _check(
        checks,
        "user_feature_ban_blocks_feature_access",
        not user_blocked.get("allowed") and user_blocked.get("reason") == "active_feature_ban",
        reason=user_blocked.get("reason"),
        punishment_id_present=bool(user_blocked.get("punishment_id")),
    )

    user_punishment_id = user_blocked.get("punishment_id") or user_action.get("punishment_id")
    _post(base_url, "/v1/appeal", {"punishment_id": user_punishment_id, "reason": "please review"})
    user_review = _post(
        base_url,
        "/v1/admin/appeals/review",
        {"punishment_id": user_punishment_id, "resolution": "approved", "admin_note": "reviewed"},
    )
    user_restored = _feature_access(base_url, None, "manual-feature-ban-smoke-user", "comments")
    _check(
        checks,
        "user_feature_appeal_auto_unbans",
        (user_review.get("auto_unban") or {}).get("reason") == "feature_ban_revoked" and user_restored.get("allowed"),
        reason=(user_review.get("auto_unban") or {}).get("reason"),
        access_reason=user_restored.get("reason"),
    )


def _check(checks: list[dict[str, Any]], name: str, ok: Any, **details: Any) -> None:
    check = {"name": name, "ok": bool(ok)}
    for key, value in details.items():
        if value is not None:
            check[key] = value
    checks.append(check)


def _feature_access(base_url: str, site_id: int | None, user_id: str, feature_scope: str) -> dict[str, Any]:
    payload = {"user_id": user_id, "feature_scope": feature_scope}
    if site_id is not None:
        payload["site_id"] = site_id
    return _post(base_url, "/v1/feature-access", payload)


def _get(base_url: str, path: str) -> dict[str, Any]:
    return _request("GET", f"{base_url}{path}", None)


def _post(base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _request("POST", f"{base_url}{path}", payload)


def _request(method: str, url: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            return json.loads(error.read().decode("utf-8"))
        except json.JSONDecodeError:
            return {"ok": False, "status": error.code, "reason": "http_error"}


def markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# ATEE Feature Ban Closure Smoke",
        "",
        f"- OK: {summary.get('ok')}",
        f"- Mode: {summary.get('mode')}",
        f"- Started: {summary.get('started_at')}",
        f"- Completed: {summary.get('completed_at')}",
        "",
        "## Checks",
        "",
        "| Check | OK | Reason | Route | Effective action | Target |",
        "|---|---|---|---|---|---|",
    ]
    for check in summary.get("checks") or []:
        lines.append(
            "| {name} | {ok} | {reason} | {route} | {action} | {target} |".format(
                name=check.get("name"),
                ok=check.get("ok"),
                reason=check.get("reason") or check.get("access_reason") or "-",
                route=check.get("route") or "-",
                action=check.get("effective_action") or "-",
                target=check.get("target_type") or "-",
            )
        )
    security = summary.get("security") or {}
    lines.extend(
        [
            "",
            "## Security Notes",
            "",
            f"- Raw prompt stored: {bool(security.get('raw_prompt_stored'))}",
            f"- Raw request body stored: {bool(security.get('raw_request_body_stored'))}",
            f"- Secrets omitted: {bool(security.get('secrets_omitted'))}",
            "- API keys, auth headers, provider endpoints, proxy URLs, raw prompts, and raw request bodies are intentionally omitted.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

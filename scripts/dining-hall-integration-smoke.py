import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit


DEFAULT_CORE_URL = "http://127.0.0.1:8787"
DEFAULT_SITE_URL = "http://127.0.0.1:5001/"
DEFAULT_SITE_NAME = "dining-hall-demo"

DINING_HALL_PROTECTED_FEATURES = [
    "login",
    "register",
    "posts",
    "comments",
    "delete_posts",
    "delete_topics",
    "admin_actions",
    "account_settings",
]

DINING_HALL_CUSTOM_PATH_RULES = [
    {"methods": ["POST"], "path_regex": r"^/api/topics/\d+/pin$", "feature_scope": "admin_actions"},
    {"methods": ["PUT"], "path": "/api/me/password", "feature_scope": "account_settings"},
]

PROTECTED_WRITE_CHECKS = [
    ("posts", "POST", "/api/topics", {"title": "atee smoke blocked", "description": "blocked"}),
    ("comments", "POST", "/api/topics/1/posts", {"content": "atee smoke blocked"}),
    ("delete_topics", "DELETE", "/api/topics/1", {}),
    ("admin_actions", "POST", "/api/topics/1/pin", {}),
    ("account_settings", "PUT", "/api/me/password", {"old_password": "old", "new_password": "newpass1"}),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Register and smoke-check the Dining Hall demo through ATEE Site Proxy.")
    parser.add_argument("--core-url", default=DEFAULT_CORE_URL, help="ATEE Core URL, default http://127.0.0.1:8787")
    parser.add_argument("--site-url", default=DEFAULT_SITE_URL, help="Dining Hall URL, default http://127.0.0.1:5001/")
    parser.add_argument("--site-name", default=DEFAULT_SITE_NAME, help="Managed site name.")
    parser.add_argument("--admin-token", default="", help="ATEE admin token. Prefer --admin-token-env for shell history safety.")
    parser.add_argument("--admin-token-env", default="ATEE_ADMIN_TOKEN", help="Environment variable containing the ATEE admin token.")
    parser.add_argument("--skip-block-checks", action="store_true", help="Only register and verify proxy HTML injection.")
    parser.add_argument("--keep-feature-bans", action="store_true", help="Leave temporary site feature bans active after checks.")
    args = parser.parse_args()

    token = args.admin_token or os.environ.get(args.admin_token_env, "")
    summary = run_smoke(
        core_url=args.core_url,
        site_url=args.site_url,
        site_name=args.site_name,
        admin_token=token,
        run_block_checks=not args.skip_block_checks,
        cleanup_feature_bans=not args.keep_feature_bans,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


def build_site_payload(site_url: str = DEFAULT_SITE_URL, site_name: str = DEFAULT_SITE_NAME, site_id: int | None = None) -> dict[str, Any]:
    normalized_site_url = _normalize_base_url(site_url)
    payload: dict[str, Any] = {
        "name": site_name,
        "base_url": normalized_site_url,
        "environment": "staging",
        "allowed_domains": _allowed_domains(normalized_site_url),
        "auth_mode": "none",
        "protected_features": list(DINING_HALL_PROTECTED_FEATURES),
        "page_guard_enabled": True,
        "site_proxy": {
            "enabled": True,
            "auto_apply_admin_actions": False,
            "path_rules": list(DINING_HALL_CUSTOM_PATH_RULES),
        },
    }
    if site_id:
        payload["id"] = int(site_id)
    return payload


def run_smoke(
    core_url: str,
    site_url: str,
    site_name: str,
    admin_token: str = "",
    run_block_checks: bool = True,
    cleanup_feature_bans: bool = True,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    core_url = core_url.rstrip("/")
    checks: list[dict[str, Any]] = []
    created_action_ids: list[int] = []

    core_health = _request_json("GET", urljoin(core_url + "/", "health"), admin_token=admin_token)
    _check(checks, "atee_core_reachable", core_health["status"] == 200 and core_health["json"].get("ok") is True, status=core_health["status"])

    site_health = _request_text("GET", _normalize_base_url(site_url))
    _check(checks, "dining_hall_reachable", site_health["status"] == 200, status=site_health["status"])

    existing_site_id = _find_existing_site_id(core_url, site_name, site_url, admin_token)
    registration_payload = build_site_payload(site_url, site_name, existing_site_id)
    registered = _request_json(
        "POST",
        urljoin(core_url + "/", "v1/admin/sites"),
        registration_payload,
        admin_token=admin_token,
    )
    site = registered["json"].get("site") if isinstance(registered["json"].get("site"), dict) else {}
    site_id = int(site.get("id") or 0)
    proxy_path = str((site.get("site_proxy") or {}).get("proxy_path") or "")
    _check(
        checks,
        "dining_hall_site_registered",
        registered["status"] < 400 and registered["json"].get("ok") is True and site_id > 0,
        status=registered["status"],
        site_id=site_id or None,
        updated_existing=bool(existing_site_id),
    )
    _check(
        checks,
        "dining_hall_custom_rules_present",
        _has_rule(site, DINING_HALL_CUSTOM_PATH_RULES[0]) and _has_rule(site, DINING_HALL_CUSTOM_PATH_RULES[1]),
        site_id=site_id or None,
    )

    if site_id:
        proxy_html = _request_text("GET", urljoin(core_url + "/", proxy_path.lstrip("/")))
        _check(
            checks,
            "site_proxy_runtime_guard_injected",
            proxy_html["status"] == 200 and f'src="{proxy_path.rstrip("/")}/atee-runtime-guard.js"' in proxy_html["text"],
            status=proxy_html["status"],
        )

    if site_id and run_block_checks:
        try:
            for feature, method, path, payload in PROTECTED_WRITE_CHECKS:
                fuse = _request_json(
                    "POST",
                    urljoin(core_url + "/", "v1/admin/site-feature-bans"),
                    {"site_id": site_id, "feature_scope": feature, "duration_seconds": 600, "reason": "dining hall integration smoke"},
                    admin_token=admin_token,
                )
                action_id = (((fuse["json"].get("action_result") or {}).get("record") or {}).get("id"))
                if action_id:
                    created_action_ids.append(int(action_id))
                proxied_write = _request_json(
                    method,
                    urljoin(core_url + "/", f"{proxy_path.strip('/')}{path}"),
                    payload,
                    admin_token=admin_token,
                )
                _check(
                    checks,
                    f"protected_write_blocks_{feature}",
                    proxied_write["status"] == 403
                    and proxied_write["json"].get("atee_blocked") is True
                    and proxied_write["json"].get("feature_scope") == feature,
                    status=proxied_write["status"],
                    feature_scope=proxied_write["json"].get("feature_scope"),
                )
        finally:
            if cleanup_feature_bans:
                for action_id in created_action_ids:
                    _request_json(
                        "POST",
                        urljoin(core_url + "/", "v1/admin/actions/revoke"),
                        {"action_id": action_id, "reason": "dining hall integration smoke cleanup"},
                        admin_token=admin_token,
                    )

    passed = sum(1 for check in checks if check["ok"])
    return {
        "ok": bool(checks) and passed == len(checks),
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "core_url": core_url,
        "site_url": _normalize_base_url(site_url),
        "site_name": site_name,
        "site_id": site_id or None,
        "proxy_url": urljoin(core_url + "/", proxy_path.lstrip("/")) if proxy_path else "",
        "checks": checks,
        "totals": {"passed": passed, "total": len(checks)},
        "security": {"admin_token_echoed": False, "target_secrets_echoed": False},
    }


def _find_existing_site_id(core_url: str, site_name: str, site_url: str, admin_token: str) -> int | None:
    response = _request_json("GET", urljoin(core_url.rstrip("/") + "/", "v1/admin/sites"), admin_token=admin_token)
    if response["status"] >= 400:
        return None
    normalized_url = _normalize_base_url(site_url)
    for site in response["json"].get("sites") or []:
        if not isinstance(site, dict):
            continue
        if site.get("name") == site_name or site.get("base_url") == normalized_url:
            try:
                return int(site.get("id") or 0) or None
            except (TypeError, ValueError):
                return None
    return None


def _allowed_domains(site_url: str) -> list[str]:
    host = (urlsplit(site_url).hostname or "127.0.0.1").lower()
    domains = [host]
    if host == "127.0.0.1":
        domains.append("localhost")
    elif host == "localhost":
        domains.append("127.0.0.1")
    return domains


def _normalize_base_url(site_url: str) -> str:
    parsed = urlsplit(site_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("site_url must be an absolute http(s) URL")
    path = parsed.path or "/"
    if not path.endswith("/"):
        path = path + "/"
    return parsed._replace(path=path, query="", fragment="").geturl()


def _has_rule(site: dict[str, Any], expected: dict[str, Any]) -> bool:
    rules = ((site.get("site_proxy") or {}).get("path_rules") or [])
    return any(
        all(rule.get(key) == value for key, value in expected.items())
        for rule in rules
        if isinstance(rule, dict)
    )


def _check(checks: list[dict[str, Any]], name: str, ok: bool, **details: Any) -> None:
    check = {"name": name, "ok": bool(ok)}
    for key, value in details.items():
        if value is not None:
            check[key] = value
    checks.append(check)


def _request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    admin_token: str = "",
) -> dict[str, Any]:
    response = _request(method, url, payload, admin_token)
    try:
        parsed = json.loads(response["text"]) if response["text"] else {}
    except json.JSONDecodeError:
        parsed = {}
    return {**response, "json": parsed}


def _request_text(method: str, url: str, payload: dict[str, Any] | None = None, admin_token: str = "") -> dict[str, Any]:
    return _request(method, url, payload, admin_token)


def _request(method: str, url: str, payload: dict[str, Any] | None = None, admin_token: str = "") -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Accept", "application/json, text/html;q=0.9, */*;q=0.8")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    if admin_token:
        request.add_header("Authorization", f"Bearer {admin_token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return {
                "status": int(response.status),
                "text": response.read().decode("utf-8", errors="replace"),
            }
    except urllib.error.HTTPError as error:
        try:
            text = error.read().decode("utf-8", errors="replace")
        finally:
            error.close()
        return {"status": int(error.code), "text": text}
    except urllib.error.URLError as error:
        return {"status": 0, "text": str(error.reason)}


if __name__ == "__main__":
    sys.exit(main())

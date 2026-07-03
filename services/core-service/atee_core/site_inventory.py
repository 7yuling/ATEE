import json
import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


SITE_ENVIRONMENTS = {"dev", "test", "staging", "production"}
AUTH_MODES = {"none", "storage_state", "cookies"}
ACTION_TYPES = {
    "login",
    "register",
    "submit",
    "search",
    "save",
    "delete",
    "menu",
    "pagination",
    "dialog_trigger",
    "dialog_confirm",
    "upload",
    "navigation",
    "form_field",
    "unknown",
}
RISK_LEVELS = {"low", "medium", "high", "critical"}
SITE_PROXY_DEFAULT_FEATURES = [
    "login",
    "register",
    "posts",
    "comments",
    "uploads",
    "delete_posts",
    "delete_topics",
    "admin_actions",
]
SITE_PROXY_DEFAULT_ACTION_TYPES = ["login", "register", "submit", "delete", "upload"]
SITE_PROXY_DEFAULT_FEATURE_MAP = {
    "#btn-login": "login",
    "#login-btn": "login",
    "#reg-btn": "register",
    "#btn-create": "posts",
    "#send-btn": "comments",
    "login": "login",
    "register": "register",
    "upload": "uploads",
    "delete": "delete_posts",
}
SITE_PROXY_DEFAULT_PATH_RULES = [
    {"methods": ["POST"], "path": "/api/login", "feature_scope": "login"},
    {"methods": ["POST"], "path": "/api/register", "feature_scope": "register"},
    {"methods": ["POST"], "path": "/api/topics", "feature_scope": "posts"},
    {"methods": ["POST"], "path_regex": r"^/api/topics/\d+/posts$", "feature_scope": "comments"},
    {"methods": ["DELETE"], "path_regex": r"^/api/posts/\d+$", "feature_scope": "delete_posts"},
    {"methods": ["DELETE"], "path_regex": r"^/api/topics/\d+$", "feature_scope": "delete_topics"},
    {"methods": ["POST", "PUT", "PATCH", "DELETE"], "path_prefix": "/api/admin/", "feature_scope": "admin_actions"},
]
SITE_PROXY_ALLOWED_RULE_KEYS = {"methods", "path", "path_prefix", "path_regex", "feature_scope"}
SITE_PROXY_ALLOWED_TEMPLATE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class SiteProxyConfigMixin:
    def _site_proxy_config(
        self,
        value: Any,
        protected_features: list[str] | None = None,
        site_id: int | None = None,
    ) -> dict[str, Any]:
        payload = value if isinstance(value, dict) else {}
        enabled = payload.get("enabled")
        feature_map = self._feature_map(payload.get("feature_map"))
        protected_action_types = self._features(
            payload.get("protected_action_types") or SITE_PROXY_DEFAULT_ACTION_TYPES
        ) or list(SITE_PROXY_DEFAULT_ACTION_TYPES)
        protected = self._unique_features(
            [
                *SITE_PROXY_DEFAULT_FEATURES,
                *(protected_features or []),
                *feature_map.values(),
                *(rule["feature_scope"] for rule in self._path_rules(payload.get("path_rules"))),
            ]
        )
        return {
            "enabled": True if enabled is None else bool(enabled),
            "standard": "atee_site_proxy_v1",
            "mode": "reverse_proxy_injection",
            "proxy_path": f"/proxy/sites/{site_id}/" if site_id else "",
            "feature_access_path": f"/proxy/sites/{site_id}/v1/feature-access" if site_id else "",
            "user_id_headers": self._user_id_headers(payload.get("user_id_headers")),
            "protected_features": protected,
            "protected_action_types": protected_action_types[:20],
            "feature_map": feature_map,
            "path_rules": self._path_rules(payload.get("path_rules")),
            "admin_session_enabled": bool(payload.get("admin_session_enabled")),
            "admin_session_ref": self._text(payload.get("admin_session_ref"), "", 240),
            "admin_action_templates": self._admin_action_templates(payload.get("admin_action_templates")),
            "auto_apply_admin_actions": False if payload.get("auto_apply_admin_actions") is False else True,
            "observe_actions": False if payload.get("observe_actions") is False else True,
            "observe_events": bool(payload.get("observe_events")),
        }

    def _feature_map(self, value: Any) -> dict[str, str]:
        payload = value if isinstance(value, dict) else {}
        merged = dict(SITE_PROXY_DEFAULT_FEATURE_MAP)
        for key, raw_feature in payload.items():
            selector = self._text(key, "", 160)
            feature = self._text(raw_feature, "", 120)
            if selector and feature:
                merged[selector] = feature
        return dict(list(merged.items())[:100])

    def _path_rules(self, value: Any) -> list[dict[str, Any]]:
        raw_rules = value if isinstance(value, list) else []
        merged = [dict(rule) for rule in SITE_PROXY_DEFAULT_PATH_RULES]
        for raw_rule in raw_rules:
            if not isinstance(raw_rule, dict):
                continue
            rule = {key: raw_rule.get(key) for key in SITE_PROXY_ALLOWED_RULE_KEYS if key in raw_rule}
            feature = self._text(rule.get("feature_scope"), "", 120)
            if not feature:
                continue
            methods = raw_rule.get("methods") or raw_rule.get("method") or []
            if isinstance(methods, str):
                methods = [methods]
            methods = [self._text(method, "", 12).upper() for method in methods]
            methods = [method for method in methods if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}]
            if not methods:
                continue
            normalized: dict[str, Any] = {"methods": methods[:5], "feature_scope": feature}
            for key in ("path", "path_prefix", "path_regex"):
                text = self._text(rule.get(key), "", 240)
                if not text:
                    continue
                if key == "path_regex":
                    try:
                        re.compile(text)
                    except re.error:
                        continue
                normalized[key] = text
                break
            if any(key in normalized for key in ("path", "path_prefix", "path_regex")):
                merged.append(normalized)
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for rule in merged:
            key = (
                tuple(rule.get("methods") or []),
                rule.get("path") or "",
                rule.get("path_prefix") or "",
                rule.get("path_regex") or "",
                rule.get("feature_scope") or "",
            )
            if key not in seen:
                deduped.append(rule)
                seen.add(key)
        return deduped[:50]

    def _admin_action_templates(self, value: Any) -> dict[str, dict[str, Any]]:
        raw_templates = value if isinstance(value, dict) else {}
        templates: dict[str, dict[str, Any]] = {}
        for raw_feature, raw_template in raw_templates.items():
            feature = self._text(raw_feature, "", 120)
            if not feature or not isinstance(raw_template, dict):
                continue
            method = self._text(raw_template.get("method"), "POST", 12).upper()
            if method not in SITE_PROXY_ALLOWED_TEMPLATE_METHODS:
                method = "POST"
            path = self._text(raw_template.get("path"), "", 240)
            if not path.startswith("/"):
                continue
            success_status = raw_template.get("success_status", [200, 201, 202, 204])
            if isinstance(success_status, int):
                statuses = [success_status]
            elif isinstance(success_status, list):
                statuses = [self._bounded_int(item, 100, 599, 200) for item in success_status[:10]]
            else:
                statuses = [200, 201, 202, 204]
            templates[feature] = {
                "method": method,
                "path": path,
                "body_template": self._template_value(raw_template.get("body_template") or {}),
                "success_status": sorted(set(statuses)) or [200, 201, 202, 204],
            }
        return dict(list(templates.items())[:50])

    def _template_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            output: dict[str, Any] = {}
            for raw_key, raw_item in list(value.items())[:50]:
                key = self._text(raw_key, "", 80)
                if not key:
                    continue
                if any(marker in key.lower() for marker in ("authorization", "cookie", "token", "secret", "api_key", "password")):
                    output[key] = "[REDACTED_TEMPLATE_VALUE]"
                else:
                    output[key] = self._template_value(raw_item)
            return output
        if isinstance(value, list):
            return [self._template_value(item) for item in value[:50]]
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (int, float)):
            return value
        return self._text(value, "", 500)

    def _user_id_headers(self, value: Any) -> list[str]:
        if isinstance(value, str):
            raw_items = value.replace("\n", ",").split(",")
        elif isinstance(value, list):
            raw_items = value
        else:
            raw_items = ["X-ATEE-User-Id", "X-User-Id"]
        headers: list[str] = []
        for item in raw_items:
            header = self._text(item, "", 80)
            if header and header not in headers:
                headers.append(header)
        return headers[:10] or ["X-ATEE-User-Id", "X-User-Id"]

    def _unique_features(self, values: list[str]) -> list[str]:
        features: list[str] = []
        for item in values:
            feature = self._text(item, "", 120)
            if feature and feature not in features:
                features.append(feature)
        return features[:100]

    def _features(self, value: Any) -> list[str]:
        if isinstance(value, str):
            raw_items = value.replace("\n", ",").split(",")
        elif isinstance(value, list):
            raw_items = value
        else:
            raw_items = []
        features: list[str] = []
        for item in raw_items:
            feature = self._text(item, "", 120)
            if feature and feature not in features:
                features.append(feature)
        return features[:50]

    def _bounded_int(self, value: Any, minimum: int, maximum: int, default: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(minimum, min(maximum, number))

    def _text(self, value: Any, default: str = "", limit: int = 200) -> str:
        text = str(value if value is not None else default).strip()
        if not text:
            text = default
        return text[:limit]

    def _dedupe_site_actions(self, actions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        for action in actions:
            key = self._action_inventory_key(action)
            if key in seen:
                continue
            deduped.append(action)
            seen.add(key)
        return deduped, len(actions) - len(deduped)

    def _action_inventory_key(self, action: dict[str, Any]) -> tuple[str, ...]:
        selector = self._normalize_action_selector(action.get("selector"))
        return (
            self._normalize_action_url(action.get("page_url")),
            self._text(action.get("action_type"), "", 80).lower(),
            self._text(action.get("risk_level"), "", 40).lower(),
            self._normalize_action_label(action.get("label")),
            selector,
            self._text(action.get("form_method"), "", 20).upper(),
            self._normalize_action_target(action.get("form_action") or action.get("href")),
            self._text(action.get("suggested_feature_scope"), "", 120).lower(),
        )

    def _normalize_action_selector(self, value: Any) -> str:
        selector = self._text(value, "", 240).lower()
        selector = re.sub(r"\s*>\s*", ">", selector)
        selector = re.sub(r"\s+", " ", selector)
        selector = re.sub(r":nth-(?:child|of-type)\(\d+\)", ":nth(*)", selector)
        selector = re.sub(r"\b\d{2,}\b", "*", selector)
        selector = re.sub(r"([#._-])\d+\b", r"\1*", selector)
        return selector

    def _normalize_action_label(self, value: Any) -> str:
        label = self._text(value, "", 160).lower()
        label = re.sub(r"\s+", " ", label)
        label = re.sub(r"\b\d{2,}\b", "*", label)
        return label

    def _normalize_action_target(self, value: Any) -> str:
        target = self._text(value, "", 240)
        if not target:
            return ""
        parsed = urlsplit(target if "://" in target else f"https://target.example{target if target.startswith('/') else '/' + target}")
        path = self._normalize_action_path(parsed.path or "/")
        if "://" in target:
            return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).lower()
        return path.lower()

    def _normalize_action_url(self, value: Any) -> str:
        raw = self._text(value, "", 500)
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return raw.lower()
        return urlunsplit((parsed.scheme, parsed.netloc, self._normalize_action_path(parsed.path or "/"), "", "")).lower()

    def _normalize_action_path(self, value: Any) -> str:
        path = str(value or "/")
        parts = []
        for part in path.split("/"):
            if not part:
                continue
            if re.fullmatch(r"\d+", part) or re.fullmatch(r"[0-9a-f]{8,}", part, flags=re.IGNORECASE):
                parts.append(":id")
            elif re.fullmatch(r"[0-9a-f]{8}-[0-9a-f-]{18,}", part, flags=re.IGNORECASE):
                parts.append(":id")
            else:
                parts.append(part.lower())
        return "/" + "/".join(parts)


class SQLiteSiteInventoryStore(SiteProxyConfigMixin):
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_schema()

    def upsert_site(self, site: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        site_id = int(site.get("id") or 0)
        with self._lock, closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            if site_id:
                cursor = conn.execute(
                    """
                    UPDATE managed_sites
                    SET name = ?, base_url = ?, environment = ?, allowed_domains_json = ?,
                        auth_mode = ?, session_state_ref = ?, status = ?, protected_features_json = ?,
                        page_guard_enabled = ?, global_fuse_policy_json = ?, site_proxy_json = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        site["name"],
                        site["base_url"],
                        site["environment"],
                        json.dumps(site["allowed_domains"], ensure_ascii=False, sort_keys=True),
                        site["auth_mode"],
                        site["session_state_ref"],
                        site["status"],
                        json.dumps(site["protected_features"], ensure_ascii=False, sort_keys=True),
                        int(bool(site["page_guard_enabled"])),
                        json.dumps(site["global_fuse_policy"], ensure_ascii=False, sort_keys=True),
                        json.dumps(site["site_proxy"], ensure_ascii=False, sort_keys=True),
                        now,
                        site_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ValueError("site_not_found")
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO managed_sites
                    (name, base_url, environment, allowed_domains_json, auth_mode,
                     session_state_ref, status, protected_features_json, page_guard_enabled,
                     global_fuse_policy_json, site_proxy_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        site["name"],
                        site["base_url"],
                        site["environment"],
                        json.dumps(site["allowed_domains"], ensure_ascii=False, sort_keys=True),
                        site["auth_mode"],
                        site["session_state_ref"],
                        site["status"],
                        json.dumps(site["protected_features"], ensure_ascii=False, sort_keys=True),
                        int(bool(site["page_guard_enabled"])),
                        json.dumps(site["global_fuse_policy"], ensure_ascii=False, sort_keys=True),
                        json.dumps(site["site_proxy"], ensure_ascii=False, sort_keys=True),
                        now,
                        now,
                    ),
                )
                site_id = int(cursor.lastrowid)
            conn.commit()
            row = conn.execute("SELECT * FROM managed_sites WHERE id = ?", (site_id,)).fetchone()
        return self._site_from_row(row)

    def get_site(self, site_id: int) -> dict[str, Any] | None:
        with self._lock, closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM managed_sites WHERE id = ?", (int(site_id),)).fetchone()
        return self._site_from_row(row) if row else None

    def list_sites(self) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT s.*,
                       (SELECT COUNT(*) FROM site_scan_runs r WHERE r.site_id = s.id) AS scan_count,
                       (SELECT COUNT(*) FROM site_action_inventory a WHERE a.site_id = s.id) AS action_count,
                       (SELECT MAX(updated_at) FROM site_scan_runs r WHERE r.site_id = s.id) AS last_scan_at
                FROM managed_sites s
                ORDER BY s.id DESC
                """
            ).fetchall()
        return [self._site_from_row(row) for row in rows]

    def insert_scan(
        self,
        site_id: int,
        scan: dict[str, Any],
        actions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        existing_duplicates = 0
        with self._lock, closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            existing_action_keys = self._existing_action_keys(conn, int(site_id))
            new_actions: list[dict[str, Any]] = []
            for action in actions:
                action_key = self._action_inventory_key(action)
                if action_key in existing_action_keys:
                    existing_duplicates += 1
                    continue
                new_actions.append(action)
                existing_action_keys.add(action_key)
            if scan.get("status") == "completed" and actions and not new_actions:
                return self._duplicate_scan_record(int(site_id), scan, now, existing_duplicates)
            summary = self._scan_summary(new_actions, scan.get("status", "completed"))
            cursor = conn.execute(
                """
                INSERT INTO site_scan_runs
                (site_id, start_url, status, allow_high_risk_actions, max_pages,
                 max_actions, timeout_ms, summary_json, error_untrusted_text, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(site_id),
                    scan["start_url"],
                    scan["status"],
                    int(bool(scan["allow_high_risk_actions"])),
                    int(scan["max_pages"]),
                    int(scan["max_actions"]),
                    int(scan["timeout_ms"]),
                    json.dumps(summary, ensure_ascii=False, sort_keys=True),
                    scan.get("error_untrusted_text") or "",
                    now,
                    now,
                ),
            )
            scan_id = int(cursor.lastrowid)
            for action in new_actions:
                self._insert_action(conn, int(site_id), scan_id, action, now)
            conn.commit()
            row = conn.execute("SELECT * FROM site_scan_runs WHERE id = ?", (scan_id,)).fetchone()
        record = self._scan_from_row(row)
        record["inserted_actions"] = len(new_actions)
        record["existing_duplicates_removed"] = existing_duplicates
        return record

    def list_scans(self, site_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 50), 200))
        query = "SELECT * FROM site_scan_runs"
        params: tuple[Any, ...] = ()
        if site_id:
            query += " WHERE site_id = ?"
            params = (int(site_id),)
        query += " ORDER BY id DESC LIMIT ?"
        params = (*params, limit)
        with self._lock, closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        return [self._scan_from_row(row) for row in rows]

    def list_actions(
        self,
        site_id: int | None = None,
        scan_id: int | None = None,
        risk_level: str = "all",
        action_type: str = "all",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        desired_limit = max(1, min(int(limit or 100), 500))
        clauses: list[str] = []
        params: list[Any] = []
        if site_id:
            clauses.append("site_id = ?")
            params.append(int(site_id))
        if scan_id:
            clauses.append("scan_id = ?")
            params.append(int(scan_id))
        if risk_level in RISK_LEVELS:
            clauses.append("risk_level = ?")
            params.append(risk_level)
        if action_type in ACTION_TYPES:
            clauses.append("action_type = ?")
            params.append(action_type)
        query = "SELECT * FROM site_action_inventory"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY CASE risk_level WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, id DESC LIMIT ?"
        params.append(500)
        with self._lock, closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, tuple(params)).fetchall()
        actions, _ = self._dedupe_site_actions([self._action_from_row(row) for row in rows])
        return actions[:desired_limit]

    def _existing_action_keys(self, conn: sqlite3.Connection, site_id: int) -> set[tuple[str, ...]]:
        rows = conn.execute("SELECT * FROM site_action_inventory WHERE site_id = ?", (int(site_id),)).fetchall()
        return {self._action_inventory_key(self._action_from_row(row)) for row in rows}

    def _duplicate_scan_record(
        self,
        site_id: int,
        scan: dict[str, Any],
        created_at: str,
        existing_duplicates: int,
    ) -> dict[str, Any]:
        return {
            "id": None,
            "site_id": int(site_id),
            "start_url": scan["start_url"],
            "status": "duplicate",
            "allow_high_risk_actions": bool(scan["allow_high_risk_actions"]),
            "max_pages": int(scan["max_pages"]),
            "max_actions": int(scan["max_actions"]),
            "timeout_ms": int(scan["timeout_ms"]),
            "summary": self._scan_summary([], "duplicate"),
            "error_untrusted_text": "",
            "created_at": created_at,
            "updated_at": created_at,
            "duplicate_of_existing": True,
            "inserted_actions": 0,
            "existing_duplicates_removed": existing_duplicates,
        }

    def delete_scan(self, scan_id: int) -> dict[str, Any]:
        with self._lock, closing(self._connect()) as conn:
            action_cursor = conn.execute("DELETE FROM site_action_inventory WHERE scan_id = ?", (int(scan_id),))
            scan_cursor = conn.execute("DELETE FROM site_scan_runs WHERE id = ?", (int(scan_id),))
            conn.commit()
        deleted = int(scan_cursor.rowcount)
        if not deleted:
            return {"ok": False, "status": 404, "reason": "site_scan_not_found"}
        return {
            "ok": True,
            "status": 200,
            "deleted": deleted,
            "record_type": "site_scan",
            "deleted_actions": int(action_cursor.rowcount),
            "scan_id": int(scan_id),
        }

    def clear_scans(self, site_id: int | None = None) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if site_id:
            clauses.append("site_id = ?")
            params.append(int(site_id))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._lock, closing(self._connect()) as conn:
            scan_ids = [
                int(row[0])
                for row in conn.execute(f"SELECT id FROM site_scan_runs{where}", tuple(params)).fetchall()
            ]
            deleted_actions = 0
            if scan_ids:
                placeholders = ",".join("?" for _ in scan_ids)
                deleted_actions = int(
                    conn.execute(
                        f"DELETE FROM site_action_inventory WHERE scan_id IN ({placeholders})",
                        tuple(scan_ids),
                    ).rowcount
                )
            scan_cursor = conn.execute(f"DELETE FROM site_scan_runs{where}", tuple(params))
            conn.commit()
        return {
            "ok": True,
            "status": 200,
            "deleted": int(scan_cursor.rowcount),
            "record_type": "site_scan",
            "deleted_actions": deleted_actions,
            "site_id": int(site_id) if site_id else None,
        }

    def delete_action(self, action_id: int) -> dict[str, Any]:
        with self._lock, closing(self._connect()) as conn:
            cursor = conn.execute("DELETE FROM site_action_inventory WHERE id = ?", (int(action_id),))
            conn.commit()
        deleted = int(cursor.rowcount)
        if not deleted:
            return {"ok": False, "status": 404, "reason": "site_action_not_found"}
        return {
            "ok": True,
            "status": 200,
            "deleted": deleted,
            "record_type": "site_action",
            "site_action_id": int(action_id),
            "action_id": int(action_id),
        }

    def clear_actions(
        self,
        site_id: int | None = None,
        scan_id: int | None = None,
        risk_level: str = "all",
        action_type: str = "all",
    ) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if site_id:
            clauses.append("site_id = ?")
            params.append(int(site_id))
        if scan_id:
            clauses.append("scan_id = ?")
            params.append(int(scan_id))
        if risk_level in RISK_LEVELS:
            clauses.append("risk_level = ?")
            params.append(risk_level)
        if action_type in ACTION_TYPES:
            clauses.append("action_type = ?")
            params.append(action_type)
        query = "DELETE FROM site_action_inventory"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        with self._lock, closing(self._connect()) as conn:
            cursor = conn.execute(query, tuple(params))
            conn.commit()
        return {"ok": True, "status": 200, "deleted": int(cursor.rowcount), "record_type": "site_action"}

    def _insert_action(
        self,
        conn: sqlite3.Connection,
        site_id: int,
        scan_id: int,
        action: dict[str, Any],
        created_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO site_action_inventory
            (site_id, scan_id, page_url, action_type, risk_level, label,
             selector, role, tag_name, aria_label, href, form_method, form_action,
             is_dialog_trigger, causes_navigation, submits_form, suggested_event_type,
             suggested_feature_scope, recommended_test_type, requires_admin_review,
             metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                site_id,
                scan_id,
                action["page_url"],
                action["action_type"],
                action["risk_level"],
                action["label"],
                action["selector"],
                action["role"],
                action["tag_name"],
                action["aria_label"],
                action["href"],
                action["form_method"],
                action["form_action"],
                int(bool(action["is_dialog_trigger"])),
                int(bool(action["causes_navigation"])),
                int(bool(action["submits_form"])),
                action["suggested_event_type"],
                action["suggested_feature_scope"],
                action["recommended_test_type"],
                int(bool(action["requires_admin_review"])),
                json.dumps(action.get("metadata") or {}, ensure_ascii=False, sort_keys=True),
                created_at,
            ),
        )

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS managed_sites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    allowed_domains_json TEXT NOT NULL,
                    auth_mode TEXT NOT NULL,
                    session_state_ref TEXT NOT NULL,
                    status TEXT NOT NULL,
                    protected_features_json TEXT NOT NULL DEFAULT '[]',
                    page_guard_enabled INTEGER NOT NULL DEFAULT 0,
                    global_fuse_policy_json TEXT NOT NULL DEFAULT '{}',
                    site_proxy_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            site_columns = {row[1] for row in conn.execute("PRAGMA table_info(managed_sites)").fetchall()}
            if "protected_features_json" not in site_columns:
                conn.execute("ALTER TABLE managed_sites ADD COLUMN protected_features_json TEXT NOT NULL DEFAULT '[]'")
            if "page_guard_enabled" not in site_columns:
                conn.execute("ALTER TABLE managed_sites ADD COLUMN page_guard_enabled INTEGER NOT NULL DEFAULT 0")
            if "global_fuse_policy_json" not in site_columns:
                conn.execute("ALTER TABLE managed_sites ADD COLUMN global_fuse_policy_json TEXT NOT NULL DEFAULT '{}'")
            if "site_proxy_json" not in site_columns:
                conn.execute("ALTER TABLE managed_sites ADD COLUMN site_proxy_json TEXT NOT NULL DEFAULT '{}'")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS site_scan_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id INTEGER NOT NULL,
                    start_url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    allow_high_risk_actions INTEGER NOT NULL,
                    max_pages INTEGER NOT NULL,
                    max_actions INTEGER NOT NULL,
                    timeout_ms INTEGER NOT NULL,
                    summary_json TEXT NOT NULL,
                    error_untrusted_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS site_action_inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id INTEGER NOT NULL,
                    scan_id INTEGER NOT NULL,
                    page_url TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    label TEXT NOT NULL,
                    selector TEXT NOT NULL,
                    role TEXT NOT NULL,
                    tag_name TEXT NOT NULL,
                    aria_label TEXT NOT NULL,
                    href TEXT NOT NULL,
                    form_method TEXT NOT NULL,
                    form_action TEXT NOT NULL,
                    is_dialog_trigger INTEGER NOT NULL,
                    causes_navigation INTEGER NOT NULL,
                    submits_form INTEGER NOT NULL,
                    suggested_event_type TEXT NOT NULL,
                    suggested_feature_scope TEXT NOT NULL,
                    recommended_test_type TEXT NOT NULL,
                    requires_admin_review INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_managed_sites_environment ON managed_sites(environment)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_site_scan_runs_site_id ON site_scan_runs(site_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_site_action_inventory_site_id ON site_action_inventory(site_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_site_action_inventory_scan_id ON site_action_inventory(scan_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_site_action_inventory_risk ON site_action_inventory(risk_level)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_site_action_inventory_type ON site_action_inventory(action_type)")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _site_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        site = dict(row)
        site["allowed_domains"] = json.loads(site.pop("allowed_domains_json") or "[]")
        site["protected_features"] = json.loads(site.pop("protected_features_json", "[]") or "[]")
        site["page_guard_enabled"] = bool(site.get("page_guard_enabled"))
        site["global_fuse_policy"] = json.loads(site.pop("global_fuse_policy_json", "{}") or "{}")
        site["site_proxy"] = self._site_proxy_config(
            json.loads(site.pop("site_proxy_json", "{}") or "{}"),
            site["protected_features"],
            int(site["id"]),
        )
        site["scan_count"] = int(site.get("scan_count") or 0)
        site["action_count"] = int(site.get("action_count") or 0)
        return site

    def _scan_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        scan = dict(row)
        scan["allow_high_risk_actions"] = bool(scan["allow_high_risk_actions"])
        scan["summary"] = json.loads(scan.pop("summary_json") or "{}")
        return scan

    def _action_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        action = dict(row)
        action["is_dialog_trigger"] = bool(action["is_dialog_trigger"])
        action["causes_navigation"] = bool(action["causes_navigation"])
        action["submits_form"] = bool(action["submits_form"])
        action["requires_admin_review"] = bool(action["requires_admin_review"])
        action["metadata"] = json.loads(action.pop("metadata_json") or "{}")
        return action

    def _scan_summary(self, actions: list[dict[str, Any]], status: str) -> dict[str, Any]:
        pages = {action.get("page_url") for action in actions if action.get("page_url")}
        risks: dict[str, int] = {}
        types: dict[str, int] = {}
        for action in actions:
            risks[action["risk_level"]] = risks.get(action["risk_level"], 0) + 1
            types[action["action_type"]] = types.get(action["action_type"], 0) + 1
        return {
            "status": status,
            "pages": len(pages),
            "actions": len(actions),
            "high_risk_actions": risks.get("high", 0) + risks.get("critical", 0),
            "risk_levels": risks,
            "action_types": types,
        }


class SiteInventory(SiteProxyConfigMixin):
    def __init__(self, sqlite_path: str | Path | None = None):
        self.store = SQLiteSiteInventoryStore(sqlite_path) if sqlite_path else None
        self._sites: list[dict[str, Any]] = []
        self._scans: list[dict[str, Any]] = []
        self._actions: list[dict[str, Any]] = []
        self._next_site_id = 1
        self._next_scan_id = 1
        self._next_action_id = 1

    def register_site(self, payload: dict[str, Any]) -> dict[str, Any]:
        site = self._site_from_payload(payload)
        if self.store:
            try:
                return self.store.upsert_site(site)
            except ValueError:
                return {}
        if site.get("id"):
            for index, existing in enumerate(self._sites):
                if int(existing["id"]) == int(site["id"]):
                    site["created_at"] = existing["created_at"]
                    site["updated_at"] = datetime.now(timezone.utc).isoformat()
                    site["site_proxy"] = self._site_proxy_config(site.get("site_proxy"), site["protected_features"], int(site["id"]))
                    self._sites[index] = site
                    return dict(site)
            return {}
        site["id"] = self._next_site_id
        self._next_site_id += 1
        now = datetime.now(timezone.utc).isoformat()
        site["created_at"] = now
        site["updated_at"] = now
        site["site_proxy"] = self._site_proxy_config(site.get("site_proxy"), site["protected_features"], int(site["id"]))
        self._sites.append(site)
        return dict(site)

    def list_sites(self) -> list[dict[str, Any]]:
        if self.store:
            return self.store.list_sites()
        sites = []
        for site in self._sites:
            item = dict(site)
            item["site_proxy"] = self._site_proxy_config(
                item.get("site_proxy"),
                item.get("protected_features") or [],
                int(item["id"]),
            )
            item["scan_count"] = sum(1 for scan in self._scans if scan["site_id"] == site["id"])
            item["action_count"] = sum(1 for action in self._actions if action["site_id"] == site["id"])
            item["last_scan_at"] = max(
                [scan["updated_at"] for scan in self._scans if scan["site_id"] == site["id"]],
                default=None,
            )
            sites.append(item)
        return list(reversed(sites))

    def get_site(self, site_id: int) -> dict[str, Any] | None:
        if self.store:
            return self.store.get_site(site_id)
        for site in self._sites:
            if int(site["id"]) == int(site_id):
                item = dict(site)
                item["site_proxy"] = self._site_proxy_config(
                    item.get("site_proxy"),
                    item.get("protected_features") or [],
                    int(item["id"]),
                )
                return item
        return None

    def record_scan(self, payload: dict[str, Any], scanner_result: dict[str, Any] | None = None) -> dict[str, Any]:
        site_id = self._bounded_int(payload.get("site_id"), 0, 2_147_483_647, 0)
        site = self.get_site(site_id)
        if not site:
            return {"ok": False, "status": 404, "reason": "site_not_found"}
        allow_high_risk = bool(payload.get("allow_high_risk_actions"))
        if site.get("environment") == "production" and allow_high_risk and not payload.get("production_confirmed"):
            return {"ok": False, "status": 409, "reason": "production_high_risk_scan_requires_confirmation"}
        actions = scanner_result.get("actions") if scanner_result else payload.get("actions")
        actions = [self._action_from_payload(action, site, payload) for action in (actions or [])]
        actions, duplicates_removed = self._dedupe_site_actions(actions)
        auto_mapping = self._auto_match_site_actions(site, actions)
        status = "completed" if scanner_result is None or scanner_result.get("ok", True) else "failed"
        if not actions and not scanner_result:
            status = "queued"
        if scanner_result and scanner_result.get("status") == "failed":
            status = "failed"
        scan = {
            "site_id": site_id,
            "start_url": self._url(payload.get("start_url") or site["base_url"], site["base_url"]),
            "status": status,
            "allow_high_risk_actions": allow_high_risk,
            "max_pages": self._bounded_int(payload.get("max_pages"), 1, 100, 10),
            "max_actions": self._bounded_int(payload.get("max_actions"), 1, 1000, 100),
            "timeout_ms": self._bounded_int(payload.get("timeout_ms"), 1000, 120000, 30000),
            "error_untrusted_text": self._scan_error_text(scanner_result, payload.get("error_untrusted_text")),
        }
        if self.store:
            record = self.store.insert_scan(site_id, scan, actions)
            existing_duplicates = int(record.get("existing_duplicates_removed") or 0)
            inserted_actions = int(record.get("inserted_actions") if record.get("inserted_actions") is not None else len(actions))
            return {
                "ok": status != "failed",
                "scan": record,
                "actions": [] if record.get("duplicate_of_existing") else actions,
                "count": inserted_actions,
                "duplicates_removed": duplicates_removed + existing_duplicates,
                "auto_mapping": auto_mapping,
            }
        result = self._record_memory_scan(site_id, scan, actions)
        result["duplicates_removed"] = duplicates_removed + int((result.get("scan") or {}).get("existing_duplicates_removed") or 0)
        result["auto_mapping"] = auto_mapping
        return result

    def _auto_match_site_actions(self, site: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, Any]:
        if not actions:
            return {"matched": 0, "unapplied": 0, "features": []}
        proxy = dict(site.get("site_proxy") or {})
        feature_map = dict(proxy.get("feature_map") or {})
        path_rules = list(proxy.get("path_rules") or [])
        existing_rule_keys = {self._rule_key(rule) for rule in path_rules}
        matched_features: list[str] = []
        matched = 0
        unapplied = 0
        for action in actions:
            feature = self._feature_scope_for_action(action)
            auto_match = {
                "status": "unapplied",
                "feature_scope": "",
                "selector_applied": False,
                "path_rule_applied": False,
            }
            if feature:
                matched += 1
                matched_features.append(feature)
                action["suggested_feature_scope"] = feature
                auto_match["status"] = "applied"
                auto_match["feature_scope"] = feature
                selector = self._text(action.get("selector"), "", 160)
                if selector:
                    feature_map[selector] = feature
                    auto_match["selector_applied"] = True
                rule = self._path_rule_for_action(action, feature)
                if rule:
                    rule_key = self._rule_key(rule)
                    if rule_key not in existing_rule_keys:
                        path_rules.append(rule)
                        existing_rule_keys.add(rule_key)
                    auto_match["path_rule_applied"] = True
            else:
                unapplied += 1
            action["metadata"] = {
                **(action.get("metadata") if isinstance(action.get("metadata"), dict) else {}),
                "atee_auto_match": auto_match,
            }
        features = self._unique_features(matched_features)
        if features:
            updated_site = {
                **site,
                "protected_features": self._unique_features([*(site.get("protected_features") or []), *features]),
                "site_proxy": {
                    **proxy,
                    "feature_map": feature_map,
                    "path_rules": path_rules,
                },
            }
            self.register_site(updated_site)
        return {
            "matched": matched,
            "unapplied": unapplied,
            "features": features,
        }

    def _feature_scope_for_action(self, action: dict[str, Any]) -> str:
        action_type = self._text(action.get("action_type"), "", 80).lower()
        haystack = " ".join(
            self._text(action.get(key), "", 240).lower()
            for key in ("label", "selector", "suggested_feature_scope", "suggested_event_type", "href", "form_action")
        )
        if "comment" in haystack or "评论" in haystack:
            return "comments"
        if any(marker in haystack for marker in ("publish", "post", "topic", "article", "发帖", "发布", "帖子")):
            return "posts"
        if "upload" in haystack or "上传" in haystack or action_type == "upload":
            return "uploads"
        if action_type == "login":
            return "login"
        if action_type == "register":
            return "register"
        if action_type == "delete":
            return "delete_posts"
        if any(marker in haystack for marker in ("admin", "moderation", "role", "permission", "后台", "管理", "权限")):
            return "admin_actions"
        return ""

    def _path_rule_for_action(self, action: dict[str, Any], feature: str) -> dict[str, Any]:
        method = self._text(action.get("form_method"), "", 20).upper()
        if method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return {}
        form_action = self._text(action.get("form_action"), "", 240)
        if not form_action:
            return {}
        parsed = urlsplit(form_action)
        path = parsed.path if parsed.scheme or parsed.netloc else form_action
        if not path.startswith("/"):
            return {}
        return {"methods": [method], "path": path, "feature_scope": feature}

    def _rule_key(self, rule: dict[str, Any]) -> tuple[Any, ...]:
        return (
            tuple(rule.get("methods") or []),
            rule.get("path") or "",
            rule.get("path_prefix") or "",
            rule.get("path_regex") or "",
            rule.get("feature_scope") or "",
        )

    def _scan_error_text(self, scanner_result: dict[str, Any] | None, fallback: Any = "") -> str:
        error_text = ""
        if scanner_result:
            error_text = self._text(scanner_result.get("error"), "", 1000)
            if not error_text:
                errors = scanner_result.get("errors")
                if isinstance(errors, list) and errors:
                    first_error = errors[0]
                    if isinstance(first_error, dict):
                        error_text = self._text(
                            first_error.get("error") or first_error.get("reason") or first_error.get("message"),
                            "",
                            1000,
                        )
                    else:
                        error_text = self._text(first_error, "", 1000)
        if not error_text:
            error_text = self._text(fallback, "", 1000)
        return re.sub(r"https?://[^\s\"')]+", "[url]", error_text)[:1000]

    def list_scans(self, site_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if self.store:
            return self.store.list_scans(site_id=site_id, limit=limit)
        scans = [scan for scan in self._scans if not site_id or scan["site_id"] == int(site_id)]
        return list(reversed(scans))[: max(1, min(int(limit or 50), 200))]

    def list_actions(
        self,
        site_id: int | None = None,
        scan_id: int | None = None,
        risk_level: str = "all",
        action_type: str = "all",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if self.store:
            return self.store.list_actions(site_id, scan_id, risk_level, action_type, limit)
        actions = list(self._actions)
        if site_id:
            actions = [action for action in actions if action["site_id"] == int(site_id)]
        if scan_id:
            actions = [action for action in actions if action["scan_id"] == int(scan_id)]
        if risk_level in RISK_LEVELS:
            actions = [action for action in actions if action["risk_level"] == risk_level]
        if action_type in ACTION_TYPES:
            actions = [action for action in actions if action["action_type"] == action_type]
        actions, _ = self._dedupe_site_actions(list(reversed(actions)))
        return actions[: max(1, min(int(limit or 100), 500))]

    def delete_scan(self, scan_id: int) -> dict[str, Any]:
        if self.store:
            return self.store.delete_scan(scan_id)
        scan_id = int(scan_id)
        before_scans = len(self._scans)
        before_actions = len(self._actions)
        self._scans = [scan for scan in self._scans if int(scan["id"]) != scan_id]
        self._actions = [action for action in self._actions if int(action["scan_id"]) != scan_id]
        deleted = before_scans - len(self._scans)
        if not deleted:
            return {"ok": False, "status": 404, "reason": "site_scan_not_found"}
        return {
            "ok": True,
            "status": 200,
            "deleted": deleted,
            "record_type": "site_scan",
            "deleted_actions": before_actions - len(self._actions),
            "scan_id": scan_id,
        }

    def clear_scans(self, site_id: int | None = None) -> dict[str, Any]:
        if self.store:
            return self.store.clear_scans(site_id=site_id)
        site_id = int(site_id) if site_id else None
        deleted_scan_ids = {
            int(scan["id"])
            for scan in self._scans
            if site_id is None or int(scan["site_id"]) == site_id
        }
        before_scans = len(self._scans)
        before_actions = len(self._actions)
        self._scans = [scan for scan in self._scans if int(scan["id"]) not in deleted_scan_ids]
        self._actions = [action for action in self._actions if int(action["scan_id"]) not in deleted_scan_ids]
        return {
            "ok": True,
            "status": 200,
            "deleted": before_scans - len(self._scans),
            "record_type": "site_scan",
            "deleted_actions": before_actions - len(self._actions),
            "site_id": site_id,
        }

    def delete_action(self, action_id: int) -> dict[str, Any]:
        if self.store:
            return self.store.delete_action(action_id)
        action_id = int(action_id)
        before = len(self._actions)
        self._actions = [action for action in self._actions if int(action["id"]) != action_id]
        deleted = before - len(self._actions)
        if not deleted:
            return {"ok": False, "status": 404, "reason": "site_action_not_found"}
        return {
            "ok": True,
            "status": 200,
            "deleted": deleted,
            "record_type": "site_action",
            "site_action_id": action_id,
            "action_id": action_id,
        }

    def clear_actions(
        self,
        site_id: int | None = None,
        scan_id: int | None = None,
        risk_level: str = "all",
        action_type: str = "all",
    ) -> dict[str, Any]:
        if self.store:
            return self.store.clear_actions(
                site_id=site_id,
                scan_id=scan_id,
                risk_level=risk_level,
                action_type=action_type,
            )
        before = len(self._actions)

        def keep(action: dict[str, Any]) -> bool:
            if site_id and int(action["site_id"]) != int(site_id):
                return True
            if scan_id and int(action["scan_id"]) != int(scan_id):
                return True
            if risk_level in RISK_LEVELS and action["risk_level"] != risk_level:
                return True
            if action_type in ACTION_TYPES and action["action_type"] != action_type:
                return True
            return False

        self._actions = [action for action in self._actions if keep(action)]
        return {
            "ok": True,
            "status": 200,
            "deleted": before - len(self._actions),
            "record_type": "site_action",
        }

    def _record_memory_scan(self, site_id: int, scan: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        existing_action_keys = {
            self._action_inventory_key(action)
            for action in self._actions
            if int(action.get("site_id") or 0) == int(site_id)
        }
        new_actions = []
        existing_duplicates = 0
        for action in actions:
            action_key = self._action_inventory_key(action)
            if action_key in existing_action_keys:
                existing_duplicates += 1
                continue
            new_actions.append(action)
            existing_action_keys.add(action_key)
        if scan["status"] == "completed" and actions and not new_actions:
            scan_record = {
                "id": None,
                **scan,
                "status": "duplicate",
                "summary": self._memory_summary([], "duplicate"),
                "created_at": now,
                "updated_at": now,
                "duplicate_of_existing": True,
                "inserted_actions": 0,
                "existing_duplicates_removed": existing_duplicates,
            }
            return {"ok": True, "scan": scan_record, "actions": [], "count": 0}
        scan_record = {
            "id": self._next_scan_id,
            **scan,
            "summary": self._memory_summary(new_actions, scan["status"]),
            "created_at": now,
            "updated_at": now,
            "inserted_actions": len(new_actions),
            "existing_duplicates_removed": existing_duplicates,
        }
        self._next_scan_id += 1
        for action in new_actions:
            action["id"] = self._next_action_id
            action["site_id"] = site_id
            action["scan_id"] = scan_record["id"]
            action["created_at"] = now
            self._next_action_id += 1
            self._actions.append(action)
        self._scans.append(scan_record)
        return {"ok": scan["status"] != "failed", "scan": scan_record, "actions": new_actions, "count": len(new_actions)}

    def _site_from_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        base_url = self._url(payload.get("base_url") or payload.get("site_url"), "https://target.example")
        host = urlsplit(base_url).hostname or "target.example"
        allowed_domains = payload.get("allowed_domains") or [host]
        if isinstance(allowed_domains, str):
            allowed_domains = [item.strip() for item in allowed_domains.replace("\n", ",").split(",") if item.strip()]
        environment = str(payload.get("environment") or "staging").strip().lower()
        auth_mode = str(payload.get("auth_mode") or "none").strip().lower()
        protected_features = self._features(payload.get("protected_features"))
        site_proxy = payload.get("site_proxy") or payload.get("site_proxy_config") or payload.get("proxy_config")
        return {
            "id": self._bounded_int(payload.get("id"), 0, 2_147_483_647, 0),
            "name": self._text(payload.get("name") or payload.get("site_name"), "target-site", 80),
            "base_url": base_url,
            "environment": environment if environment in SITE_ENVIRONMENTS else "staging",
            "allowed_domains": [self._domain(item) for item in allowed_domains][:20] or [host],
            "auth_mode": auth_mode if auth_mode in AUTH_MODES else "none",
            "session_state_ref": self._text(payload.get("session_state_ref"), "", 240),
            "status": self._text(payload.get("status"), "active", 40),
            "protected_features": protected_features,
            "page_guard_enabled": bool(payload.get("page_guard_enabled") or payload.get("guard_enabled")),
            "global_fuse_policy": self._global_fuse_policy(payload.get("global_fuse_policy")),
            "site_proxy": self._site_proxy_config(site_proxy, protected_features),
        }

    def _action_from_payload(self, payload: dict[str, Any], site: dict[str, Any], scan_payload: dict[str, Any]) -> dict[str, Any]:
        action_type = str(payload.get("action_type") or "unknown").strip().lower()
        risk_level = str(payload.get("risk_level") or self._risk_for_type(action_type)).strip().lower()
        page_url = self._url(payload.get("page_url") or scan_payload.get("start_url") or site["base_url"], site["base_url"])
        label = self._text(payload.get("label") or payload.get("text"), "unlabeled control", 160)
        suggested_feature_scope = self._text(
            payload.get("suggested_feature_scope") or self._feature_scope_for(action_type, label),
            "",
            120,
        )
        return {
            "page_url": page_url,
            "action_type": action_type if action_type in ACTION_TYPES else "unknown",
            "risk_level": risk_level if risk_level in RISK_LEVELS else self._risk_for_type(action_type),
            "label": label,
            "selector": self._text(payload.get("selector"), "", 240),
            "role": self._text(payload.get("role"), "", 80),
            "tag_name": self._text(payload.get("tag_name"), "", 40),
            "aria_label": self._text(payload.get("aria_label"), "", 160),
            "href": self._text(payload.get("href"), "", 240),
            "form_method": self._text(payload.get("form_method"), "", 20),
            "form_action": self._text(payload.get("form_action"), "", 240),
            "is_dialog_trigger": bool(payload.get("is_dialog_trigger")),
            "causes_navigation": bool(payload.get("causes_navigation")),
            "submits_form": bool(payload.get("submits_form")),
            "suggested_event_type": self._text(payload.get("suggested_event_type") or action_type, action_type, 80),
            "suggested_feature_scope": suggested_feature_scope,
            "recommended_test_type": self._text(
                payload.get("recommended_test_type") or self._test_type_for(action_type, risk_level),
                "smoke",
                80,
            ),
            "requires_admin_review": bool(
                payload.get("requires_admin_review")
                if "requires_admin_review" in payload
                else risk_level in {"high", "critical"}
            ),
            "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        }

    def _url(self, value: Any, default: str) -> str:
        raw = self._text(value, default, 500)
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            parsed = urlsplit(default)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))

    def _domain(self, value: Any) -> str:
        raw = self._text(value, "", 120).lower()
        parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
        return (parsed.hostname or raw).strip(".")

    def _global_fuse_policy(self, value: Any) -> dict[str, Any]:
        payload = value if isinstance(value, dict) else {}
        return {
            "auto_suggest": bool(payload.get("auto_suggest", True)),
            "auto_execute": False,
            "threshold": self._bounded_int(payload.get("threshold"), 1, 100, 3),
            "window_seconds": self._bounded_int(payload.get("window_seconds"), 60, 86400, 3600),
        }

    def _bounded_int(self, value: Any, minimum: int, maximum: int, default: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(minimum, min(maximum, number))

    def _risk_for_type(self, action_type: str) -> str:
        if action_type in {"delete"}:
            return "critical"
        if action_type in {"save", "upload", "dialog_confirm", "submit", "register", "login"}:
            return "high"
        if action_type in {"search", "pagination", "menu", "navigation", "dialog_trigger"}:
            return "medium"
        return "low"

    def _test_type_for(self, action_type: str, risk_level: str) -> str:
        if risk_level in {"high", "critical"}:
            return "approval_regression"
        if action_type in {"search", "pagination", "menu"}:
            return "smoke"
        return "functional"

    def _feature_scope_for(self, action_type: str, label: str) -> str:
        normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in f"{action_type}_{label}")[:80]
        return "_".join(part for part in normalized.split("_") if part) or action_type or "unknown"

    def _memory_summary(self, actions: list[dict[str, Any]], status: str) -> dict[str, Any]:
        pages = {action.get("page_url") for action in actions if action.get("page_url")}
        risks: dict[str, int] = {}
        types: dict[str, int] = {}
        for action in actions:
            risks[action["risk_level"]] = risks.get(action["risk_level"], 0) + 1
            types[action["action_type"]] = types.get(action["action_type"], 0) + 1
        return {
            "status": status,
            "pages": len(pages),
            "actions": len(actions),
            "high_risk_actions": risks.get("high", 0) + risks.get("critical", 0),
            "risk_levels": risks,
            "action_types": types,
        }

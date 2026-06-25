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

    def _text(self, value: Any, default: str = "", limit: int = 200) -> str:
        text = str(value if value is not None else default).strip()
        if not text:
            text = default
        return text[:limit]


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
        summary = self._scan_summary(actions, scan.get("status", "completed"))
        with self._lock, closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
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
            for action in actions:
                self._insert_action(conn, int(site_id), scan_id, action, now)
            conn.commit()
            row = conn.execute("SELECT * FROM site_scan_runs WHERE id = ?", (scan_id,)).fetchone()
        return self._scan_from_row(row)

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
        params.append(max(1, min(int(limit or 100), 500)))
        with self._lock, closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._action_from_row(row) for row in rows]

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
            "error_untrusted_text": self._text(
                (scanner_result or {}).get("error") or payload.get("error_untrusted_text") or "",
                "",
                1000,
            ),
        }
        if self.store:
            record = self.store.insert_scan(site_id, scan, actions)
            return {"ok": status != "failed", "scan": record, "actions": actions, "count": len(actions)}
        return self._record_memory_scan(site_id, scan, actions)

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
        return list(reversed(actions))[: max(1, min(int(limit or 100), 500))]

    def _record_memory_scan(self, site_id: int, scan: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        scan_record = {
            "id": self._next_scan_id,
            **scan,
            "summary": self._memory_summary(actions, scan["status"]),
            "created_at": now,
            "updated_at": now,
        }
        self._next_scan_id += 1
        for action in actions:
            action["id"] = self._next_action_id
            action["site_id"] = site_id
            action["scan_id"] = scan_record["id"]
            action["created_at"] = now
            self._next_action_id += 1
            self._actions.append(action)
        self._scans.append(scan_record)
        return {"ok": scan["status"] != "failed", "scan": scan_record, "actions": actions, "count": len(actions)}

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

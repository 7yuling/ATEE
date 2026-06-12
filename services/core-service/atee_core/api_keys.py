import hashlib
import os
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_SCOPES = {"backend", "frontend"}


class ApiKeyRegistry:
    def __init__(self, sqlite_path: str | Path | None = None):
        self.path = Path(sqlite_path) if sqlite_path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_schema()

    def list(self, include_revoked: bool = False) -> dict[str, Any]:
        if not self.path:
            return {"ok": False, "status": 503, "reason": "api_key_store_unavailable", "keys": []}
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            if include_revoked:
                rows = conn.execute(
                    """
                    SELECT id, name, scope, env_name, key_prefix, key_suffix, created_at, last_used_at, revoked_at
                    FROM api_keys
                    ORDER BY id DESC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, name, scope, env_name, key_prefix, key_suffix, created_at, last_used_at, revoked_at
                    FROM api_keys
                    WHERE revoked_at IS NULL
                    ORDER BY id DESC
                    """
                ).fetchall()
        keys = [self._public_row(dict(row)) for row in rows]
        return {
            "ok": True,
            "keys": keys,
            "count": len(keys),
            "display": {"locale": "zh-CN", "message_zh": "API key 列表已返回，密钥只显示脱敏值。"},
        }

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.path:
            return {"ok": False, "status": 503, "reason": "api_key_store_unavailable"}
        name = str(payload.get("name") or "").strip()[:80]
        scope = str(payload.get("scope") or "backend").strip().lower()
        if scope not in VALID_SCOPES:
            return {"ok": False, "status": 400, "reason": "invalid_api_key_scope"}
        if not name:
            return {"ok": False, "status": 400, "reason": "api_key_name_required"}
        raw_key = str(payload.get("key_value") or "").strip() or f"ak-{secrets.token_urlsafe(32)}"
        prefix = raw_key[:8]
        suffix = raw_key[-6:] if len(raw_key) > 6 else raw_key
        now = self._now_iso()
        key_hash = self._hash_key(raw_key)
        requested_env = str(payload.get("env_name") or "").strip()
        env_name = self._clean_env_name(requested_env) if requested_env else ""
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                INSERT INTO api_keys
                (name, scope, env_name, key_prefix, key_suffix, key_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (name, scope, env_name, prefix, suffix, key_hash, now),
            )
            key_id = int(cursor.lastrowid)
            if not env_name:
                env_name = f"ATEE_{scope.upper()}_API_KEY_{key_id}"
                conn.execute("UPDATE api_keys SET env_name = ? WHERE id = ?", (env_name, key_id))
            conn.commit()
        os.environ[env_name] = raw_key
        return {
            "ok": True,
            "key": raw_key,
            "record": {
                "id": key_id,
                "name": name,
                "scope": scope,
                "env_name": env_name,
                "masked_key": self._mask(prefix, suffix),
                "created_at": now,
                "last_used_at": None,
                "revoked_at": None,
            },
            "display": {"locale": "zh-CN", "message_zh": "API key 已创建，明文只在本次响应返回。"},
        }

    def delete(self, key_id: int) -> dict[str, Any]:
        if not self.path:
            return {"ok": False, "status": 503, "reason": "api_key_store_unavailable"}
        now = self._now_iso()
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM api_keys WHERE id = ?", (int(key_id),)).fetchone()
            if not row:
                return {"ok": False, "status": 404, "reason": "api_key_not_found"}
            conn.execute("UPDATE api_keys SET revoked_at = ? WHERE id = ?", (now, int(key_id)))
            conn.commit()
        env_name = str(row["env_name"] or "")
        if env_name:
            os.environ.pop(env_name, None)
        return {
            "ok": True,
            "id": int(key_id),
            "env_name": env_name,
            "display": {"locale": "zh-CN", "message_zh": "API key 已删除，当前进程环境变量也已清除。"},
        }

    def _public_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id"),
            "name": row.get("name"),
            "scope": row.get("scope"),
            "env_name": row.get("env_name"),
            "masked_key": self._mask(str(row.get("key_prefix") or ""), str(row.get("key_suffix") or "")),
            "created_at": row.get("created_at"),
            "last_used_at": row.get("last_used_at"),
            "revoked_at": row.get("revoked_at"),
        }

    def _hash_key(self, raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def _mask(self, prefix: str, suffix: str) -> str:
        return f"{prefix}{'*' * 18}{suffix}"

    def _clean_env_name(self, value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value.strip().upper())
        if not cleaned or not re.match(r"^[A-Z_]", cleaned):
            cleaned = f"ATEE_{cleaned}"
        return cleaned[:120]

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _connect(self) -> sqlite3.Connection:
        if not self.path:
            raise RuntimeError("api_key_store_unavailable")
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    env_name TEXT NOT NULL,
                    key_prefix TEXT NOT NULL,
                    key_suffix TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    revoked_at TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_scope ON api_keys(scope)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_revoked ON api_keys(revoked_at)")
            conn.commit()

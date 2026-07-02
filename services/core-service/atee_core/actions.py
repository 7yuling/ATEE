import json
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class SQLiteActionStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_schema()

    def insert(self, record: dict[str, Any]) -> int:
        with self._lock, closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                INSERT INTO action_records
                (action, target_scope_json, expires_at, reversible, idempotency_key, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["action"],
                    json.dumps(record["target_scope"], ensure_ascii=False, sort_keys=True),
                    record["expires_at"],
                    int(bool(record["reversible"])),
                    record["idempotency_key"],
                    record["status"],
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def load_all(self) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, action, target_scope_json, expires_at, reversible, idempotency_key,
                       status, revoked_at, revoke_reason_untrusted_text, created_at
                FROM action_records
                ORDER BY id ASC
                """
            ).fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["target_scope"] = json.loads(record.pop("target_scope_json") or "{}")
            record["reversible"] = bool(record["reversible"])
            records.append(record)
        return records

    def update_status(self, action_id: int, status: str, reason: str = "") -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                UPDATE action_records
                SET status = ?, revoked_at = ?, revoke_reason_untrusted_text = ?
                WHERE id = ? AND status = 'active'
                """,
                (status, now if status == "revoked" else None, reason if status == "revoked" else None, action_id),
            )
            conn.commit()
            if cursor.rowcount != 1:
                return None
            row = conn.execute(
                """
                SELECT id, action, target_scope_json, expires_at, reversible, idempotency_key,
                       status, revoked_at, revoke_reason_untrusted_text, created_at
                FROM action_records
                WHERE id = ?
                """,
                (action_id,),
            ).fetchone()
        if not row:
            return None
        record = dict(row)
        record["target_scope"] = json.loads(record.pop("target_scope_json") or "{}")
        record["reversible"] = bool(record["reversible"])
        return record

    def delete_non_active(self, action_id: int) -> int:
        with self._lock, closing(self._connect()) as conn:
            cursor = conn.execute(
                "DELETE FROM action_records WHERE id = ? AND status <> 'active'",
                (int(action_id),),
            )
            conn.commit()
            return int(cursor.rowcount)

    def clear_non_active(self, status: str = "all") -> int:
        status = status if status in {"revoked", "expired", "all"} else "all"
        with self._lock, closing(self._connect()) as conn:
            if status == "all":
                cursor = conn.execute("DELETE FROM action_records WHERE status <> 'active'")
            else:
                cursor = conn.execute("DELETE FROM action_records WHERE status = ?", (status,))
            conn.commit()
            return int(cursor.rowcount)

    def mark_expired(self, now_iso: str) -> int:
        with self._lock, closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                UPDATE action_records
                SET status = 'expired'
                WHERE status = 'active' AND expires_at <= ?
                """,
                (now_iso,),
            )
            conn.commit()
            return int(cursor.rowcount)

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS action_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    target_scope_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    reversible INTEGER NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(action_records)").fetchall()}
            if "status" not in columns:
                conn.execute("ALTER TABLE action_records ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            if "revoked_at" not in columns:
                conn.execute("ALTER TABLE action_records ADD COLUMN revoked_at TEXT")
            if "revoke_reason_untrusted_text" not in columns:
                conn.execute("ALTER TABLE action_records ADD COLUMN revoke_reason_untrusted_text TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_action_records_action ON action_records(action)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_action_records_expires_at ON action_records(expires_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_action_records_status ON action_records(status)")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn


class ActionExecutor:
    def __init__(self, sqlite_path: str | Path | None = None):
        self.store = SQLiteActionStore(sqlite_path) if sqlite_path else None
        self.actions: list[dict[str, Any]] = self.store.load_all() if self.store else []

    def execute(self, decision: dict[str, Any], gateway: dict[str, Any]) -> dict[str, Any]:
        if not gateway.get("executed"):
            return {"executed": False, "reason": gateway.get("reason")}

        action = gateway["effective_action"]
        duration = int(decision.get("duration_seconds") or 0)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=duration)
        record = {
            "action": action,
            "target_scope": decision.get("target_scope") or {"type": "request"},
            "expires_at": expires_at.isoformat(),
            "reversible": True,
            "idempotency_key": self._idempotency_key(action, decision),
            "status": "active",
            "revoked_at": None,
            "revoke_reason_untrusted_text": None,
        }
        if self.store:
            record["id"] = self.store.insert(record)
        self.actions.append(record)
        return {"executed": True, "record": self._decorate_record(record)}

    def list_actions(self, status: str = "active", *, cleanup_expired: bool = True) -> list[dict[str, Any]]:
        if cleanup_expired:
            self.cleanup_expired()
        status = status if status in {"active", "revoked", "expired", "all"} else "active"
        if self.store:
            self.actions = self.store.load_all()
        if status == "all":
            return [self._decorate_record(record) for record in self.actions]
        return [self._decorate_record(record) for record in self.actions if record.get("status", "active") == status]

    def find_active_user_feature(self, user_hash: str, feature: str, site_id: int | None = None) -> dict[str, Any] | None:
        user_hash = str(user_hash or "").strip()
        feature = str(feature or "").strip()
        if not user_hash or not feature:
            return None
        for record in self.list_actions(status="active"):
            target = record.get("target_scope") or {}
            if (
                record.get("action") == "feature_ban"
                and target.get("type") == "user_feature"
                and str(target.get("user_hash") or "") == user_hash
                and str(target.get("feature") or "") == feature
                and self._site_matches(target, site_id)
            ):
                return record
        return None

    def find_active_site_feature(self, site_id: int | None, feature: str) -> dict[str, Any] | None:
        site_id = self._clean_site_id(site_id)
        feature = str(feature or "").strip()
        if site_id is None or not feature:
            return None
        for record in self.list_actions(status="active"):
            target = record.get("target_scope") or {}
            if (
                record.get("action") == "feature_ban"
                and target.get("type") == "site_feature"
                and self._clean_site_id(target.get("site_id")) == site_id
                and str(target.get("feature") or "") == feature
            ):
                return record
        return None

    def active_action(self, action_id: int) -> dict[str, Any] | None:
        for record in self.list_actions(status="active"):
            if int(record.get("id") or -1) == int(action_id):
                return record
        return None

    def revoke(self, action_id: int, reason: str = "") -> dict[str, Any]:
        self.cleanup_expired()
        for record in self.actions:
            if int(record.get("id") or -1) == action_id and record.get("status", "active") == "active":
                if not record.get("reversible"):
                    return {"ok": False, "status": 409, "reason": "action_not_reversible"}
                reason = reason[:2000]
                if self.store:
                    updated = self.store.update_status(action_id, "revoked", reason)
                    self.actions = self.store.load_all()
                    if not updated:
                        return {"ok": False, "status": 404, "reason": "active_action_not_found"}
                    return {"ok": True, "status": 200, "action": self._decorate_record(updated)}
                record["status"] = "revoked"
                record["revoked_at"] = datetime.now(timezone.utc).isoformat()
                record["revoke_reason_untrusted_text"] = reason
                return {"ok": True, "status": 200, "action": self._decorate_record(record)}
        return {"ok": False, "status": 404, "reason": "active_action_not_found"}

    def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        changed = 0
        if self.store:
            changed = self.store.mark_expired(now_iso)
            if changed:
                self.actions = self.store.load_all()
            return changed
        for record in self.actions:
            if record.get("status", "active") != "active":
                continue
            try:
                expires_at = datetime.fromisoformat(str(record.get("expires_at")))
            except ValueError:
                continue
            if expires_at <= now:
                record["status"] = "expired"
                changed += 1
        return changed

    def delete_record(self, action_id: int) -> dict[str, Any]:
        if self.store:
            self.actions = self.store.load_all()
        for record in self.actions:
            if int(record.get("id") or -1) == int(action_id) and record.get("status", "active") == "active":
                return {"ok": False, "status": 409, "reason": "active_action_must_be_revoked_before_delete"}
        if self.store:
            deleted = self.store.delete_non_active(action_id)
            self.actions = self.store.load_all()
        else:
            before = len(self.actions)
            self.actions = [record for record in self.actions if int(record.get("id") or -1) != int(action_id)]
            deleted = before - len(self.actions)
        if deleted:
            return {
                "ok": True,
                "status": 200,
                "deleted": deleted,
                "record_type": "action_record",
                "action_id": int(action_id),
            }
        return {"ok": False, "status": 404, "reason": "action_record_not_found"}

    def clear_records(self, status: str = "all") -> dict[str, Any]:
        if status == "active":
            return {
                "ok": False,
                "status": 409,
                "reason": "active_actions_must_be_revoked_before_delete",
            }
        status = status if status in {"revoked", "expired", "all"} else "all"
        if self.store:
            self.actions = self.store.load_all()
        active_skipped = sum(1 for record in self.actions if record.get("status", "active") == "active")
        if self.store:
            deleted = self.store.clear_non_active(status)
            self.actions = self.store.load_all()
        else:
            before = len(self.actions)
            if status == "all":
                self.actions = [record for record in self.actions if record.get("status", "active") == "active"]
            else:
                self.actions = [record for record in self.actions if record.get("status", "active") != status]
            deleted = before - len(self.actions)
        return {
            "ok": True,
            "status": 200,
            "deleted": deleted,
            "record_type": "action_record",
            "filter_status": status,
            "active_skipped": active_skipped if status == "all" else 0,
        }

    def _idempotency_key(self, action: str, decision: dict[str, Any]) -> str:
        target = decision.get("target_scope") or {}
        if target.get("type") == "user_feature":
            return (
                f"{action}:user_feature:{target.get('site_id') or 'global'}:"
                f"{target.get('user_hash') or 'unknown'}:{target.get('feature') or 'unknown'}"
            )
        if target.get("type") == "site_feature":
            return f"{action}:site_feature:{target.get('site_id') or 'unknown'}:{target.get('feature') or 'unknown'}"
        return f"{action}:{target.get('type')}:{target.get('hash') or target.get('name') or target.get('user_hash') or 'request'}"

    def _decorate_record(self, record: dict[str, Any]) -> dict[str, Any]:
        decorated = dict(record)
        if decorated.get("action") == "feature_ban" and decorated.get("id") is not None:
            decorated["punishment_id"] = f"action:{decorated['id']}"
        return decorated

    def _site_matches(self, target: dict[str, Any], site_id: int | None) -> bool:
        site_id = self._clean_site_id(site_id)
        target_site_id = self._clean_site_id(target.get("site_id"))
        if site_id is None:
            return target_site_id is None
        return target_site_id in {None, site_id}

    def _clean_site_id(self, value: Any) -> int | None:
        try:
            site_id = int(value)
        except (TypeError, ValueError):
            return None
        return site_id if site_id > 0 else None

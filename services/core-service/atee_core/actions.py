import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class SQLiteActionStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def insert(self, record: dict[str, Any]) -> int:
        with closing(sqlite3.connect(self.path)) as conn:
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
        with closing(sqlite3.connect(self.path)) as conn:
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
        with closing(sqlite3.connect(self.path)) as conn:
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

    def mark_expired(self, now_iso: str) -> int:
        with closing(sqlite3.connect(self.path)) as conn:
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
        with closing(sqlite3.connect(self.path)) as conn:
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
        return {"executed": True, "record": record}

    def list_actions(self, status: str = "active") -> list[dict[str, Any]]:
        self.cleanup_expired()
        status = status if status in {"active", "revoked", "expired", "all"} else "active"
        if self.store:
            self.actions = self.store.load_all()
        if status == "all":
            return list(self.actions)
        return [record for record in self.actions if record.get("status", "active") == status]

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
                    return {"ok": True, "status": 200, "action": updated}
                record["status"] = "revoked"
                record["revoked_at"] = datetime.now(timezone.utc).isoformat()
                record["revoke_reason_untrusted_text"] = reason
                return {"ok": True, "status": 200, "action": record}
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

    def _idempotency_key(self, action: str, decision: dict[str, Any]) -> str:
        target = decision.get("target_scope") or {}
        return f"{action}:{target.get('type')}:{target.get('hash') or target.get('name') or 'request'}"

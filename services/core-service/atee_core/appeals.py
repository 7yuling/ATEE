from collections import defaultdict, deque
from contextlib import closing
from datetime import datetime, timezone
import sqlite3
from pathlib import Path
from time import time
from typing import Any


class SQLiteAppealStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def load_pending(self) -> dict[str, dict[str, Any]]:
        return {appeal["punishment_id"]: appeal for appeal in self.list(status="pending")}

    def list(self, status: str = "pending", limit: int = 50) -> list[dict[str, Any]]:
        status = status if status in {"pending", "approved", "rejected", "all"} else "pending"
        limit = max(1, min(int(limit), 100))
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            if status == "all":
                rows = conn.execute(
                    """
                    SELECT punishment_id, banned_ip_hash, reason_untrusted_text, status,
                           created_at, reviewed_at, resolution, admin_note_untrusted_text
                    FROM appeals
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT punishment_id, banned_ip_hash, reason_untrusted_text, status,
                           created_at, reviewed_at, resolution, admin_note_untrusted_text
                    FROM appeals
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def save(self, appeal: dict[str, Any]) -> None:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO appeals
                (punishment_id, banned_ip_hash, reason_untrusted_text, status, created_at,
                 reviewed_at, resolution, admin_note_untrusted_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    appeal["punishment_id"],
                    appeal["banned_ip_hash"],
                    appeal["reason_untrusted_text"],
                    appeal["status"],
                    datetime.now(timezone.utc).isoformat(),
                    appeal.get("reviewed_at"),
                    appeal.get("resolution"),
                    appeal.get("admin_note_untrusted_text"),
                ),
            )
            conn.commit()

    def review(self, punishment_id: str, status: str, admin_note: str) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                UPDATE appeals
                SET status = ?, reviewed_at = ?, resolution = ?, admin_note_untrusted_text = ?
                WHERE punishment_id = ? AND status = 'pending'
                """,
                (status, now, status, admin_note, punishment_id),
            )
            conn.commit()
            if cursor.rowcount != 1:
                return None
            row = conn.execute(
                """
                SELECT punishment_id, banned_ip_hash, reason_untrusted_text, status,
                       created_at, reviewed_at, resolution, admin_note_untrusted_text
                FROM appeals
                WHERE punishment_id = ?
                """,
                (punishment_id,),
            ).fetchone()
        return dict(row) if row else None

    def _ensure_schema(self) -> None:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS appeals (
                    punishment_id TEXT PRIMARY KEY,
                    banned_ip_hash TEXT NOT NULL,
                    reason_untrusted_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(appeals)").fetchall()}
            if "reviewed_at" not in columns:
                conn.execute("ALTER TABLE appeals ADD COLUMN reviewed_at TEXT")
            if "resolution" not in columns:
                conn.execute("ALTER TABLE appeals ADD COLUMN resolution TEXT")
            if "admin_note_untrusted_text" not in columns:
                conn.execute("ALTER TABLE appeals ADD COLUMN admin_note_untrusted_text TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_appeals_status ON appeals(status)")
            conn.commit()


class AppealService:
    def __init__(self, sqlite_path: str | Path | None = None):
        self._get_hits: dict[str, deque[float]] = defaultdict(deque)
        self._post_hits: dict[str, deque[float]] = defaultdict(deque)
        self.store = SQLiteAppealStore(sqlite_path) if sqlite_path else None
        self.appeals: dict[str, dict[str, Any]] = self.store.load_pending() if self.store else {}

    def can_access_page(self, banned_ip_hash: str) -> tuple[bool, str]:
        allowed = self._rate_limit(self._get_hits[banned_ip_hash], 60, 5)
        return (allowed, "ok" if allowed else "rate_limited")

    def submit(self, payload: dict[str, Any], ip_hash: str | None) -> dict[str, Any]:
        punishment_id = str(payload.get("punishment_id") or "")
        banned_ip_hash = str(payload.get("banned_ip_hash") or ip_hash or "")
        if not punishment_id:
            return {"status": 400, "accepted": False, "reason": "punishment_id_required"}

        limiter_key = f"{punishment_id}:{banned_ip_hash}"
        if not self._rate_limit(self._post_hits[limiter_key], 3600, 1):
            return {"status": 429, "accepted": False, "reason": "appeal_rate_limited_no_db_write"}

        if punishment_id in self.appeals and self.appeals[punishment_id]["status"] == "pending":
            return {"status": 200, "accepted": True, "reason": "pending_appeal_already_exists"}

        reason = str(payload.get("reason") or "")[:2000]
        appeal = {
            "punishment_id": punishment_id,
            "banned_ip_hash": banned_ip_hash,
            "reason_untrusted_text": reason,
            "status": "pending",
        }
        self.appeals[punishment_id] = appeal
        if self.store:
            self.store.save(appeal)
        return {"status": 202, "accepted": True, "appeal": appeal}

    def list(self, status: str = "pending", limit: int = 50) -> list[dict[str, Any]]:
        if self.store:
            return self.store.list(status=status, limit=limit)
        appeals = list(self.appeals.values())
        if status != "all":
            appeals = [appeal for appeal in appeals if appeal.get("status") == status]
        return appeals[: max(1, min(int(limit), 100))]

    def review(self, payload: dict[str, Any]) -> dict[str, Any]:
        punishment_id = str(payload.get("punishment_id") or "")
        resolution = str(payload.get("resolution") or "")
        admin_note = str(payload.get("admin_note") or "")[:2000]
        if not punishment_id:
            return {"ok": False, "status": 400, "reason": "punishment_id_required"}
        if resolution not in {"approved", "rejected"}:
            return {"ok": False, "status": 400, "reason": "resolution_must_be_approved_or_rejected"}

        if self.store:
            reviewed = self.store.review(punishment_id, resolution, admin_note)
        else:
            appeal = self.appeals.get(punishment_id)
            reviewed = None
            if appeal and appeal.get("status") == "pending":
                appeal = dict(appeal)
                appeal["status"] = resolution
                appeal["reviewed_at"] = datetime.now(timezone.utc).isoformat()
                appeal["resolution"] = resolution
                appeal["admin_note_untrusted_text"] = admin_note
                reviewed = appeal
        if not reviewed:
            return {"ok": False, "status": 404, "reason": "pending_appeal_not_found"}
        self.appeals.pop(punishment_id, None)
        return {"ok": True, "status": 200, "appeal": reviewed}

    def _rate_limit(self, hits: deque[float], window_seconds: int, limit: int) -> bool:
        now = time()
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True

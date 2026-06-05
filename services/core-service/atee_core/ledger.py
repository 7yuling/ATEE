import json
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SQLiteLedgerStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._ensure_schema()

    def insert(self, record: dict[str, Any]) -> int:
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self._lock, closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                INSERT INTO ledger_records
                (event_type, severity, ip_hash, rule_id, endpoint_type, action, summary, created_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("event_type"),
                    record.get("severity"),
                    record.get("ip_hash"),
                    record.get("rule_id"),
                    record.get("endpoint_type"),
                    record.get("action"),
                    record.get("summary"),
                    record.get("created_at"),
                    payload,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def count(self) -> int:
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute("SELECT COUNT(*) FROM ledger_records").fetchone()
            return int(row[0] if row else 0)

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, event_type, severity, ip_hash, rule_id, endpoint_type, action, summary, created_at
                FROM ledger_records
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def trim_to_max_bytes(self, max_bytes: int) -> None:
        if not self.path.exists() or self.path.stat().st_size <= max_bytes:
            return
        with self._lock, closing(self._connect()) as conn:
            while self.path.exists() and self.path.stat().st_size > max_bytes:
                conn.execute(
                    """
                    DELETE FROM ledger_records
                    WHERE id IN (
                        SELECT id FROM ledger_records
                        ORDER BY id ASC
                        LIMIT 100
                    )
                    """
                )
                conn.commit()
                conn.execute("VACUUM")
                if conn.execute("SELECT COUNT(*) FROM ledger_records").fetchone()[0] == 0:
                    break

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ledger_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    ip_hash TEXT,
                    rule_id TEXT,
                    endpoint_type TEXT,
                    action TEXT,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_created_at ON ledger_records(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_severity ON ledger_records(severity)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_event_type ON ledger_records(event_type)")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn


class SecurityLedgerLite:
    def __init__(self, max_bytes: int = 256 * 1024 * 1024, sqlite_path: str | Path | None = None):
        self.max_bytes = max_bytes
        self.records: list[dict[str, Any]] = []
        self.aggregates: dict[tuple[str, str, str, int], dict[str, Any]] = {}
        self.store = SQLiteLedgerStore(sqlite_path) if sqlite_path else None

    def record(self, event: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        severity = event.get("severity", "medium")
        if severity == "low":
            key = (
                str(event.get("ip_hash")),
                str(event.get("rule_id")),
                str(event.get("endpoint_type")),
                int(now.timestamp() // 60),
            )
            aggregate = self.aggregates.setdefault(
                key,
                {
                    "event_type": "aggregated_low_risk",
                    "ip_hash": event.get("ip_hash"),
                    "rule_id": event.get("rule_id"),
                    "endpoint_type": event.get("endpoint_type"),
                    "count": 0,
                    "window_seconds": 60,
                    "created_at": now.isoformat(),
                },
            )
            aggregate["count"] += 1
            return aggregate

        record = {
            "event_type": event.get("event_type", "security_event"),
            "severity": severity,
            "ip_hash": event.get("ip_hash"),
            "rule_id": event.get("rule_id"),
            "endpoint_type": event.get("endpoint_type"),
            "action": event.get("action"),
            "summary": str(event.get("summary", ""))[:4096],
            "created_at": now.isoformat(),
        }
        self.records.append(record)
        if self.store:
            record["id"] = self.store.insert(record)
            self.store.trim_to_max_bytes(self.max_bytes)
        self._trim_if_needed()
        return record

    def status(self) -> dict[str, Any]:
        return {
            "max_bytes": self.max_bytes,
            "records": len(self.records),
            "aggregates": len(self.aggregates),
            "sqlite_enabled": self.store is not None,
            "sqlite_path": str(self.store.path) if self.store else None,
            "persisted_records": self.store.count() if self.store else 0,
            "sqlite_bytes": self.store.path.stat().st_size if self.store and self.store.path.exists() else 0,
            "raw_prompt_storage": False,
            "raw_request_body_storage": False,
        }

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        if self.store:
            return self.store.recent(limit)
        return list(reversed(self.records[-limit:]))

    def _trim_if_needed(self) -> None:
        rough_bytes = sum(len(str(record)) for record in self.records)
        while self.records and rough_bytes > self.max_bytes:
            self.records.pop(0)
            rough_bytes = sum(len(str(record)) for record in self.records)

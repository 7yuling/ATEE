import json
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


QUEUE_STATUSES = {"pending", "retry", "processing", "completed", "dead_letter", "all"}
ACTIVE_QUEUE_STATUSES = ("pending", "retry", "processing")


class AsyncReviewQueueFull(RuntimeError):
    def __init__(self, status: dict[str, Any]):
        self.status = status
        super().__init__("async_review_queue_full")


class AsyncReviewQueue:
    def __init__(
        self,
        path: str | Path,
        max_attempts: int = 3,
        retry_backoff_seconds: int = 60,
        stale_processing_seconds: int = 300,
        max_depth: int = 5000,
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_attempts = max(1, int(max_attempts))
        self.retry_backoff_seconds = max(1, int(retry_backoff_seconds))
        self.stale_processing_seconds = max(1, int(stale_processing_seconds))
        self.max_depth = max(1, int(max_depth))
        self._ensure_schema()

    def enqueue(self, packet: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
        now = self._now_iso()
        now_ts = time.time()
        with closing(sqlite3.connect(self.path)) as conn:
            active_depth = self._active_depth(conn)
            if active_depth >= self.max_depth:
                raise AsyncReviewQueueFull(self._status_from_conn(conn))
            cursor = conn.execute(
                """
                INSERT INTO async_review_jobs
                (status, attempts, max_attempts, event_type, route, ip_hash, rule_id,
                 packet_json, route_json, created_at, updated_at, next_attempt_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "pending",
                    0,
                    self.max_attempts,
                    route.get("event_type"),
                    route.get("route"),
                    packet.get("ip_hash"),
                    (packet.get("fast_path_signal") or {}).get("rule_id"),
                    json.dumps(packet, ensure_ascii=False, sort_keys=True),
                    json.dumps(route, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                    now_ts,
                ),
            )
            conn.commit()
            job_id = int(cursor.lastrowid)
        return self.get(job_id, include_payload=False) or {"id": job_id, "status": "pending"}

    def claim_due(self, limit: int = 10) -> list[dict[str, Any]]:
        self.requeue_stale_processing()
        limit = max(1, min(int(limit), 100))
        now = self._now_iso()
        now_ts = time.time()
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT *
                FROM async_review_jobs
                WHERE status IN ('pending', 'retry') AND next_attempt_at <= ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (now_ts, limit),
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            for job_id in ids:
                conn.execute(
                    """
                    UPDATE async_review_jobs
                    SET status = 'processing',
                        attempts = attempts + 1,
                        processing_started_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now_ts, now, job_id),
                )
            conn.commit()
        jobs: list[dict[str, Any]] = []
        for job_id in ids:
            job = self.get(job_id, include_payload=True)
            if job:
                jobs.append(job)
        return jobs

    def complete(self, job_id: int, result: dict[str, Any]) -> dict[str, Any] | None:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                """
                UPDATE async_review_jobs
                SET status = 'completed',
                    result_json = ?,
                    last_error = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(result, ensure_ascii=False, sort_keys=True), self._now_iso(), int(job_id)),
            )
            conn.commit()
        return self.get(job_id, include_payload=False)

    def fail(self, job_id: int, error: str) -> dict[str, Any] | None:
        job = self.get(job_id, include_payload=False)
        if not job:
            return None
        attempts = int(job.get("attempts") or 0)
        max_attempts = int(job.get("max_attempts") or self.max_attempts)
        status = "dead_letter" if attempts >= max_attempts else "retry"
        next_attempt_at = None if status == "dead_letter" else time.time() + self.retry_backoff_seconds * attempts
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                """
                UPDATE async_review_jobs
                SET status = ?,
                    last_error = ?,
                    next_attempt_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (status, str(error)[:512], next_attempt_at, self._now_iso(), int(job_id)),
            )
            conn.commit()
        return self.get(job_id, include_payload=False)

    def defer(self, job_id: int, reason: str, delay_seconds: int = 60) -> dict[str, Any] | None:
        next_attempt_at = time.time() + max(1, int(delay_seconds))
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                """
                UPDATE async_review_jobs
                SET status = 'retry',
                    attempts = CASE WHEN attempts > 0 THEN attempts - 1 ELSE 0 END,
                    last_error = ?,
                    next_attempt_at = ?,
                    processing_started_at = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (str(reason)[:512], next_attempt_at, self._now_iso(), int(job_id)),
            )
            conn.commit()
        return self.get(job_id, include_payload=False)

    def requeue_stale_processing(self) -> int:
        cutoff = time.time() - self.stale_processing_seconds
        with closing(sqlite3.connect(self.path)) as conn:
            cursor = conn.execute(
                """
                UPDATE async_review_jobs
                SET status = 'retry',
                    next_attempt_at = ?,
                    updated_at = ?
                WHERE status = 'processing' AND processing_started_at IS NOT NULL AND processing_started_at < ?
                """,
                (time.time(), self._now_iso(), cutoff),
            )
            conn.commit()
            return int(cursor.rowcount)

    def list(self, status: str = "pending", limit: int = 50) -> list[dict[str, Any]]:
        status = status if status in QUEUE_STATUSES else "pending"
        limit = max(1, min(int(limit), 100))
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            if status == "all":
                rows = conn.execute(
                    """
                    SELECT *
                    FROM async_review_jobs
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM async_review_jobs
                    WHERE status = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
        return [self._row_to_job(row, include_payload=False) for row in rows]

    def get(self, job_id: int, include_payload: bool = False) -> dict[str, Any] | None:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM async_review_jobs WHERE id = ?", (int(job_id),)).fetchone()
        return self._row_to_job(row, include_payload=include_payload) if row else None

    def status(self) -> dict[str, Any]:
        with closing(sqlite3.connect(self.path)) as conn:
            return self._status_from_conn(conn)

    def _status_from_conn(self, conn: sqlite3.Connection) -> dict[str, Any]:
        counts = {key: 0 for key in ["pending", "retry", "processing", "completed", "dead_letter"]}
        rows = conn.execute(
            """
            SELECT status, COUNT(*)
            FROM async_review_jobs
            GROUP BY status
            """
        ).fetchall()
        for status, count in rows:
            if status in counts:
                counts[status] = int(count)
        active_depth = counts["pending"] + counts["retry"] + counts["processing"]
        return {
            **counts,
            "queued": counts["pending"] + counts["retry"],
            "active_depth": active_depth,
            "max_depth": self.max_depth,
            "available_depth": max(0, self.max_depth - active_depth),
            "backpressure": active_depth >= self.max_depth,
            "max_attempts": self.max_attempts,
            "sqlite_enabled": True,
            "sqlite_path": str(self.path),
        }

    def _active_depth(self, conn: sqlite3.Connection) -> int:
        placeholders = ",".join("?" for _ in ACTIVE_QUEUE_STATUSES)
        return int(
            conn.execute(
                f"SELECT COUNT(*) FROM async_review_jobs WHERE status IN ({placeholders})",
                ACTIVE_QUEUE_STATUSES,
            ).fetchone()[0]
        )

    def _row_to_job(self, row: sqlite3.Row, include_payload: bool = False) -> dict[str, Any]:
        packet = json.loads(row["packet_json"] or "{}")
        job = {
            "id": int(row["id"]),
            "status": row["status"],
            "attempts": int(row["attempts"] or 0),
            "max_attempts": int(row["max_attempts"] or self.max_attempts),
            "event_type": row["event_type"],
            "route": row["route"],
            "site_id": packet.get("site_id"),
            "user_hash": packet.get("user_hash"),
            "ip_hash": row["ip_hash"],
            "rule_id": row["rule_id"],
            "feature_scope": packet.get("feature_scope") or packet.get("endpoint_type"),
            "body_signals": (packet.get("body_summary") or {}).get("signals") or [],
            "body_preview": (packet.get("body_summary") or {}).get("preview"),
            "last_error": row["last_error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "next_attempt_at": row["next_attempt_at"],
        }
        if include_payload:
            job["packet"] = packet
            job["route_detail"] = json.loads(row["route_json"] or "{}")
        if row["result_json"]:
            job["result"] = json.loads(row["result_json"])
        return job

    def _ensure_schema(self) -> None:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS async_review_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    event_type TEXT,
                    route TEXT,
                    ip_hash TEXT,
                    rule_id TEXT,
                    packet_json TEXT NOT NULL,
                    route_json TEXT NOT NULL,
                    result_json TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    next_attempt_at REAL,
                    processing_started_at REAL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_async_review_status ON async_review_jobs(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_async_review_next ON async_review_jobs(next_attempt_at)")
            conn.commit()

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

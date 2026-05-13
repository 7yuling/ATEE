from collections import defaultdict, deque
from time import time
from typing import Any


class AppealService:
    def __init__(self):
        self._get_hits: dict[str, deque[float]] = defaultdict(deque)
        self._post_hits: dict[str, deque[float]] = defaultdict(deque)
        self.appeals: dict[str, dict[str, Any]] = {}

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
        return {"status": 202, "accepted": True, "appeal": appeal}

    def _rate_limit(self, hits: deque[float], window_seconds: int, limit: int) -> bool:
        now = time()
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True


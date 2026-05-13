from datetime import datetime, timezone
from typing import Any


class SecurityLedgerLite:
    def __init__(self, max_bytes: int = 256 * 1024 * 1024):
        self.max_bytes = max_bytes
        self.records: list[dict[str, Any]] = []
        self.aggregates: dict[tuple[str, str, str, int], dict[str, Any]] = {}

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
        self._trim_if_needed()
        return record

    def status(self) -> dict[str, Any]:
        return {
            "max_bytes": self.max_bytes,
            "records": len(self.records),
            "aggregates": len(self.aggregates),
            "raw_prompt_storage": False,
            "raw_request_body_storage": False,
        }

    def _trim_if_needed(self) -> None:
        rough_bytes = sum(len(str(record)) for record in self.records)
        while self.records and rough_bytes > self.max_bytes:
            self.records.pop(0)
            rough_bytes = sum(len(str(record)) for record in self.records)


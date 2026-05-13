from datetime import datetime, timedelta, timezone
from typing import Any


class ActionExecutor:
    def __init__(self):
        self.actions: list[dict[str, Any]] = []

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
        }
        self.actions.append(record)
        return {"executed": True, "record": record}

    def _idempotency_key(self, action: str, decision: dict[str, Any]) -> str:
        target = decision.get("target_scope") or {}
        return f"{action}:{target.get('type')}:{target.get('hash') or target.get('name') or 'request'}"


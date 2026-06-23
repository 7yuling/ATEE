from dataclasses import dataclass, field
from typing import Any


ALLOWED_ACTIONS = {
    "allow",
    "challenge",
    "cooldown",
    "feature_ban",
    "account_ban_short",
    "ip_ban_short",
    "adjust_trust_score",
    "adjust_single_user_trust_score",
    "rule_hint",
}

FORBIDDEN_ACTIONS = {
    "permanent_ban",
    "delete_user",
    "delete_content",
    "modify_global_policy",
    "modify_global_scoring_rule",
    "bulk_reset_trust_score",
    "shell_exec",
    "shutdown_site",
    "ban_all_users",
    "close_site_directly",
}


@dataclass
class RequestContext:
    method: str = "GET"
    path: str = "/"
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, Any] = field(default_factory=dict)
    body: Any = None
    remote_addr: str = "127.0.0.1"
    user_id: str | None = None
    site_id: int | None = None
    session_id: str | None = None
    event_type: str | None = None
    feature_scope: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any], remote_addr: str = "127.0.0.1") -> "RequestContext":
        headers = payload.get("headers") or {}
        return cls(
            method=str(payload.get("method", "GET")).upper(),
            path=str(payload.get("path", "/")),
            headers={str(k): str(v) for k, v in headers.items()},
            query=payload.get("query") or {},
            body=payload.get("body"),
            remote_addr=str(payload.get("remote_addr") or remote_addr),
            user_id=_optional_str(payload.get("user_id")),
            site_id=_optional_int(payload.get("site_id")),
            session_id=_optional_str(payload.get("session_id")),
            event_type=_optional_str(payload.get("event_type")),
            feature_scope=_optional_str(payload.get("feature_scope")),
        )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None

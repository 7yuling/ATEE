from .models import RequestContext


SYNC_EVENT_TYPES = {
    "login",
    "admin_login",
    "register",
    "payment",
    "refund",
    "privilege",
    "admin_action",
    "password_change",
    "email_change",
    "api_key",
}

ASYNC_EVENT_TYPES = {
    "post_create",
    "comment_create",
    "upload",
    "private_message",
}


class RequestRouter:
    def route(self, ctx: RequestContext, fast_path: dict) -> dict:
        if fast_path["action"] == "skip":
            return {"route": "skip", "reason": fast_path["reason"]}
        if fast_path["action"] in {"block_403", "rate_limited"}:
            return {"route": "fast_path_block", "reason": fast_path["reason"]}

        event_type = self._normalize_event_type(ctx)
        if event_type in SYNC_EVENT_TYPES:
            return {"route": "sync_agent", "event_type": event_type, "reason": "sensitive operation"}
        if event_type in ASYNC_EVENT_TYPES:
            return {"route": "async_agent", "event_type": event_type, "reason": "content operation"}
        if ctx.method == "GET":
            return {"route": "skip", "event_type": event_type, "reason": "low-risk read path"}
        return {"route": "async_agent", "event_type": event_type, "reason": "default write operation"}

    def _normalize_event_type(self, ctx: RequestContext) -> str:
        if ctx.event_type:
            return ctx.event_type.strip().lower().replace("-", "_")
        path = ctx.path.lower()
        if "login" in path:
            return "login"
        if "register" in path or "signup" in path:
            return "register"
        if "payment" in path or "pay" in path:
            return "payment"
        if "admin" in path:
            return "admin_action"
        if "comment" in path:
            return "comment_create"
        if "upload" in path:
            return "upload"
        if "message" in path:
            return "private_message"
        return "read" if ctx.method == "GET" else "write"


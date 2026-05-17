import hashlib
from typing import Any

from .models import RequestContext


SENSITIVE_HEADERS = {"cookie", "authorization", "x-api-key", "x-auth-token"}
SENSITIVE_KEYS = {
    "password",
    "passwd",
    "token",
    "authorization",
    "cookie",
    "secret",
    "api_key",
    "密码",
    "口令",
    "令牌",
    "密钥",
    "验证码",
    "手机",
    "手机号",
    "邮箱",
    "身份证",
    "银行卡",
}


class PromptPacketCompiler:
    def __init__(self, salt: str = "atee-local-demo"):
        self.salt = salt

    def compile(self, ctx: RequestContext, real_ip: dict[str, Any], fast_path: dict, route: dict) -> dict[str, Any]:
        clean_headers = {
            k: v
            for k, v in ctx.headers.items()
            if k.lower() not in SENSITIVE_HEADERS and "token" not in k.lower()
        }
        body_summary = self._summarize_body(ctx.body)
        return {
            "method": ctx.method,
            "path": ctx.path,
            "headers": clean_headers,
            "query_keys": sorted(str(k) for k in ctx.query.keys()),
            "body_summary": body_summary,
            "user_hash": self._hash(ctx.user_id),
            "session_hash": self._hash(ctx.session_id),
            "ip_hash": self._hash(real_ip.get("client_ip")),
            "endpoint_type": route.get("event_type"),
            "fast_path_signal": {
                "action": fast_path.get("action"),
                "rule_id": fast_path.get("rule_id"),
            },
            "allowed_actions": sorted(
                ["allow", "challenge", "cooldown", "feature_ban", "account_ban_short", "ip_ban_short", "adjust_trust_score", "rule_hint"]
            ),
            "forbidden_actions": sorted(
                ["shell_exec", "ban_all_users", "delete_user", "delete_content", "modify_global_policy"]
            ),
            "admin_policy": {
                "raw_prompt_storage": False,
                "business_db_mutation": False,
                "content_delete": False,
            },
            "privacy_note": "标准敏感字段会被脱敏；自由文本中的全部隐私无法保证 100% 识别。",
        }

    def _summarize_body(self, body: Any) -> dict[str, Any]:
        if body is None:
            return {"type": "empty", "length": 0, "signals": []}
        redacted = self._redact(body)
        text = str(redacted)
        signals = []
        lowered = text.lower()
        for signal in (
            "script",
            "union select",
            "password",
            "token",
            "phone",
            "@",
            "密码",
            "手机号",
            "手机",
            "邮箱",
            "身份证",
            "银行卡",
            "验证码",
            "spam",
            "scam",
            "广告",
            "刷屏",
            "诈骗",
            "赌博",
            "撞库",
            "password_spray",
        ):
            if signal in lowered:
                signals.append(signal)
        return {
            "type": type(body).__name__,
            "length": len(text),
            "preview": text[:160],
            "truncated": len(text) > 160,
            "signals": signals,
        }

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            redacted = {}
            for key, item in value.items():
                key_text = str(key)
                if self._is_sensitive_key(key_text):
                    redacted[key_text] = "[REDACTED]"
                else:
                    redacted[key_text] = self._redact(item)
            return redacted
        if isinstance(value, list):
            return [self._redact(item) for item in value[:20]]
        return value

    def _is_sensitive_key(self, key: str) -> bool:
        lowered = key.lower()
        if lowered in SENSITIVE_KEYS or "token" in lowered:
            return True
        return any(word in key for word in ("密码", "口令", "令牌", "密钥", "验证码", "手机号", "手机", "邮箱", "身份证", "银行卡"))

    def _hash(self, value: Any) -> str | None:
        if value is None:
            return None
        data = f"{self.salt}:{value}".encode("utf-8")
        return hashlib.sha256(data).hexdigest()[:24]

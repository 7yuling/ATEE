import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from time import monotonic, perf_counter
from typing import Any

from .secret_store import SecretStoreError, load_secret_file


REMOTE_ATTEMPT_COST_CENTS = 1
FAILURE_CIRCUIT_THRESHOLD = 3
FAILURE_CIRCUIT_COOLDOWN_SECONDS = 60
REMOTE_FAILURE_REASONS = {"provider_request_failed", "provider_timeout"}


class RemoteLLMGateway:
    def __init__(self, config: Any, base_dir: str | Path | None = None):
        self.config = config
        self.base_dir = Path(base_dir) if base_dir else None
        self.calls = 0
        self.failures = 0
        self.last_result: dict[str, Any] | None = None
        self.daily_spend_cents = 0
        self.budget_day = date.today().isoformat()
        self.consecutive_failures = 0
        self.circuit_opened_until = 0.0

    def review(self, packet: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
        start = perf_counter()
        self.calls += 1

        if self.config.llm_mode == "disabled":
            result = self._fallback_result("llm_disabled")
        elif self.config.llm_mode in {"openai_compatible", "remote"}:
            result = self._openai_compatible_review(packet, route)
        else:
            result = self._mock_review(packet, route)

        result["latency_ms"] = int((perf_counter() - start) * 1000)
        self.last_result = result
        self._record_result(result)
        return result

    def test_connection(self) -> dict[str, Any]:
        packet = {
            "method": "POST",
            "path": "/health-check",
            "body_summary": {"preview": "hello", "signals": []},
            "endpoint_type": "health_check",
            "privacy_note": "raw prompt storage disabled",
        }
        result = self.review(packet, {"route": "sync_agent", "event_type": "health_check"})
        return {
            "ok": result["ok"],
            "provider": result["provider"],
            "model": result["model"],
            "mode": self.config.llm_mode,
            "reason": result.get("reason"),
            "latency_ms": result["latency_ms"],
            "api_base_configured": bool(self.config.llm_api_base),
            "api_key_configured": bool(self._load_api_key()),
            "proxy_configured": bool(getattr(self.config, "llm_proxy_url", None)),
            "budget": self._budget_status(),
            "circuit": self._circuit_status(),
            "display": {
                "locale": "zh-CN",
                "message_zh": "模型网关连接正常。" if result["ok"] else "模型网关当前不可用，请检查供应商、模型名、网络和密钥配置。",
            },
        }

    def status(self) -> dict[str, Any]:
        self._refresh_budget_window()
        return {
            "mode": self.config.llm_mode,
            "provider": self.config.llm_provider,
            "model": self.config.llm_model,
            "calls": self.calls,
            "failures": self.failures,
            "last_ok": None if self.last_result is None else bool(self.last_result.get("ok")),
            "api_base_configured": bool(self.config.llm_api_base),
            "api_key_configured": bool(self._load_api_key()),
            "proxy_configured": bool(getattr(self.config, "llm_proxy_url", None)),
            "budget": self._budget_status(),
            "circuit": self._circuit_status(),
            "raw_prompt_storage": False,
        }

    def _openai_compatible_review(self, packet: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
        api_key = self._load_api_key()
        if not self.config.llm_api_base:
            return self._fallback_result("missing_api_base")
        if self._insecure_remote_api_base():
            return self._fallback_result("insecure_api_base_requires_https")
        if not api_key:
            return self._fallback_result("missing_api_key")
        if self._circuit_is_open():
            return self._fallback_result("llm_circuit_open")
        if not self._reserve_budget():
            return self._fallback_result("llm_budget_exhausted")

        payload = {
            "model": self.config.llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are ATEE security reviewer. Return only JSON with keys "
                        "selected_action and ai_confidence. Allowed selected_action values: "
                        "allow, challenge, cooldown, feature_ban, account_ban_short, "
                        "ip_ban_short, rule_hint."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "route": route,
                            "packet_summary": {
                                "endpoint_type": packet.get("endpoint_type"),
                                "method": packet.get("method"),
                                "path": packet.get("path"),
                                "body_summary": packet.get("body_summary"),
                                "fast_path_signal": packet.get("fast_path_signal"),
                                "privacy_note": packet.get("privacy_note"),
                            },
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            ],
            "temperature": 0,
            "max_tokens": 200,
        }
        request = urllib.request.Request(
            self._chat_completions_url(),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        timeout_seconds = max(1.0, float(self.config.remote_hard_timeout_ms) / 1000.0)
        request_start = perf_counter()
        try:
            with self._open(request, timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except TimeoutError:
            return self._fallback_result("provider_timeout")
        except urllib.error.HTTPError as exc:
            exc.close()
            return self._fallback_result("provider_request_failed")
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                return self._fallback_result("provider_timeout")
            return self._fallback_result("provider_request_failed")
        except (OSError, json.JSONDecodeError):
            return self._fallback_result("provider_request_failed")

        provider_latency_ms = int((perf_counter() - request_start) * 1000)

        return {
            "ok": True,
            "provider": self.config.llm_provider,
            "model": self.config.llm_model,
            "llm_called": True,
            "reason": "provider_json_decision",
            "agent_decision": self._parse_openai_decision(data),
            "raw_prompt_stored": False,
            "provider_latency_ms": provider_latency_ms,
            "soft_timeout_exceeded": provider_latency_ms > int(self.config.remote_soft_timeout_ms),
            "display": {
                "locale": "zh-CN",
                "message_zh": "模型网关已完成结构化判断。",
            },
        }

    def _parse_openai_decision(self, data: dict[str, Any]) -> dict[str, Any]:
        choices = data.get("choices") if isinstance(data, dict) else None
        content = ""
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else {}
            content = str((message or {}).get("content") or "")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {}
        confidence = parsed.get("ai_confidence", 0.50) if isinstance(parsed, dict) else 0.50
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.50
        return {
            "selected_action": parsed.get("selected_action", "rule_hint") if isinstance(parsed, dict) else "rule_hint",
            "ai_confidence": max(0.0, min(1.0, confidence)),
        }

    def _fallback_result(self, reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "provider": self.config.llm_provider,
            "model": self.config.llm_model,
            "llm_called": False,
            "reason": reason,
            "agent_decision": {"selected_action": "rule_hint", "ai_confidence": 0.50},
            "raw_prompt_stored": False,
        }

    def _record_result(self, result: dict[str, Any]) -> None:
        if not result.get("ok"):
            self.failures += 1
        reason = str(result.get("reason") or "")
        if result.get("ok"):
            self.consecutive_failures = 0
            self.circuit_opened_until = 0.0
        elif reason in REMOTE_FAILURE_REASONS:
            self.consecutive_failures += 1
            if self.consecutive_failures >= FAILURE_CIRCUIT_THRESHOLD:
                self.circuit_opened_until = monotonic() + FAILURE_CIRCUIT_COOLDOWN_SECONDS

    def _reserve_budget(self) -> bool:
        self._refresh_budget_window()
        budget = self._daily_budget_cents()
        if budget <= 0:
            return True
        if self.daily_spend_cents + REMOTE_ATTEMPT_COST_CENTS > budget:
            return False
        self.daily_spend_cents += REMOTE_ATTEMPT_COST_CENTS
        return True

    def _refresh_budget_window(self) -> None:
        today = date.today().isoformat()
        if self.budget_day != today:
            self.budget_day = today
            self.daily_spend_cents = 0

    def _daily_budget_cents(self) -> int:
        try:
            return max(0, int(getattr(self.config, "llm_daily_budget_cents", 0) or 0))
        except (TypeError, ValueError):
            return 0

    def _budget_status(self) -> dict[str, Any]:
        self._refresh_budget_window()
        budget = self._daily_budget_cents()
        remaining = None if budget <= 0 else max(0, budget - self.daily_spend_cents)
        return {
            "daily_budget_cents": budget,
            "daily_spend_cents": self.daily_spend_cents,
            "daily_remaining_cents": remaining,
            "estimated_cost_per_remote_attempt_cents": REMOTE_ATTEMPT_COST_CENTS,
            "budget_day": self.budget_day,
        }

    def _circuit_is_open(self) -> bool:
        return monotonic() < self.circuit_opened_until

    def _circuit_status(self) -> dict[str, Any]:
        remaining_ms = max(0, int((self.circuit_opened_until - monotonic()) * 1000))
        return {
            "open": remaining_ms > 0,
            "consecutive_failures": self.consecutive_failures,
            "failure_threshold": FAILURE_CIRCUIT_THRESHOLD,
            "cooldown_seconds": FAILURE_CIRCUIT_COOLDOWN_SECONDS,
            "remaining_ms": remaining_ms,
        }

    def _chat_completions_url(self) -> str:
        base = str(self.config.llm_api_base or "").rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def _open(self, request: urllib.request.Request, timeout_seconds: float):
        proxy_url = getattr(self.config, "llm_proxy_url", None)
        if proxy_url:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": str(proxy_url), "https": str(proxy_url)})
            )
            return opener.open(request, timeout=timeout_seconds)
        return urllib.request.urlopen(request, timeout=timeout_seconds)

    def _insecure_remote_api_base(self) -> bool:
        parsed = urllib.parse.urlparse(str(self.config.llm_api_base or ""))
        if parsed.scheme != "http":
            return False
        host = (parsed.hostname or "").lower()
        return host not in {"127.0.0.1", "localhost", "::1"}

    def _load_api_key(self) -> str | None:
        env_name = str(getattr(self.config, "llm_api_key_env", "") or "")
        if env_name and os.environ.get(env_name):
            return os.environ[env_name].lstrip("\ufeff").strip() or None
        key_file = getattr(self.config, "llm_api_key_file", None)
        if not key_file:
            return None
        try:
            return load_secret_file(self._resolve_file_path(str(key_file)))
        except (OSError, SecretStoreError):
            return None

    def _resolve_file_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute() or self.base_dir is None:
            return path
        return self.base_dir / path

    def _mock_review(self, packet: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
        body_summary = packet.get("body_summary") or {}
        preview = str(body_summary.get("preview") or "").lower()
        signals = set(body_summary.get("signals") or [])
        event_type = str(route.get("event_type") or packet.get("endpoint_type") or "")

        selected_action = "allow"
        confidence = 0.52
        reason = "mock_allow"

        if signals.intersection({"credential_attack", "撞库", "password_spray"}):
            selected_action = "challenge"
            confidence = 0.78
            reason = "mock_credential_attack"
        elif signals.intersection({"spam", "scam", "刷屏", "广告", "诈骗", "赌博"}):
            selected_action = "rule_hint"
            confidence = 0.72
            reason = "mock_suspicious_content"
        elif event_type in {"payment", "privilege", "admin_action", "api_key"}:
            selected_action = "challenge"
            confidence = 0.62
            reason = "mock_sensitive_operation"
        elif "ignore previous" in preview or "忽略前面的" in preview:
            selected_action = "rule_hint"
            confidence = 0.70
            reason = "mock_prompt_injection_hint"

        return {
            "ok": True,
            "provider": self.config.llm_provider,
            "model": self.config.llm_model,
            "llm_called": True,
            "reason": reason,
            "agent_decision": {
                "selected_action": selected_action,
                "ai_confidence": confidence,
            },
            "raw_prompt_stored": False,
            "display": {
                "locale": "zh-CN",
                "message_zh": "模型网关 mock 已完成结构化判断。",
            },
        }

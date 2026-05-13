from copy import deepcopy
from pathlib import Path
from typing import Any

from .actions import ActionExecutor
from .appeals import AppealService
from .config import DEFAULT_CONFIG, AdminConfig, ConfigStore, config_to_dict
from .decision_engine import AgentDecisionEngine
from .fast_path import FastPathRuleGate
from .i18n import response_display, runtime_display
from .ip_resolver import TrustedRealIpResolver
from .ledger import SecurityLedgerLite
from .models import RequestContext
from .onboarding import get_onboarding_steps
from .prompt_packet import PromptPacketCompiler
from .router import RequestRouter
from .runtime import RuntimeController
from .tool_gateway import ToolGateway


class CoreService:
    def __init__(self, config: AdminConfig | None = None, config_path: str | Path | None = None):
        self.config_store = ConfigStore(config_path) if config_path else None
        if config is not None:
            self.config = deepcopy(config)
        elif self.config_store:
            self.config = self.config_store.load()
        else:
            self.config = deepcopy(DEFAULT_CONFIG)
        self._load_bypass_key()
        self.ip_resolver = TrustedRealIpResolver(self.config.trusted_proxy_cidrs)
        self.fast_path = FastPathRuleGate()
        self.router = RequestRouter()
        self.packet_compiler = PromptPacketCompiler()
        self.decision_engine = AgentDecisionEngine()
        self.tool_gateway = ToolGateway()
        self.executor = ActionExecutor()
        self.ledger = SecurityLedgerLite(self.config.ledger_max_bytes)
        self.appeals = AppealService()
        self.runtime = RuntimeController(self.config)

    def check(self, payload: dict[str, Any], remote_addr: str = "127.0.0.1") -> dict[str, Any]:
        ctx = RequestContext.from_payload(payload, remote_addr=remote_addr)
        real_ip = self.ip_resolver.resolve(ctx.headers, ctx.remote_addr)
        fast_path = self.fast_path.evaluate(ctx, real_ip)
        route = self.router.route(ctx, fast_path)

        if route["route"] == "skip":
            packet = self.packet_compiler.compile(ctx, real_ip, fast_path, route)
            ledger_record = self.ledger.record(
                {
                    "severity": "low",
                    "event_type": "skip",
                    "ip_hash": packet.get("ip_hash"),
                    "rule_id": fast_path.get("rule_id"),
                    "endpoint_type": route.get("event_type"),
                    "action": "allow",
                    "summary": "low-risk request skipped",
                }
            )
            return self._response(ctx, real_ip, fast_path, route, {"selected_action": "allow"}, None, ledger_record, None)

        if route["route"] == "fast_path_block":
            packet = self.packet_compiler.compile(ctx, real_ip, fast_path, route)
            ledger_record = self.ledger.record(
                {
                    "severity": "high",
                    "event_type": "fast_path_block",
                    "ip_hash": packet.get("ip_hash"),
                    "rule_id": fast_path.get("rule_id"),
                    "endpoint_type": route.get("event_type"),
                    "action": fast_path.get("action"),
                    "summary": fast_path.get("reason"),
                }
            )
            decision = {
                "selected_action": "cooldown" if fast_path["action"] == "rate_limited" else "challenge",
                "scores": {
                    "evidence_score": 0.80,
                    "behavior_score": 0.70 if fast_path["action"] == "rate_limited" else 0.20,
                    "reputation_score": 0.35,
                    "ai_confidence": 0.50,
                    "final_confidence": 0.52 if fast_path["action"] != "rate_limited" else 0.645,
                },
                "duration_seconds": 300,
                "target_scope": {"type": "request"},
                "reason_codes": [f"fast_path:{fast_path.get('rule_id')}"],
            }
            gateway = self.tool_gateway.validate(decision, real_ip, self.config)
            action_record = self.executor.execute(decision, gateway)
            return self._response(ctx, real_ip, fast_path, route, decision, gateway, ledger_record, action_record)

        packet = self.packet_compiler.compile(ctx, real_ip, fast_path, route)
        decision = self.decision_engine.decide(packet, route, payload.get("agent_decision"))
        gateway = self.tool_gateway.validate(decision, real_ip, self.config)
        action_record = self.executor.execute(decision, gateway)
        ledger_record = self.ledger.record(
            {
                "severity": "medium" if decision["selected_action"] in {"allow", "rule_hint"} else "high",
                "event_type": "agent_decision",
                "ip_hash": packet.get("ip_hash"),
                "rule_id": fast_path.get("rule_id"),
                "endpoint_type": route.get("event_type"),
                "action": gateway.get("effective_action"),
                "summary": decision.get("admin_explanation", ""),
            }
        )
        return self._response(ctx, real_ip, fast_path, route, decision, gateway, ledger_record, action_record)

    def event(self, payload: dict[str, Any], remote_addr: str = "127.0.0.1") -> dict[str, Any]:
        event_payload = dict(payload)
        event_payload.setdefault("method", "POST")
        return self.check(event_payload, remote_addr=remote_addr)

    def appeal(self, payload: dict[str, Any], remote_addr: str = "127.0.0.1") -> dict[str, Any]:
        ctx = RequestContext.from_payload(payload, remote_addr=remote_addr)
        real_ip = self.ip_resolver.resolve(ctx.headers, ctx.remote_addr)
        ip_hash = self.packet_compiler._hash(real_ip.get("client_ip"))
        result = self.appeals.submit(payload, ip_hash)
        result["display"] = self._appeal_display(result)
        if result["status"] != 429:
            self.ledger.record(
                {
                    "severity": "medium",
                    "event_type": "appeal",
                    "ip_hash": ip_hash,
                    "endpoint_type": "appeal",
                    "action": "record_appeal",
                    "summary": result.get("reason") or "appeal submitted",
                }
            )
        return result

    def runtime_status(self) -> dict[str, Any]:
        status = {
            **self.runtime.status(),
            "ledger": self.ledger.status(),
            "actions_executed": len(self.executor.actions),
            "pending_appeals": sum(1 for appeal in self.appeals.appeals.values() if appeal["status"] == "pending"),
            "config": self.config_store.public_payload(self.config) if self.config_store else config_to_dict(self.config),
        }
        status["display"] = runtime_display(status)
        return status

    def set_mode(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.runtime.set_mode(str(payload.get("mode", "")))
        if result.get("ok"):
            self._save_config()
        result["display"] = runtime_display(self.runtime.status())
        return result

    def pause_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.runtime.pause_agent(bool(payload.get("paused", True)))
        if result.get("ok"):
            self._save_config()
        result["display"] = runtime_display(self.runtime.status())
        return result

    def config_status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "config": self.config_store.public_payload(self.config) if self.config_store else config_to_dict(self.config),
            "display": {
                "locale": "zh-CN",
                "message_zh": "配置已加载。敏感密钥不会通过该接口返回。",
            },
        }

    def update_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "locale",
            "trusted_proxy_cidrs",
            "auto_ip_ban_enabled",
            "local_precheck_ms",
            "remote_soft_timeout_ms",
            "remote_hard_timeout_ms",
            "ledger_max_bytes",
            "bypass_enabled",
            "bypass_key_file",
        }
        changed: dict[str, Any] = {}
        for key in allowed:
            if key not in payload:
                continue
            value = payload[key]
            if key == "trusted_proxy_cidrs":
                value = [str(item) for item in (value or [])]
            elif key.endswith("_ms") or key == "ledger_max_bytes":
                value = int(value)
            elif key in {"auto_ip_ban_enabled", "bypass_enabled"}:
                value = bool(value)
            elif value is not None:
                value = str(value)
            setattr(self.config, key, value)
            changed[key] = value

        if changed:
            self._load_bypass_key()
            self.ip_resolver = TrustedRealIpResolver(self.config.trusted_proxy_cidrs)
            self.ledger.max_bytes = self.config.ledger_max_bytes
            self._save_config()
        return {
            "ok": True,
            "changed": changed,
            "config": self.config_store.public_payload(self.config) if self.config_store else config_to_dict(self.config),
            "display": {
                "locale": "zh-CN",
                "message_zh": "配置已保存。" if changed else "没有配置变更。",
            },
        }

    def onboarding_steps(self) -> dict[str, Any]:
        return get_onboarding_steps()

    def _save_config(self) -> None:
        if self.config_store:
            self.config_store.save(self.config)

    def _load_bypass_key(self) -> None:
        if not self.config.bypass_key_file:
            return
        try:
            self.config.bypass_key = Path(self.config.bypass_key_file).read_text(encoding="utf-8").strip()
        except OSError:
            self.config.bypass_key = None

    def break_glass_status(self, headers: dict[str, str] | None = None) -> dict[str, Any]:
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        supplied = headers.get("x-atee-bypass")
        valid = bool(self.config.bypass_enabled and self.config.bypass_key and supplied == self.config.bypass_key)
        if valid:
            self.ledger.record(
                {
                    "severity": "high",
                    "event_type": "break_glass",
                    "endpoint_type": "admin",
                    "action": "bypass_status_check",
                    "summary": "Break-glass header accepted; rotate key after use.",
                }
            )
        return {
            "enabled": self.config.bypass_enabled,
            "header": "X-ATEE-Bypass",
            "url_parameter_supported": False,
            "valid_for_request": valid,
            "rotate_key_after_use": valid,
            "display": {
                "locale": "zh-CN",
                "message_zh": "紧急旁路已验证，请使用后立即轮换密钥。" if valid else "紧急旁路未启用或本次请求未通过验证。",
                "url_parameter_supported_zh": "不支持固定 URL 明文参数。",
            },
        }

    def _appeal_display(self, result: dict[str, Any]) -> dict[str, str]:
        status = result.get("status")
        if status == 202:
            message = "申诉已提交，请等待管理员处理。"
        elif status == 200:
            message = "该处罚已有待处理申诉，请不要重复提交。"
        elif status == 429:
            message = "申诉提交过于频繁，本次没有写入数据库。"
        else:
            message = "申诉请求未被接受，请检查处罚编号。"
        return {"locale": "zh-CN", "message_zh": message}

    def _response(
        self,
        ctx: RequestContext,
        real_ip: dict[str, Any],
        fast_path: dict[str, Any],
        route: dict[str, Any],
        decision: dict[str, Any],
        gateway: dict[str, Any] | None,
        ledger_record: dict[str, Any] | None,
        action_record: dict[str, Any] | None,
    ) -> dict[str, Any]:
        runtime_status = self.runtime.status()
        return {
            "request": {"method": ctx.method, "path": ctx.path},
            "real_ip": real_ip,
            "fast_path": fast_path,
            "route": route,
            "decision": decision,
            "tool_gateway": gateway,
            "action_result": action_record,
            "ledger_record": ledger_record,
            "runtime": runtime_status,
            "display": response_display(route, decision, gateway, runtime_status),
        }

import json
import hashlib
import hmac
import os
import platform
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from .actions import ActionExecutor
from .admin_auth import AdminAuthService
from .api_keys import ApiKeyRegistry
from .appeals import AppealService
from .async_review import AsyncReviewQueue, AsyncReviewQueueFull
from .config import DEFAULT_CONFIG, AdminConfig, ConfigStore, config_to_dict
from .decision_engine import AgentDecisionEngine
from .fast_path import FastPathRuleGate
from .i18n import response_display, runtime_display
from .ip_resolver import TrustedRealIpResolver
from .ledger import SecurityLedgerLite
from .llm_gateway import RemoteLLMGateway
from .models import RequestContext
from .onboarding import get_onboarding_steps
from .prompt_packet import PromptPacketCompiler
from .router import RequestRouter
from .runtime import RuntimeController, VALID_MODES
from .secret_store import SecretStoreError, load_secret_file
from .tool_gateway import ToolGateway


ASYNC_REVIEW_PAUSE_REASONS = {"llm_budget_exhausted"}
MANUAL_FEATURE_BAN_MAX_SECONDS = 7 * 24 * 3600
INTEGRATION_PLAN_DEFAULT_FEATURES = ["comments"]
INTEGRATION_PLAN_SENSITIVE_MARKERS = (
    "authorization",
    "bearer ",
    "api_key",
    "api key",
    "admin_token",
    "admin token",
    "proxy_url",
    "proxy url",
)


class AsyncReviewProcessingPaused(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class CoreService:
    def __init__(self, config: AdminConfig | None = None, config_path: str | Path | None = None):
        self.config_store = ConfigStore(config_path) if config_path else None
        if config is not None:
            self.config = deepcopy(config)
        elif self.config_store:
            self.config = self.config_store.load()
        else:
            self.config = deepcopy(DEFAULT_CONFIG)
        self.project_root = self._infer_project_root()
        self._load_admin_token()
        self._load_bypass_key()
        self.ip_resolver = TrustedRealIpResolver(self.config.trusted_proxy_cidrs)
        self.fast_path = FastPathRuleGate()
        self.router = RequestRouter()
        self.packet_compiler = PromptPacketCompiler()
        self.decision_engine = AgentDecisionEngine()
        self.llm_gateway = RemoteLLMGateway(self.config, base_dir=self.project_root)
        self._load_llm_gateway_state()
        self.tool_gateway = ToolGateway()
        state_sqlite_path = self._resolve_project_path(self.config.ledger_sqlite_path)
        self.executor = ActionExecutor(state_sqlite_path)
        self.ledger = SecurityLedgerLite(self.config.ledger_max_bytes, state_sqlite_path)
        self.appeals = AppealService(state_sqlite_path)
        self.admin_auth = AdminAuthService(state_sqlite_path)
        self.api_keys = ApiKeyRegistry(state_sqlite_path)
        self.async_reviews = self._make_async_review_queue(state_sqlite_path)
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
            return self._response(ctx, real_ip, fast_path, route, {"selected_action": "allow"}, None, ledger_record, None, None)

        if route["route"] == "fast_path_block":
            packet = self.packet_compiler.compile(ctx, real_ip, fast_path, route)
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
            ledger_record = self.ledger.record(
                {
                    "severity": "high",
                    "event_type": "fast_path_block",
                    "ip_hash": packet.get("ip_hash"),
                    "rule_id": fast_path.get("rule_id"),
                    "endpoint_type": route.get("event_type"),
                    "action": fast_path.get("action"),
                    "summary": fast_path.get("reason"),
                    "details": self._ledger_details(packet, route, fast_path, decision, None, None),
                }
            )
            gateway = self.tool_gateway.validate(decision, real_ip, self.config)
            action_record = self.executor.execute(decision, gateway)
            return self._response(ctx, real_ip, fast_path, route, decision, gateway, ledger_record, action_record, None)

        packet = self.packet_compiler.compile(ctx, real_ip, fast_path, route)
        if route["route"] == "async_agent":
            return self._enqueue_async_review(ctx, real_ip, fast_path, route, packet)

        llm_result = self.llm_gateway.review(packet, route)
        self._save_llm_gateway_state()
        agent_decision = payload.get("agent_decision") or llm_result.get("agent_decision")
        decision = self.decision_engine.decide(packet, route, agent_decision)
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
                "summary": f"{decision.get('admin_explanation', '')} llm_reason={llm_result.get('reason')}",
                "details": self._ledger_details(packet, route, fast_path, decision, llm_result, gateway),
            }
        )
        return self._response(ctx, real_ip, fast_path, route, decision, gateway, ledger_record, action_record, llm_result)

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

    def feature_access(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_id = str(payload.get("user_id") or "").strip()
        feature = str(payload.get("feature_scope") or payload.get("feature") or "").strip()
        if not user_id:
            return {
                "ok": False,
                "status": 400,
                "allowed": False,
                "reason": "user_id_required",
            }
        if not feature:
            return {
                "ok": False,
                "status": 400,
                "allowed": False,
                "reason": "feature_scope_required",
            }

        user_hash = self.packet_compiler._hash(user_id)
        active_action = self.executor.find_active_user_feature(str(user_hash or ""), feature)
        if active_action:
            return {
                "ok": True,
                "status": 200,
                "allowed": False,
                "reason": "active_feature_ban",
                "user_hash": user_hash,
                "feature_scope": feature,
                "active_action": active_action,
                "punishment_id": active_action.get("punishment_id"),
                "expires_at": active_action.get("expires_at"),
                "display": {
                    "locale": "zh-CN",
                    "message_zh": "Feature access is blocked by an active ATEE feature_ban.",
                },
            }
        return {
            "ok": True,
            "status": 200,
            "allowed": True,
            "reason": "no_active_feature_ban",
            "user_hash": user_hash,
            "feature_scope": feature,
            "active_action": None,
            "punishment_id": None,
            "expires_at": None,
            "display": {
                "locale": "zh-CN",
                "message_zh": "Feature access is allowed; no active ATEE feature_ban matched.",
            },
        }

    def runtime_status(self) -> dict[str, Any]:
        status = {
            **self.runtime.status(),
            "ledger": self.ledger.status(),
            "actions_executed": len(self.executor.actions),
            "active_actions": len(self.executor.list_actions(status="active")),
            "pending_appeals": sum(1 for appeal in self.appeals.appeals.values() if appeal["status"] == "pending"),
            "async_review": self.async_reviews.status() if self.async_reviews else {"sqlite_enabled": False},
            "async_review_worker": self.async_review_worker_status(),
            "llm_gateway": self.llm_gateway.status(),
            "admin_auth": self.admin_auth_status(),
            "config": self.config_store.public_payload(self.config) if self.config_store else config_to_dict(self.config),
        }
        status["display"] = runtime_display(status)
        return status

    def set_mode(self, payload: dict[str, Any], actor: dict[str, str] | None = None) -> dict[str, Any]:
        result = self.runtime.set_mode(str(payload.get("mode", "")))
        if result.get("ok"):
            self._save_config()
            self._record_admin_audit(
                "admin_runtime_mode",
                "set_mode",
                f"runtime_mode={result.get('mode')}",
                actor,
            )
        result["display"] = runtime_display(self.runtime.status())
        return result

    def pause_agent(self, payload: dict[str, Any], actor: dict[str, str] | None = None) -> dict[str, Any]:
        result = self.runtime.pause_agent(bool(payload.get("paused", True)))
        if result.get("ok"):
            self._save_config()
            self._record_admin_audit(
                "admin_pause_agent",
                "pause_agent",
                f"agent_paused={result.get('agent_paused')}",
                actor,
            )
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

    def update_config(self, payload: dict[str, Any], actor: dict[str, str] | None = None) -> dict[str, Any]:
        if self.config.runtime_mode == "read_only":
            return {
                "ok": False,
                "status": 423,
                "reason": "read_only_mode_blocks_config_update",
                "display": {
                    "locale": "zh-CN",
                    "message_zh": "只读模式下不会保存运行配置。",
                },
            }
        api_key_value = str(payload.get("llm_api_key_value") or "").lstrip("\ufeff").strip()
        allowed = {
            "runtime_mode",
            "locale",
            "trusted_proxy_cidrs",
            "agent_paused",
            "auto_ip_ban_enabled",
            "local_precheck_ms",
            "remote_soft_timeout_ms",
            "remote_hard_timeout_ms",
            "ledger_max_bytes",
            "ledger_sqlite_path",
            "async_review_worker_enabled",
            "async_review_worker_interval_seconds",
            "async_review_worker_batch_size",
            "async_review_queue_max_depth",
            "admin_auth_enabled",
            "admin_token_file",
            "admin_token_env",
            "llm_mode",
            "llm_provider",
            "llm_model",
            "llm_api_base",
            "llm_api_key_file",
            "llm_api_key_env",
            "llm_proxy_url",
            "llm_daily_budget_cents",
            "bypass_enabled",
            "bypass_key_file",
            "appeal_paths",
        }
        changed: dict[str, Any] = {}
        for key in allowed:
            if key not in payload:
                continue
            value = payload[key]
            if key == "trusted_proxy_cidrs":
                raw_items = str(value).replace(",", "\n").splitlines() if isinstance(value, str) else (value or [])
                value = [str(item).strip() for item in raw_items if str(item).strip()]
            elif key == "appeal_paths":
                raw_items = str(value).replace(",", "\n").splitlines() if isinstance(value, str) else (value or [])
                value = tuple(str(item).strip() for item in raw_items if str(item).strip())
            elif key == "runtime_mode":
                value = str(value)
                if value not in VALID_MODES:
                    continue
            elif key.endswith("_ms") or key in {
                "ledger_max_bytes",
                "llm_daily_budget_cents",
                "async_review_worker_interval_seconds",
                "async_review_worker_batch_size",
                "async_review_queue_max_depth",
            }:
                value = int(value)
            elif key in {"agent_paused", "auto_ip_ban_enabled", "bypass_enabled", "admin_auth_enabled", "async_review_worker_enabled"}:
                value = bool(value)
            elif value is not None:
                value = str(value)
            setattr(self.config, key, value)
            changed[key] = value
        if api_key_value:
            env_name = str(self.config.llm_api_key_env or "ATEE_LLM_API_KEY").strip()
            if env_name:
                os.environ[env_name] = api_key_value
                changed["llm_api_key_env_configured"] = True

        if changed:
            llm_gateway_state = self.llm_gateway.runtime_state()
            self._load_admin_token()
            self._load_bypass_key()
            self.ip_resolver = TrustedRealIpResolver(self.config.trusted_proxy_cidrs)
            self.llm_gateway = RemoteLLMGateway(self.config, base_dir=self.project_root)
            self.llm_gateway.restore_runtime_state(llm_gateway_state)
            if "ledger_max_bytes" in changed or "ledger_sqlite_path" in changed or "async_review_queue_max_depth" in changed:
                state_sqlite_path = self._resolve_project_path(self.config.ledger_sqlite_path)
                self.ledger = SecurityLedgerLite(self.config.ledger_max_bytes, state_sqlite_path)
                if "ledger_sqlite_path" in changed:
                    self.executor = ActionExecutor(state_sqlite_path)
                    self.appeals = AppealService(state_sqlite_path)
                    self.admin_auth = AdminAuthService(state_sqlite_path)
                    self.api_keys = ApiKeyRegistry(state_sqlite_path)
                if "ledger_sqlite_path" in changed or "async_review_queue_max_depth" in changed:
                    self.async_reviews = self._make_async_review_queue(state_sqlite_path)
            self._save_config()
            self._save_llm_gateway_state()
            public_changed = self._public_changed(changed)
            self._record_admin_audit(
                "admin_config_update",
                "update_config",
                f"changed_keys={','.join(sorted(public_changed))}",
                actor,
            )
        return {
            "ok": True,
            "changed": self._public_changed(changed),
            "config": self.config_store.public_payload(self.config) if self.config_store else config_to_dict(self.config),
            "display": {
                "locale": "zh-CN",
                "message_zh": "配置已保存。" if changed else "没有配置变更。",
            },
        }

    def onboarding_steps(self) -> dict[str, Any]:
        return get_onboarding_steps()

    def environment_preflight(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []

        def add_check(check_id: str, title: str, ok: bool, detail: str, next_action: str = "") -> None:
            checks.append(
                {
                    "id": check_id,
                    "title_zh": title,
                    "ok": bool(ok),
                    "detail_zh": detail,
                    "next_action_zh": next_action,
                }
            )

        config_path = self.config_store.path if self.config_store else None
        add_check(
            "python_runtime",
            "Python 运行环境",
            sys.version_info >= (3, 10),
            f"当前 Python {platform.python_version()}，建议使用 3.10 或更高版本。",
            "低版本请先升级 Python，再启动 Core Service。",
        )
        add_check(
            "config_file",
            "配置文件",
            bool(config_path and config_path.exists()),
            "已找到 config/config.json。" if config_path and config_path.exists() else "未找到 config/config.json。",
            "首次部署请执行 cp config/config.example.json config/config.json。",
        )

        admin_dir = self.project_root / "apps" / "admin-console"
        admin_assets_ok = all((admin_dir / name).is_file() for name in ["index.html", "styles.css", "admin.js"])
        add_check(
            "admin_console_assets",
            "管理台静态资源",
            admin_assets_ok,
            "管理台构建产物可由 Core Service 托管。" if admin_assets_ok else "管理台构建产物缺失。",
            "运行 npm run build:admin 重新生成管理台资源。",
        )

        ledger_path = self._resolve_project_path(self.config.ledger_sqlite_path)
        ledger_writable = False
        if ledger_path:
            try:
                ledger_path.parent.mkdir(parents=True, exist_ok=True)
                probe = ledger_path.parent / ".atee-write-test"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink(missing_ok=True)
                ledger_writable = True
            except OSError:
                ledger_writable = False
        add_check(
            "ledger_writable",
            "账本目录",
            ledger_writable,
            "SQLite 账本目录可写。" if ledger_writable else "SQLite 账本目录不可写或未配置。",
            "为服务用户授予 data/ 目录写入权限。",
        )

        remote_mode = self.config.llm_mode in {"openai_compatible", "remote"}
        api_key_ready = bool(self.llm_gateway.status().get("api_key_configured"))
        llm_ok = not remote_mode or (bool(self.config.llm_api_base) and api_key_ready)
        add_check(
            "llm_gateway_config",
            "模型网关配置",
            llm_ok,
            "当前模型模式可启动。" if llm_ok else "远程模型模式缺少 API Base 或 API Key。",
            "在网关配置中填写 API Base，并通过环境变量或密钥文件注入 API Key。",
        )

        proxy_ok = bool(self.config.trusted_proxy_cidrs) or not self.config.auto_ip_ban_enabled
        add_check(
            "trusted_proxy",
            "真实 IP 与代理",
            proxy_ok,
            "自动 IP 封禁边界安全。" if proxy_ok else "已开启自动 IP 封禁，但未配置 trusted_proxy_cidrs。",
            "先关闭自动 IP 封禁，或填写可信反向代理 CIDR。",
        )

        bypass_ok = not self.config.bypass_enabled or bool(self.config.bypass_key_file)
        add_check(
            "break_glass",
            "紧急恢复旁路",
            bypass_ok,
            "紧急旁路未启用或已有密钥文件。" if bypass_ok else "紧急旁路已启用，但未配置密钥文件。",
            "配置旁路密钥文件，使用后立即轮换。",
        )

        ok = all(item["ok"] for item in checks)
        return {
            "ok": ok,
            "checks": checks,
            "summary": {
                "passed": sum(1 for item in checks if item["ok"]),
                "total": len(checks),
                "system": platform.system() or "unknown",
                "python": platform.python_version(),
            },
            "display": {
                "locale": "zh-CN",
                "message_zh": "环境预检通过。" if ok else "环境预检发现需要处理的项目。",
            },
        }

    def integration_plan(self, payload: dict[str, Any], actor: dict[str, str] | None = None) -> dict[str, Any]:
        site_name = self._plan_text(payload.get("site_name"), "target-site", 80)
        site_url = self._plan_url(payload.get("site_url"), "https://target.example")
        site_type = self._plan_text(payload.get("site_type"), "通用网站", 80)
        adapter_type = self._plan_text(payload.get("adapter_type"), "HTTP API", 80)
        core_url = self._plan_url(payload.get("core_url"), "http://127.0.0.1:8787")
        appeal_path = self._plan_path(payload.get("appeal_path"), "/atee-appeal")
        protected_features = self._plan_features(payload.get("protected_features"))

        self._record_admin_audit(
            "admin_integration_plan",
            "generate_integration_plan",
            f"site_type={site_type} adapter_type={adapter_type} features={len(protected_features)}",
            actor,
        )

        if adapter_type != "HTTP API":
            return {
                "ok": False,
                "status": 422,
                "reason": "unsupported_adapter_type",
                "site": {
                    "name": site_name,
                    "url": site_url,
                    "site_type": site_type,
                    "adapter_type": adapter_type,
                },
                "steps": [],
                "endpoint_mappings": [],
                "payload_examples": {},
                "verification_requests": [],
                "safety_notes_zh": [
                    "首版接入向导只生成 HTTP API 方案；请选择 HTTP API 后重新生成。",
                    "Node/Express、Python/FastAPI 和反向代理方案保留给后续扩展。",
                ],
                "display": {
                    "locale": "zh-CN",
                    "message_zh": "当前首版只支持 HTTP API 接入方案。",
                },
            }

        first_feature = protected_features[0]
        check_payload = {
            "method": "POST",
            "path": "/login",
            "headers": {"X-Forwarded-For": "203.0.113.10"},
            "query": {},
            "body": {"username": "demo-user"},
            "remote_addr": "203.0.113.10",
            "user_id": "site-user-123",
            "session_id": "session-123",
            "event_type": "login",
        }
        event_payload = {
            "method": "POST",
            "path": "/comment",
            "headers": {"X-Forwarded-For": "203.0.113.10"},
            "query": {},
            "body": {"text": "normal comment"},
            "remote_addr": "203.0.113.10",
            "user_id": "site-user-123",
            "session_id": "session-123",
            "event_type": "comment_create",
            "feature_scope": first_feature,
        }
        feature_payload = {
            "user_id": "site-user-123",
            "feature_scope": first_feature,
        }
        appeal_payload = {
            "punishment_id": "action:123",
            "reason": "please review this action",
        }

        return {
            "ok": True,
            "site": {
                "name": site_name,
                "url": site_url,
                "site_type": site_type,
                "adapter_type": adapter_type,
                "appeal_path": appeal_path,
                "protected_features": protected_features,
            },
            "core_url": core_url,
            "steps": [
                {
                    "id": "preflight",
                    "title_zh": "1. 先运行 ATEE 环境预检",
                    "detail_zh": "确认 Core Service、账本目录、模型网关和可信代理边界都处于可用状态。",
                },
                {
                    "id": "observe",
                    "title_zh": "2. 先以观察模式接入目标网站",
                    "detail_zh": f"在 {site_name} 的后端请求链路中调用 ATEE HTTP API，先记录结果，不直接改变业务数据。",
                },
                {
                    "id": "wire",
                    "title_zh": "3. 接入登录、写操作、功能访问和申诉入口",
                    "detail_zh": "登录和高风险同步动作走 /v1/check；评论、上传等事件走 /v1/event；功能入口先查 /v1/feature-access；用户申诉提交到 /v1/appeal。",
                },
                {
                    "id": "verify",
                    "title_zh": "4. 用验证请求跑通闭环",
                    "detail_zh": "确认正常请求通过、攻击样例被 Fast-Path 拦截、功能限制能展示 punishment_id，且申诉能进入管理台。",
                },
            ],
            "endpoint_mappings": [
                {
                    "site_route": "/login",
                    "core_endpoint": "/v1/check",
                    "method": "POST",
                    "purpose_zh": "登录、注册、支付等需要同步判断的高风险入口。",
                    "when_zh": "业务后端准备执行动作前调用；根据 route 和 tool_gateway 结果决定是否继续。",
                },
                {
                    "site_route": "/comment",
                    "core_endpoint": "/v1/event",
                    "method": "POST",
                    "purpose_zh": "评论、发帖、上传等写入事件。",
                    "when_zh": "业务事件发生前或刚发生后调用；普通内容可进入异步 AI 审查队列。",
                },
                {
                    "site_route": f"/features/{first_feature}",
                    "core_endpoint": "/v1/feature-access",
                    "method": "POST",
                    "purpose_zh": "检查指定用户是否被临时限制使用某个功能。",
                    "when_zh": "渲染或执行受保护功能前调用；被限制时展示返回的 punishment_id 和申诉入口。",
                },
                {
                    "site_route": appeal_path,
                    "core_endpoint": "/v1/appeal",
                    "method": "POST",
                    "purpose_zh": "提交用户申诉。",
                    "when_zh": "用户填写申诉理由后调用；管理台审核通过后可撤销可逆的功能限制。",
                },
            ],
            "payload_examples": {
                "check": {"url": f"{core_url}/v1/check", "json": check_payload},
                "event": {"url": f"{core_url}/v1/event", "json": event_payload},
                "feature_access": {"url": f"{core_url}/v1/feature-access", "json": feature_payload},
                "appeal": {"url": f"{core_url}/v1/appeal", "json": appeal_payload},
            },
            "verification_requests": [
                {
                    "id": "safe_check",
                    "title_zh": "正常登录预检",
                    "command": self._curl_example(core_url, "/v1/check", check_payload),
                    "expect_zh": "返回 route=skip 或 sync_agent，且不会出现 Fast-Path 拦截。",
                },
                {
                    "id": "attack_event",
                    "title_zh": "明显攻击样例",
                    "command": self._curl_example(
                        core_url,
                        "/v1/event",
                        {**event_payload, "body": {"text": "<script>alert(1)</script>"}},
                    ),
                    "expect_zh": "返回 route=fast_path_block，规则命中 FP_XSS_001。",
                },
                {
                    "id": "feature_access",
                    "title_zh": "功能访问检查",
                    "command": self._curl_example(core_url, "/v1/feature-access", feature_payload),
                    "expect_zh": "未限制时 allowed=true；存在功能限制时返回 punishment_id。",
                },
                {
                    "id": "appeal",
                    "title_zh": "申诉提交",
                    "command": self._curl_example(core_url, "/v1/appeal", appeal_payload),
                    "expect_zh": "返回 status=202，并能在管理台申诉列表中看到待处理记录。",
                },
            ],
            "safety_notes_zh": [
                "目标网站只转发最小请求上下文，不保存完整原始请求体到 ATEE 账本。",
                "生产上线先保持 observe 模式，复核 24 小时账本摘要后再考虑自动化处置。",
                "可信代理 CIDR 要填写代理节点网段，不要填写普通用户地址段。",
                "申诉入口必须对被限制用户可访问，并按纯文本展示用户输入。",
            ],
            "display": {
                "locale": "zh-CN",
                "message_zh": "HTTP API 接入方案已生成。",
            },
        }

    def security_flow_rehearsal(self, actor: dict[str, str] | None = None) -> dict[str, Any]:
        if self.config.runtime_mode == "read_only":
            return {
                "ok": False,
                "status": 423,
                "reason": "read_only_mode_blocks_security_flow",
                "display": {
                    "locale": "zh-CN",
                    "message_zh": "只读模式下不会执行安全流程演练。",
                },
            }

        steps: list[dict[str, Any]] = []

        def add_step(step_id: str, title: str, ok: bool, detail: str, code: str = "") -> None:
            steps.append(
                {
                    "id": step_id,
                    "title_zh": title,
                    "ok": bool(ok),
                    "status_zh": "通过" if ok else "需处理",
                    "detail_zh": str(detail)[:240],
                    "code": str(code or "")[:80],
                }
            )

        def run_step(step_id: str, title: str, callback) -> None:
            try:
                ok, detail, code = callback()
            except Exception as error:
                ok = False
                detail = f"{title}执行失败：{type(error).__name__}"
                code = "exception"
            add_step(step_id, title, bool(ok), str(detail), str(code or ""))

        def preflight_step() -> tuple[bool, str, str]:
            result = self.environment_preflight()
            summary = result.get("summary") or {}
            passed = int(summary.get("passed") or 0)
            total = int(summary.get("total") or 0)
            failed_ids = ",".join(item.get("id", "") for item in result.get("checks", []) if not item.get("ok"))
            return bool(result.get("ok")), f"环境预检完成，通过 {passed}/{total} 项。", failed_ids

        def safe_request_step() -> tuple[bool, str, str]:
            result = self.check(
                {
                    "method": "GET",
                    "path": "/security-flow/health",
                    "headers": {},
                    "body": {"text": "normal security flow rehearsal request"},
                },
                remote_addr="198.51.100.20",
            )
            route = (result.get("route") or {}).get("route")
            return route == "skip", f"低风险请求路由为 {route or '-'}。", str(route or "")

        def fast_path_step() -> tuple[bool, str, str]:
            result = self.check(
                {
                    "method": "POST",
                    "path": "/comment",
                    "event_type": "comment_create",
                    "body": {"text": "<script>alert(1)</script>"},
                },
                remote_addr="198.51.100.21",
            )
            route = (result.get("route") or {}).get("route")
            action = (result.get("tool_gateway") or {}).get("effective_action") or (
                result.get("decision") or {}
            ).get("selected_action")
            return route == "fast_path_block", f"攻击样例命中 {route or '-'}，处置动作 {action or '-'}。", str(route or "")

        def async_queue_step() -> tuple[bool, str, str]:
            result = self.check(
                {
                    "method": "POST",
                    "path": "/comment",
                    "event_type": "comment_create",
                    "body": {"text": "normal comment for async AI review"},
                },
                remote_addr="198.51.100.22",
            )
            route = (result.get("route") or {}).get("route")
            reason = (result.get("llm_gateway") or {}).get("reason")
            return route == "async_agent", f"普通评论进入 {route or '-'}，原因 {reason or '-'}。", str(reason or route or "")

        def appeal_step() -> tuple[bool, str, str]:
            punishment_id = f"flow-{uuid4().hex[:12]}"
            result = self.appeal(
                {
                    "punishment_id": punishment_id,
                    "reason": "安全流程演练申诉，请管理员复核。",
                },
                remote_addr="198.51.100.23",
            )
            status = int(result.get("status") or 0)
            closed = {}
            if status in {200, 202}:
                closed = self.review_appeal(
                    {
                        "punishment_id": punishment_id,
                        "resolution": "rejected",
                        "admin_note": "安全流程演练自动关闭，不进入真实待办。",
                    },
                    actor=actor,
                )
            closed_ok = bool(closed.get("ok"))
            detail = f"申诉入口返回 HTTP {status}，演练申诉已自动关闭。" if closed_ok else f"申诉入口返回 HTTP {status}。"
            code = f"{status}:{closed.get('reason') or closed.get('appeal', {}).get('status') or ''}"
            return status in {200, 202} and closed_ok, detail, code

        def llm_gateway_step() -> tuple[bool, str, str]:
            result = self.test_llm_gateway()
            display = result.get("display") or {}
            reason = result.get("reason") or ""
            detail = display.get("message_zh") or ("模型网关连接正常。" if result.get("ok") else "模型网关当前不可用。")
            return bool(result.get("ok")), detail, str(reason)

        def ledger_step() -> tuple[bool, str, str]:
            result = self.ledger_recent(limit=5, include_details=False)
            count = len(result.get("records") or [])
            status = result.get("status") or {}
            return bool(result.get("ok")), f"账本摘要可读取，最近返回 {count} 条，累计 {status.get('persisted_records', 0)} 条。", "public_summary"

        run_step("preflight", "环境预检", preflight_step)
        run_step("safe_request", "安全请求", safe_request_step)
        run_step("fast_path", "快速拦截", fast_path_step)
        run_step("async_queue", "异步 AI 审查", async_queue_step)
        run_step("appeal", "申诉入口", appeal_step)
        run_step("llm_gateway", "模型网关", llm_gateway_step)
        run_step("ledger", "安全账本", ledger_step)

        passed = sum(1 for item in steps if item["ok"])
        failed = len(steps) - passed
        self._record_admin_audit(
            "admin_security_flow_rehearsal",
            "run_security_flow",
            f"steps={len(steps)} failed={failed}",
            actor,
        )
        return {
            "ok": True,
            "flow_steps": steps,
            "summary": {
                "total": len(steps),
                "passed": passed,
                "failed": failed,
            },
            "display": {
                "locale": "zh-CN",
                "message_zh": f"安全流程演练已完成，{failed} 项需要处理。",
            },
        }

    def agent_chat(self, payload: dict[str, Any], actor: dict[str, str] | None = None) -> dict[str, Any]:
        message = str(payload.get("message") or "").strip()
        context = {
            "site_type": str(payload.get("site_type") or "通用网站")[:80],
            "adapter_type": str(payload.get("adapter_type") or "HTTP API")[:80],
            "runtime_mode": self.config.runtime_mode,
        }
        if not message:
            return {
                "ok": False,
                "status": 400,
                "reason": "message_required",
                "reply_zh": "请输入需要 Agent 协助判断的问题。",
            }
        result = self.llm_gateway.chat(message, context)
        self._save_llm_gateway_state()
        self._record_admin_audit(
            "admin_agent_chat",
            "agent_chat",
            f"site_type={context['site_type']} adapter_type={context['adapter_type']} reason={result.get('reason')}",
            actor,
        )
        return {
            **result,
            "context": context,
            "display": result.get("display")
            or {
                "locale": "zh-CN",
                "message_zh": "Agent 对话已返回。",
            },
        }

    def test_llm_gateway(self) -> dict[str, Any]:
        result = self.llm_gateway.test_connection()
        self._save_llm_gateway_state()
        return result

    def async_review_worker_status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.config.async_review_worker_enabled),
            "interval_seconds": int(self.config.async_review_worker_interval_seconds),
            "batch_size": int(self.config.async_review_worker_batch_size),
            "adaptive": True,
            "max_batch_size": 100,
        }

    def admin_async_reviews(self, status: str = "pending", limit: int = 50) -> dict[str, Any]:
        if not self.async_reviews:
            return {
                "ok": False,
                "status": 503,
                "reason": "async_review_queue_unavailable",
                "jobs": [],
                "queue": {"sqlite_enabled": False},
                "display": {
                    "locale": "zh-CN",
                    "message_zh": "异步 AI 审查队列不可用，请先配置 ledger_sqlite_path。",
                },
            }
        jobs = self.async_reviews.list(status=status, limit=limit)
        return {
            "ok": True,
            "jobs": jobs,
            "count": len(jobs),
            "queue": self.async_reviews.status(),
            "display": {
                "locale": "zh-CN",
                "message_zh": "异步 AI 审查队列已返回；列表只包含脱敏后的队列摘要。",
            },
        }

    def process_async_reviews(self, limit: int = 10) -> dict[str, Any]:
        if self.config.runtime_mode == "read_only":
            return {
                "ok": False,
                "status": 423,
                "reason": "read_only_mode_blocks_async_review_processing",
                "display": {
                    "locale": "zh-CN",
                    "message_zh": "只读模式下不会处理异步 AI 审查队列。",
                },
            }
        if not self.async_reviews:
            return {
                "ok": False,
                "status": 503,
                "reason": "async_review_queue_unavailable",
                "display": {
                    "locale": "zh-CN",
                    "message_zh": "异步 AI 审查队列不可用，请先配置 ledger_sqlite_path。",
                },
            }
        try:
            limit = int(limit or 10)
        except (TypeError, ValueError):
            limit = 10
        capacity = self.llm_gateway.available_review_attempts(limit)
        if not capacity.get("ok") or int(capacity.get("available") or 0) <= 0:
            return {
                "ok": True,
                "claimed": 0,
                "processed": [],
                "paused": True,
                "reason": capacity.get("reason") or "async_review_processing_paused",
                "budget": capacity.get("budget"),
                "queue": self.async_reviews.status(),
                "display": {
                    "locale": "zh-CN",
                    "message_zh": "Async AI review processing is paused until budget is available.",
                },
            }
        limit = min(limit, int(capacity.get("available") or limit))
        jobs = self.async_reviews.claim_due(limit=limit)
        processed: list[dict[str, Any]] = []
        for job in jobs:
            try:
                review_result = self._process_async_review_job(job)
            except AsyncReviewProcessingPaused as error:
                updated = self.async_reviews.defer(job["id"], error.reason, delay_seconds=60)
                processed.append(
                    {
                        "id": job["id"],
                        "status": (updated or {}).get("status", "retry"),
                        "paused": True,
                        "reason": error.reason,
                    }
                )
                break
            except Exception as error:
                updated = self.async_reviews.fail(job["id"], str(error))
                status = (updated or {}).get("status", "retry")
                self.ledger.record(
                    {
                        "severity": "high" if status == "dead_letter" else "medium",
                        "event_type": "async_review_dead_letter" if status == "dead_letter" else "async_review_retry",
                        "ip_hash": job.get("ip_hash"),
                        "rule_id": job.get("rule_id"),
                        "endpoint_type": job.get("event_type"),
                        "action": status,
                        "summary": f"async_review_job id={job['id']} failed reason={str(error)[:160]}",
                    }
                )
                processed.append({"id": job["id"], "status": status, "error": str(error)[:160]})
                continue
            completed = self.async_reviews.complete(job["id"], review_result)
            processed.append(
                {
                    "id": job["id"],
                    "status": (completed or {}).get("status", "completed"),
                    "effective_action": (review_result.get("tool_gateway") or {}).get("effective_action"),
                    "reason": (review_result.get("llm_gateway") or {}).get("reason"),
                }
            )

        return {
            "ok": True,
            "claimed": len(jobs),
            "processed": processed,
            "queue": self.async_reviews.status(),
            "display": {
                "locale": "zh-CN",
                "message_zh": f"异步 AI 审查已处理 {len(processed)} 条。",
            },
        }

    def run_async_reviews(self, payload: dict[str, Any] | None = None, actor: dict[str, str] | None = None) -> dict[str, Any]:
        payload = payload or {}
        try:
            limit = int(payload.get("limit") or 10)
        except (TypeError, ValueError):
            limit = 10
        result = self.process_async_reviews(limit=limit)
        if result.get("ok"):
            self._record_admin_audit(
                "admin_async_review_run",
                "run_async_reviews",
                f"claimed={result.get('claimed')} processed={len(result.get('processed') or [])}",
                actor,
            )
        return result

    def manual_review_async_job(self, payload: dict[str, Any], actor: dict[str, str] | None = None) -> dict[str, Any]:
        if self.config.runtime_mode == "read_only":
            return {
                "ok": False,
                "status": 423,
                "reason": "read_only_mode_blocks_manual_review",
                "display": {
                    "locale": "zh-CN",
                    "message_zh": "只读模式下不会执行人工审查动作。",
                },
            }
        if not self.async_reviews:
            return {
                "ok": False,
                "status": 503,
                "reason": "async_review_queue_unavailable",
                "display": {
                    "locale": "zh-CN",
                    "message_zh": "异步 AI 审查队列不可用，无法执行人工审查。",
                },
            }
        try:
            job_id = int(payload.get("job_id"))
        except (TypeError, ValueError):
            return {"ok": False, "status": 400, "reason": "job_id_required"}
        job = self.async_reviews.get(job_id, include_payload=True)
        if not job:
            return {"ok": False, "status": 404, "reason": "async_review_job_not_found"}
        if job.get("status") == "completed":
            return {"ok": False, "status": 409, "reason": "async_review_job_already_completed"}
        if job.get("status") == "processing":
            return {"ok": False, "status": 409, "reason": "async_review_job_processing"}

        packet = job.get("packet") or {}
        user_hash = str(payload.get("user_hash") or packet.get("user_hash") or "").strip()
        feature = str(payload.get("feature_scope") or packet.get("feature_scope") or packet.get("endpoint_type") or "").strip()
        if not user_hash:
            return {"ok": False, "status": 400, "reason": "user_hash_required"}
        if not feature:
            return {"ok": False, "status": 400, "reason": "feature_scope_required"}
        try:
            duration_seconds = int(payload.get("duration_seconds") or 3600)
        except (TypeError, ValueError):
            duration_seconds = 3600
        duration_seconds = max(60, min(duration_seconds, MANUAL_FEATURE_BAN_MAX_SECONDS))
        admin_note = str(payload.get("admin_note") or "").strip()[:1000]
        decision = {
            "selected_action": "feature_ban",
            "scores": {
                "evidence_score": 1.0,
                "behavior_score": 1.0,
                "reputation_score": 1.0,
                "ai_confidence": 0.0,
                "final_confidence": 1.0,
            },
            "reason_codes": ["manual_review", f"async_review_job:{job_id}"],
            "admin_explanation": "Manual reviewer applied a feature ban from an async review queue item.",
            "duration_seconds": duration_seconds,
            "target_scope": {
                "type": "user_feature",
                "user_hash": user_hash,
                "feature": feature,
            },
        }
        gateway = {
            "allowed": True,
            "executed": True,
            "effective_action": "feature_ban",
            "reason": "manual_review_policy_passed",
        }
        action_record = self.executor.execute(decision, gateway)
        ledger_record = self.ledger.record(
            {
                "severity": "high",
                "event_type": "manual_async_review_action",
                "ip_hash": packet.get("ip_hash"),
                "rule_id": (packet.get("fast_path_signal") or {}).get("rule_id"),
                "endpoint_type": job.get("event_type"),
                "action": "feature_ban",
                "summary": self._admin_summary(
                    (
                        f"manual_async_review job_id={job_id} action=feature_ban "
                        f"user_hash={user_hash} feature={feature} duration_seconds={duration_seconds} note={admin_note}"
                    ),
                    actor,
                ),
            }
        )
        result = {
            "manual_review": True,
            "reviewer_action": "feature_ban",
            "decision": decision,
            "tool_gateway": gateway,
            "action_result": action_record,
            "ledger_record": ledger_record,
            "raw_prompt_stored": False,
            "raw_request_body_stored": False,
        }
        completed = self.async_reviews.complete(job_id, result)
        return {
            "ok": True,
            "status": 200,
            "job": completed,
            "action_result": action_record,
            "ledger_record": ledger_record,
            "queue": self.async_reviews.status(),
            "display": {
                "locale": "zh-CN",
                "message_zh": "人工审查动作已执行，异步审查任务已标记完成。",
            },
        }

    def ledger_recent(self, limit: int = 20, *, include_details: bool = True) -> dict[str, Any]:
        records = self.ledger.recent(limit, include_details=include_details)
        status = self.ledger.status()
        if not include_details:
            records = [self._public_ledger_record(record) for record in records]
            status = self._public_ledger_status(status)
        return {
            "ok": True,
            "records": records,
            "status": status,
            "display": {
                "locale": "zh-CN",
                "message_zh": "最近账本记录已返回。低危聚合事件不会高频写入 SQLite。",
            },
        }

    def admin_appeals(self, status: str = "pending", limit: int = 50) -> dict[str, Any]:
        appeals = self.appeals.list(status=status, limit=limit)
        return {
            "ok": True,
            "appeals": appeals,
            "count": len(appeals),
            "display": {
                "locale": "zh-CN",
                "message_zh": "申诉列表已返回。申诉理由按不可信文本处理。",
            },
        }

    def admin_captcha(self) -> dict[str, Any]:
        return self.admin_auth.create_captcha()

    def register_admin(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.admin_auth.register(payload)
        if result.get("ok"):
            self._record_admin_audit(
                "admin_account",
                "register_first_admin",
                f"username={result.get('username')}",
                {"id": result.get("username", "unknown"), "id_hash": self._short_hash(result.get("username", "unknown")), "source_hash": self._short_hash("bootstrap")},
            )
        return result

    def login_admin(self, payload: dict[str, Any], remote_addr: str = "") -> dict[str, Any]:
        result = self.admin_auth.login(payload, remote_addr=remote_addr)
        if result.get("ok"):
            self._record_admin_audit(
                "admin_login",
                "captcha_login",
                f"username={result.get('username')}",
                {"id": result.get("username", "unknown"), "id_hash": self._short_hash(result.get("username", "unknown")), "source_hash": self._short_hash(remote_addr or "unknown")},
            )
        return result

    def admin_accounts(self) -> dict[str, Any]:
        return self.admin_auth.list_admins()

    def create_admin_account(self, payload: dict[str, Any], actor: dict[str, str] | None = None) -> dict[str, Any]:
        if self.config.runtime_mode == "read_only":
            return {"ok": False, "status": 423, "reason": "read_only_mode_blocks_admin_account_create"}
        result = self.admin_auth.create_admin(payload)
        if result.get("ok"):
            self._record_admin_audit("admin_account", "create_admin", f"username={result.get('username')}", actor)
        return result

    def change_admin_password(self, payload: dict[str, Any], actor: dict[str, str] | None = None) -> dict[str, Any]:
        if self.config.runtime_mode == "read_only":
            return {"ok": False, "status": 423, "reason": "read_only_mode_blocks_admin_password_change"}
        result = self.admin_auth.change_password(payload, actor_username=actor.get("id") if actor else None)
        if result.get("ok"):
            self._record_admin_audit("admin_account", "change_password", f"username={result.get('username')}", actor)
        return result

    def admin_api_keys(self, include_revoked: bool = False) -> dict[str, Any]:
        return self.api_keys.list(include_revoked=include_revoked)

    def create_api_key(self, payload: dict[str, Any], actor: dict[str, str] | None = None) -> dict[str, Any]:
        if self.config.runtime_mode == "read_only":
            return {"ok": False, "status": 423, "reason": "read_only_mode_blocks_api_key_create"}
        result = self.api_keys.create(payload)
        if result.get("ok"):
            record = result.get("record") or {}
            if record.get("scope") == "backend" and payload.get("activate_provider_key", True):
                self.config.llm_api_key_env = str(record.get("env_name") or self.config.llm_api_key_env)
                self._rebuild_llm_gateway()
                self._save_config()
            self._record_admin_audit(
                "admin_api_key",
                "create_api_key",
                f"name={record.get('name')} scope={record.get('scope')} env_name={record.get('env_name')}",
                actor,
            )
        return result

    def delete_api_key(self, key_id: int, actor: dict[str, str] | None = None) -> dict[str, Any]:
        if self.config.runtime_mode == "read_only":
            return {"ok": False, "status": 423, "reason": "read_only_mode_blocks_api_key_delete"}
        result = self.api_keys.delete(key_id)
        if result.get("ok"):
            if result.get("env_name") == self.config.llm_api_key_env:
                self._rebuild_llm_gateway()
                self._save_config()
            self._record_admin_audit("admin_api_key", "delete_api_key", f"id={key_id} env_name={result.get('env_name')}", actor)
        return result

    def review_appeal(self, payload: dict[str, Any], actor: dict[str, str] | None = None) -> dict[str, Any]:
        if self.config.runtime_mode == "read_only":
            return {
                "ok": False,
                "status": 423,
                "reason": "read_only_mode_blocks_appeal_review",
                "display": {
                    "locale": "zh-CN",
                    "message_zh": "只读模式下不会审核申诉。",
                },
            }
        result = self.appeals.review(payload)
        if result.get("ok"):
            appeal = result["appeal"]
            if appeal.get("status") == "approved":
                result["auto_unban"] = self._auto_unban_approved_appeal(appeal, actor)
            else:
                result["auto_unban"] = {
                    "ok": False,
                    "executed": False,
                    "reason": "appeal_not_approved",
                }
            self.ledger.record(
                {
                    "severity": "medium",
                    "event_type": "appeal_review",
                    "endpoint_type": "admin",
                    "action": f"appeal_{appeal.get('status')}",
                    "summary": self._admin_summary(
                        f"appeal_review punishment_id={appeal.get('punishment_id')}",
                        actor,
                    ),
                }
            )
        result["display"] = {
            "locale": "zh-CN",
            "message_zh": "申诉审核已保存。" if result.get("ok") else "申诉审核未保存，请检查处罚编号和审核结果。",
        }
        return result

    def admin_actions(self, status: str = "active") -> dict[str, Any]:
        actions = self.executor.list_actions(status=status, cleanup_expired=self.config.runtime_mode != "read_only")
        return {
            "ok": True,
            "actions": actions,
            "count": len(actions),
            "display": {
                "locale": "zh-CN",
                "message_zh": "动作列表已返回。撤销只影响 ATEE 执行动作记录。",
            },
        }

    def revoke_action(self, payload: dict[str, Any], actor: dict[str, str] | None = None) -> dict[str, Any]:
        if self.config.runtime_mode == "read_only":
            return {
                "ok": False,
                "status": 423,
                "reason": "read_only_mode_blocks_action_revoke",
                "display": {
                    "locale": "zh-CN",
                    "message_zh": "只读模式下不会撤销动作记录。",
                },
            }
        try:
            action_id = int(payload.get("action_id"))
        except (TypeError, ValueError):
            result = {"ok": False, "status": 400, "reason": "action_id_required"}
        else:
            result = self.executor.revoke(action_id, str(payload.get("reason") or ""))
        if result.get("ok"):
            action = result["action"]
            self.ledger.record(
                {
                    "severity": "medium",
                    "event_type": "action_revoke",
                    "endpoint_type": "admin",
                    "action": "revoke_action",
                    "summary": self._admin_summary(
                        f"action_revoke id={action.get('id')} action={action.get('action')}",
                        actor,
                    ),
                }
            )
        result["display"] = {
            "locale": "zh-CN",
            "message_zh": "动作已撤销。" if result.get("ok") else "动作撤销未完成，请检查动作编号或状态。",
        }
        return result

    def cleanup_expired_actions(self, actor: dict[str, str] | None = None) -> dict[str, Any]:
        if self.config.runtime_mode == "read_only":
            return {
                "ok": False,
                "status": 423,
                "reason": "read_only_mode_blocks_action_cleanup",
                "display": {
                    "locale": "zh-CN",
                    "message_zh": "只读模式下不会清理过期动作。",
                },
            }
        changed = self.executor.cleanup_expired()
        if changed:
            self.ledger.record(
                {
                    "severity": "medium",
                    "event_type": "action_cleanup",
                    "endpoint_type": "admin",
                    "action": "cleanup_expired_actions",
                    "summary": self._admin_summary(f"expired_actions_marked={changed}", actor),
                }
            )
        return {
            "ok": True,
            "expired_marked": changed,
            "active_actions": len(self.executor.list_actions(status="active")),
            "display": {
                "locale": "zh-CN",
                "message_zh": f"已标记 {changed} 条过期动作。",
            },
        }

    def _enqueue_async_review(
        self,
        ctx: RequestContext,
        real_ip: dict[str, Any],
        fast_path: dict[str, Any],
        route: dict[str, Any],
        packet: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.async_reviews:
            decision = self.decision_engine.decide(packet, route, None)
            ledger_record = self.ledger.record(
                {
                    "severity": "medium",
                    "event_type": "async_review_queue_unavailable",
                    "ip_hash": packet.get("ip_hash"),
                    "rule_id": fast_path.get("rule_id"),
                    "endpoint_type": route.get("event_type"),
                    "action": "review_not_queued",
                    "summary": "async AI review queue unavailable; request allowed pending manual inspection",
                    "details": self._ledger_details(packet, route, fast_path, decision, None, None),
                }
            )
            llm_result = {
                "ok": False,
                "llm_called": False,
                "reason": "async_review_queue_unavailable",
            }
            return self._response(ctx, real_ip, fast_path, route, decision, None, ledger_record, None, llm_result)

        try:
            job = self.async_reviews.enqueue(packet, route)
        except AsyncReviewQueueFull as error:
            queue_status = error.status
            decision = {
                "selected_action": "allow",
                "scores": {
                    "evidence_score": 0.0,
                    "behavior_score": 0.0,
                    "reputation_score": 0.0,
                    "ai_confidence": 0.0,
                    "final_confidence": 0.0,
                },
                "reason_codes": ["route:async_agent", "async_review:backpressure"],
                "admin_explanation": "Async AI review queue is at capacity; request is allowed but review was not queued.",
                "duration_seconds": 0,
                "target_scope": {"type": "request"},
            }
            llm_result = {
                "ok": False,
                "llm_called": False,
                "reason": "async_review_backpressure",
                "queue": queue_status,
            }
            ledger_record = self.ledger.record(
                {
                    "severity": "high",
                    "event_type": "async_review_backpressure",
                    "ip_hash": packet.get("ip_hash"),
                    "rule_id": fast_path.get("rule_id"),
                    "endpoint_type": route.get("event_type"),
                    "action": "review_not_queued",
                    "summary": (
                        "async_review_queue at capacity "
                        f"active_depth={queue_status.get('active_depth')} max_depth={queue_status.get('max_depth')}"
                    ),
                    "details": self._ledger_details(packet, route, fast_path, decision, llm_result, None),
                }
            )
            response = self._response(ctx, real_ip, fast_path, route, decision, None, ledger_record, None, llm_result)
            response["async_review_queue"] = queue_status
            return response
        decision = {
            "selected_action": "allow",
            "scores": {
                "evidence_score": 0.0,
                "behavior_score": 0.0,
                "reputation_score": 0.0,
                "ai_confidence": 0.0,
                "final_confidence": 0.0,
            },
            "reason_codes": ["route:async_agent", "async_review:queued"],
            "admin_explanation": "Queued for async AI review; request is allowed while the worker reviews sanitized evidence with the configured model gateway.",
            "duration_seconds": 0,
            "target_scope": {"type": "request"},
        }
        ledger_record = self.ledger.record(
            {
                "severity": "medium",
                "event_type": "async_review_queued",
                "ip_hash": packet.get("ip_hash"),
                "rule_id": fast_path.get("rule_id"),
                "endpoint_type": route.get("event_type"),
                "action": "queued",
                "summary": f"async_review_job id={job.get('id')} queued",
                "details": self._ledger_details(packet, route, fast_path, decision, None, None),
            }
        )
        llm_result = {
            "ok": True,
            "llm_called": False,
            "reason": "async_review_queued",
            "job_id": job.get("id"),
            "status": job.get("status"),
        }
        response = self._response(ctx, real_ip, fast_path, route, decision, None, ledger_record, None, llm_result)
        response["async_review_job"] = job
        return response

    def _process_async_review_job(self, job: dict[str, Any]) -> dict[str, Any]:
        packet = job.get("packet") or {}
        route = job.get("route_detail") or {"route": "async_agent", "event_type": job.get("event_type")}
        llm_result = self.llm_gateway.review(packet, route)
        self._save_llm_gateway_state()
        if not llm_result.get("ok"):
            reason = str(llm_result.get("reason") or "llm_review_failed")
            if reason in ASYNC_REVIEW_PAUSE_REASONS:
                raise AsyncReviewProcessingPaused(reason)
            raise RuntimeError(str(llm_result.get("reason") or "llm_review_failed"))
        decision = self.decision_engine.decide(packet, route, llm_result.get("agent_decision"))
        gateway = self.tool_gateway.validate(decision, {"can_ip_ban": False}, self.config)
        action_record = self.executor.execute(decision, gateway)
        ledger_record = self.ledger.record(
            {
                "severity": "medium" if decision["selected_action"] in {"allow", "rule_hint"} else "high",
                "event_type": "async_review_decision",
                "ip_hash": packet.get("ip_hash"),
                "rule_id": (packet.get("fast_path_signal") or {}).get("rule_id"),
                "endpoint_type": route.get("event_type"),
                "action": gateway.get("effective_action"),
                "summary": (
                    f"async_review_job id={job.get('id')} "
                    f"decision={decision.get('selected_action')} reason={llm_result.get('reason')}"
                ),
                "details": self._ledger_details(
                    packet,
                    route,
                    packet.get("fast_path_signal") or {},
                    decision,
                    llm_result,
                    gateway,
                ),
            }
        )
        return {
            "llm_gateway": llm_result,
            "decision": decision,
            "tool_gateway": gateway,
            "action_result": action_record,
            "ledger_record": ledger_record,
            "raw_prompt_stored": False,
            "raw_request_body_stored": False,
        }

    def _save_config(self) -> None:
        if self.config_store:
            self.config_store.save(self.config)

    def _make_async_review_queue(self, state_sqlite_path: Path | None) -> AsyncReviewQueue | None:
        if not state_sqlite_path:
            return None
        return AsyncReviewQueue(
            state_sqlite_path,
            max_depth=int(getattr(self.config, "async_review_queue_max_depth", 5000) or 5000),
        )

    def _load_llm_gateway_state(self) -> None:
        state_path = self._llm_gateway_state_path()
        if not state_path:
            return
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.llm_gateway.restore_runtime_state(state)

    def _save_llm_gateway_state(self) -> None:
        state_path = self._llm_gateway_state_path()
        if not state_path:
            return
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                json.dumps(self.llm_gateway.runtime_state(), ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
        except OSError:
            return

    def _llm_gateway_state_path(self) -> Path | None:
        if not self.config_store:
            return None
        ledger_path = self._resolve_project_path(self.config.ledger_sqlite_path)
        state_dir = ledger_path.parent if ledger_path else self.project_root / "data"
        return state_dir / "atee_llm_gateway_state.json"

    def _resolve_project_path(self, value: str | None) -> Path | None:
        if not value:
            return None
        path = Path(value)
        if path.is_absolute():
            return path
        return self.project_root / path

    def _infer_project_root(self) -> Path:
        if not self.config_store:
            return Path.cwd()
        config_parent = self.config_store.path.resolve().parent
        if config_parent.name.lower() == "config":
            return config_parent.parent
        return config_parent

    def _load_bypass_key(self) -> None:
        if not self.config.bypass_key_file:
            return
        key_path = self._resolve_project_path(self.config.bypass_key_file)
        try:
            self.config.bypass_key = key_path.read_text(encoding="utf-8").strip() if key_path else None
        except OSError:
            self.config.bypass_key = None

    def _load_admin_token(self) -> None:
        self._admin_token = None
        env_name = str(self.config.admin_token_env or "")
        if env_name:
            self._admin_token = (os.environ.get(env_name) or "").strip() or None
        if self._admin_token or not self.config.admin_token_file:
            return
        token_path = self._resolve_project_path(self.config.admin_token_file)
        try:
            self._admin_token = (load_secret_file(token_path) or "").strip() if token_path else None
        except (OSError, SecretStoreError):
            self._admin_token = None

    def admin_auth_status(self) -> dict[str, Any]:
        account_status = self.admin_auth.status()
        return {
            "enabled": bool(self.config.admin_auth_enabled),
            "token_configured": bool(self._admin_token),
            "legacy_token_configured": bool(self._admin_token),
            "token_file_configured": bool(self.config.admin_token_file),
            "token_env": self.config.admin_token_env,
            **account_status,
        }

    def admin_authorized(self, headers: dict[str, str] | None = None) -> bool:
        if not self.config.admin_auth_enabled:
            return True
        supplied = self._admin_token_from_headers(headers or {})
        if supplied and self.admin_auth.validate_session(supplied):
            return True
        if self._admin_token and supplied:
            return hmac.compare_digest(supplied, self._admin_token)
        return False

    def admin_auth_challenge(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": "admin_auth_required",
            "admin_auth": self.admin_auth_status(),
            "display": {
                "locale": "zh-CN",
                "message_zh": "管理接口需要验证码登录会话或兼容 Admin Token。",
            },
        }

    def _admin_token_from_headers(self, headers: dict[str, str]) -> str | None:
        normalized = {str(key).lower(): str(value) for key, value in headers.items()}
        bearer = normalized.get("authorization", "")
        if bearer.lower().startswith("bearer "):
            return bearer[7:].strip()
        header_token = normalized.get("x-atee-admin-token")
        return header_token.strip() if header_token else None

    def admin_actor_from_headers(self, headers: dict[str, str] | None = None, remote_addr: str = "") -> dict[str, str]:
        normalized = {str(key).lower(): str(value) for key, value in (headers or {}).items()}
        supplied = self._admin_token_from_headers(headers or {})
        session = self.admin_auth.validate_session(supplied or "")
        actor_id = self._clean_admin_actor_id((session or {}).get("username") or normalized.get("x-atee-admin-id", "unknown"))
        source = normalized.get("x-real-ip") or remote_addr or "unknown"
        return {
            "id": actor_id,
            "id_hash": self._short_hash(actor_id),
            "source_hash": self._short_hash(source),
        }

    def _clean_admin_actor_id(self, value: str) -> str:
        cleaned = "".join(ch for ch in str(value).strip() if ch.isalnum() or ch in {"@", ".", "_", "-"})
        return (cleaned or "unknown")[:80]

    def _short_hash(self, value: str) -> str:
        digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
        return f"sha256:{digest[:16]}"

    def _admin_summary(self, summary: str, actor: dict[str, str] | None = None) -> str:
        actor = actor or {"id": "unknown", "id_hash": self._short_hash("unknown"), "source_hash": self._short_hash("unknown")}
        return (
            f"{summary} admin_actor_id={actor.get('id', 'unknown')} "
            f"admin_actor_hash={actor.get('id_hash')} admin_source_hash={actor.get('source_hash')}"
        )

    def _record_admin_audit(
        self,
        event_type: str,
        action: str,
        summary: str,
        actor: dict[str, str] | None = None,
        severity: str = "medium",
    ) -> None:
        self.ledger.record(
            {
                "severity": severity,
                "event_type": event_type,
                "endpoint_type": "admin",
                "action": action,
                "summary": self._admin_summary(summary, actor),
            }
        )

    def _plan_text(self, value: Any, default: str, limit: int) -> str:
        text = str(value or "").strip()
        if not text:
            return default
        if any(marker in text.lower() for marker in INTEGRATION_PLAN_SENSITIVE_MARKERS):
            return "[redacted]"
        return text[:limit]

    def _plan_url(self, value: Any, default: str) -> str:
        text = self._plan_text(value, default, 200)
        if text == "[redacted]":
            return default
        try:
            parsed = urlsplit(text)
        except ValueError:
            return default
        if parsed.scheme and parsed.netloc:
            hostname = parsed.hostname or parsed.netloc.rsplit("@", 1)[-1]
            try:
                port = parsed.port
            except ValueError:
                return default
            netloc = f"{hostname}:{port}" if port else hostname
            path = parsed.path.rstrip("/")
            return urlunsplit((parsed.scheme, netloc, path, "", "")).rstrip("/") or default
        return text.split("?", 1)[0].split("#", 1)[0].rstrip("/")[:160] or default

    def _plan_path(self, value: Any, default: str) -> str:
        text = self._plan_text(value, default, 120)
        if text == "[redacted]":
            return default
        if not text.startswith("/"):
            text = f"/{text}"
        return text.split("?", 1)[0].split("#", 1)[0] or default

    def _plan_features(self, value: Any) -> list[str]:
        if isinstance(value, list):
            raw_items = value
        else:
            raw_items = str(value or "").replace(";", ",").replace("\n", ",").split(",")
        features = []
        for item in raw_items:
            feature = self._plan_text(item, "", 40)
            if feature and feature != "[redacted]" and feature not in features:
                features.append(feature)
            if len(features) >= 8:
                break
        return features or list(INTEGRATION_PLAN_DEFAULT_FEATURES)

    def _curl_example(self, core_url: str, path: str, payload: dict[str, Any]) -> str:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        escaped = body.replace('"', '\\"')
        return f'curl -X POST "{core_url}{path}" -H "Content-Type: application/json" -d "{escaped}"'

    def _rebuild_llm_gateway(self) -> None:
        llm_gateway_state = self.llm_gateway.runtime_state()
        self.llm_gateway = RemoteLLMGateway(self.config, base_dir=self.project_root)
        self.llm_gateway.restore_runtime_state(llm_gateway_state)
        self._save_llm_gateway_state()

    def _ledger_details(
        self,
        packet: dict[str, Any],
        route: dict[str, Any],
        fast_path: dict[str, Any],
        decision: dict[str, Any] | None,
        llm_result: dict[str, Any] | None,
        gateway: dict[str, Any] | None,
    ) -> dict[str, Any]:
        decision = decision or {}
        llm_result = llm_result or {}
        gateway = gateway or {}
        return {
            "request": {
                "method": packet.get("method"),
                "path": packet.get("path"),
                "headers": packet.get("headers") or {},
                "query_keys": packet.get("query_keys") or [],
                "body_summary": packet.get("body_summary") or {},
                "user_hash": packet.get("user_hash"),
                "session_hash": packet.get("session_hash"),
                "ip_hash": packet.get("ip_hash"),
                "endpoint_type": packet.get("endpoint_type"),
                "feature_scope": packet.get("feature_scope"),
            },
            "route": route,
            "fast_path": {
                "action": fast_path.get("action"),
                "rule_id": fast_path.get("rule_id"),
                "reason": fast_path.get("reason"),
            },
            "core_decision": {
                "selected_action": decision.get("selected_action"),
                "scores": decision.get("scores") or {},
                "reason_codes": decision.get("reason_codes") or [],
                "admin_explanation": decision.get("admin_explanation"),
                "duration_seconds": decision.get("duration_seconds"),
                "target_scope": decision.get("target_scope"),
            },
            "core_scores": decision.get("scores") or {},
            "tool_gateway": {
                "allowed": gateway.get("allowed"),
                "effective_action": gateway.get("effective_action"),
                "reason": gateway.get("reason"),
            },
            "llm_gateway": {
                "ok": llm_result.get("ok"),
                "llm_called": llm_result.get("llm_called"),
                "provider": llm_result.get("provider"),
                "reason": llm_result.get("reason"),
                "latency_ms": llm_result.get("latency_ms"),
            },
        }

    def _public_ledger_record(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            key: record.get(key)
            for key in ("id", "created_at", "event_type", "severity", "action")
            if key in record
        }

    def _public_ledger_status(self, status: dict[str, Any]) -> dict[str, Any]:
        return {
            key: status.get(key)
            for key in (
                "records",
                "aggregates",
                "sqlite_enabled",
                "persisted_records",
                "sqlite_bytes",
                "raw_prompt_storage",
                "raw_request_body_storage",
            )
            if key in status
        }

    def _public_changed(self, changed: dict[str, Any]) -> dict[str, Any]:
        public = dict(changed)
        if "llm_api_base" in public:
            public.pop("llm_api_base", None)
            public["llm_api_base_configured"] = bool(changed.get("llm_api_base"))
        if "llm_api_key_file" in public:
            public.pop("llm_api_key_file", None)
            public["llm_api_key_file_configured"] = bool(changed.get("llm_api_key_file"))
        if "llm_proxy_url" in public:
            public.pop("llm_proxy_url", None)
            public["llm_proxy_configured"] = bool(changed.get("llm_proxy_url"))
        if "admin_token_file" in public:
            public.pop("admin_token_file", None)
            public["admin_token_file_configured"] = bool(changed.get("admin_token_file"))
        return public

    def _auto_unban_approved_appeal(self, appeal: dict[str, Any], actor: dict[str, str] | None = None) -> dict[str, Any]:
        punishment_id = str(appeal.get("punishment_id") or "").strip()
        action_id, parse_reason = self._parse_action_punishment_id(punishment_id)
        if action_id is None:
            return {
                "ok": False,
                "executed": False,
                "reason": parse_reason,
                "punishment_id": punishment_id,
            }

        action = self.executor.active_action(action_id)
        if not action:
            return {
                "ok": False,
                "executed": False,
                "reason": "active_action_not_found",
                "punishment_id": punishment_id,
                "action_id": action_id,
            }
        if action.get("action") != "feature_ban":
            return {
                "ok": False,
                "executed": False,
                "reason": "action_is_not_feature_ban",
                "punishment_id": punishment_id,
                "action_id": action_id,
            }
        if not action.get("reversible"):
            return {
                "ok": False,
                "executed": False,
                "reason": "action_not_reversible",
                "punishment_id": punishment_id,
                "action_id": action_id,
            }

        revoked = self.executor.revoke(action_id, f"appeal approved: {punishment_id}")
        if not revoked.get("ok"):
            return {
                "ok": False,
                "executed": False,
                "reason": revoked.get("reason") or "action_revoke_failed",
                "punishment_id": punishment_id,
                "action_id": action_id,
            }
        self.ledger.record(
            {
                "severity": "medium",
                "event_type": "appeal_auto_unban",
                "endpoint_type": "admin",
                "action": "revoke_feature_ban",
                "summary": self._admin_summary(
                    f"appeal_auto_unban punishment_id={punishment_id} action_id={action_id}",
                    actor,
                ),
            }
        )
        return {
            "ok": True,
            "executed": True,
            "reason": "feature_ban_revoked",
            "punishment_id": punishment_id,
            "action_id": action_id,
            "action": revoked.get("action"),
        }

    def _parse_action_punishment_id(self, punishment_id: str) -> tuple[int | None, str]:
        if not punishment_id.startswith("action:"):
            return None, "unsupported_punishment_id"
        raw_action_id = punishment_id.removeprefix("action:")
        try:
            action_id = int(raw_action_id)
        except (TypeError, ValueError):
            return None, "invalid_action_punishment_id"
        if action_id <= 0:
            return None, "invalid_action_punishment_id"
        return action_id, "ok"

    def break_glass_status(self, headers: dict[str, str] | None = None, actor: dict[str, str] | None = None) -> dict[str, Any]:
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        supplied = headers.get("x-atee-bypass")
        valid = bool(self.config.bypass_enabled and self.config.bypass_key and supplied == self.config.bypass_key)
        self._record_admin_audit(
            "break_glass",
            "bypass_status_check",
            f"valid_for_request={valid} rotate_key_after_use={valid}",
            actor,
            severity="high" if valid else "medium",
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
        llm_result: dict[str, Any] | None,
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
            "llm_gateway": llm_result,
            "ledger_record": ledger_record,
            "runtime": runtime_status,
            "display": response_display(route, decision, gateway, runtime_status),
        }

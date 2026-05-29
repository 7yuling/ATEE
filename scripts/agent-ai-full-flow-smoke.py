import argparse
import json
import os
import sys
import tempfile
import threading
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "services" / "core-service"
sys.path.insert(0, str(CORE_PATH))

from atee_core.config import ConfigStore  # noqa: E402
from atee_core.core import CoreService  # noqa: E402


DRILL_KEY_ENV = "ATEE_AGENT_AI_FULL_FLOW_SMOKE_KEY"
REMOTE_MODES = {"openai_compatible", "remote"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a sanitized ATEE Agent AI full-flow smoke check.")
    parser.add_argument("--config", default=str(ROOT / "config" / "config.json"))
    parser.add_argument("--include-live", action="store_true", help="Call the configured live provider once.")
    parser.add_argument("--budget-cents", type=int, default=1)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    os.chdir(ROOT)
    config_path = Path(args.config)
    budget_cents = max(1, int(args.budget_cents))
    if args.include_live:
        summary = _run_live(config_path, budget_cents)
    else:
        summary = _run_fake(config_path, budget_cents)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(_markdown_report(summary), encoding="utf-8")
        summary["report_path"] = str(args.report)

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


def _run_fake(config_path: Path, budget_cents: int) -> dict:
    previous_key = os.environ.get(DRILL_KEY_ENV)
    os.environ[DRILL_KEY_ENV] = f"local-agent-flow-{uuid4().hex}"
    try:
        with _FakeProvider() as provider:
            config = _base_drill_config(config_path, budget_cents)
            config.llm_mode = "openai_compatible"
            config.llm_provider = "agent-flow-smoke-provider"
            config.llm_model = "agent-flow-smoke-model"
            config.llm_api_base = provider.base_url
            config.llm_api_key_env = DRILL_KEY_ENV
            config.llm_api_key_file = None
            config.llm_proxy_url = None
            config.remote_soft_timeout_ms = min(int(config.remote_soft_timeout_ms), 100)
            config.remote_hard_timeout_ms = min(int(config.remote_hard_timeout_ms), 1000)
            return _run_flow(config, mode="fake", provider_calls=lambda: provider.calls)
    finally:
        if previous_key is None:
            os.environ.pop(DRILL_KEY_ENV, None)
        else:
            os.environ[DRILL_KEY_ENV] = previous_key


def _run_live(config_path: Path, budget_cents: int) -> dict:
    base_config = ConfigStore(config_path).load()
    if base_config.llm_mode not in REMOTE_MODES:
        return {
            "ok": False,
            "generated_at": _utc_now(),
            "mode": "live",
            "live_used": True,
            "reason": "remote_llm_not_configured",
            "config": _public_config(base_config),
            "steps": [],
        }
    config = _base_drill_config(config_path, budget_cents)
    return _run_flow(config, mode="live", provider_calls=None)


def _base_drill_config(config_path: Path, budget_cents: int):
    config = deepcopy(ConfigStore(config_path).load())
    temp_dir = Path(tempfile.mkdtemp(prefix="atee-agent-flow-"))
    config.ledger_sqlite_path = str(temp_dir / "flow.sqlite3")
    config.llm_daily_budget_cents = budget_cents
    return config


def _run_flow(config, mode: str, provider_calls) -> dict:
    core = CoreService(config=config)
    steps: list[dict] = []

    runtime_before = core.runtime_status()
    llm_status_before = runtime_before.get("llm_gateway") or {}
    _add_step(
        steps,
        "runtime_status",
        bool(llm_status_before.get("api_key_configured") and llm_status_before.get("api_base_configured")),
        runtime_mode=runtime_before.get("runtime_mode"),
        agent_paused=bool(runtime_before.get("agent_paused")),
        api_key_configured=bool(llm_status_before.get("api_key_configured")),
        api_base_configured=bool(llm_status_before.get("api_base_configured")),
        proxy_configured=bool(llm_status_before.get("proxy_configured")),
        circuit_open=bool((llm_status_before.get("circuit") or {}).get("open")),
    )

    read_result = core.check({"method": "GET", "path": "/assets/app.js"}, remote_addr="198.51.100.23")
    _add_step(
        steps,
        "low_risk_read_skip",
        read_result.get("route", {}).get("route") == "skip" and not read_result.get("llm_gateway"),
        route=read_result.get("route", {}).get("route"),
        fast_path_rule=read_result.get("fast_path", {}).get("rule_id"),
        llm_called=bool(read_result.get("llm_gateway")),
    )

    ai_result = core.check(
        {
            "method": "POST",
            "path": "/api/login",
            "event_type": "login",
            "user_id": "flow-demo-user",
            "body": {
                "login_result": "failed",
                "failed_attempts_last_10m": 2,
                "device_age_days": 1,
                "risk_note": "new device login rehearsal, no credentials included",
            },
        },
        remote_addr="198.51.100.23",
    )
    llm_result = ai_result.get("llm_gateway") or {}
    _add_step(
        steps,
        "sync_agent_ai_review",
        ai_result.get("route", {}).get("route") == "sync_agent" and bool(llm_result.get("ok")),
        route=ai_result.get("route", {}).get("route"),
        llm_reason=llm_result.get("reason"),
        llm_latency_ms=llm_result.get("latency_ms"),
        selected_action=ai_result.get("decision", {}).get("selected_action"),
        final_confidence=ai_result.get("decision", {}).get("scores", {}).get("final_confidence"),
        tool_effective_action=ai_result.get("tool_gateway", {}).get("effective_action"),
        tool_executed=bool(ai_result.get("tool_gateway", {}).get("executed")),
        ledger_written=bool(ai_result.get("ledger_record")),
    )

    attack_result = core.check(
        {"method": "POST", "path": "/api/comment", "body": {"content": "<script>alert(1)</script>"}},
        remote_addr="198.51.100.23",
    )
    _add_step(
        steps,
        "fast_path_attack_block",
        attack_result.get("route", {}).get("route") == "fast_path_block" and not attack_result.get("llm_gateway"),
        route=attack_result.get("route", {}).get("route"),
        fast_path_rule=attack_result.get("fast_path", {}).get("rule_id"),
        selected_action=attack_result.get("decision", {}).get("selected_action"),
        llm_called=bool(attack_result.get("llm_gateway")),
    )

    punishment_id = f"flow-smoke-{uuid4().hex}"
    appeal_result = core.appeal(
        {
            "punishment_id": punishment_id,
            "reason": "Full-flow smoke appeal rehearsal. Treat this as untrusted text.",
        },
        remote_addr="198.51.100.23",
    )
    _add_step(
        steps,
        "appeal_submit",
        appeal_result.get("status") in {200, 202},
        status=appeal_result.get("status"),
        appeal_status=_appeal_status(appeal_result),
    )

    actor = core.admin_actor_from_headers({"X-ATEE-Admin-Id": "ops-flow-reviewer"}, remote_addr="127.0.0.1")
    review_result = core.review_appeal(
        {
            "punishment_id": punishment_id,
            "resolution": "approved",
            "admin_note": "Full-flow smoke approved for validation.",
        },
        actor=actor,
    )
    _add_step(
        steps,
        "admin_appeal_review",
        bool(review_result.get("ok")),
        appeal_status=_appeal_status(review_result),
    )

    ledger_result = core.ledger_recent(limit=10)
    admin_summaries = [str(record.get("summary") or "") for record in ledger_result.get("records") or []]
    _add_step(
        steps,
        "ledger_recent",
        bool(ledger_result.get("ok")) and len(ledger_result.get("records") or []) >= 4,
        record_count=len(ledger_result.get("records") or []),
        has_admin_actor_hash=any("admin_actor_hash=sha256:" in item for item in admin_summaries),
    )

    final_status = core.runtime_status()
    final_llm = final_status.get("llm_gateway") or {}
    final = {
        "budget": final_llm.get("budget"),
        "circuit": final_llm.get("circuit"),
        "pending_appeals": final_status.get("pending_appeals"),
        "ledger": _public_ledger_status(final_status.get("ledger") or {}),
        "provider_calls": provider_calls() if callable(provider_calls) else None,
    }
    expected_calls_ok = True if mode == "live" else final["provider_calls"] == 1
    ok = all(step.get("ok") for step in steps) and not (final_llm.get("circuit") or {}).get("open") and expected_calls_ok
    return {
        "ok": ok,
        "generated_at": _utc_now(),
        "mode": mode,
        "live_used": mode == "live",
        "config": _public_config(config),
        "steps": steps,
        "final": final,
    }


def _add_step(steps: list[dict], name: str, ok: bool, **details) -> None:
    steps.append({"name": name, "ok": bool(ok), **details})


def _appeal_status(payload: dict) -> str | None:
    appeal = payload.get("appeal")
    return appeal.get("status") if isinstance(appeal, dict) else None


def _public_config(config) -> dict:
    return {
        "llm_mode": config.llm_mode,
        "api_base_configured": bool(config.llm_api_base),
        "api_key_file_configured": bool(config.llm_api_key_file),
        "api_key_env_configured": bool(config.llm_api_key_env),
        "proxy_configured": bool(config.llm_proxy_url),
        "raw_prompt_storage": False,
    }


def _public_ledger_status(status: dict) -> dict:
    return {
        "sqlite_enabled": bool(status.get("sqlite_enabled")),
        "records": status.get("records"),
        "persisted_records": status.get("persisted_records"),
        "raw_prompt_storage": bool(status.get("raw_prompt_storage")),
        "raw_request_body_storage": bool(status.get("raw_request_body_storage")),
    }


def _markdown_report(summary: dict) -> str:
    final = summary.get("final") or {}
    budget = final.get("budget") or {}
    circuit = final.get("circuit") or {}
    lines = [
        "# ATEE Agent AI Full-Flow Smoke Report",
        "",
        f"- Generated at UTC: {summary.get('generated_at')}",
        f"- Overall OK: {bool(summary.get('ok'))}",
        f"- Mode: {summary.get('mode')}",
        f"- Live used: {bool(summary.get('live_used'))}",
        f"- One-sentence summary: {_overall_sentence(summary)}",
        f"- Daily spend cents: {budget.get('daily_spend_cents')}",
        f"- Circuit open: {bool(circuit.get('open'))}",
        f"- Provider calls observed: {final.get('provider_calls')}",
        "",
        "## Steps",
        "",
        "| Module | One-sentence response | Code response status | Key response |",
        "| --- | --- | --- | --- |",
    ]
    for step in summary.get("steps") or []:
        lines.append(
            "| "
            f"{step.get('name')} | "
            f"{_step_sentence(step)} | "
            f"{_step_code_status(step)} | "
            f"{_step_key_response(step)} |"
        )
    lines.extend(
        [
            "",
            "## Security Notes",
            "",
            "- The default run uses a temporary local fake provider and does not call the configured live provider.",
            "- Add --include-live only for an intentional one-call live provider full-flow rehearsal.",
            "- API keys, key file paths, proxy URLs, API base URLs, authorization headers, raw prompts, raw request bodies, and temporary ledger paths are intentionally omitted.",
            "",
        ]
    )
    return "\n".join(lines)


def _overall_sentence(summary: dict) -> str:
    if summary.get("ok") and summary.get("live_used"):
        return "真实模型链路、Fast-Path、申诉、管理员审核和账本摘要均在临时沙箱中闭环通过。"
    if summary.get("ok"):
        return "本地假供应商沙箱链路已闭环通过，未触达真实模型供应商。"
    return "全流程演练存在失败步骤，请先查看 Steps 表格中的 FAIL 项。"


def _step_sentence(step: dict) -> str:
    name = step.get("name")
    if name == "runtime_status":
        return "运行状态可读取，模型配置、预算和熔断摘要可见。"
    if name == "low_risk_read_skip":
        return "低风险静态请求被本地规则跳过，没有调用 AI。"
    if name == "sync_agent_ai_review":
        return "登录类风险请求进入同步 Agent 审核，并返回结构化判断。"
    if name == "fast_path_attack_block":
        return "XSS 样例被 Fast-Path 直接拦截，没有继续发送给模型。"
    if name == "appeal_submit":
        return "用户申诉被接收并进入待处理队列。"
    if name == "admin_appeal_review":
        return "管理员审核申诉成功，审核行为写入账本摘要。"
    if name == "ledger_recent":
        return "安全账本可读取近期摘要，包含管理员操作者哈希。"
    return "模块返回了可解析响应。"


def _step_code_status(step: dict) -> str:
    state = "OK" if step.get("ok") else "FAIL"
    name = step.get("name")
    if name == "appeal_submit":
        return f"{state}; http_status={step.get('status')}"
    if step.get("llm_reason"):
        return f"{state}; reason={step.get('llm_reason')}"
    if step.get("route"):
        return f"{state}; route={step.get('route')}"
    return state


def _step_key_response(step: dict) -> str:
    safe_keys = [
        "runtime_mode",
        "agent_paused",
        "api_base_configured",
        "api_key_configured",
        "proxy_configured",
        "circuit_open",
        "fast_path_rule",
        "llm_called",
        "llm_latency_ms",
        "selected_action",
        "tool_effective_action",
        "tool_executed",
        "ledger_written",
        "appeal_status",
        "record_count",
        "has_admin_actor_hash",
    ]
    parts = [f"{key}={step.get(key)}" for key in safe_keys if key in step]
    return "; ".join(parts) or "-"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class _FakeProvider:
    def __init__(self):
        self.calls = 0
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}/v1"

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def _handler_class(self):
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0") or 0)
                self.rfile.read(length)
                with provider._lock:
                    provider.calls += 1

                content = json.dumps({"selected_action": "rule_hint", "ai_confidence": 0.62})
                response = {"choices": [{"message": {"content": content}}]}
                data = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format, *args):
                return

        return Handler


if __name__ == "__main__":
    raise SystemExit(main())

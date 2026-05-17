import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "services" / "core-service"
sys.path.insert(0, str(CORE_PATH))

from atee_core.config import ConfigStore  # noqa: E402
from atee_core.llm_gateway import RemoteLLMGateway  # noqa: E402


DEFAULT_BAD_PROXY_URL = "http://127.0.0.1:9"
REMOTE_MODES = {"openai_compatible", "remote"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ATEE provider/proxy fault drills without exposing secrets.")
    parser.add_argument("--config", default=str(ROOT / "config" / "config.json"))
    parser.add_argument("--bad-proxy-url", default=DEFAULT_BAD_PROXY_URL)
    parser.add_argument("--include-live", action="store_true", help="Also call the configured live provider once.")
    parser.add_argument("--report", help="Write a sanitized Markdown drill report to this path.")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = ConfigStore(config_path).load()
    base_dir = _infer_project_root(config_path)

    summary = {
        "ok": False,
        "config": _public_config_summary(config),
        "bad_proxy": _run_bad_proxy_drill(config, base_dir, args.bad_proxy_url),
        "live": {"skipped": True, "reason": "include_live_not_requested"},
    }
    if args.include_live:
        summary["live"] = _run_live_probe(config, base_dir)

    summary["ok"] = bool(summary["bad_proxy"].get("ok")) and (
        summary["live"].get("skipped") or bool(summary["live"].get("ok"))
    )
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(_markdown_report(summary), encoding="utf-8")
        summary["report_path"] = str(report_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


def _run_bad_proxy_drill(config, base_dir: Path, bad_proxy_url: str) -> dict:
    if config.llm_mode not in REMOTE_MODES:
        return {"ok": False, "skipped": True, "reason": "remote_llm_not_configured"}

    drill_config = deepcopy(config)
    drill_config.llm_proxy_url = bad_proxy_url
    drill_config.remote_soft_timeout_ms = min(int(drill_config.remote_soft_timeout_ms), 100)
    drill_config.remote_hard_timeout_ms = min(int(drill_config.remote_hard_timeout_ms), 1000)
    drill_config.llm_daily_budget_cents = 0

    gateway = RemoteLLMGateway(drill_config, base_dir=base_dir)
    results = [gateway.test_connection() for _ in range(4)]
    reasons = [str(result.get("reason") or "") for result in results]
    status = gateway.status()
    fourth_blocked_by_circuit = reasons[-1] == "llm_circuit_open"
    first_three_failed_at_provider = all(reason in {"provider_request_failed", "provider_timeout"} for reason in reasons[:3])
    return {
        "ok": first_three_failed_at_provider and fourth_blocked_by_circuit and status["circuit"]["open"],
        "skipped": False,
        "reasons": reasons,
        "provider_failures_before_circuit": reasons[:3],
        "fourth_request_reason": reasons[-1],
        "circuit": status["circuit"],
        "api_key_configured": bool(status["api_key_configured"]),
        "api_base_configured": bool(status["api_base_configured"]),
        "proxy_configured_for_drill": True,
    }


def _run_live_probe(config, base_dir: Path) -> dict:
    if config.llm_mode not in REMOTE_MODES:
        return {"ok": False, "skipped": True, "reason": "remote_llm_not_configured"}
    gateway = RemoteLLMGateway(deepcopy(config), base_dir=base_dir)
    result = gateway.test_connection()
    return {
        "ok": bool(result.get("ok")),
        "skipped": False,
        "reason": result.get("reason"),
        "latency_ms": result.get("latency_ms"),
        "budget": result.get("budget"),
        "circuit": result.get("circuit"),
        "api_key_configured": bool(result.get("api_key_configured")),
        "api_base_configured": bool(result.get("api_base_configured")),
        "proxy_configured": bool(result.get("proxy_configured")),
    }


def _public_config_summary(config) -> dict:
    return {
        "mode": config.llm_mode,
        "provider": config.llm_provider,
        "model": config.llm_model,
        "api_base_configured": bool(config.llm_api_base),
        "api_key_file_configured": bool(config.llm_api_key_file),
        "api_key_env_configured": bool(config.llm_api_key_env),
        "proxy_configured": bool(config.llm_proxy_url),
    }


def _markdown_report(summary: dict) -> str:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    config = summary.get("config") or {}
    bad_proxy = summary.get("bad_proxy") or {}
    circuit = bad_proxy.get("circuit") or {}
    live = summary.get("live") or {}
    lines = [
        "# ATEE Provider Fault Drill Report",
        "",
        f"- Generated at UTC: {generated_at}",
        f"- Overall OK: {bool(summary.get('ok'))}",
        f"- Provider: {config.get('provider')}",
        f"- Model: {config.get('model')}",
        f"- Mode: {config.get('mode')}",
        f"- API base configured: {bool(config.get('api_base_configured'))}",
        f"- API key source configured: {bool(config.get('api_key_file_configured') or config.get('api_key_env_configured'))}",
        f"- Proxy configured in saved config: {bool(config.get('proxy_configured'))}",
        "",
        "## Bad Proxy Drill",
        "",
        f"- OK: {bool(bad_proxy.get('ok'))}",
        f"- Failure reasons before circuit: {', '.join(bad_proxy.get('provider_failures_before_circuit') or [])}",
        f"- Fourth request reason: {bad_proxy.get('fourth_request_reason')}",
        f"- Circuit open: {bool(circuit.get('open'))}",
        f"- Consecutive failures: {circuit.get('consecutive_failures')}",
        f"- Failure threshold: {circuit.get('failure_threshold')}",
        f"- Cooldown seconds: {circuit.get('cooldown_seconds')}",
        "",
        "## Live Probe",
        "",
    ]
    if live.get("skipped"):
        lines.extend(
            [
                "- Skipped: True",
                f"- Reason: {live.get('reason')}",
            ]
        )
    else:
        lines.extend(
            [
                "- Skipped: False",
                f"- OK: {bool(live.get('ok'))}",
                f"- Reason: {live.get('reason')}",
                f"- Latency ms: {live.get('latency_ms')}",
            ]
        )
    lines.extend(
        [
            "",
            "## Security Notes",
            "",
            "- API keys, key file paths, proxy URLs, raw prompts, and raw request bodies are intentionally omitted.",
            "- The default drill uses an in-memory bad proxy and does not modify config/config.json.",
            "- Use --include-live only for an intentional live provider recovery probe.",
            "",
        ]
    )
    return "\n".join(lines)


def _infer_project_root(config_path: Path) -> Path:
    parent = config_path.resolve().parent
    if parent.name.lower() == "config":
        return parent.parent
    return parent


if __name__ == "__main__":
    raise SystemExit(main())

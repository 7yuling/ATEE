import argparse
import json
import os
import sys
import threading
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "services" / "core-service"
sys.path.insert(0, str(CORE_PATH))

from atee_core.config import AdminConfig, ConfigStore  # noqa: E402
from atee_core.llm_gateway import RemoteLLMGateway  # noqa: E402


DRILL_KEY_ENV = "ATEE_PROVIDER_LIVE_BATCH_DRILL_KEY"
LIVE_ATTEMPT_LIMIT = 3
REMOTE_MODES = {"openai_compatible", "remote"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an ATEE provider small-batch drill with sanitized output.")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--budget-cents", type=int, default=3)
    parser.add_argument("--config", default=str(ROOT / "config" / "config.json"))
    parser.add_argument("--include-live", action="store_true", help="Call the configured live provider.")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    attempts = max(1, args.attempts)
    budget_cents = max(1, args.budget_cents)
    if args.include_live and attempts > LIVE_ATTEMPT_LIMIT:
        parser.error(f"--include-live is capped at {LIVE_ATTEMPT_LIMIT} attempts")

    if args.include_live:
        summary = _run_live_batch(Path(args.config), attempts, budget_cents)
    else:
        summary = _run_fake_batch(attempts, budget_cents)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(_markdown_report(summary), encoding="utf-8")
        summary["report_path"] = str(args.report)

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


def _run_fake_batch(attempts: int, budget_cents: int) -> dict:
    previous_key = os.environ.get(DRILL_KEY_ENV)
    os.environ[DRILL_KEY_ENV] = f"local-live-batch-{uuid4().hex}"
    try:
        with _FakeProvider() as provider:
            gateway = RemoteLLMGateway(
                AdminConfig(
                    llm_mode="openai_compatible",
                    llm_provider="batch-drill-provider",
                    llm_model="batch-drill-model",
                    llm_api_base=provider.base_url,
                    llm_api_key_env=DRILL_KEY_ENV,
                    llm_daily_budget_cents=budget_cents,
                    remote_soft_timeout_ms=100,
                    remote_hard_timeout_ms=1000,
                )
            )
            results = [gateway.test_connection() for _ in range(attempts)]
            return _summary(
                mode="fake",
                attempts=attempts,
                budget_cents=budget_cents,
                results=results,
                status=gateway.status(),
                provider_calls=provider.calls,
            )
    finally:
        if previous_key is None:
            os.environ.pop(DRILL_KEY_ENV, None)
        else:
            os.environ[DRILL_KEY_ENV] = previous_key


def _run_live_batch(config_path: Path, attempts: int, budget_cents: int) -> dict:
    config = ConfigStore(config_path).load()
    if config.llm_mode not in REMOTE_MODES:
        return {
            "ok": False,
            "mode": "live",
            "attempts": attempts,
            "budget_cents": budget_cents,
            "reason": "remote_llm_not_configured",
        }
    drill_config = deepcopy(config)
    drill_config.llm_daily_budget_cents = min(attempts, budget_cents)
    gateway = RemoteLLMGateway(drill_config, base_dir=_infer_project_root(config_path))
    results = [gateway.test_connection() for _ in range(attempts)]
    return _summary(
        mode="live",
        attempts=attempts,
        budget_cents=drill_config.llm_daily_budget_cents,
        results=results,
        status=gateway.status(),
        provider_calls=None,
    )


def _summary(
    *,
    mode: str,
    attempts: int,
    budget_cents: int,
    results: list[dict],
    status: dict,
    provider_calls: int | None,
) -> dict:
    reasons = [str(result.get("reason") or "") for result in results]
    expected_remote_calls = min(attempts, budget_cents)
    expected_exhausted = attempts - expected_remote_calls
    reason_counts = _count_reasons(reasons)
    ok = (
        reason_counts.get("provider_json_decision", 0) == expected_remote_calls
        and reason_counts.get("llm_budget_exhausted", 0) == expected_exhausted
        and status["budget"]["daily_spend_cents"] == expected_remote_calls
        and status["budget"]["daily_remaining_cents"] == 0
        and not status["circuit"]["open"]
    )
    if provider_calls is not None:
        ok = ok and provider_calls == expected_remote_calls
    return {
        "ok": ok,
        "mode": mode,
        "live_used": mode == "live",
        "attempts": attempts,
        "budget_cents": budget_cents,
        "expected_remote_calls": expected_remote_calls,
        "provider_calls": provider_calls,
        "reasons": reasons,
        "reason_counts": reason_counts,
        "latency_ms": _latency_summary(results),
        "budget": status["budget"],
        "circuit": status["circuit"],
        "api_key_configured": bool(status["api_key_configured"]),
        "api_base_configured": bool(status["api_base_configured"]),
        "proxy_configured": bool(status["proxy_configured"]),
        "raw_prompt_storage": bool(status["raw_prompt_storage"]),
    }


def _count_reasons(reasons: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for reason in reasons:
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _latency_summary(results: list[dict]) -> dict:
    values = [int(result.get("latency_ms") or 0) for result in results]
    if not values:
        return {"min": 0, "max": 0, "avg": 0}
    return {
        "min": min(values),
        "max": max(values),
        "avg": round(sum(values) / len(values), 2),
    }


def _markdown_report(summary: dict) -> str:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    latency = summary.get("latency_ms") or {}
    lines = [
        "# ATEE Provider Live Batch Drill Report",
        "",
        f"- Generated at UTC: {generated_at}",
        f"- Overall OK: {bool(summary.get('ok'))}",
        f"- Mode: {summary.get('mode')}",
        f"- Live used: {bool(summary.get('live_used'))}",
        f"- Attempts: {summary.get('attempts')}",
        f"- Budget cents: {summary.get('budget_cents')}",
        f"- Expected remote calls: {summary.get('expected_remote_calls')}",
        f"- Provider calls observed: {summary.get('provider_calls')}",
        f"- API key configured: {bool(summary.get('api_key_configured'))}",
        f"- API base configured: {bool(summary.get('api_base_configured'))}",
        f"- Proxy configured: {bool(summary.get('proxy_configured'))}",
        "",
        "## Reason Counts",
        "",
    ]
    for reason, count in sorted((summary.get("reason_counts") or {}).items()):
        lines.append(f"- {reason}: {count}")
    lines.extend(
        [
            "",
            "## Latency",
            "",
            f"- Min ms: {latency.get('min')}",
            f"- Max ms: {latency.get('max')}",
            f"- Avg ms: {latency.get('avg')}",
            "",
            "## Security Notes",
            "",
            "- The default drill uses a temporary local fake provider and does not call the configured live provider.",
            "- Use --include-live only for an intentional small-batch live provider rehearsal.",
            f"- Live mode is capped at {LIVE_ATTEMPT_LIMIT} attempts by default.",
            "- API keys, key file paths, proxy URLs, API base URLs, raw prompts, and raw request bodies are intentionally omitted.",
            "",
        ]
    )
    return "\n".join(lines)


def _infer_project_root(config_path: Path) -> Path:
    parent = config_path.resolve().parent
    if parent.name.lower() == "config":
        return parent.parent
    return parent


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

                content = json.dumps({"selected_action": "allow", "ai_confidence": 0.61})
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

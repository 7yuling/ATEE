import argparse
import json
import os
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "services" / "core-service"
sys.path.insert(0, str(CORE_PATH))

from atee_core.config import AdminConfig  # noqa: E402
from atee_core.llm_gateway import RemoteLLMGateway  # noqa: E402


DRILL_KEY_ENV = "ATEE_PROVIDER_BUDGET_DRILL_KEY"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local ATEE provider budget/limit drill.")
    parser.add_argument("--attempts", type=int, default=6)
    parser.add_argument("--budget-cents", type=int, default=2)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    attempts = max(1, args.attempts)
    budget_cents = max(1, args.budget_cents)
    if attempts <= budget_cents:
        parser.error("--attempts must be greater than --budget-cents so exhaustion can be verified")

    previous_key = os.environ.get(DRILL_KEY_ENV)
    os.environ[DRILL_KEY_ENV] = f"local-drill-{uuid4().hex}"
    try:
        with _FakeProvider() as provider:
            gateway = RemoteLLMGateway(
                AdminConfig(
                    llm_mode="openai_compatible",
                    llm_provider="local-budget-drill",
                    llm_model="local-budget-model",
                    llm_api_base=provider.base_url,
                    llm_api_key_env=DRILL_KEY_ENV,
                    llm_daily_budget_cents=budget_cents,
                    remote_soft_timeout_ms=100,
                    remote_hard_timeout_ms=1000,
                )
            )
            results = [gateway.test_connection() for _ in range(attempts)]
            summary = _summary(attempts, budget_cents, provider.calls, results, gateway.status())
    finally:
        if previous_key is None:
            os.environ.pop(DRILL_KEY_ENV, None)
        else:
            os.environ[DRILL_KEY_ENV] = previous_key

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(_markdown_report(summary), encoding="utf-8")
        summary["report_path"] = str(args.report)

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


def _summary(attempts: int, budget_cents: int, provider_calls: int, results: list[dict], status: dict) -> dict:
    reasons = [str(result.get("reason") or "") for result in results]
    expected_remote_calls = min(attempts, budget_cents)
    expected_exhausted = attempts - expected_remote_calls
    ok_results = reasons[:expected_remote_calls]
    exhausted_results = reasons[expected_remote_calls:]
    budget = status["budget"]
    return {
        "ok": provider_calls == expected_remote_calls
        and ok_results == ["provider_json_decision"] * expected_remote_calls
        and exhausted_results == ["llm_budget_exhausted"] * expected_exhausted
        and budget["daily_spend_cents"] == expected_remote_calls
        and budget["daily_remaining_cents"] == 0,
        "attempts": attempts,
        "budget_cents": budget_cents,
        "expected_remote_calls": expected_remote_calls,
        "provider_calls": provider_calls,
        "reasons": reasons,
        "reason_counts": _count_reasons(reasons),
        "budget": budget,
        "circuit": status["circuit"],
        "api_key_configured": bool(status["api_key_configured"]),
        "api_base_configured": bool(status["api_base_configured"]),
        "raw_prompt_storage": bool(status["raw_prompt_storage"]),
    }


def _count_reasons(reasons: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for reason in reasons:
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _markdown_report(summary: dict) -> str:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    lines = [
        "# ATEE Provider Budget Drill Report",
        "",
        f"- Generated at UTC: {generated_at}",
        f"- Overall OK: {bool(summary.get('ok'))}",
        f"- Attempts: {summary.get('attempts')}",
        f"- Budget cents: {summary.get('budget_cents')}",
        f"- Provider calls made: {summary.get('provider_calls')}",
        f"- Expected remote calls: {summary.get('expected_remote_calls')}",
        f"- API key configured: {bool(summary.get('api_key_configured'))}",
        f"- API base configured: {bool(summary.get('api_base_configured'))}",
        "",
        "## Reason Counts",
        "",
    ]
    for reason, count in sorted((summary.get("reason_counts") or {}).items()):
        lines.append(f"- {reason}: {count}")
    budget = summary.get("budget") or {}
    lines.extend(
        [
            "",
            "## Budget",
            "",
            f"- Daily budget cents: {budget.get('daily_budget_cents')}",
            f"- Daily spend cents: {budget.get('daily_spend_cents')}",
            f"- Daily remaining cents: {budget.get('daily_remaining_cents')}",
            "",
            "## Security Notes",
            "",
            "- The drill uses a temporary local fake provider and does not call the configured live provider.",
            "- API keys, key file paths, proxy URLs, API base URLs, raw prompts, and raw request bodies are intentionally omitted.",
            "- Budget exhaustion should return llm_budget_exhausted without sending additional provider requests.",
            "",
        ]
    )
    return "\n".join(lines)


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

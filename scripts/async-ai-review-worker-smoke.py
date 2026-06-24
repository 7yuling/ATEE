import argparse
import json
import os
import sys
import tempfile
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "services" / "core-service"
sys.path.insert(0, str(CORE_PATH))

from atee_core.async_review_worker import AsyncReviewWorker  # noqa: E402
from atee_core.config import AdminConfig, ConfigStore  # noqa: E402
from atee_core.core import CoreService  # noqa: E402


DRILL_KEY_ENV = "ATEE_ASYNC_AI_WORKER_SMOKE_KEY"
REMOTE_MODES = {"openai_compatible", "remote"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a sanitized async AI review worker smoke check.")
    parser.add_argument("--config", default=str(ROOT / "config" / "config.json"))
    parser.add_argument("--include-live", action="store_true", help="Call the configured live provider through the worker once.")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    os.chdir(ROOT)
    config_path = Path(args.config)
    summary = _run_live(config_path) if args.include_live else _run_fake()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(_markdown_report(summary), encoding="utf-8")
        summary["report_path"] = str(args.report)

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


def _run_fake() -> dict:
    previous_key = os.environ.get(DRILL_KEY_ENV)
    os.environ[DRILL_KEY_ENV] = f"async-worker-key-{uuid4().hex}"
    try:
        with _FakeProvider(mode="success") as provider:
            budget = _run_budget_scenario(provider.base_url, provider_calls=lambda: provider.calls)
        with _FakeProvider(mode="failure") as provider:
            circuit = _run_circuit_scenario(provider.base_url, provider_calls=lambda: provider.calls)
    finally:
        if previous_key is None:
            os.environ.pop(DRILL_KEY_ENV, None)
        else:
            os.environ[DRILL_KEY_ENV] = previous_key

    return {
        "ok": bool(budget.get("ok") and circuit.get("ok")),
        "generated_at": _utc_now(),
        "mode": "fake",
        "live_used": False,
        "scenarios": [budget, circuit],
        "security": _security_notes(),
    }


def _run_live(config_path: Path) -> dict:
    base_config = ConfigStore(config_path).load()
    if base_config.llm_mode not in REMOTE_MODES:
        return {
            "ok": False,
            "generated_at": _utc_now(),
            "mode": "live",
            "live_used": True,
            "reason": "remote_llm_not_configured",
            "scenarios": [],
            "security": _security_notes(),
        }
    config = deepcopy(base_config)
    temp_dir = Path(tempfile.mkdtemp(prefix="atee-async-worker-live-"))
    config.ledger_sqlite_path = str(temp_dir / "worker-live.sqlite3")
    config.async_review_worker_enabled = True
    config.async_review_worker_interval_seconds = 1
    config.async_review_worker_batch_size = 1
    scenario = _run_worker_scenario(
        name="live_worker_single_review",
        config=config,
        job_count=1,
        expected_completed=1,
        expected_dead_letter=0,
        expected_provider_calls=None,
        expect_circuit_open=False,
    )
    return {
        "ok": bool(scenario.get("ok")),
        "generated_at": _utc_now(),
        "mode": "live",
        "live_used": True,
        "scenarios": [scenario],
        "security": _security_notes(),
    }


def _run_budget_scenario(base_url: str, provider_calls) -> dict:
    config = _fake_config(base_url, budget_cents=1)
    return _run_worker_scenario(
        name="budget_exhaustion_pauses_pending",
        config=config,
        job_count=2,
        expected_completed=1,
        expected_dead_letter=0,
        expected_pending=1,
        expected_provider_calls=1,
        expect_circuit_open=False,
        provider_calls=provider_calls,
    )


def _run_circuit_scenario(base_url: str, provider_calls) -> dict:
    config = _fake_config(base_url, budget_cents=0)
    return _run_worker_scenario(
        name="provider_failure_circuit_breaker",
        config=config,
        job_count=3,
        expected_completed=0,
        expected_dead_letter=0,
        expected_provider_calls=3,
        expect_circuit_open=True,
        provider_calls=provider_calls,
    )


def _fake_config(base_url: str, budget_cents: int) -> AdminConfig:
    temp_dir = Path(tempfile.mkdtemp(prefix="atee-async-worker-smoke-"))
    return AdminConfig(
        llm_mode="openai_compatible",
        llm_provider="async-worker-smoke-provider",
        llm_model="async-worker-smoke-model",
        llm_api_base=base_url,
        llm_api_key_env=DRILL_KEY_ENV,
        llm_daily_budget_cents=budget_cents,
        ledger_sqlite_path=str(temp_dir / "worker.sqlite3"),
        async_review_worker_enabled=True,
        async_review_worker_interval_seconds=1,
        async_review_worker_batch_size=3,
        remote_soft_timeout_ms=100,
        remote_hard_timeout_ms=1000,
    )


def _run_worker_scenario(
    name: str,
    config: AdminConfig,
    job_count: int,
    expected_completed: int,
    expected_dead_letter: int,
    expected_provider_calls: int | None,
    expect_circuit_open: bool,
    expected_pending: int | None = None,
    provider_calls=None,
) -> dict:
    core = CoreService(config=config)
    if core.async_reviews:
        core.async_reviews.retry_backoff_seconds = 0
    queued = [_enqueue_comment(core, index) for index in range(job_count)]
    worker = AsyncReviewWorker(
        core,
        interval_seconds=config.async_review_worker_interval_seconds,
        batch_size=config.async_review_worker_batch_size,
    )
    try:
        worker.start()
        deadline = time.time() + 8
        completed = dead_letter = 0
        while time.time() < deadline:
            completed = core.admin_async_reviews(status="completed").get("count", 0)
            dead_letter = core.admin_async_reviews(status="dead_letter").get("count", 0)
            if completed >= expected_completed and dead_letter >= expected_dead_letter:
                break
            time.sleep(0.05)
    finally:
        worker.stop()

    status = core.runtime_status()
    queue_status = status.get("async_review") or {}
    llm_status = status.get("llm_gateway") or {}
    circuit = llm_status.get("circuit") or {}
    budget = llm_status.get("budget") or {}
    actual_provider_calls = provider_calls() if callable(provider_calls) else None
    provider_calls_ok = True if expected_provider_calls is None else actual_provider_calls == expected_provider_calls
    pending_ok = True if expected_pending is None else int(queue_status.get("pending") or 0) == expected_pending
    ok = (
        completed == expected_completed
        and dead_letter == expected_dead_letter
        and pending_ok
        and provider_calls_ok
        and bool(circuit.get("open")) is bool(expect_circuit_open)
    )
    return {
        "name": name,
        "ok": ok,
        "queued": len(queued),
        "completed": completed,
        "dead_letter": dead_letter,
        "provider_calls": actual_provider_calls,
        "expected_provider_calls": expected_provider_calls,
        "budget": {
            "daily_budget_cents": budget.get("daily_budget_cents"),
            "daily_spend_cents": budget.get("daily_spend_cents"),
            "daily_remaining_cents": budget.get("daily_remaining_cents"),
        },
        "circuit": {
            "open": bool(circuit.get("open")),
            "consecutive_failures": circuit.get("consecutive_failures"),
            "failure_threshold": circuit.get("failure_threshold"),
        },
        "worker": {
            "last_error": worker.last_error,
            "last_claimed": (worker.last_result or {}).get("claimed"),
        },
        "queue": _public_queue_status(queue_status),
    }


def _enqueue_comment(core: CoreService, index: int) -> dict:
    return core.check(
        {
            "method": "POST",
            "path": "/comment",
            "event_type": "comment_create",
            "body": {"text": f"async worker smoke comment {index}"},
        },
        remote_addr="198.51.100.42",
    )


def _public_queue_status(status: dict) -> dict:
    return {
        "queued": status.get("queued"),
        "pending": status.get("pending"),
        "retry": status.get("retry"),
        "completed": status.get("completed"),
        "dead_letter": status.get("dead_letter"),
        "sqlite_enabled": bool(status.get("sqlite_enabled")),
    }


def _security_notes() -> dict:
    return {
        "raw_prompt_stored": False,
        "raw_request_body_stored": False,
        "secrets_omitted": True,
        "live_requires_explicit_flag": True,
    }


def _markdown_report(summary: dict) -> str:
    lines = [
        "# ATEE Async AI Review Worker Smoke Report",
        "",
        f"- Generated at UTC: {summary.get('generated_at')}",
        f"- Overall OK: {bool(summary.get('ok'))}",
        f"- Mode: {summary.get('mode')}",
        f"- Live used: {bool(summary.get('live_used'))}",
        f"- One-sentence summary: {_overall_sentence(summary)}",
        "",
        "## Scenarios",
        "",
    ]
    for scenario in summary.get("scenarios") or []:
        budget = scenario.get("budget") or {}
        circuit = scenario.get("circuit") or {}
        lines.extend(
            [
                f"### {scenario.get('name')}",
                "",
                f"- OK: {bool(scenario.get('ok'))}",
                f"- Queued jobs: {scenario.get('queued')}",
                f"- Completed jobs: {scenario.get('completed')}",
                f"- Dead-letter jobs: {scenario.get('dead_letter')}",
                f"- Provider calls: {scenario.get('provider_calls')}",
                f"- Daily spend cents: {budget.get('daily_spend_cents')}",
                f"- Circuit open: {bool(circuit.get('open'))}",
                "",
            ]
        )
    lines.extend(
        [
            "## Security Notes",
            "",
            "- Default mode uses a temporary local fake provider and does not call the configured live provider.",
            "- Live provider calls require `--include-live`.",
            "- API keys, API base URLs, proxy URLs, key file paths, raw prompts, raw request bodies, auth headers, and temporary ledger paths are omitted.",
            "",
        ]
    )
    return "\n".join(lines)


def _overall_sentence(summary: dict) -> str:
    if not summary.get("ok"):
        return "Async AI review worker smoke did not complete all expected checks."
    if summary.get("live_used"):
        return "Async AI review worker completed one live configured-provider review without exposing secrets."
    return "Async AI review worker completed budget and circuit-breaker rehearsal with only local fake providers."


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class _FakeProvider:
    def __init__(self, mode: str = "success"):
        self.mode = mode
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
                if provider.mode == "failure":
                    self.send_response(500)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return

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

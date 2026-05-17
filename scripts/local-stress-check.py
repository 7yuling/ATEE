import argparse
import json
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "services" / "core-service"
sys.path.insert(0, str(CORE_PATH))

from atee_core.config import AdminConfig  # noqa: E402
from atee_core.core import CoreService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local ATEE mixed-load and restart-recovery check.")
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--duration-seconds", type=float, default=0.0)
    parser.add_argument("--max-requests", type=int, default=0)
    parser.add_argument("--target-rps", type=float, default=0.0)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    request_count = max(1, args.requests)
    workers = max(1, args.workers)
    duration_seconds = max(0.0, args.duration_seconds)
    max_requests = max(0, args.max_requests)
    target_rps = max(0.0, args.target_rps)

    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "config" / "config.json"
        core = CoreService(
            config=AdminConfig(
                runtime_mode="auto",
                llm_mode="mock",
                llm_provider="mock",
                llm_model="atee-local-mock-v1",
            ),
            config_path=config_path,
        )

        load = _run_mixed_load(
            core=core,
            workers=workers,
            request_count=request_count,
            duration_seconds=duration_seconds,
            max_requests=max_requests,
            target_rps=target_rps,
        )

        appeal = core.appeal({"punishment_id": "stress-pending", "reason": "本地压力检查申诉"})
        active_actions = core.admin_actions(status="active")["actions"]
        revoked = None
        if active_actions:
            revoked = core.revoke_action({"action_id": active_actions[0]["id"], "reason": "local stress rollback"})
        expired = core.executor.execute(
            {
                "selected_action": "challenge",
                "duration_seconds": -1,
                "target_scope": {"type": "request", "hash": "local-stress-expired"},
            },
            {"executed": True, "effective_action": "challenge"},
        )
        cleanup = core.cleanup_expired_actions()
        before_restart = core.runtime_status()

        restarted = CoreService(config_path=config_path)
        after_restart = restarted.runtime_status()
        summary = {
            "ok": not load["errors"]
            and appeal.get("accepted")
            and expired.get("executed")
            and cleanup.get("expired_marked", 0) >= 1
            and after_restart["ledger"]["persisted_records"] == before_restart["ledger"]["persisted_records"]
            and restarted.admin_appeals(status="pending")["count"] >= 1
            and restarted.admin_actions(status="expired")["count"] >= 1,
            "mode": "duration" if duration_seconds > 0 else "requests",
            "requests": load["completed"],
            "target_requests": None if duration_seconds > 0 else request_count,
            "target_duration_seconds": duration_seconds if duration_seconds > 0 else None,
            "max_requests": max_requests if max_requests > 0 else None,
            "workers": workers,
            "target_rps": target_rps if target_rps > 0 else None,
            "elapsed_seconds": load["elapsed_seconds"],
            "throughput_rps": load["throughput_rps"],
            "routes": load["routes"],
            "errors": load["errors"],
            "ledger": after_restart["ledger"],
            "pending_appeals": restarted.admin_appeals(status="pending")["count"],
            "revoked_actions": restarted.admin_actions(status="revoked")["count"],
            "expired_actions": restarted.admin_actions(status="expired")["count"],
            "revoked_ok": None if revoked is None else bool(revoked.get("ok")),
        }
        if args.report:
            summary["report_path"] = str(args.report)
            _write_report(args.report, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if summary["ok"] else 1


def _run_mixed_load(
    *,
    core: CoreService,
    workers: int,
    request_count: int,
    duration_seconds: float,
    max_requests: int,
    target_rps: float,
) -> dict:
    errors: list[str] = []
    routes: dict[str, int] = {}
    completed = 0
    next_index = 0
    started = time.monotonic()
    deadline = started + duration_seconds if duration_seconds > 0 else None
    if duration_seconds > 0:
        target = max_requests if max_requests > 0 else sys.maxsize
    else:
        target = request_count

    with ThreadPoolExecutor(max_workers=workers) as executor:
        while True:
            if next_index >= target:
                break
            if deadline is not None and time.monotonic() >= deadline and completed > 0:
                break
            max_batch_size = max(1, workers)
            if target_rps > 0:
                max_batch_size = min(max_batch_size, max(1, int(target_rps)))
            batch_size = min(max_batch_size, target - next_index)
            if batch_size <= 0:
                break
            futures = []
            for _ in range(batch_size):
                futures.append(executor.submit(core.check, _payload_for_index(next_index)))
                next_index += 1
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as exc:  # pragma: no cover - command line diagnostic path
                    errors.append(repr(exc))
                    continue
                completed += 1
                route = str((result.get("route") or {}).get("route") or "unknown")
                routes[route] = routes.get(route, 0) + 1
            _throttle_to_target_rps(started, completed, target_rps)

    elapsed = max(time.monotonic() - started, 0.001)
    return {
        "completed": completed,
        "elapsed_seconds": round(elapsed, 3),
        "throughput_rps": round(completed / elapsed, 2),
        "routes": routes,
        "errors": errors[:10],
    }


def _throttle_to_target_rps(started: float, completed: int, target_rps: float) -> None:
    if target_rps <= 0 or completed <= 0:
        return
    expected_elapsed = completed / target_rps
    actual_elapsed = time.monotonic() - started
    sleep_seconds = expected_elapsed - actual_elapsed
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)


def _write_report(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# ATEE Local Stress Report",
        "",
        f"- Generated at UTC: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Overall OK: {summary['ok']}",
        f"- Mode: {summary['mode']}",
        f"- Workers: {summary['workers']}",
        f"- Target rps: {summary['target_rps']}",
        f"- Requests completed: {summary['requests']}",
        f"- Elapsed seconds: {summary['elapsed_seconds']}",
        f"- Throughput rps: {summary['throughput_rps']}",
        "",
        "## Routes",
        "",
    ]
    for route, count in sorted(summary["routes"].items()):
        lines.append(f"- {route}: {count}")
    lines.extend(
        [
            "",
            "## Recovery Checks",
            "",
            f"- Pending appeals after restart: {summary['pending_appeals']}",
            f"- Revoked actions after restart: {summary['revoked_actions']}",
            f"- Expired actions after restart: {summary['expired_actions']}",
            f"- Persisted ledger records: {summary['ledger']['persisted_records']}",
            "",
            "## Security Notes",
            "",
            "- The stress check uses a temporary mock LLM configuration and temporary SQLite state.",
            "- API keys, key file paths, proxy URLs, API base URLs, raw prompts, and raw request bodies are intentionally omitted.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _payload_for_index(index: int) -> dict:
    if index % 10 == 0:
        return {
            "method": "POST",
            "path": "/comment",
            "event_type": "comment_create",
            "body": {"text": f"<script>alert({index})</script>"},
            "remote_addr": f"203.0.113.{index % 30}",
        }
    if index % 5 == 0:
        return {
            "method": "GET",
            "path": f"/assets/stress-{index}.css",
            "remote_addr": f"198.51.100.{index % 30}",
        }
    if index % 3 == 0:
        return {
            "method": "POST",
            "path": "/login",
            "event_type": "login",
            "body": {"username": f"user-{index}", "password": "redacted-by-compiler"},
            "remote_addr": f"192.0.2.{index % 30}",
        }
    return {
        "method": "POST",
        "path": "/comment",
        "event_type": "comment_create",
        "body": {"text": f"普通中文评论 {index}"},
        "remote_addr": f"192.0.2.{index % 30}",
    }


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "config/secrets",
    "node_modules",
}

SKIP_FILES = {
    "config/config.json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a sanitized local ATEE release gate.")
    parser.add_argument("--quick", action="store_true", help="Run the fast local gate used by tests.")
    parser.add_argument("--skip-agent-smoke", action="store_true", help="Skip the fake Agent AI full-flow smoke.")
    parser.add_argument("--report", type=Path, help="Write a sanitized Markdown report.")
    args = parser.parse_args()

    runner = ReleaseGateRunner(args)
    summary = runner.run()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(_markdown_report(summary), encoding="utf-8")
        summary["report_path"] = str(args.report)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


class ReleaseGateRunner:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.steps: list[dict[str, Any]] = []

    def run(self) -> dict[str, Any]:
        self._run_command("config_preflight", [sys.executable, "services/core-service/check_config.py"])
        self._run_command("python_compile", [sys.executable, "-m", "compileall", "services", "adapters", "apps", "tests", "scripts"])
        if self.args.quick:
            test_command = [
                sys.executable,
                "-m",
                "unittest",
                "tests.test_agent_ai_full_flow_smoke",
                "tests.test_deployment_assets",
            ]
        else:
            test_command = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
        self._run_command("unit_tests", test_command, parse_tests=True)
        if not self.args.skip_agent_smoke:
            self._run_command(
                "agent_ai_full_flow_smoke",
                [
                    sys.executable,
                    "scripts/agent-ai-full-flow-smoke.py",
                    "--report",
                    "reports/agent-ai-full-flow-smoke-local-gate.md",
                ],
            )
        self.steps.append(_sensitive_scan())

        ok = all(step.get("ok") for step in self.steps)
        return {
            "ok": ok,
            "generated_at": _utc_now(),
            "mode": "quick" if self.args.quick else "full",
            "steps": self.steps,
            "security": {
                "raw_command_output_omitted": True,
                "sensitive_scan_scope": "workspace_without_config_secrets_node_modules_or_local_config",
            },
        }

    def _run_command(self, name: str, command: list[str], parse_tests: bool = False) -> None:
        started = time.monotonic()
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        output = (completed.stdout or "") + "\n" + (completed.stderr or "")
        step: dict[str, Any] = {
            "name": name,
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "elapsed_ms": elapsed_ms,
        }
        if parse_tests:
            tests = _parse_test_count(output)
            if tests is not None:
                step["tests_ran"] = tests
        if completed.returncode != 0:
            step["reason"] = "command_failed"
        self.steps.append(step)


def _parse_test_count(output: str) -> int | None:
    match = re.search(r"Ran\s+(\d+)\s+tests?", output)
    return int(match.group(1)) if match else None


def _sensitive_scan() -> dict[str, Any]:
    patterns = _sensitive_patterns()
    findings: list[dict[str, Any]] = []
    scanned_files = 0
    for path in _iter_scan_files(ROOT):
        text = _read_text(path)
        if text is None:
            continue
        scanned_files += 1
        rel = path.relative_to(ROOT).as_posix()
        for name, pattern in patterns:
            if pattern.search(text):
                findings.append({"file": rel, "pattern": name})
                break
    return {
        "name": "sensitive_scan",
        "ok": not findings,
        "scanned_files": scanned_files,
        "findings_count": len(findings),
        "findings": findings[:20],
    }


def _sensitive_patterns() -> list[tuple[str, re.Pattern[str]]]:
    provider_host = "api" + "." + "deepseek" + "." + "com"
    proxy_marker = "127" + ".0.0.1:" + "10808"
    provider_key_name = "deepseek" + "_api_key"
    fake_drill_secret = "budget" + "-drill-secret"
    local_drill = "local" + "-drill-[A-Za-z0-9]"
    local_live_batch = "local" + "-live-batch-[A-Za-z0-9]"
    local_agent_flow = "local" + "-agent-flow-[A-Za-z0-9]"
    return [
        ("api_key_shape", re.compile(r"(^|[^A-Za-z0-9_])sk-[A-Za-z0-9]{20,}")),
        ("fake_drill_secret", re.compile("|".join([fake_drill_secret, local_drill, local_live_batch, local_agent_flow]))),
        ("provider_host", re.compile(re.escape(provider_host))),
        ("proxy_marker", re.compile(re.escape(proxy_marker))),
        ("provider_key_filename", re.compile(re.escape(provider_key_name))),
    ]


def _iter_scan_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel in SKIP_FILES:
            continue
        if _is_skipped_path(rel):
            continue
        yield path


def _is_skipped_path(rel: str) -> bool:
    parts = rel.split("/")
    for skip in SKIP_DIRS:
        skip_parts = skip.split("/")
        if parts[: len(skip_parts)] == skip_parts:
            return True
    return False


def _read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:4096]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="ignore")


def _markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# ATEE Local Release Gate Report",
        "",
        f"- Generated at UTC: {summary.get('generated_at')}",
        f"- Overall OK: {bool(summary.get('ok'))}",
        f"- Mode: {summary.get('mode')}",
        "",
        "## Steps",
        "",
    ]
    for step in summary.get("steps") or []:
        state = "OK" if step.get("ok") else "FAIL"
        detail = ""
        if step.get("tests_ran") is not None:
            detail = f" tests={step.get('tests_ran')}"
        elif step.get("findings_count") is not None:
            detail = f" findings={step.get('findings_count')}"
        lines.append(f"- {step.get('name')}: {state}{detail}")
    lines.extend(
        [
            "",
            "## Security Notes",
            "",
            "- Raw command output is intentionally omitted from this report.",
            "- The sensitive scan skips local runtime config, config/secrets, node_modules, Git internals, and Python cache folders.",
            "- API keys, provider hosts, proxy endpoints, authorization headers, raw prompts, and raw request bodies are not printed.",
            "",
        ]
    )
    return "\n".join(lines)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())

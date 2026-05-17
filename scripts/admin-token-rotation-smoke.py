import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_NAME = "ATEE_ADMIN_TOKEN"


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate the ATEE Admin Token and run a sanitized smoke recheck.")
    parser.add_argument("--env-file", required=True, help="Environment file containing ATEE_ADMIN_TOKEN")
    parser.add_argument("--env-name", default=DEFAULT_ENV_NAME)
    parser.add_argument("--base-url", required=True, help="ATEE public base URL")
    parser.add_argument("--allow-http", action="store_true", help="Allow http:// targets for local rehearsal only")
    parser.add_argument("--expect-admin-auth", action="store_true", help="Require admin auth during smoke recheck")
    parser.add_argument("--verify-audit-actor", action="store_true")
    parser.add_argument("--audit-actor-id", default="rotation-smoke-check")
    parser.add_argument("--expected-audit-actor")
    parser.add_argument("--restart-command", help="Command line to restart/reload ATEE after rotating the env file")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    env_file = Path(args.env_file).expanduser()
    old_token = _read_env_value(env_file, args.env_name)
    old_fingerprint = _fingerprint(old_token) if old_token else None

    rotation = _rotate_token(env_file, args.env_name)
    new_token = _read_env_value(env_file, args.env_name)
    restart = _run_restart(args.restart_command)
    old_rejected = _check_old_token_rejected(args.base_url, old_token, args.timeout) if old_token else {
        "ok": True,
        "skipped": True,
        "reason": "old_token_not_present",
    }
    smoke = _run_smoke_check(args, new_token)

    summary = {
        "ok": bool(rotation.get("ok")) and bool(restart.get("ok") or restart.get("skipped")) and bool(old_rejected.get("ok")) and bool(smoke.get("ok")),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "env_name": args.env_name,
        "old_token_fingerprint": old_fingerprint,
        "new_token_fingerprint": _fingerprint(new_token) if new_token else None,
        "rotation": _public_rotation(rotation),
        "restart": restart,
        "old_token_rejected": old_rejected,
        "smoke": _public_smoke(smoke),
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(_markdown_report(summary), encoding="utf-8")
        summary["report_path"] = str(args.report)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


def _rotate_token(env_file: Path, env_name: str) -> dict[str, Any]:
    script = ROOT / "scripts" / "rotate-admin-token.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--env-file", str(env_file), "--env-name", env_name, "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"ok": False, "reason": "rotation_output_not_json"}
    payload["returncode"] = completed.returncode
    payload["ok"] = bool(payload.get("ok")) and completed.returncode == 0
    return payload


def _run_restart(command: str | None) -> dict[str, Any]:
    if not command:
        return {"ok": True, "skipped": True, "reason": "restart_command_not_provided"}
    args: str | list[str] = command if os.name == "nt" else shlex.split(command)
    completed = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)
    return {
        "ok": completed.returncode == 0,
        "skipped": False,
        "returncode": completed.returncode,
        "stdout_present": bool(completed.stdout.strip()),
        "stderr_present": bool(completed.stderr.strip()),
    }


def _run_smoke_check(args: argparse.Namespace, new_token: str | None) -> dict[str, Any]:
    if not new_token:
        return {"ok": False, "reason": "new_token_not_found"}
    token_env = f"{args.env_name}_ROTATION_SMOKE"
    env = os.environ.copy()
    env[token_env] = new_token
    command = [
        sys.executable,
        str(ROOT / "scripts" / "production-smoke-check.py"),
        "--base-url",
        args.base_url,
        "--admin-token-env",
        token_env,
        "--timeout",
        str(args.timeout),
    ]
    if args.allow_http:
        command.append("--allow-http")
    if args.expect_admin_auth:
        command.append("--expect-admin-auth")
    if args.verify_audit_actor:
        command.extend(["--verify-audit-actor", "--audit-actor-id", args.audit_actor_id])
        if args.expected_audit_actor:
            command.extend(["--expected-audit-actor", args.expected_audit_actor])
    completed = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=False)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"ok": False, "reason": "smoke_output_not_json"}
    payload["returncode"] = completed.returncode
    payload["ok"] = bool(payload.get("ok")) and completed.returncode == 0
    return payload


def _check_old_token_rejected(base_url: str, old_token: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/v1/admin/config",
        headers={"Authorization": f"Bearer {old_token}", "Content-Type": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {"ok": False, "status": int(response.status), "reason": "old_token_still_authorized"}
    except urllib.error.HTTPError as error:
        status = int(error.code)
        error.close()
        return {"ok": status in {401, 403}, "status": status}
    except (OSError, TimeoutError) as exc:
        return {"ok": False, "status": 0, "reason": exc.__class__.__name__}


def _read_env_value(path: Path, name: str) -> str | None:
    if not path.exists():
        return None
    prefix = f"{name}="
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line.split("=", 1)[1].strip()
    return None


def _fingerprint(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def _public_rotation(rotation: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": bool(rotation.get("ok")),
        "returncode": rotation.get("returncode"),
        "env_name": rotation.get("env_name"),
        "token_fingerprint": rotation.get("token_fingerprint"),
        "token_written": bool(rotation.get("token_written")),
        "token_shown": bool(rotation.get("token_shown")),
    }


def _public_smoke(smoke: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": bool(smoke.get("ok")),
        "returncode": smoke.get("returncode"),
        "checks": [
            {
                "name": check.get("name"),
                "ok": bool(check.get("ok")),
                "skipped": bool(check.get("skipped")),
            }
            for check in smoke.get("checks", [])
        ],
    }


def _markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# ATEE Admin Token Rotation Smoke Report",
        "",
        f"- Generated at: {summary.get('generated_at')}",
        f"- Overall ok: {summary.get('ok')}",
        f"- Env name: {summary.get('env_name')}",
        f"- Old token fingerprint: {summary.get('old_token_fingerprint') or 'none'}",
        f"- New token fingerprint: {summary.get('new_token_fingerprint') or 'none'}",
        f"- Restart: {'skipped' if summary.get('restart', {}).get('skipped') else summary.get('restart', {}).get('ok')}",
        f"- Old token rejected: {summary.get('old_token_rejected', {}).get('ok')}",
        f"- Smoke recheck ok: {summary.get('smoke', {}).get('ok')}",
        "",
        "## Security Notes",
        "- This report intentionally omits the token values, authorization headers, full target URL, and actor identifiers.",
        "- Re-run the smoke check after any service restart or secret manager change.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "services" / "core-service"
sys.path.insert(0, str(CORE_PATH))

from atee_core.config import AdminConfig, ConfigStore  # noqa: E402
from atee_core.core import CoreService  # noqa: E402


EXCLUDED_MARKER = "excluded-backup-drill-marker"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an isolated ATEE backup/restore integration drill.")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--keep-temp", action="store_true", help="Keep the temporary drill directory for manual inspection.")
    args = parser.parse_args()

    powershell = _find_powershell()

    temp = tempfile.TemporaryDirectory()
    temp_root = Path(temp.name)
    try:
        source_root = temp_root / "source-install"
        target_root = temp_root / "target-install"
        backup_dir = temp_root / "backups"
        source_state = _create_source_state(source_root)
        target_secret = _create_target_placeholder_secret(target_root)
        backup = _run_backup(powershell, source_root, backup_dir)
        archive = _inspect_archive(backup["archive_path"])
        restore = _run_restore(powershell, backup["archive_path"], target_root)
        restored_state = _inspect_restored_state(target_root, target_secret)
        summary = _summary(source_state, backup, archive, restore, restored_state)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(_markdown_report(summary), encoding="utf-8")
            summary["report_path"] = str(args.report)
        if args.keep_temp:
            summary["temp_root"] = str(temp_root)
            temp = None
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if summary["ok"] else 1
    finally:
        if temp is not None:
            temp.cleanup()


def _find_powershell() -> str | None:
    return shutil.which("powershell") or shutil.which("pwsh")


def _create_source_state(project_root: Path) -> dict:
    config_path = project_root / "config" / "config.json"
    ConfigStore(config_path).save(
        AdminConfig(
            runtime_mode="auto",
            agent_paused=False,
            llm_mode="mock",
            llm_provider="mock",
            llm_model="atee-local-mock-v1",
        )
    )
    core = CoreService(config_path=config_path)
    for index in range(12):
        core.check(_payload_for_index(index))
    appeal = core.appeal({"punishment_id": "backup-drill-pending", "reason": "backup restore drill"})

    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "atee-server.out.log").write_text("backup restore drill log\n", encoding="utf-8")

    secrets_dir = project_root / "config" / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / "excluded.txt").write_text(EXCLUDED_MARKER, encoding="utf-8")

    status = core.runtime_status()
    return {
        "persisted_records": status["ledger"]["persisted_records"],
        "pending_appeals": core.admin_appeals(status="pending")["count"],
        "active_actions": core.admin_actions(status="active")["count"],
        "appeal_accepted": bool(appeal.get("accepted")),
    }


def _payload_for_index(index: int) -> dict:
    if index % 4 == 0:
        return {
            "method": "POST",
            "path": "/comment",
            "event_type": "comment_create",
            "body": {"text": f"<script>alert({index})</script>"},
            "remote_addr": f"203.0.113.{index % 10}",
        }
    if index % 3 == 0:
        return {
            "method": "POST",
            "path": "/login",
            "event_type": "login",
            "body": {"username": f"user-{index}"},
            "remote_addr": f"192.0.2.{index % 10}",
        }
    return {
        "method": "POST",
        "path": "/comment",
        "event_type": "comment_create",
        "body": {"text": f"backup restore drill comment {index}"},
        "remote_addr": f"198.51.100.{index % 10}",
    }


def _create_target_placeholder_secret(project_root: Path) -> Path:
    target_secret = project_root / "config" / "secrets" / "existing.txt"
    target_secret.parent.mkdir(parents=True, exist_ok=True)
    target_secret.write_text("target-placeholder", encoding="utf-8")
    return target_secret


def _run_backup(powershell: str | None, source_root: Path, backup_dir: Path) -> dict:
    if not powershell:
        return _run_backup_python(source_root, backup_dir)
    command = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ROOT / "scripts" / "windows" / "backup-atee-state.ps1"),
        "-ProjectRoot",
        str(source_root),
        "-BackupDir",
        str(backup_dir),
        "-IncludeLogs",
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
    archive_path = _parse_backup_path(completed.stdout)
    return {
        "ok": completed.returncode == 0 and archive_path is not None and archive_path.exists(),
        "returncode": completed.returncode,
        "archive_path": archive_path,
    }


def _run_backup_python(source_root: Path, backup_dir: Path) -> dict:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive_path = backup_dir / f"atee-state-{timestamp}.zip"
    included: list[str] = []
    excluded = ["config/secrets/**"]

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in _backup_candidates(source_root):
            source_path = source_root / relative
            if not source_path.exists() or not source_path.is_file():
                continue
            archive.write(source_path, relative.as_posix())
            included.append(relative.as_posix())
        manifest = {
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "included": included,
            "excluded": excluded,
        }
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    return {
        "ok": archive_path.exists(),
        "returncode": 0,
        "archive_path": archive_path,
    }


def _backup_candidates(source_root: Path) -> list[Path]:
    candidates = [
        Path("config/config.json"),
        Path("data/atee_ledger.sqlite3"),
    ]
    logs_dir = source_root / "logs"
    if logs_dir.exists():
        for path in sorted(logs_dir.rglob("*")):
            if path.is_file():
                candidates.append(path.relative_to(source_root))
    return candidates

def _parse_backup_path(stdout: str) -> Path | None:
    for line in stdout.splitlines():
        marker = "Created backup:"
        if marker in line:
            return Path(line.split(marker, 1)[1].strip())
    return None


def _inspect_archive(archive_path: Path | None) -> dict:
    if not archive_path or not archive_path.exists():
        return {"ok": False, "reason": "archive_missing"}
    with zipfile.ZipFile(archive_path) as archive:
        names = {name.replace("\\", "/") for name in archive.namelist()}
        manifest = json.loads(archive.read("manifest.json").decode("utf-8-sig"))
        combined_text = "\n".join(names)
        for name in names:
            if name.endswith(".json") or name.endswith(".log") or name.endswith(".txt"):
                combined_text += "\n" + archive.read(name).decode("utf-8", errors="ignore")
    contains_secrets = any(name.startswith("config/secrets/") for name in names)
    contains_marker = EXCLUDED_MARKER in combined_text
    return {
        "ok": not contains_secrets
        and not contains_marker
        and "config/config.json" in names
        and "data/atee_ledger.sqlite3" in names
        and "logs/atee-server.out.log" in names,
        "archive_name": archive_path.name,
        "contains_config": "config/config.json" in names,
        "contains_sqlite": "data/atee_ledger.sqlite3" in names,
        "contains_logs": "logs/atee-server.out.log" in names,
        "contains_secrets": contains_secrets,
        "contains_excluded_marker": contains_marker,
        "manifest_included": manifest.get("included") or [],
        "manifest_excluded": manifest.get("excluded") or [],
    }


def _run_restore(powershell: str | None, backup_path: Path | None, target_root: Path) -> dict:
    target_root.mkdir(parents=True, exist_ok=True)
    if not backup_path:
        return {"ok": False, "reason": "backup_path_missing"}
    if not powershell:
        return _run_restore_python(backup_path, target_root)
    command = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ROOT / "scripts" / "windows" / "restore-atee-state.ps1"),
        "-BackupPath",
        str(backup_path),
        "-ProjectRoot",
        str(target_root),
        "-Force",
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
    return {"ok": completed.returncode == 0, "returncode": completed.returncode}


def _run_restore_python(backup_path: Path, target_root: Path) -> dict:
    try:
        with zipfile.ZipFile(backup_path) as archive:
            for member in archive.infolist():
                relative = Path(member.filename)
                if member.is_dir() or relative.name == "manifest.json":
                    continue
                destination = (target_root / relative).resolve()
                if not destination.is_relative_to(target_root.resolve()):
                    return {"ok": False, "returncode": 1, "reason": "unsafe_archive_path"}
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
        return {"ok": True, "returncode": 0}
    except (OSError, zipfile.BadZipFile) as exc:
        return {"ok": False, "returncode": 1, "reason": type(exc).__name__}


def _inspect_restored_state(project_root: Path, target_secret: Path) -> dict:
    config_path = project_root / "config" / "config.json"
    sqlite_path = project_root / "data" / "atee_ledger.sqlite3"
    marker_restored = False
    if (project_root / "config" / "secrets" / "excluded.txt").exists():
        marker_restored = EXCLUDED_MARKER in (project_root / "config" / "secrets" / "excluded.txt").read_text(
            encoding="utf-8", errors="ignore"
        )
    restored = CoreService(config_path=config_path) if config_path.exists() else None
    ledger = restored.runtime_status()["ledger"] if restored else {}
    return {
        "config_restored": config_path.exists(),
        "sqlite_restored": sqlite_path.exists(),
        "persisted_records": int(ledger.get("persisted_records") or 0),
        "pending_appeals": restored.admin_appeals(status="pending")["count"] if restored else 0,
        "active_actions": restored.admin_actions(status="active")["count"] if restored else 0,
        "target_placeholder_secret_preserved": target_secret.exists(),
        "source_secret_restored": marker_restored,
    }


def _summary(source: dict, backup: dict, archive: dict, restore: dict, restored: dict) -> dict:
    ok = (
        source["persisted_records"] > 0
        and source["appeal_accepted"]
        and backup["ok"]
        and archive["ok"]
        and restore["ok"]
        and restored["config_restored"]
        and restored["sqlite_restored"]
        and restored["persisted_records"] == source["persisted_records"]
        and restored["pending_appeals"] == source["pending_appeals"]
        and restored["target_placeholder_secret_preserved"]
        and not restored["source_secret_restored"]
    )
    return {
        "ok": ok,
        "source": source,
        "backup": {
            "ok": backup["ok"],
            "archive_name": archive.get("archive_name"),
        },
        "archive": archive,
        "restore": {
            "ok": restore["ok"],
            "config_restored": restored["config_restored"],
            "sqlite_restored": restored["sqlite_restored"],
            "persisted_records": restored["persisted_records"],
            "pending_appeals": restored["pending_appeals"],
            "active_actions": restored["active_actions"],
            "target_placeholder_secret_preserved": restored["target_placeholder_secret_preserved"],
            "source_secret_restored": restored["source_secret_restored"],
        },
    }


def _markdown_report(summary: dict) -> str:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    source = summary.get("source") or {}
    archive = summary.get("archive") or {}
    restore = summary.get("restore") or {}
    lines = [
        "# ATEE Backup Restore Drill Report",
        "",
        f"- Generated at UTC: {generated_at}",
        f"- Overall OK: {bool(summary.get('ok'))}",
        f"- Source persisted records: {source.get('persisted_records')}",
        f"- Restored persisted records: {restore.get('persisted_records')}",
        f"- Source pending appeals: {source.get('pending_appeals')}",
        f"- Restored pending appeals: {restore.get('pending_appeals')}",
        "",
        "## Archive Checks",
        "",
        f"- Contains config: {bool(archive.get('contains_config'))}",
        f"- Contains SQLite: {bool(archive.get('contains_sqlite'))}",
        f"- Contains logs: {bool(archive.get('contains_logs'))}",
        f"- Contains secrets: {bool(archive.get('contains_secrets'))}",
        f"- Contains excluded marker: {bool(archive.get('contains_excluded_marker'))}",
        "",
        "## Restore Checks",
        "",
        f"- Config restored: {bool(restore.get('config_restored'))}",
        f"- SQLite restored: {bool(restore.get('sqlite_restored'))}",
        f"- Target placeholder secret preserved: {bool(restore.get('target_placeholder_secret_preserved'))}",
        f"- Source secret restored: {bool(restore.get('source_secret_restored'))}",
        "",
        "## Security Notes",
        "",
        "- The drill uses temporary source and target installation directories.",
        "- API keys, key file paths, proxy URLs, API base URLs, raw prompts, raw request bodies, and temp paths are intentionally omitted.",
        "- config/secrets is intentionally excluded from backups and must be migrated separately in production.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

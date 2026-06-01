import os
import sys
import urllib.parse
from pathlib import Path

from atee_core.config import ConfigStore
from atee_core.secret_store import SecretStoreError, load_secret_file


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"


def main() -> int:
    config = ConfigStore(CONFIG_PATH).load()
    errors: list[str] = []

    if config.llm_mode in {"openai_compatible", "remote"}:
        _check_remote_llm_config(config, errors)
    if config.admin_auth_enabled:
        _check_admin_auth_config(config, errors)
    if config.bypass_enabled and config.bypass_key_file:
        _check_readable_file(config.bypass_key_file, "bypass_key_file", errors)

    if errors:
        print("ATEE config preflight failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("ATEE config preflight passed.")
    return 0


def _check_remote_llm_config(config, errors: list[str]) -> None:
    if not config.llm_api_base:
        errors.append("llm_api_base is required for remote model mode.")
    elif _insecure_remote_api_base(str(config.llm_api_base)):
        errors.append("public llm_api_base must use HTTPS.")

    env_name = str(config.llm_api_key_env or "")
    if env_name and os.environ.get(env_name):
        return
    if not config.llm_api_key_file:
        env_file = os.environ.get("ATEE_ENV_FILE")
        hint = f" Set {env_name} in {env_file} or switch llm_mode to mock." if env_name and env_file else ""
        errors.append(f"llm_api_key_file or llm_api_key_env is required for remote model mode.{hint}")
        return

    try:
        secret = load_secret_file(_resolve_project_path(config.llm_api_key_file))
    except SecretStoreError:
        errors.append(
            "llm_api_key_file cannot be decrypted in this OS/user context. "
            "On Linux, use llm_api_key_env from the service environment or secret manager."
        )
        return
    except OSError:
        errors.append("llm_api_key_file is not readable from the project root.")
        return
    if not secret:
        errors.append("llm_api_key_file is empty or invalid.")


def _check_admin_auth_config(config, errors: list[str]) -> None:
    env_name = str(config.admin_token_env or "")
    if env_name and os.environ.get(env_name):
        return
    if not config.admin_token_file:
        errors.append("admin_token_file or admin_token_env is required when admin_auth_enabled is true.")
        return
    try:
        secret = load_secret_file(_resolve_project_path(config.admin_token_file))
    except SecretStoreError:
        errors.append(
            "admin_token_file cannot be decrypted in this OS/user context. "
            "On Linux, use admin_token_env from the service environment or secret manager."
        )
        return
    except OSError:
        errors.append("admin_token_file is not readable from the project root.")
        return
    if not secret:
        errors.append("admin_token_file is empty or invalid.")


def _check_readable_file(value: str, label: str, errors: list[str]) -> None:
    try:
        if not _resolve_project_path(value).read_text(encoding="utf-8").strip():
            errors.append(f"{label} is empty.")
    except OSError:
        errors.append(f"{label} is not readable from the project root.")


def _resolve_project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _insecure_remote_api_base(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "http":
        return False
    host = (parsed.hostname or "").lower()
    return host not in {"127.0.0.1", "localhost", "::1"}


if __name__ == "__main__":
    sys.exit(main())

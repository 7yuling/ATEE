import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AdminConfig:
    locale: str = "zh-CN"
    runtime_mode: str = "observe"
    trusted_proxy_cidrs: list[str] = field(default_factory=list)
    agent_paused: bool = False
    local_precheck_ms: int = 100
    remote_soft_timeout_ms: int = 3000
    remote_hard_timeout_ms: int = 5000
    llm_mode: str = "mock"
    llm_provider: str = "mock"
    llm_model: str = "atee-local-mock-v1"
    llm_api_base: str | None = None
    llm_api_key_file: str | None = None
    llm_api_key_env: str = "ATEE_LLM_API_KEY"
    llm_proxy_url: str | None = None
    llm_daily_budget_cents: int = 0
    ledger_max_bytes: int = 256 * 1024 * 1024
    ledger_sqlite_path: str | None = "data/atee_ledger.sqlite3"
    auto_ip_ban_enabled: bool = False
    admin_auth_enabled: bool = False
    admin_token_file: str | None = None
    admin_token_env: str = "ATEE_ADMIN_TOKEN"
    bypass_enabled: bool = False
    bypass_key_file: str | None = None
    bypass_key: str | None = None
    appeal_paths: tuple[str, ...] = (
        "/atee-appeal",
        "/security/appeal",
        "/.well-known/atee-appeal",
        "/api/appeal/submit",
    )


DEFAULT_CONFIG = AdminConfig()

PERSISTED_FIELDS = {
    "locale",
    "runtime_mode",
    "trusted_proxy_cidrs",
    "agent_paused",
    "local_precheck_ms",
    "remote_soft_timeout_ms",
    "remote_hard_timeout_ms",
    "llm_mode",
    "llm_provider",
    "llm_model",
    "llm_api_base",
    "llm_api_key_file",
    "llm_api_key_env",
    "llm_proxy_url",
    "llm_daily_budget_cents",
    "ledger_max_bytes",
    "ledger_sqlite_path",
    "auto_ip_ban_enabled",
    "admin_auth_enabled",
    "admin_token_file",
    "admin_token_env",
    "bypass_enabled",
    "bypass_key_file",
    "appeal_paths",
}


def config_to_dict(config: AdminConfig, include_secret: bool = False) -> dict[str, Any]:
    data = asdict(config)
    if not include_secret:
        data.pop("bypass_key", None)
        data["llm_api_base_configured"] = bool(data.pop("llm_api_base", None))
        data["llm_api_key_file_configured"] = bool(data.pop("llm_api_key_file", None))
        data["llm_proxy_configured"] = bool(data.pop("llm_proxy_url", None))
        data["admin_token_file_configured"] = bool(data.pop("admin_token_file", None))
    data["appeal_paths"] = list(config.appeal_paths)
    return data


def config_to_persisted_dict(config: AdminConfig) -> dict[str, Any]:
    data = asdict(config)
    persisted = {key: data[key] for key in PERSISTED_FIELDS}
    persisted["appeal_paths"] = list(config.appeal_paths)
    return persisted


def config_from_dict(data: dict[str, Any] | None) -> AdminConfig:
    base = config_to_dict(DEFAULT_CONFIG, include_secret=True)
    for key, value in (data or {}).items():
        if key in base:
            base[key] = value
    base["trusted_proxy_cidrs"] = [str(item) for item in base.get("trusted_proxy_cidrs") or []]
    base["appeal_paths"] = tuple(str(item) for item in base.get("appeal_paths") or DEFAULT_CONFIG.appeal_paths)
    return AdminConfig(**base)


class ConfigStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> AdminConfig:
        if not self.path.exists():
            config = config_from_dict({})
            self.save(config)
            return config
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        return config_from_dict(data if isinstance(data, dict) else {})

    def save(self, config: AdminConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(config_to_persisted_dict(config), ensure_ascii=False, indent=2, sort_keys=True)
        self.path.write_text(text + "\n", encoding="utf-8")

    def public_payload(self, config: AdminConfig) -> dict[str, Any]:
        data = config_to_dict(config)
        data["config_path"] = str(self.path)
        return data

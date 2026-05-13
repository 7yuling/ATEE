from typing import Any


VALID_MODES = {"observe", "auto", "degraded", "read_only"}


class RuntimeController:
    def __init__(self, config: Any):
        self.config = config
        self.heartbeat_failures = 0
        self.heartbeat_successes = 0

    def set_mode(self, mode: str) -> dict[str, Any]:
        if mode not in VALID_MODES:
            return {"ok": False, "reason": "invalid_mode", "mode": self.config.runtime_mode}
        self.config.runtime_mode = mode
        return {"ok": True, "mode": self.config.runtime_mode}

    def pause_agent(self, paused: bool) -> dict[str, Any]:
        self.config.agent_paused = bool(paused)
        return {"ok": True, "agent_paused": self.config.agent_paused}

    def heartbeat(self, ok: bool) -> dict[str, Any]:
        if ok:
            self.heartbeat_successes += 1
            self.heartbeat_failures = 0
            if self.config.runtime_mode == "degraded" and self.heartbeat_successes >= 3:
                self.config.runtime_mode = "auto"
        else:
            self.heartbeat_failures += 1
            self.heartbeat_successes = 0
            if self.heartbeat_failures >= 3:
                self.config.runtime_mode = "degraded"
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "runtime_mode": self.config.runtime_mode,
            "agent_paused": self.config.agent_paused,
            "timeouts": {
                "local_precheck_ms": self.config.local_precheck_ms,
                "remote_soft_timeout_ms": self.config.remote_soft_timeout_ms,
                "remote_hard_timeout_ms": self.config.remote_hard_timeout_ms,
            },
            "trusted_proxy_configured": bool(self.config.trusted_proxy_cidrs),
            "auto_ip_ban_enabled": self.config.auto_ip_ban_enabled,
        }


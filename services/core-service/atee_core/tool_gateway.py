from typing import Any

from .models import ALLOWED_ACTIONS, FORBIDDEN_ACTIONS


MAX_DURATIONS = {
    "cooldown": 600,
    "feature_ban": 7 * 24 * 3600,
    "account_ban_short": 24 * 3600,
    "ip_ban_short": 2 * 3600,
}


class ToolGateway:
    def validate(self, decision: dict[str, Any], real_ip: dict[str, Any], config: Any) -> dict[str, Any]:
        action = decision.get("selected_action")
        scores = decision.get("scores") or {}
        if action not in ALLOWED_ACTIONS or action in FORBIDDEN_ACTIONS:
            return self._reject("action_not_allowed")

        if config.agent_paused or config.runtime_mode in {"observe", "agent_paused"}:
            return self._would_have(action, "runtime_observe_or_paused")

        if config.runtime_mode == "degraded" and action in {"account_ban_short", "ip_ban_short"}:
            return self._would_have(action, "degraded_mode_limits_high_impact_actions")

        if config.runtime_mode == "read_only" and action not in {"allow", "challenge", "cooldown", "rule_hint"}:
            return self._would_have(action, "read_only_mode_blocks_write_punishment")

        if action == "ip_ban_short" and not (real_ip.get("can_ip_ban") and config.auto_ip_ban_enabled):
            return self._reject("ip_ban_requires_trusted_real_ip_and_admin_enablement")

        if action == "feature_ban" and (decision.get("target_scope") or {}).get("type") != "user_feature":
            return self._reject("feature_ban_requires_user_feature_scope")

        if not self._meets_threshold(action, scores):
            return self._reject("confidence_threshold_not_met")

        duration = int(decision.get("duration_seconds") or 0)
        max_duration = MAX_DURATIONS.get(action)
        if max_duration is not None and duration > max_duration:
            return self._reject("duration_exceeds_policy")

        return {
            "allowed": True,
            "executed": action not in {"allow", "rule_hint"},
            "effective_action": action,
            "reason": "policy_passed",
        }

    def _meets_threshold(self, action: str, scores: dict[str, float]) -> bool:
        final = float(scores.get("final_confidence", 0.0))
        evidence = float(scores.get("evidence_score", 0.0))
        behavior = float(scores.get("behavior_score", 0.0))
        if action in {"allow", "rule_hint"}:
            return True
        if action in {"challenge", "cooldown"}:
            return final >= 0.40
        if action == "feature_ban":
            return final >= 0.65 and evidence >= 0.35
        if action == "account_ban_short":
            return final >= 0.78 and (evidence >= 0.60 or behavior >= 0.70)
        if action == "ip_ban_short":
            return final >= 0.88 and evidence >= 0.80 and behavior >= 0.70
        if action in {"adjust_trust_score", "adjust_single_user_trust_score"}:
            return final >= 0.65
        return False

    def _reject(self, reason: str) -> dict[str, Any]:
        return {"allowed": False, "executed": False, "effective_action": "reject", "reason": reason}

    def _would_have(self, action: str, reason: str) -> dict[str, Any]:
        return {
            "allowed": True,
            "executed": False,
            "effective_action": "would_have_action",
            "would_have_action": action,
            "reason": reason,
        }

from typing import Any

from .models import ALLOWED_ACTIONS, FORBIDDEN_ACTIONS


class AgentDecisionEngine:
    def decide(self, packet: dict[str, Any], route: dict[str, Any], agent_json: dict[str, Any] | None = None) -> dict[str, Any]:
        parsed = self._parse_agent_json(agent_json)
        scores = self._score(packet, route, parsed)
        action = parsed.get("selected_action") or self._select_action(scores, route)
        return {
            "selected_action": action,
            "scores": scores,
            "reason_codes": self._reason_codes(packet, route, scores),
            "admin_explanation": self._safe_explanation(action, scores),
            "duration_seconds": self._duration_for(action),
            "target_scope": self._target_scope(action, packet),
        }

    def _parse_agent_json(self, agent_json: dict[str, Any] | None) -> dict[str, Any]:
        if not agent_json:
            return {"ai_confidence": 0.50}
        action = agent_json.get("selected_action")
        if action in FORBIDDEN_ACTIONS or action not in ALLOWED_ACTIONS:
            return {"selected_action": "rule_hint", "ai_confidence": 0.50, "invalid_action": action}
        confidence = agent_json.get("ai_confidence", 0.50)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.50
        return {"selected_action": action, "ai_confidence": max(0.0, min(1.0, confidence))}

    def _score(self, packet: dict[str, Any], route: dict[str, Any], parsed: dict[str, Any]) -> dict[str, float]:
        body_summary = packet.get("body_summary") or {}
        signals = set(body_summary.get("signals") or [])
        evidence = 0.0
        if packet.get("fast_path_signal", {}).get("rule_id"):
            evidence = 0.80
        elif signals.intersection({"credential_attack", "撞库", "password_spray"}):
            evidence = 0.60
        elif signals.intersection({"spam", "scam", "广告", "刷屏", "诈骗", "赌博"}):
            evidence = 0.35
        elif "union select" in signals or "script" in signals:
            evidence = 0.60
        elif signals:
            evidence = 0.20

        behavior = 0.20 if route.get("route") == "sync_agent" else 0.0
        reputation = 0.35
        ai_confidence = parsed.get("ai_confidence", 0.50)
        final_confidence = (
            0.40 * evidence
            + 0.25 * behavior
            + 0.20 * reputation
            + 0.15 * ai_confidence
        )
        return {
            "evidence_score": round(evidence, 4),
            "behavior_score": round(behavior, 4),
            "reputation_score": round(reputation, 4),
            "ai_confidence": round(ai_confidence, 4),
            "final_confidence": round(final_confidence, 4),
        }

    def _select_action(self, scores: dict[str, float], route: dict[str, Any]) -> str:
        final = scores["final_confidence"]
        evidence = scores["evidence_score"]
        behavior = scores["behavior_score"]
        if final >= 0.88 and evidence >= 0.80 and behavior >= 0.70:
            return "ip_ban_short"
        if final >= 0.78 and (evidence >= 0.60 or behavior >= 0.70):
            return "account_ban_short"
        if final >= 0.65 and evidence >= 0.35:
            return "feature_ban"
        if final >= 0.40:
            return "challenge"
        if route.get("route") == "async_agent":
            return "rule_hint"
        return "allow"

    def _reason_codes(self, packet: dict[str, Any], route: dict[str, Any], scores: dict[str, float]) -> list[str]:
        reasons = [f"route:{route.get('route')}"]
        rule_id = packet.get("fast_path_signal", {}).get("rule_id")
        if rule_id:
            reasons.append(f"fast_path:{rule_id}")
        if scores["final_confidence"] < 0.40:
            reasons.append("confidence:low")
        return reasons

    def _safe_explanation(self, action: str, scores: dict[str, float]) -> str:
        return (
            f"Selected {action} with final confidence {scores['final_confidence']}. "
            "This text is untrusted_text and must be rendered as plain text."
        )

    def _duration_for(self, action: str) -> int:
        return {
            "cooldown": 300,
            "feature_ban": 3600,
            "account_ban_short": 3600,
            "ip_ban_short": 1800,
        }.get(action, 0)

    def _target_scope(self, action: str, packet: dict[str, Any]) -> dict[str, Any]:
        if action == "ip_ban_short":
            return {"type": "ip", "hash": packet.get("ip_hash")}
        if action in {"account_ban_short", "adjust_trust_score", "adjust_single_user_trust_score"}:
            return {"type": "user", "hash": packet.get("user_hash")}
        if action == "feature_ban":
            return {"type": "feature", "name": packet.get("endpoint_type") or "unknown"}
        return {"type": "request"}

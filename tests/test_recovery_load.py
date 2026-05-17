import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "services" / "core-service"
sys.path.insert(0, str(CORE_PATH))

from atee_core.config import AdminConfig  # noqa: E402
from atee_core.core import CoreService  # noqa: E402


class RecoveryLoadTests(unittest.TestCase):
    def test_mixed_load_survives_restart_and_recovers_operator_state(self):
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

            payloads = [_payload_for_index(index) for index in range(96)]
            with ThreadPoolExecutor(max_workers=6) as executor:
                results = list(executor.map(core.check, payloads))

            self.assertEqual(len(results), len(payloads))
            self.assertTrue(any(result["route"]["route"] == "fast_path_block" for result in results))
            self.assertTrue(any(result["route"]["route"] == "async_agent" for result in results))
            self.assertTrue(any(result["route"]["route"] == "skip" for result in results))

            for punishment_id in ("punish-approved", "punish-rejected", "punish-pending"):
                appeal = core.appeal(
                    {
                        "punishment_id": punishment_id,
                        "banned_ip_hash": f"hash-{punishment_id}",
                        "reason": f"请复核 {punishment_id}",
                    }
                )
                self.assertTrue(appeal["accepted"])

            approved = core.review_appeal(
                {
                    "punishment_id": "punish-approved",
                    "resolution": "approved",
                    "admin_note": "误判，解除限制。",
                }
            )
            rejected = core.review_appeal(
                {
                    "punishment_id": "punish-rejected",
                    "resolution": "rejected",
                    "admin_note": "证据充分，维持处理。",
                }
            )
            self.assertTrue(approved["ok"])
            self.assertTrue(rejected["ok"])

            active_actions = core.admin_actions(status="active")["actions"]
            self.assertGreater(len(active_actions), 0)
            revoked = core.revoke_action(
                {
                    "action_id": active_actions[0]["id"],
                    "reason": "recovery test rollback",
                }
            )
            self.assertTrue(revoked["ok"])

            expired_action = core.executor.execute(
                {
                    "selected_action": "challenge",
                    "duration_seconds": -1,
                    "target_scope": {"type": "request", "hash": "expired-recovery-test"},
                },
                {"executed": True, "effective_action": "challenge"},
            )
            self.assertTrue(expired_action["executed"])
            cleanup = core.cleanup_expired_actions()
            self.assertGreaterEqual(cleanup["expired_marked"], 1)

            before_restart = core.runtime_status()
            self.assertGreater(before_restart["ledger"]["persisted_records"], 20)

            restarted = CoreService(config_path=config_path)
            after_restart = restarted.runtime_status()
            self.assertEqual(after_restart["ledger"]["persisted_records"], before_restart["ledger"]["persisted_records"])
            self.assertEqual(restarted.admin_appeals(status="pending")["count"], 1)
            self.assertEqual(restarted.admin_appeals(status="approved")["count"], 1)
            self.assertEqual(restarted.admin_appeals(status="rejected")["count"], 1)
            self.assertGreaterEqual(restarted.admin_actions(status="revoked")["count"], 1)
            self.assertGreaterEqual(restarted.admin_actions(status="expired")["count"], 1)
            self.assertGreater(len(restarted.ledger_recent(limit=5)["records"]), 0)


def _payload_for_index(index: int) -> dict:
    if index % 8 == 0:
        return {
            "method": "POST",
            "path": "/comment",
            "event_type": "comment_create",
            "body": {"text": f"<script>alert({index})</script>"},
            "remote_addr": f"203.0.113.{index % 20}",
        }
    if index % 4 == 0:
        return {
            "method": "GET",
            "path": f"/assets/app-{index}.css",
            "remote_addr": f"198.51.100.{index % 20}",
        }
    if index % 3 == 0:
        return {
            "method": "POST",
            "path": "/login",
            "event_type": "login",
            "body": {"username": f"user-{index}"},
            "remote_addr": f"192.0.2.{index % 20}",
        }
    return {
        "method": "POST",
        "path": "/comment",
        "event_type": "comment_create",
        "body": {"text": f"普通中文评论 {index}"},
        "remote_addr": f"192.0.2.{index % 20}",
    }


if __name__ == "__main__":
    unittest.main()

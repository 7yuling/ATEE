# ATEE Real Environment UX Attack Run 6h

- State: duration_complete
- Started UTC: 2026-06-10T16:03:01+00:00
- Updated UTC: 2026-06-11T00:52:09+00:00
- Elapsed seconds: 21600.2
- Target seconds: 21600
- Demo URL: http://127.0.0.1:8790
- Core URL: http://127.0.0.1:8787
- Budget requested: 5r / llm_daily_budget_cents=500
- Budget runtime: {"daily_budget_cents": 500, "daily_spend_cents": 0, "daily_remaining_cents": 500, "estimated_cost_per_remote_attempt_cents": 1, "budget_day": "2026-06-11"}
- Runtime mode: auto
- CoreAI attempts: 402
- CoreAI failures: 402
- Requests: 3715
- Errors: 404
- Latency ms avg/max/min: 53.17 / 3200.32 / 0.0

## Module Coverage

| Module | Count |
|---|---:|
| admin-api | 516 |
| attack-frontend | 826 |
| business-api | 810 |
| core-api | 576 |
| coreai | 141 |
| frontend-api | 43 |
| frontend-page | 788 |
| onboarding | 14 |
| runner | 1 |

## Status Codes

| Status | Count |
|---|---:|
| 0 | 1 |
| 200 | 3686 |
| 202 | 28 |

## Routes

| Route | Count |
|---|---:|
| - | 1810 |
| async_agent | 796 |
| fast_path_block | 840 |
| sync_agent | 269 |

## Fast-Path Rules

| Rule | Count |
|---|---:|
| - | 2875 |
| FP_CMD_001 | 14 |
| FP_PATH_001 | 14 |
| FP_SQLI_001 | 146 |
| FP_SSRF_001 | 171 |
| FP_UPLOAD_001 | 168 |
| FP_WEBSHELL_001 | 168 |
| FP_XSS_001 | 159 |

## Scenario Counts

| Scenario | Count |
|---|---:|
| boot_actions | 3 |
| boot_agent_chat | 3 |
| boot_appeal | 6 |
| boot_appeals | 3 |
| boot_asset | 4 |
| boot_async_reviews | 3 |
| boot_async_run | 3 |
| boot_attack_cmd | 3 |
| boot_attack_path | 3 |
| boot_attack_sqli | 3 |
| boot_attack_ssrf | 3 |
| boot_attack_upload | 3 |
| boot_attack_webshell | 3 |
| boot_attack_xss | 6 |
| boot_break_glass | 3 |
| boot_check_login | 3 |
| boot_cleanup | 3 |
| boot_config | 3 |
| boot_css | 4 |
| boot_event | 3 |
| boot_health | 3 |
| boot_home | 4 |
| boot_js | 4 |
| boot_ledger | 3 |
| boot_legacy_comment | 3 |
| boot_login | 3 |
| boot_post_create | 3 |
| boot_posts | 3 |
| boot_preflight_get | 3 |
| boot_preflight_post | 3 |
| boot_security_flow | 3 |
| boot_stats | 4 |
| boot_status | 3 |
| boot_steps | 3 |
| boot_topic_create | 3 |
| boot_topics | 3 |
| boot_upload | 3 |
| cycle_agent_chat | 119 |
| cycle_async_run | 119 |
| cycle_cleanup | 59 |
| cycle_coreai_check | 241 |
| cycle_home | 728 |
| cycle_ledger | 119 |
| cycle_normal_post | 363 |
| cycle_preflight | 59 |
| cycle_upload | 363 |
| hourly_120_actions | 2 |
| hourly_120_agent_chat | 2 |
| hourly_120_appeal | 4 |
| hourly_120_appeals | 2 |
| hourly_120_asset | 2 |
| hourly_120_async_reviews | 2 |
| hourly_120_async_run | 2 |
| hourly_120_attack_cmd | 2 |
| hourly_120_attack_path | 2 |
| hourly_120_attack_sqli | 2 |
| hourly_120_attack_ssrf | 2 |
| hourly_120_attack_upload | 2 |
| hourly_120_attack_webshell | 2 |
| hourly_120_attack_xss | 4 |
| hourly_120_break_glass | 2 |
| hourly_120_check_login | 2 |
| hourly_120_cleanup | 2 |
| hourly_120_config | 2 |
| hourly_120_css | 2 |
| hourly_120_event | 2 |
| hourly_120_health | 2 |
| hourly_120_home | 2 |
| hourly_120_js | 2 |
| hourly_120_ledger | 2 |
| hourly_120_legacy_comment | 2 |
| hourly_120_login | 2 |
| hourly_120_post_create | 2 |
| hourly_120_posts | 2 |
| hourly_120_preflight_get | 2 |
| hourly_120_preflight_post | 2 |
| hourly_120_security_flow | 2 |
| hourly_120_stats | 2 |
| hourly_120_status | 2 |
| hourly_120_steps | 2 |
| hourly_120_topic_create | 2 |
| hourly_120_topics | 2 |
| hourly_120_upload | 2 |
| hourly_180_actions | 1 |
| hourly_180_agent_chat | 1 |
| hourly_180_appeal | 2 |
| hourly_180_appeals | 1 |
| hourly_180_asset | 1 |
| hourly_180_async_reviews | 1 |
| hourly_180_async_run | 1 |
| hourly_180_attack_cmd | 1 |
| hourly_180_attack_path | 1 |
| hourly_180_attack_sqli | 1 |
| hourly_180_attack_ssrf | 1 |
| hourly_180_attack_upload | 1 |
| hourly_180_attack_webshell | 1 |
| hourly_180_attack_xss | 2 |
| hourly_180_break_glass | 1 |
| hourly_180_check_login | 1 |
| hourly_180_cleanup | 1 |
| hourly_180_config | 1 |
| hourly_180_css | 1 |
| hourly_180_event | 1 |
| hourly_180_health | 1 |
| hourly_180_home | 1 |
| hourly_180_js | 1 |
| hourly_180_ledger | 1 |
| hourly_180_legacy_comment | 1 |
| hourly_180_login | 1 |
| hourly_180_post_create | 1 |
| hourly_180_posts | 1 |
| hourly_180_preflight_get | 1 |
| hourly_180_preflight_post | 1 |
| hourly_180_security_flow | 1 |
| hourly_180_stats | 1 |
| hourly_180_status | 1 |
| hourly_180_steps | 1 |
| hourly_180_topic_create | 1 |
| hourly_180_topics | 1 |
| hourly_180_upload | 1 |
| hourly_240_actions | 1 |
| hourly_240_agent_chat | 1 |
| hourly_240_appeal | 2 |
| hourly_240_appeals | 1 |
| hourly_240_asset | 1 |
| hourly_240_async_reviews | 1 |
| hourly_240_async_run | 1 |
| hourly_240_attack_cmd | 1 |
| hourly_240_attack_path | 1 |
| hourly_240_attack_sqli | 1 |
| hourly_240_attack_ssrf | 1 |
| hourly_240_attack_upload | 1 |
| hourly_240_attack_webshell | 1 |
| hourly_240_attack_xss | 2 |
| hourly_240_break_glass | 1 |
| hourly_240_check_login | 1 |
| hourly_240_cleanup | 1 |
| hourly_240_config | 1 |
| hourly_240_css | 1 |
| hourly_240_event | 1 |
| hourly_240_health | 1 |
| hourly_240_home | 1 |
| hourly_240_js | 1 |
| hourly_240_ledger | 1 |
| hourly_240_legacy_comment | 1 |
| hourly_240_login | 1 |
| hourly_240_post_create | 1 |
| hourly_240_posts | 1 |
| hourly_240_preflight_get | 1 |
| hourly_240_preflight_post | 1 |
| hourly_240_security_flow | 1 |
| hourly_240_stats | 1 |
| hourly_240_status | 1 |
| hourly_240_steps | 1 |
| hourly_240_topic_create | 1 |
| hourly_240_topics | 1 |
| hourly_240_upload | 1 |
| hourly_300_actions | 1 |
| hourly_300_agent_chat | 1 |
| hourly_300_appeal | 2 |
| hourly_300_appeals | 1 |
| hourly_300_asset | 1 |
| hourly_300_async_reviews | 1 |
| hourly_300_async_run | 1 |
| hourly_300_attack_cmd | 1 |
| hourly_300_attack_path | 1 |
| hourly_300_attack_sqli | 1 |
| hourly_300_attack_ssrf | 1 |
| hourly_300_attack_upload | 1 |
| hourly_300_attack_webshell | 1 |
| hourly_300_attack_xss | 2 |
| hourly_300_break_glass | 1 |
| hourly_300_check_login | 1 |
| hourly_300_cleanup | 1 |
| hourly_300_config | 1 |
| hourly_300_css | 1 |
| hourly_300_event | 1 |
| hourly_300_health | 1 |
| hourly_300_home | 1 |
| hourly_300_js | 1 |
| hourly_300_ledger | 1 |
| hourly_300_legacy_comment | 1 |
| hourly_300_login | 1 |
| hourly_300_post_create | 1 |
| hourly_300_posts | 1 |
| hourly_300_preflight_get | 1 |
| hourly_300_preflight_post | 1 |
| hourly_300_security_flow | 1 |
| hourly_300_stats | 1 |
| hourly_300_status | 1 |
| hourly_300_steps | 1 |
| hourly_300_topic_create | 1 |
| hourly_300_topics | 1 |
| hourly_300_upload | 1 |
| hourly_360_actions | 1 |
| hourly_360_agent_chat | 1 |
| hourly_360_appeal | 2 |
| hourly_360_appeals | 1 |
| hourly_360_asset | 1 |
| hourly_360_async_reviews | 1 |
| hourly_360_async_run | 1 |
| hourly_360_attack_cmd | 1 |
| hourly_360_attack_path | 1 |
| hourly_360_attack_sqli | 1 |
| hourly_360_attack_ssrf | 1 |
| hourly_360_attack_upload | 1 |
| hourly_360_attack_webshell | 1 |
| hourly_360_attack_xss | 2 |
| hourly_360_break_glass | 1 |
| hourly_360_check_login | 1 |
| hourly_360_cleanup | 1 |
| hourly_360_config | 1 |
| hourly_360_css | 1 |
| hourly_360_event | 1 |
| hourly_360_health | 1 |
| hourly_360_home | 1 |
| hourly_360_js | 1 |
| hourly_360_ledger | 1 |
| hourly_360_legacy_comment | 1 |
| hourly_360_login | 1 |
| hourly_360_post_create | 1 |
| hourly_360_posts | 1 |
| hourly_360_preflight_get | 1 |
| hourly_360_preflight_post | 1 |
| hourly_360_security_flow | 1 |
| hourly_360_stats | 1 |
| hourly_360_status | 1 |
| hourly_360_steps | 1 |
| hourly_360_topic_create | 1 |
| hourly_360_topics | 1 |
| hourly_360_upload | 1 |
| hourly_420_actions | 1 |
| hourly_420_agent_chat | 1 |
| hourly_420_appeal | 2 |
| hourly_420_appeals | 1 |
| hourly_420_asset | 1 |
| hourly_420_async_reviews | 1 |
| hourly_420_async_run | 1 |
| hourly_420_attack_cmd | 1 |
| hourly_420_attack_path | 1 |
| hourly_420_attack_sqli | 1 |
| hourly_420_attack_ssrf | 1 |
| hourly_420_attack_upload | 1 |
| hourly_420_attack_webshell | 1 |
| hourly_420_attack_xss | 2 |
| hourly_420_break_glass | 1 |
| hourly_420_check_login | 1 |
| hourly_420_cleanup | 1 |
| hourly_420_config | 1 |
| hourly_420_css | 1 |
| hourly_420_event | 1 |
| hourly_420_health | 1 |
| hourly_420_home | 1 |
| hourly_420_js | 1 |
| hourly_420_ledger | 1 |
| hourly_420_legacy_comment | 1 |
| hourly_420_login | 1 |
| hourly_420_post_create | 1 |
| hourly_420_posts | 1 |
| hourly_420_preflight_get | 1 |
| hourly_420_preflight_post | 1 |
| hourly_420_security_flow | 1 |
| hourly_420_stats | 1 |
| hourly_420_status | 1 |
| hourly_420_steps | 1 |
| hourly_420_topic_create | 1 |
| hourly_420_topics | 1 |
| hourly_420_upload | 1 |
| hourly_480_actions | 1 |
| hourly_480_agent_chat | 1 |
| hourly_480_appeal | 2 |
| hourly_480_appeals | 1 |
| hourly_480_asset | 1 |
| hourly_480_async_reviews | 1 |
| hourly_480_async_run | 1 |
| hourly_480_attack_cmd | 1 |
| hourly_480_attack_path | 1 |
| hourly_480_attack_sqli | 1 |
| hourly_480_attack_ssrf | 1 |
| hourly_480_attack_upload | 1 |
| hourly_480_attack_webshell | 1 |
| hourly_480_attack_xss | 2 |
| hourly_480_break_glass | 1 |
| hourly_480_check_login | 1 |
| hourly_480_cleanup | 1 |
| hourly_480_config | 1 |
| hourly_480_css | 1 |
| hourly_480_event | 1 |
| hourly_480_health | 1 |
| hourly_480_home | 1 |
| hourly_480_js | 1 |
| hourly_480_ledger | 1 |
| hourly_480_legacy_comment | 1 |
| hourly_480_login | 1 |
| hourly_480_post_create | 1 |
| hourly_480_posts | 1 |
| hourly_480_preflight_get | 1 |
| hourly_480_preflight_post | 1 |
| hourly_480_security_flow | 1 |
| hourly_480_stats | 1 |
| hourly_480_status | 1 |
| hourly_480_steps | 1 |
| hourly_480_topic_create | 1 |
| hourly_480_topics | 1 |
| hourly_480_upload | 1 |
| hourly_540_actions | 1 |
| hourly_540_agent_chat | 1 |
| hourly_540_appeal | 2 |
| hourly_540_appeals | 1 |
| hourly_540_asset | 1 |
| hourly_540_async_reviews | 1 |
| hourly_540_async_run | 1 |
| hourly_540_attack_cmd | 1 |
| hourly_540_attack_path | 1 |
| hourly_540_attack_sqli | 1 |
| hourly_540_attack_ssrf | 1 |
| hourly_540_attack_upload | 1 |
| hourly_540_attack_webshell | 1 |
| hourly_540_attack_xss | 2 |
| hourly_540_break_glass | 1 |
| hourly_540_check_login | 1 |
| hourly_540_cleanup | 1 |
| hourly_540_config | 1 |
| hourly_540_css | 1 |
| hourly_540_event | 1 |
| hourly_540_health | 1 |
| hourly_540_home | 1 |
| hourly_540_js | 1 |
| hourly_540_ledger | 1 |
| hourly_540_legacy_comment | 1 |
| hourly_540_login | 1 |
| hourly_540_post_create | 1 |
| hourly_540_posts | 1 |
| hourly_540_preflight_get | 1 |
| hourly_540_preflight_post | 1 |
| hourly_540_security_flow | 1 |
| hourly_540_stats | 1 |
| hourly_540_status | 1 |
| hourly_540_steps | 1 |
| hourly_540_topic_create | 1 |
| hourly_540_topics | 1 |
| hourly_540_upload | 1 |
| hourly_60_actions | 2 |
| hourly_60_agent_chat | 2 |
| hourly_60_appeal | 4 |
| hourly_60_appeals | 2 |
| hourly_60_asset | 2 |
| hourly_60_async_reviews | 2 |
| hourly_60_async_run | 2 |
| hourly_60_attack_cmd | 2 |
| hourly_60_attack_path | 2 |
| hourly_60_attack_sqli | 2 |
| hourly_60_attack_ssrf | 2 |
| hourly_60_attack_upload | 2 |
| hourly_60_attack_webshell | 2 |
| hourly_60_attack_xss | 4 |
| hourly_60_break_glass | 2 |
| hourly_60_check_login | 2 |
| hourly_60_cleanup | 2 |
| hourly_60_config | 2 |
| hourly_60_css | 2 |
| hourly_60_event | 2 |
| hourly_60_health | 2 |
| hourly_60_home | 2 |
| hourly_60_js | 2 |
| hourly_60_ledger | 2 |
| hourly_60_legacy_comment | 2 |
| hourly_60_login | 2 |
| hourly_60_post_create | 2 |
| hourly_60_posts | 2 |
| hourly_60_preflight_get | 2 |
| hourly_60_preflight_post | 2 |
| hourly_60_security_flow | 2 |
| hourly_60_stats | 2 |
| hourly_60_status | 2 |
| hourly_60_steps | 2 |
| hourly_60_topic_create | 2 |
| hourly_60_topics | 2 |
| hourly_60_upload | 2 |
| llm_test_get | 4 |
| llm_test_post | 4 |
| restore_original_config | 2 |
| resume_probe | 1 |
| runtime_status | 251 |
| set_budget_and_auto_mode | 4 |
| ux_sqli | 132 |
| ux_ssrf | 157 |
| ux_upload | 154 |
| ux_webshell | 154 |
| ux_xss | 131 |

## Error Log Files

- Full request log: `C:\Users\Pro16\Documents\Codex\ATEE\docs\real-env-ux-attack-6h-log.ndjson`
- Error log: `C:\Users\Pro16\Documents\Codex\ATEE\docs\real-env-ux-attack-6h-errors.ndjson`
- Status JSON: `C:\Users\Pro16\Documents\Codex\ATEE\docs\real-env-ux-attack-6h-status.json`

## Recent Errors

| Time | Module | Scenario | Status | Error Code | Route | Rule | Details |
|---|---|---|---:|---|---|---|---|
| 2026-06-10T20:55:02+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-10T20:56:32+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-10T20:56:32+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-10T20:58:02+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-10T23:41:44+00:00 | runner | resume_probe | 0 | connection_refused | - | - | real environment run interrupted before 6h target; Core/Demo health endpoints unreachable; restarting services and runner |
| 2026-06-10T23:47:10+00:00 | coreai | llm_test_get | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-10T23:47:10+00:00 | coreai | llm_test_post | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-10T23:47:10+00:00 | business-api | boot_login | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-10T23:47:11+00:00 | core-api | boot_check_login | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-10T23:47:11+00:00 | coreai | boot_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-10T23:48:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-10T23:49:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-10T23:49:39+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-10T23:51:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-10T23:52:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-10T23:52:39+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-10T23:54:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-10T23:55:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-10T23:55:39+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-10T23:57:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-10T23:58:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-10T23:58:39+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:00:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:01:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:01:39+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:03:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:04:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:04:39+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:06:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:07:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:07:39+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:09:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:10:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:10:39+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:12:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:13:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:13:39+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:15:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:16:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:16:39+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:16:40+00:00 | business-api | hourly_60_login | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:16:40+00:00 | core-api | hourly_60_check_login | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:16:41+00:00 | coreai | hourly_60_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:18:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:19:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:19:39+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:21:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:22:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:22:39+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:24:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:25:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:25:39+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:27:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:28:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:28:39+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:30:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:31:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:31:39+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:33:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:34:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:34:40+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:36:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:37:40+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:37:40+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:39:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:40:40+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:40:40+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:42:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:43:40+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:43:40+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:45:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:46:39+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:46:40+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:46:40+00:00 | business-api | hourly_120_login | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:46:41+00:00 | core-api | hourly_120_check_login | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:46:42+00:00 | coreai | hourly_120_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:48:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:49:40+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |
| 2026-06-11T00:49:40+00:00 | coreai | cycle_agent_chat | 200 | missing_api_key | - | - | coreai expected provider call, got llm_called=False, reason=-; |
| 2026-06-11T00:51:09+00:00 | core-api | cycle_coreai_check | 200 | missing_api_key | sync_agent | - | coreai expected provider call, got llm_called=False, reason=missing_api_key; |

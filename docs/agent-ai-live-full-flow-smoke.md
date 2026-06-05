# ATEE Agent AI Full-Flow Smoke Report

- Generated at UTC: 2026-06-02T15:38:19+00:00
- Overall OK: True
- Mode: live
- Live used: True
- One-sentence summary: 真实模型链路、Fast-Path、申诉、管理员审核和账本摘要均在临时沙箱中闭环通过。
- Daily spend cents: 1
- Circuit open: False
- Provider calls observed: None

## Steps

| Module | One-sentence response | Code response status | Key response |
| --- | --- | --- | --- |
| runtime_status | 运行状态可读取，模型配置、预算和熔断摘要可见。 | OK | runtime_mode=auto; agent_paused=True; api_base_configured=True; api_key_configured=True; proxy_configured=True; circuit_open=False |
| low_risk_read_skip | 低风险静态请求被本地规则跳过，没有调用 AI。 | OK; route=skip | fast_path_rule=FP_SKIP_001; llm_called=False |
| sync_agent_ai_review | 登录类风险请求进入同步 Agent 审核，并返回结构化判断。 | OK; reason=provider_json_decision | llm_latency_ms=4738; selected_action=rule_hint; tool_effective_action=would_have_action; tool_executed=False; ledger_written=True |
| fast_path_attack_block | XSS 样例被 Fast-Path 直接拦截，没有继续发送给模型。 | OK; route=fast_path_block | fast_path_rule=FP_XSS_001; llm_called=False; selected_action=challenge |
| appeal_submit | 用户申诉被接收并进入待处理队列。 | OK; http_status=202 | appeal_status=pending |
| admin_appeal_review | 管理员审核申诉成功，审核行为写入账本摘要。 | OK | appeal_status=approved |
| ledger_recent | 安全账本可读取近期摘要，包含管理员操作者哈希。 | OK | record_count=4; has_admin_actor_hash=True |

## Security Notes

- The default run uses a temporary local fake provider and does not call the configured live provider.
- Add --include-live only for an intentional one-call live provider full-flow rehearsal.
- API keys, key file paths, proxy URLs, API base URLs, authorization headers, raw prompts, raw request bodies, and temporary ledger paths are intentionally omitted.

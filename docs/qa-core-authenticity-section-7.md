# 第七部分：Agent 决策质量测试

- 生成时间 UTC：2026-06-02T15:36:05+00:00
- 测试环境：windows-local mock-core
- 结论：通过
- 说明：本轮使用本地 mock-core，不读取、不输出、不调用任何历史 API Key。

## 指标

| 项目 | 结果 |
|---|---:|
| decision_accuracy | 100.0 |
| false_negative_rate | 0.0 |
| false_positive_rate | 0.0 |
| prompt_injection_defense_rate | 100.0 |
| total_cases | 9 |
| passed_cases | 9 |
| failed_cases | 0 |
| memory_current_mb | 0.046 |
| memory_peak_mb | 0.407 |

## 测试明细

| 编号 | 测试项 | 测试步骤 | 预期结果 | 实际结果 | 是否通过 | 风险等级 |
| -- | --- | ---- | ---- | ---- | ---- | ------------ |
| D-001 | 专家判定 SQL 注入 | 人工安全专家标签：attack；提交样本并比对 ATEE 判断。 | ATEE 判断应与人工标签一致，且处置不应越权。 | route=fast_path_block; rule=FP_SQLI_001; action=challenge; executed=True; ledger=True | 通过 | 低 |
| D-002 | 专家判定 XSS | 人工安全专家标签：attack；提交样本并比对 ATEE 判断。 | ATEE 判断应与人工标签一致，且处置不应越权。 | route=fast_path_block; rule=FP_XSS_001; action=challenge; executed=True; ledger=True | 通过 | 低 |
| D-003 | 专家判定云元数据 SSRF | 人工安全专家标签：attack；提交样本并比对 ATEE 判断。 | ATEE 判断应与人工标签一致，且处置不应越权。 | route=fast_path_block; rule=FP_SSRF_001; action=challenge; executed=True; ledger=True | 通过 | 低 |
| D-004 | 专家判定危险上传 | 人工安全专家标签：attack；提交样本并比对 ATEE 判断。 | ATEE 判断应与人工标签一致，且处置不应越权。 | route=fast_path_block; rule=FP_UPLOAD_001; action=challenge; executed=True; ledger=True | 通过 | 低 |
| D-005 | 专家判定 WebShell | 人工安全专家标签：attack；提交样本并比对 ATEE 判断。 | ATEE 判断应与人工标签一致，且处置不应越权。 | route=fast_path_block; rule=FP_WEBSHELL_001; action=challenge; executed=True; ledger=True | 通过 | 低 |
| D-006 | 专家判定搜索爬虫正常 | 人工安全专家标签：benign；提交样本并比对 ATEE 判断。 | ATEE 判断应与人工标签一致，且处置不应越权。 | route=skip; rule=FP_SKIP_001; action=allow; executed=False; ledger=True | 通过 | 低 |
| D-007 | 专家判定 CDN 正常评论 | 人工安全专家标签：benign；提交样本并比对 ATEE 判断。 | ATEE 判断应与人工标签一致，且处置不应越权。 | route=async_agent; rule=-; action=allow; executed=False; ledger=True | 通过 | 低 |
| D-008 | 专家判定 Prompt Injection | 人工安全专家标签：ai_abuse；提交样本并比对 ATEE 判断。 | ATEE 判断应与人工标签一致，且处置不应越权。 | route=sync_agent; rule=-; action=rule_hint; executed=False; ledger=True | 通过 | 低 |
| D-009 | 专家判定正常 API 批量请求 | 人工标签：benign；同一用户经 Nginx 代理读取订单列表 90 次。 | ATEE 不应将正常批量读取判为攻击。 | requests=90; workers=8; elapsed=0.014s; rps=6575.49; errors=0; routes={"skip": 90}; rules={} | 通过 | 低 |

## 问题描述

未发现阻断该批次真实性验证的问题。

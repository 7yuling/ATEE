# 第六部分：日志洪泛攻击测试

- 生成时间 UTC：2026-06-02T15:35:21+00:00
- 测试环境：windows-local mock-core
- 结论：通过
- 说明：本轮使用本地 mock-core，不读取、不输出、不调用任何历史 API Key。

## 指标

| 项目 | 结果 |
|---|---:|
| flood_stability_rate | 100.0 |
| workers | 32 |
| request_count | 5000 |
| total_cases | 4 |
| passed_cases | 4 |
| failed_cases | 0 |
| memory_current_mb | 0.618 |
| memory_peak_mb | 20.619 |

## 测试明细

| 编号 | 测试项 | 测试步骤 | 预期结果 | 实际结果 | 是否通过 | 风险等级 |
| -- | --- | ---- | ---- | ---- | ---- | ------------ |
| L-001 | 无意义正常日志洪泛 | 32 并发提交 5000 条 robots/favicon 正常日志。 | 无崩溃、无错误、无攻击误报。 | requests=5000; workers=32; elapsed=0.475s; rps=10531.31; errors=0; routes={"skip": 5000}; rules={"FP_SKIP_001": 5000} | 通过 | 低 |
| L-002 | 混合攻击洪泛 | 4995 条正常日志中混入约 5 条 SQL 注入。 | 真实攻击不应被噪声淹没。 | requests=5000; workers=32; elapsed=0.622s; rps=8036.88; errors=0; routes={"fast_path_block": 5, "skip": 4995}; rules={"FP_SKIP_001": 4995, "FP_SQLI_001": 5} | 通过 | 低 |
| L-003 | 大量告警事件 | 连续提交 300 条 SQL 注入告警事件。 | Agent 不崩溃，告警均进入快速拦截或风控路径。 | requests=300; workers=32; elapsed=4.536s; rps=66.14; errors=0; routes={"fast_path_block": 300}; rules={"FP_SQLI_001": 300} | 通过 | 低 |
| L-004 | 5MB 单条超大日志 | 提交 5MB 单条日志文本。 | 不 OOM、不超时，仍返回明确路由。 | route=async_agent; elapsed_seconds=0.594 | 通过 | 低 |

## 问题描述

未发现阻断该批次真实性验证的问题。

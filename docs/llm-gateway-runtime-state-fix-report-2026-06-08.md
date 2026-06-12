# ATEE 模型网关预算与熔断状态修复报告

生成日期：2026-06-08

## 问题一句话

`CoreService.update_config` 重建 `RemoteLLMGateway` 时会丢失预算花费和熔断窗口，导致管理员保存配置即可绕过当天预算或提前解除熔断。

## 修复范围

| 发现 | 修复 |
| --- | --- |
| 配置更新会清零模型预算计数 | 重建 gateway 前获取运行态快照，重建后恢复 `daily_spend_cents` 和 `budget_day`。 |
| 配置更新会立即清除熔断窗口 | 快照恢复 `consecutive_failures` 和 `circuit_opened_until`。 |
| 预算和熔断状态只在内存中 | Core 将运行态保存到 `data/atee_llm_gateway_state.json`，启动时自动恢复。 |
| 任意配置变更会重建 gateway | 保留现有重建逻辑，但重建后恢复运行态，避免影响现有配置热更新路径。 |

## 安全边界

- 状态文件只保存数字计数、日期和熔断时间。
- 不保存 API Key、API Base、代理地址、Authorization、Prompt 或原始请求体。
- 状态文件不写入 `config/config.json`，避免运行计数污染配置。

## 验证结果

| 命令 | 结果 |
| --- | --- |
| `python -m py_compile services\core-service\atee_core\core.py services\core-service\atee_core\llm_gateway.py tests\test_core.py` | 通过 |
| `python -m unittest tests.test_core` | 52/52 通过 |

## 覆盖测试

- `test_update_config_preserves_llm_budget_and_circuit_runtime_state`
- `test_llm_budget_and_circuit_runtime_state_survive_core_restart`

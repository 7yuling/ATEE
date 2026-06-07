# ATEE 前台 live 登录超时修复报告

生成日期：2026-06-07

## 问题一句话

1 小时真实 API + 前台业务页面生产仿真中，demo thin adapter 固定 `5s` Core HTTP 超时，容易在真实 DeepSeek API 延迟抖动时触发前台 `502 core_request_failed`。

## 修复范围

| 文件 | 修改 |
| --- | --- |
| `adapters/python-fastapi/atee_adapter.py` | 将固定 `timeout=5` 改为可配置超时，默认 `25s`，支持 `ATEE_ADAPTER_TIMEOUT_SECONDS` 覆盖。 |
| `tests/test_demo_site.py` | 增加 adapter 超时配置测试和超时错误可解释性测试。 |

## 行为变化

| 项目 | 修复前 | 修复后 |
| --- | --- | --- |
| Adapter 超时 | 固定 5 秒 | 默认 25 秒 |
| 环境变量 | 不支持 | `ATEE_ADAPTER_TIMEOUT_SECONDS` |
| 超时错误 | demo 前台只能看到泛化 `core_request_failed` 和底层短 detail | detail 中包含 Core 路径和超时时间，例如 `/v1/check ... 25s` |
| Core 远程模型预算/熔断 | 不变 | 不变 |

## 验证结果

| 命令 | 结果 |
| --- | --- |
| `python -m py_compile adapters\python-fastapi\atee_adapter.py tests\test_demo_site.py` | 通过 |
| `python -m unittest tests.test_demo_site` | 6/6 通过 |

## 尚未执行

本次只完成代码级最小修复和本地单元/冒烟验证，尚未重新跑真实 API 10-15 分钟或 1 小时前台生产仿真。

建议下一步执行：

1. 10-15 分钟 live rehearsal，目标 `normal_login` 成功率接近 100%。
2. 1 小时生产仿真，目标 `frontend_failures=0`、`normal_login route=sync_agent`、`llm_reason=provider_json_decision`、`LLM circuit open=false`、预算低于 `1000 cents`。

## 运行配置建议

生产仿真时显式设置：

```powershell
$env:ATEE_ADAPTER_TIMEOUT_SECONDS = "25"
```

如果 Core 的 `remote_hard_timeout_ms` 调整高于 20000ms，应同步让 adapter timeout 高于 Core hard timeout 约 5 秒。

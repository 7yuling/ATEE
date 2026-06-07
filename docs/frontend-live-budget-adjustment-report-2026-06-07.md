# ATEE 前台 live 预算可调修复报告

生成日期：2026-06-07

## 问题一句话

前台生产仿真脚本的 `--budget-cents` 只参与运行时校验，没有主动写入 Core 配置，因此预算参数可能与真实模型网关预算不一致。

## 最小修复

| 文件 | 修改 |
| --- | --- |
| `scripts/frontend-live-production-rehearsal.mjs` | 启动 Core 后通过 `/v1/admin/config` 写入 `llm_daily_budget_cents`，再执行运行时配置校验。 |
| `tests/test_deployment_assets.py` | 增加脚本资产测试，确保预算参数会写入 Core，且不包含明文密钥。 |

## 行为变化

| 项目 | 修复前 | 修复后 |
| --- | --- | --- |
| `--budget-cents 1000` | 只校验运行时是否已经是 1000 | 自动写入 Core 后再校验 |
| `--budget-cents 0` | 被解析为默认 1000，且可能被预算保护误停 | 正确表示不限额，余量为 `null` 时不触发预算保护 |
| 管理认证 | 未涉及 | 支持 `--admin-token` 或 `ATEE_ADMIN_TOKEN` 调用受保护的配置接口 |

## 验证命令

```powershell
node --check scripts\frontend-live-production-rehearsal.mjs
python -m unittest tests.test_deployment_assets tests.test_demo_site
```

## 使用示例

```powershell
scripts\windows\run-frontend-live-production-rehearsal.cmd --budget-cents 2500 --stop-budget-remaining-cents 50
```

如管理接口开启认证：

```powershell
$env:ATEE_ADMIN_TOKEN = "<本机临时管理令牌>"
scripts\windows\run-frontend-live-production-rehearsal.cmd --budget-cents 2500
```

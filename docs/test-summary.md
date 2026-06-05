# ATEE 测试项目与覆盖摘要

更新时间：2026-06-02

## 结论

- 本轮管理台拆分后已通过：管理台单测、生产构建、浏览器端到端检查和 diff 空白检查。
- 最近一次浏览器端到端检查覆盖 32 个关键动作，包含安全请求、快速拦截、安全流程演练、操作台/配置页 LLM 测试、申诉通过/驳回、申诉只读保护、异步 AI 审查、动作管理只读保护、网关配置只读保护、Agent 对话、新手引导动作、动作撤销、账本摘要、网关配置和紧急旁路检测。
- 核心真实性验证第 2/5/6/7 项已复跑通过：28/28 通过，攻击检测率 100%，洪泛稳定性 100%，决策准确率 100%，漏报率 0%，误报率 0%。
- 已显式执行一次远程 AI live smoke：`live_used=true`，同步 Agent 审查通过，预算记录消耗 1 cent；报告保持脱敏。
- 测试报告、发布闸门和敏感扫描均不输出 API Key、Authorization、真实供应商地址、代理地址、密钥文件路径、原始 Prompt 或原始请求体。

## 本轮实际执行

| 测试项目 | 命令 | 结果 | 详细覆盖内容 |
| --- | --- | --- | --- |
| 管理台源码与静态资源单测 | `python -m unittest tests.test_admin_console` | 4 个测试通过 | 检查 HTML 使用外部静态资源和 CSP nonce；确认测试 payload 不会截断 HTML；确认构建产物包含管理台 API 端点；确认 React 源码保留 e2e ID、敏感 JSON 脱敏、Admin Token 传递边界、纯文本渲染和组件拆分后的源码覆盖。 |
| 管理台生产构建 | `npm.cmd run build:admin` | 通过 | 使用 Vite 构建 `apps/admin-console`，验证 JSX 导入、Ant Design 组件、CSS 和静态管理台产物可生成。 |
| 浏览器端到端检查 | `npm.cmd run e2e:browser` | 32 项通过 | 启动临时 Core Service，打开管理台，使用 Playwright/Chromium 点击真实按钮并校验接口返回。 |
| 全量 Python 单测 | `python -m unittest discover -s tests` | 113 个测试通过 | 覆盖 Core、HTTP、管理台、部署资产、演示站、供应商故障/预算/熔断、备份恢复、压力脚本、生产冒烟、发布闸门和核心真实性回归用例。 |
| 核心真实性验证 | `python scripts\qa-core-authenticity-suite.py --combine` | 28 项通过 | 汇总第 2/5/6/7 项，验证真实用户行为、攻击模拟、日志洪泛和 Agent 决策质量；修复后失败项为 0。 |
| 远程 AI live smoke | `python scripts\agent-ai-full-flow-smoke.py --include-live --budget-cents 100 --report docs\agent-ai-live-full-flow-smoke.md` | 通过 | 显式调用远程模型一次，验证同步 Agent 审查、Fast-Path、申诉、管理员审核和账本闭环；不输出敏感配置。 |
| Quick 发布闸门 | `python scripts\local-release-gate.py --quick --report docs\local-release-gate-commit-prep.md` | 通过 | 执行配置预检、Python 编译、32 个聚焦单测、Agent AI 全流程 fake 冒烟、异步 AI 审查 worker fake 冒烟和敏感扫描；本次敏感扫描 209 个文件，findings=0。 |
| Diff 空白检查 | `git diff --check` | 通过 | 检查本轮变更没有尾随空白或补丁格式问题；当前提示仅为 Git 在 Windows 下的 LF/CRLF 换行警告。 |

## 浏览器端到端覆盖明细

| 序号 | 模块 | 操作 | 验证点 |
| --- | --- | --- | --- |
| 1 | 管理台启动 | 打开临时服务首页 | 页面包含管理台标题、模型网关和安全演练入口。 |
| 2 | 安全演练 | 点击安全请求 | `/v1/check` 返回 `route=skip`，低风险请求不进入高成本路径。 |
| 3 | Fast-Path | 点击快速拦截 | XSS 样例返回 `route=fast_path_block`。 |
| 4 | 申诉入口 | 点击测试申诉 | `/v1/appeal` 返回 `202`，申诉进入待处理队列。 |
| 5 | 操作台 LLM 测试 | 点击测试模型网关 | 操作台入口返回 `ok=true`。 |
| 6 | 异步 AI 审查源事件 | 提交普通评论事件 | 请求进入 `async_agent`，原因是 `async_review_queued`。 |
| 7 | 异步 AI 审查列表 | 打开异步 AI 审查并刷新 | 队列返回 jobs，待处理任务可见。 |
| 8 | 异步 AI 审查处理 | 点击处理到期任务 | 返回 `ok=true` 且处理至少 1 条任务。 |
| 9 | Agent 对话 | 选择网站类型和接入方式，发送问题 | Mock 模式下返回 `reason=mock_chat`。 |
| 10 | 新手引导 | 选择网站类型和接入方式 | 下拉控件可操作。 |
| 11 | 环境预检 | 点击运行环境预检 | 返回 checks 数组，页面保留安全情况处理总流程。 |
| 12 | 引导动作 | 展开“网站类型选择”并点击动作按钮 | 切到 Agent 对话，输入框预填包含“API 服务”的接入问题。 |
| 13 | 申诉处理 | 刷新待处理申诉 | 返回 1 条待处理申诉。 |
| 14 | 申诉审核 | 填写处罚编号和备注并通过 | 返回 `ok=true`，申诉状态变为 approved。 |
| 15 | 申诉驳回 | 创建第二条申诉，填写处罚编号和备注并驳回 | 返回 `ok=true`，申诉状态变为 rejected。 |
| 16 | 运行模式 | 切换降级模式 | 返回 `mode=degraded`。 |
| 17 | 只读保护 | 切换只读模式 | 页面显示只读保护提示。 |
| 18 | 申诉通过只读保护 | 只读模式下打开申诉处理 | `approveAppealBtn` 被禁用，不能审核通过申诉。 |
| 19 | 申诉驳回只读保护 | 只读模式下打开申诉处理 | `rejectAppealBtn` 被禁用，不能驳回申诉。 |
| 20 | 异步 AI 审查只读保护 | 只读模式下打开异步 AI 审查 | `runAsyncReviewsBtn` 被禁用，不能处理队列。 |
| 21 | 动作清理只读保护 | 只读模式下打开动作管理 | `cleanupActionsBtn` 被禁用，不能清理过期动作。 |
| 22 | 动作撤销只读保护 | 只读模式下打开动作管理 | `revokeActionBtn` 被禁用，不能撤销动作。 |
| 23 | 网关配置只读保护 | 只读模式下打开网关配置 | `configSaveBtn` 被禁用，不能保存运行配置。 |
| 24 | 自动模式 | 确认切换自动模式 | 返回 `mode=auto`。 |
| 25 | 自动处置 | 自动模式下再次触发攻击 | 动作执行结果为 `executed=true`。 |
| 26 | 动作管理 | 刷新动作并选择动作 ID | 返回 actions 列表且存在可撤销动作。 |
| 27 | 动作撤销 | 填写原因并撤销 | 返回 `ok=true`，动作状态变为 revoked。 |
| 28 | 安全账本 | 设置 limit 并读取账本 | 返回数字型 `ledger_count` 摘要。 |
| 29 | 账本摘要边界 | 检查读取账本后的操作结果 | 操作结果 JSON 不包含 `records` 数组，避免在控制台展开账本详情。 |
| 30 | 网关配置 | 读取配置、保存配置、测试 LLM、验证旁路 | 配置读取成功；保存 `local_precheck_ms=123` 成功；LLM 测试入口返回 `ok=true`；无旁路 Header 时 `valid_for_request=false`。 |
| 31 | 安全流程演练 | 点击新手引导中的运行安全流程演练 | `POST /v1/admin/security-flow/run` 返回 `flow_steps`，覆盖预检、安全请求、快速拦截、异步 AI 审查、申诉、模型网关和账本摘要。 |
| 32 | 安全流程只读保护 | 只读模式下打开新手引导 | `securityFlowBtn` 被禁用，演练不会在只读模式下写入记录。 |

## 发布闸门覆盖

`scripts/local-release-gate.py --quick --report reports/local-release-gate.md` 的 quick 模式包含：

- `config_preflight`：运行 Core 配置预检，确认本地配置满足启动前置条件。
- `python_compile`：编译 `services`、`adapters`、`apps`、`tests`、`scripts`，捕获 Python 语法错误。
- `unit_tests`：运行聚焦单测集合，当前 quick 报告记录 32 个测试。
- `agent_ai_full_flow_smoke`：默认使用 fake provider，验证 Agent AI 全流程冒烟，并生成脱敏报告。
- `async_ai_review_worker_smoke`：默认使用 fake provider，验证异步 AI 审查 worker 的预算和熔断联动，并生成脱敏报告。
- `sensitive_scan`：扫描工作区，跳过本地运行配置、`config/secrets`、`node_modules`、Git 内部目录和 Python 缓存，检查密钥形状、供应商主机、代理标记等敏感信息是否误入仓库。

## 核心真实性验证覆盖

| 分项 | 命令 | 结果 | 关键结论 |
| --- | --- | --- | --- |
| 第 2 项真实用户行为 | `python scripts\qa-core-authenticity-suite.py --section 2` | 7/7 通过 | 普通用户、搜索爬虫、Cloudflare、Nginx/API 批量访问和重复提交均未误拦。 |
| 第 5 项攻击模拟 | `python scripts\qa-core-authenticity-suite.py --section 5` | 8/8 通过 | SQL、XSS、SSRF、云元数据、路径穿越、危险上传、WebShell、Prompt Injection 均按预期分类或防御。 |
| 第 6 项日志洪泛 | `python scripts\qa-core-authenticity-suite.py --section 6 --requests 5000 --workers 32` | 4/4 通过 | 正常洪泛、混合攻击洪泛、大量告警和 5MB 日志均未导致崩溃或误判。 |
| 第 7 项决策质量 | `python scripts\qa-core-authenticity-suite.py --section 7` | 9/9 通过 | 人工专家标签与 ATEE 判断一致，漏报率 0%，误报率 0%，Prompt Injection 防御 100%。 |

## Python 测试模块地图

| 测试文件 | 覆盖重点 |
| --- | --- |
| `tests/test_core.py` | Core Service 主流程、真实 IP、Fast-Path、Prompt 脱敏、中文展示、Onboarding、Agent chat、申诉、动作、配置持久化、Admin Token、账本、LLM 网关、预算、熔断、DPAPI 密钥文件。 |
| `tests/test_http_e2e.py` | Core HTTP 服务、管理台静态资源、CSP nonce、Admin API 鉴权、并发请求冒烟。 |
| `tests/test_admin_console.py` | 管理台 HTML/CSP、静态产物、前端 API 端点、e2e ID、脱敏和纯文本渲染边界。 |
| `tests/test_demo_site.py` | 演示站静态安全、登录/评论/上传/申诉链路、部署覆盖项和 Core 错误响应。 |
| `tests/test_deployment_assets.py` | Docker、Compose、Windows/Linux 启动脚本、systemd、Nginx/Caddy 示例、备份恢复、日志轮转、环境文件占位符、SSO 代理示例。 |
| `tests/test_agent_ai_full_flow_smoke.py` | Agent AI 全流程冒烟脚本；默认 fake provider；live 模式必须显式满足远程配置。 |
| `tests/test_async_review_worker.py` | 异步 AI 审查 worker 自动处理到期任务。 |
| `tests/test_async_ai_review_worker_smoke.py` | worker 冒烟脚本的预算耗尽、熔断和脱敏报告。 |
| `tests/test_provider_faults.py` | fake provider 成功与失败注入、请求体脱敏、连续失败后熔断。 |
| `tests/test_provider_fault_drill.py` | 故障演练脚本、坏代理场景、Markdown 脱敏报告。 |
| `tests/test_provider_budget_drill.py` | 预算演练脚本，预算耗尽后停止远程调用并输出脱敏报告。 |
| `tests/test_provider_live_batch_drill.py` | 批量供应商演练脚本默认 fake；live 模式有小批量安全上限。 |
| `tests/test_backup_restore_drill.py` | 备份恢复演练，确认恢复状态且排除 secrets。 |
| `tests/test_recovery_load.py` | 混合负载、重启恢复和操作者状态恢复。 |
| `tests/test_local_stress_check.py` | 本地压力脚本的请求模式和时长模式脱敏报告。 |
| `tests/test_local_release_gate.py` | 本地发布闸门自身的脱敏和步骤执行。 |
| `tests/test_admin_token_rotation_smoke.py` | Admin Token 轮换、重启和输出脱敏。 |
| `tests/test_production_smoke_check.py` | 生产冒烟脚本、SSO 操作者覆盖、真实 Core 本地闭环。 |

## 仍需单独验收

- 真实 Ubuntu 目标机上的 systemd 生命周期、端口占用、Nginx/Caddy HTTPS 和公网域名。
- 真实供应商 live 调用只在显式 `--include-live` 或专门 live 脚本中执行；默认测试不会消耗真实模型额度。
- 长时间压力测试已有脚本和历史报告，但本轮管理台拆分只重新运行了浏览器端到端与管理台相关检查。

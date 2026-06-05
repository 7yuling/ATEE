# ATEE 管理控制台功能闭环审计

- 日期：2026-06-02
- 范围：`apps/admin-console-src/src/*`、`services/core-service/atee_core/http_server.py`、`services/core-service/atee_core/core.py`、现有管理台/HTTP/浏览器 E2E 测试。
- 保密边界：本文不记录 API Key、Admin Token、代理地址、API Base 实值、密钥文件路径、Authorization、原始 Prompt 或原始请求体。

## 一句话结论

管理台主要按钮和表单已经接入真实 Core API；本轮已补齐新手引导中的安全流程一键演练，当前剩余缺口主要是配置保存前端字段级校验/聚焦，以及生产级 API Key 持久注入仍依赖服务环境或密钥管理器。

## 审计方法

- 前端源：逐项检查 `main.jsx` 中的动作函数、菜单/Tab 传参、组件按钮 `id` 和 `onClick`。
- 后端源：核对 `/v1/admin/*`、`/v1/check`、`/v1/appeal`、`/v1/onboarding/steps` 在 HTTP 层是否有路由，并继续落到 `CoreService` 方法。
- 测试源：核对 `tests/test_admin_console.py`、`tests/test_http_e2e.py` 和 `scripts/browser-e2e.mjs` 是否覆盖真实按钮链路。

## 模块闭环清单

| 模块 | 控件/功能 | 前端动作 | 后端接口 | 闭合状态 | 备注 |
|---|---|---|---|---|---|
| 顶部运行控制 | 刷新 | 读取运行状态并同步配置表单 | `GET /v1/runtime/status` | 已闭合 | 同时更新运行状态 JSON 摘要。 |
| 顶部运行控制 | 观察/自动/降级/只读模式 | `setMode(mode)` | `POST /v1/admin/mode` | 已闭合 | 自动模式有二次确认；后端会写入配置并记审计。 |
| 顶部运行控制 | 暂停/恢复 Agent | `pauseResume()` | `POST /v1/admin/pause-agent` | 已闭合 | 后端保存暂停状态并记审计。 |
| 管理认证 | 保存/清除本机会话令牌 | 写入浏览器 `sessionStorage` | 无直接后端保存 | 本地会话闭合 | 这是请求认证材料，不是生产密钥存储；后续管理请求自动带 `Authorization` 和 `X-ATEE-Admin-Id`。 |
| 仪表盘/操作台 | 测试安全请求 | 构造低风险请求 | `POST /v1/check` | 已闭合 | 预期 `skip` 或本地允许。 |
| 仪表盘/操作台 | 测试快速拦截 | 构造 XSS 评论请求 | `POST /v1/check` | 已闭合 | 预期 `fast_path_block`；自动模式下可产生动作记录。 |
| 仪表盘/操作台 | 测试申诉 | 提交演示处罚申诉 | `POST /v1/appeal` | 已闭合 | 会进入申诉列表。 |
| 仪表盘/操作台 | 测试模型网关 | 读取模型连通检测 | `GET /v1/admin/llm/test` | 已闭合 | 结果摘要会显示最近原因、预算、熔断和配置存在性。 |
| Agent 对话 | 网站类型/接入方式选择 | 保存到 React 状态 | 无直接后端保存 | 上下文闭合 | 选择项会随聊天请求提交给后端。 |
| Agent 对话 | 发送消息 | `sendAgentChat()` | `POST /v1/admin/agent/chat` | 已闭合 | 后端会调用当前 LLM gateway；mock 模式返回本地建议。 |
| 新手引导 | 加载步骤 | 页面初始化读取步骤 | `GET /v1/onboarding/steps` | 已闭合 | 步骤可展开，包含详细说明和风险提示。 |
| 新手引导 | 环境预检 | `runPreflight()` | `GET /v1/admin/preflight` | 已闭合 | 检查 Python、配置文件、静态资源、账本目录、模型网关、可信代理、紧急旁路。 |
| 新手引导 | 网站类型/接入方式 | 下拉选择共享上下文 | 无直接后端保存 | 部分闭合 | 会影响 Agent 对话上下文，但引导按钮目前只停留/跳转，不会自动生成接入方案。 |
| 新手引导 | 真实 IP、AI API、紧急恢复、申诉 | `runGuideAction(stepId)` 跳转并聚焦目标控件 | 对应模块 API | 已闭合 | 网站类型/接入方式会预填 Agent 问题；配置/申诉/安全演练步骤会聚焦目标控件。 |
| 新手引导 | 安全情况处理总流程 | `runSecurityFlow()` | `POST /v1/admin/security-flow/run` | 已闭合 | 后端按预检、安全请求、快速拦截、异步 AI 审查、申诉、模型网关和账本摘要顺序演练；演练申诉自动关闭，不污染真实待办。 |
| 申诉处理 | 状态筛选/刷新 | `showAppeals(status)` | `GET /v1/admin/appeals?status=` | 已闭合 | 表格行点击会回填处罚编号。 |
| 申诉处理 | 通过/驳回 | `reviewAppeal(resolution)` | `POST /v1/admin/appeals/review` | 已闭合 | 只读模式禁用；成功后记账本。 |
| 异步 AI 审查 | 队列筛选/刷新 | `showAsyncReviews(status)` | `GET /v1/admin/async-reviews?status=` | 已闭合 | 列表仅展示脱敏队列摘要。 |
| 异步 AI 审查 | 处理到期任务 | `runAsyncReviews()` | `POST /v1/admin/async-reviews/run` | 已闭合 | 后端会处理到期任务并写审计；只读模式下前后端均阻止处理。 |
| 动作管理 | 状态筛选/刷新 | `showActions(status)` | `GET /v1/admin/actions?status=` | 已闭合 | 表格行点击会回填动作编号。 |
| 动作管理 | 撤销动作 | `revokeAction()` | `POST /v1/admin/actions/revoke` | 已闭合 | 只读模式禁用；撤销只更新 ATEE 动作记录，不回滚业务数据库。 |
| 动作管理 | 清理过期动作 | `cleanupActions()` | `POST /v1/admin/actions/cleanup-expired` | 已闭合 | 有二次确认。 |
| 安全账本 | 读取最近记录 | `showLedger()` | `GET /v1/admin/ledger/recent?limit=` | 已闭合 | 按需求只显示摘要列和数量，不展开管理员行为详情。 |
| 网关配置 | 读取配置 | `showConfig()` | `GET /v1/admin/config` | 已闭合 | 返回公开配置，不回显敏感值。 |
| 网关配置 | 保存配置 | `saveConfig()` | `POST /v1/admin/config` | 已闭合 | 覆盖运行模式、语言、暂停、异步 worker、可信代理、超时、模型、预算、账本、申诉、认证、旁路等可调项。 |
| 网关配置 | API Key 输入 | `llm_api_key_value` 写入请求体 | `POST /v1/admin/config` | 运行时闭合 | 后端只写入当前服务进程环境变量，不写入 `config.json`、不回显；服务重启后的生产持久注入仍应由 systemd env/secret manager 完成。 |
| 网关配置 | 保存后连通检测 | 保存 API Base 或 Key 后自动测试 | `GET /v1/admin/llm/test` | 已闭合 | 结果摘要显示 `ok`、原因、预算、熔断；原始 JSON 脱敏。 |
| 网关配置 | 紧急旁路检查 | 输入 `X-ATEE-Bypass` Header | `POST /v1/admin/break-glass/status` | 已闭合 | 只验证请求级旁路是否可用，并提示使用后轮换密钥。 |
| 结果展示 | 运行状态摘要/操作结果摘要 | `RuntimeSummary` / `OperationSummary` | 前端脱敏渲染 | 已闭合 | `SECRET_JSON_KEYS` 会遮蔽 API Key、API Base、代理、Token、旁路等字段。 |

## 后端接口闭合清单

| 接口 | Core 方法 | 控制台使用处 |
|---|---|---|
| `GET /v1/runtime/status` | `runtime_status()` | 刷新、状态卡、配置表单同步 |
| `GET /v1/onboarding/steps` | `onboarding_steps()` | 新手引导折叠步骤 |
| `GET/POST /v1/admin/preflight` | `environment_preflight()` | 新手引导环境预检 |
| `POST /v1/admin/security-flow/run` | `security_flow_rehearsal()` | 新手引导安全流程演练 |
| `GET/POST /v1/admin/llm/test` | `test_llm_gateway()` | 操作台和网关配置测试 |
| `POST /v1/admin/agent/chat` | `agent_chat()` | Agent 对话 |
| `GET/POST /v1/admin/config` | `config_status()` / `update_config()` | 网关配置读取/保存 |
| `POST /v1/admin/mode` | `set_mode()` | 顶部模式切换 |
| `POST /v1/admin/pause-agent` | `pause_agent()` | 顶部暂停/恢复 |
| `GET /v1/admin/appeals` | `admin_appeals()` | 申诉列表 |
| `POST /v1/admin/appeals/review` | `review_appeal()` | 申诉审核 |
| `GET /v1/admin/actions` | `admin_actions()` | 动作列表 |
| `POST /v1/admin/actions/revoke` | `revoke_action()` | 动作撤销 |
| `POST /v1/admin/actions/cleanup-expired` | `cleanup_expired_actions()` | 清理过期动作 |
| `GET /v1/admin/async-reviews` | `admin_async_reviews()` | 异步 AI 审查队列 |
| `POST /v1/admin/async-reviews/run` | `run_async_reviews()` | 手动处理到期任务 |
| `GET /v1/admin/ledger/recent` | `ledger_recent()` | 最近账本摘要 |
| `POST /v1/admin/break-glass/status` | `break_glass_status()` | 紧急旁路验证 |
| `POST /v1/check` | `check()` | 安全请求、快速拦截演练 |
| `POST /v1/appeal` | `appeal()` | 申诉演练 |

## 自动化覆盖

| 覆盖入口 | 当前覆盖 |
|---|---|
| `tests/test_admin_console.py` | 管理台静态资源、端点字符串、e2e DOM ID、纯文本渲染、敏感 JSON 脱敏、Admin Token 请求头边界。 |
| `tests/test_http_e2e.py` | HTTP 层安全请求、Fast-Path、异步队列、申诉、动作执行/撤销、Admin API 鉴权。 |
| `scripts/browser-e2e.mjs` | 32 项真实浏览器按钮链路，覆盖操作台、Agent 对话、新手引导、安全流程演练、安全流程只读保护、申诉通过/驳回、申诉只读保护、异步 AI 审查、动作管理只读保护、网关配置只读保护、账本摘要边界、配置保存、操作台/配置页 LLM 测试、引导动作预填和紧急旁路检测。 |

## 未闭合项与最小下一步

| 优先级 | 未闭合项 | 最小解决方案 |
|---|---|---|
| P0 | 控制台输入 API Key 只保证当前服务进程运行时可用，服务重启后仍依赖外部环境注入。 | 在 UI 文案和部署文档中继续区分“运行时测试 Key”和“生产持久环境变量/secret manager”；生产持久化不要把 Key 明文写入仓库。 |
| P1 | 配置保存缺少前端字段级校验，例如 hard timeout 应不小于 soft timeout、remote 模式需要 API Base 与 Key 来源。 | 保存前增加轻量表单校验；失败时不发请求，只在操作结果摘要中显示中文原因。 |
| P1 | Agent 对话没有 Enter 发送、推荐问题和清晰的失败重试入口。 | 加 Enter/Ctrl+Enter 发送规则、常用问题按钮和最近一次失败原因展示。 |

## 下一步建议

下一步建议进入配置保存的字段级校验；安全情况处理总流程已具备一键演练、摘要展示和只读保护，剩余 P0 主要是生产持久 API Key 注入边界的文档与部署体验。

## 分板块检查记录

### 2026-06-02 板块 1：全局状态、认证与运行控制

| 检查项 | 结论 |
|---|---|
| 前端控件 | `refreshBtn`、`observeBtn`、`autoBtn`、`degradedBtn`、`readOnlyBtn`、`pauseBtn`、`saveAdminTokenBtn`、`clearAdminTokenBtn` 均有明确处理函数。 |
| 前端到后端 | 刷新走 `GET /v1/runtime/status`；模式切换走 `POST /v1/admin/mode`；暂停/恢复走 `POST /v1/admin/pause-agent`。 |
| 认证传递 | Admin Token 与操作者 ID 只保存在浏览器 `sessionStorage`；`apiRequest()` 仅对 `/v1/admin/*` 自动注入 `Authorization` 与 `X-ATEE-Admin-Id`。 |
| 后端路由 | `http_server.py` 对所有 `/v1/admin/*` 入口先执行 Admin Token 鉴权；公开运行状态不需要 Admin Token。 |
| Core 行为 | `set_mode()` 和 `pause_agent()` 会更新运行配置并写入管理员审计；`runtime_status()` 返回账本、动作、申诉、异步队列、模型网关、认证状态和公开配置。 |
| 自动化验证 | `python -m unittest tests.test_admin_console tests.test_http_e2e` 通过，8 个测试 OK；`python -m unittest tests.test_core` 通过，37 个测试 OK；`node --check scripts\browser-e2e.mjs` 通过。 |
| 是否发现问题 | 未发现需要修改的产品代码问题。 |

本板块状态：已通过，等待用户确认后进入板块 2“操作台安全演练”。

### 2026-06-02 板块 2：操作台安全演练

| 检查项 | 结论 |
|---|---|
| 前端控件 | `testSafeBtn`、`testAttackBtn`、`testAppealBtn`、`testLlmBtn` 均绑定到真实处理函数。 |
| 安全请求演练 | `testSafe()` 构造低风险浏览请求并调用 `POST /v1/check`，预期返回 `route=skip`。 |
| 快速拦截演练 | `testAttack()` 构造 XSS 评论请求并调用 `POST /v1/check`，预期返回 `route=fast_path_block`；在自动模式下可产生动作记录。 |
| 申诉演练 | `testAppeal()` 提交演示处罚申诉到 `POST /v1/appeal`，预期返回 `status=202` 并进入申诉列表。 |
| 模型网关测试 | `testLlmGateway()` 调用 `GET /v1/admin/llm/test`，由后端 `test_llm_gateway()` 返回当前模型连通、预算、熔断和配置存在状态。 |
| 结果展示 | 所有演练统一经 `run()` 写入操作结果；`OperationSummary` 先展示中文摘要，再提供脱敏原始 JSON。 |
| 自动化验证 | 补齐 `scripts/browser-e2e.mjs` 对操作台 `testLlmBtn` 的真实点击断言；浏览器 E2E 由 20 项更新为 21 项。 |
| 是否发现问题 | 未发现产品业务代码问题；已修复操作台 LLM 测试按钮缺少浏览器回归覆盖的问题。 |

本板块状态：已通过，等待用户确认后进入板块 3“Agent 对话和新手引导”。

### 2026-06-02 板块 3：Agent 对话和新手引导

| 检查项 | 结论 |
|---|---|
| Agent 前端窗口 | `AgentTab` 已提供网站类型、接入方式、对话窗口、输入框和发送按钮；消息按纯文本渲染。 |
| Agent 后端链路 | `sendAgentChat()` 调用 `POST /v1/admin/agent/chat`，后端 `agent_chat()` 将 `site_type`、`adapter_type` 和运行模式作为上下文传给模型网关，并写入管理员审计。 |
| 环境预检 | `runPreflight()` 调用 `GET /v1/admin/preflight`，后端检查 Python、配置文件、管理台静态资源、账本目录、模型网关、可信代理和紧急旁路。 |
| 新手引导内容 | `GET /v1/onboarding/steps` 返回 8 个中文步骤，每个步骤有推荐、风险和详情；页面使用折叠面板展开。 |
| 发现问题 | 引导动作原来主要是跳转或运行预检，缺少稳定按钮 ID、字段级聚焦和 Agent 问题预填，用户感知仍像说明文字。 |
| 修复情况 | `runGuideAction(stepId)` 现在会运行预检后聚焦结果、对网站类型/接入方式预填 Agent 问题、对真实 IP/AI API/紧急旁路/申诉/安全演练跳到对应板块并聚焦目标控件。 |
| 自动化验证 | `scripts/browser-e2e.mjs` 新增展开“网站类型选择”、点击 `#guideAction-site_type`、确认切到 Agent 并预填“API 服务”问题的真实浏览器断言；浏览器 E2E 由 21 项更新为 22 项。 |

本板块状态：已通过，等待用户确认后进入板块 4“申诉处理”。

### 2026-06-02 板块 4：申诉处理

| 检查项 | 结论 |
|---|---|
| 前端控件 | `appealStatusSelect`、`appealsBtn`、`appealIdInput`、`appealNoteInput`、`approveAppealBtn`、`rejectAppealBtn` 均存在并绑定到申诉处理动作。 |
| 列表刷新 | `showAppeals(status)` 调用 `GET /v1/admin/appeals?status=`，支持待处理、已通过、已驳回和全部筛选。 |
| 行回填 | 申诉表格行点击会把 `punishment_id` 回填到审核表单，减少手动复制错误。 |
| 审核动作 | `reviewAppeal(resolution)` 调用 `POST /v1/admin/appeals/review`，支持 `approved` 与 `rejected`；只读模式下按钮禁用。 |
| 后端行为 | `AppealService.review()` 校验处罚编号和审核结果，只处理 pending 申诉；`CoreService.review_appeal()` 成功后写入 `appeal_review` 账本摘要。 |
| 发现问题 | 浏览器 E2E 原先只真实点击“通过”，没有点击“驳回”；静态 DOM ID 清单也漏掉了审核备注和驳回按钮。 |
| 修复情况 | `scripts/browser-e2e.mjs` 新增第二条申诉并点击 `#rejectAppealBtn` 的真实断言；`tests/test_admin_console.py` 新增 `appealNoteInput` 和 `rejectAppealBtn` DOM ID 断言。 |
| 自动化验证 | 浏览器 E2E 由 22 项更新为 23 项；Core/HTTP/管理台测试和恢复负载测试均通过。 |

本板块状态：已通过，等待用户确认后进入板块 5“异步 AI 审查”。

### 2026-06-02 板块 5：异步 AI 审查

| 检查项 | 结论 |
|---|---|
| 前端控件 | `asyncReviewStatusSelect`、`asyncReviewsBtn`、`runAsyncReviewsBtn` 均存在；状态筛选包含 pending、retry、processing、completed、dead_letter、all。 |
| 队列刷新 | `showAsyncReviews(status)` 调用 `GET /v1/admin/async-reviews?status=`，只展示脱敏后的队列摘要。 |
| 手动处理 | `runAsyncReviews()` 调用 `POST /v1/admin/async-reviews/run`，处理到期 pending/retry 任务并刷新当前筛选列表。 |
| 后端队列 | `AsyncReviewQueue` 支持 pending、retry、processing、completed、dead_letter，处理结果不返回原始 `packet`。 |
| 后台 worker | `AsyncReviewWorker.run_once()` 走同一个 `process_async_reviews()` 后端入口，因此与手动处理共享预算、熔断和只读保护。 |
| 发现问题 | “处理到期任务”会写队列状态、可能调用模型并写审计，但原先没有受只读模式保护。 |
| 修复情况 | `process_async_reviews()` 在 `read_only` 下返回 423 并保留队列；`AsyncReviewsTab` 接收 `writeLocked` 并禁用 `runAsyncReviewsBtn`；浏览器 E2E 新增只读禁用断言。 |
| 自动化验证 | 浏览器 E2E 由 23 项更新为 24 项；新增 Core 单测确认只读模式不会消费 pending 队列。 |

本板块状态：已通过，等待用户确认后进入板块 6“动作管理”。

### 2026-06-02 板块 6：动作管理

| 检查项 | 结论 |
|---|---|
| 前端控件 | `actionStatusSelect`、`actionsBtn`、`cleanupActionsBtn`、`actionIdInput`、`revokeReasonInput`、`revokeActionBtn` 均存在并绑定到动作管理函数。 |
| 列表刷新 | `showActions(status)` 调用 `GET /v1/admin/actions?status=`，支持 active、revoked、expired、all；表格行点击会回填动作编号。 |
| 撤销动作 | `revokeAction()` 调用 `POST /v1/admin/actions/revoke`，成功后刷新当前筛选列表；撤销只更新 ATEE 动作记录，不回滚业务系统数据。 |
| 清理过期动作 | `cleanupActions()` 调用 `POST /v1/admin/actions/cleanup-expired`，成功后刷新当前筛选列表；清理只标记 ATEE 动作记录为 expired。 |
| 发现问题 | 只读模式下前端已禁用撤销和清理按钮，但后端直连 API 仍可写入；动作列表读取也会顺手清理过期动作，导致只读查询有副作用。 |
| 修复情况 | `revoke_action()` 和 `cleanup_expired_actions()` 在 `read_only` 下返回 423；`ActionExecutor.list_actions()` 增加可关闭过期清理的读取路径，`admin_actions()` 在只读模式使用无副作用查询。 |
| 自动化验证 | 新增 Core 单测确认只读模式不会撤销、不会清理、不会因列表查询标记过期；浏览器 E2E 新增动作清理和撤销按钮只读禁用断言，检查数由 24 更新为 26。 |

本板块状态：已通过，等待用户确认后进入板块 7“安全账本”。

### 2026-06-02 板块 7：安全账本

| 检查项 | 结论 |
|---|---|
| 前端控件 | `ledgerLimitInput` 和 `ledgerBtn` 均存在并绑定到 `showLedger()`。 |
| 列表读取 | `showLedger()` 调用 `GET /v1/admin/ledger/recent?limit=`，表格只显示 ID、时间、事件、等级和动作。 |
| 操作结果 | 读取账本后的操作结果只返回 `ledger_count` 和中文 `display`，不把 `records` 放进结果 JSON。 |
| 内部审计 | Core 内部 `ledger_recent(include_details=True)` 仍保留 `summary`，用于测试管理员身份记录和 Token 脱敏。 |
| 发现问题 | 管理台表格虽然不显示详情，但 HTTP 接口仍把 `summary`、`ip_hash`、`rule_id`、`endpoint_type` 和 `sqlite_path` 返回给浏览器，存在可展开详情的边界风险。 |
| 修复情况 | `ledger_recent()` 增加 `include_details` 参数；HTTP 管理接口默认使用公开摘要记录；公开记录仅保留 `id`、`created_at`、`event_type`、`severity`、`action`，公开状态移除 `sqlite_path`。 |
| 自动化验证 | 新增 Core 单测确认公开 payload 隐藏详情、HTTP E2E 确认管理接口不返回详情字段、浏览器 E2E 确认操作结果不含 `records`，检查数由 26 更新为 27。 |

本板块状态：已通过，等待用户确认后进入板块 8“网关配置”。

### 2026-06-02 板块 8：网关配置

| 检查项 | 结论 |
|---|---|
| 前端控件 | `configBtn`、`configSaveBtn`、`testLlmConfigBtn`、`breakGlassBtn` 以及模型、预算、超时、代理、账本、认证、旁路等配置输入均存在。 |
| 字段说明 | `GATEWAY_HELP` 已覆盖主要可调项；API Base、API Key、代理 URL、密钥文件等敏感写入字段使用不回显输入。 |
| 配置读取 | `showConfig()` 调用 `GET /v1/admin/config`，后端公开配置以 `*_configured` 布尔值表示 API Base、API Key 文件、代理和 Admin Token 文件。 |
| 配置保存 | `saveConfig()` 调用 `POST /v1/admin/config`；`llm_api_key_value` 只写入当前服务进程环境变量，不写入配置文件、不回显。 |
| 模型测试 | `testLlmGateway()` 调用 `GET /v1/admin/llm/test`，返回连通、预算、熔断和配置存在状态，不返回 Key 或代理 URL。 |
| 紧急旁路 | `breakGlass()` 只通过 `X-ATEE-Bypass` Header 验证状态，不支持固定 URL 明文参数。 |
| 发现问题 | 只读模式下前端已禁用保存配置按钮，但后端直连 `POST /v1/admin/config` 仍可修改运行配置并写入运行时 API Key 环境变量。 |
| 修复情况 | `update_config()` 在 `read_only` 下返回 423，不处理配置、不写环境变量、不保存文件；浏览器 E2E 新增 `configSaveBtn` 只读禁用断言。 |
| 自动化验证 | 新增 Core 单测确认只读模式不会保存配置、不会写入 `llm_api_key_value` 到环境变量；浏览器 E2E 检查数由 27 更新为 28。 |

本板块状态：已通过，等待用户确认后进入最后“系统检查”。

### 2026-06-02 最后系统检查

| 检查项 | 结论 |
|---|---|
| 管理写入口 | 已复查 `POST /v1/admin/mode`、`pause-agent`、`config`、`agent/chat`、`break-glass/status`、`appeals/review`、`actions/revoke`、`actions/cleanup-expired`、`async-reviews/run`。 |
| 只读边界 | 申诉审核、异步 AI 审查处理、动作撤销、动作清理、配置保存均有前端禁用和后端 423 保护；模式切换保留可用，用于退出只读。 |
| 敏感公开面 | 配置、模型测试、账本公开记录和生产冒烟报告均不回显 API Key、Admin Token、代理 URL、API Base、密钥文件路径或审计详情。 |
| 发现问题 1 | `review_appeal()` 缺少后端 read_only 保护，直连 API 可绕过控制台审核申诉。 |
| 修复情况 1 | `review_appeal()` 在 `read_only` 下返回 `read_only_mode_blocks_appeal_review` 423；新增 Core 单测和浏览器 `approveAppealBtn`、`rejectAppealBtn` 只读断言。 |
| 发现问题 2 | 生产冒烟脚本仍依赖 HTTP 账本 `summary` 校验 actor，与“公开账本不展开详情”的新边界冲突。 |
| 修复情况 2 | `production-smoke-check.py` 改为兼容公开账本：详细记录存在时验证 actor；公开详情隐藏时验证审计事件存在且 actor/token 未泄漏。 |
| 自动化验证 | `python -m unittest discover -s tests` 105 项通过；`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 30 项通过；`git diff --check` 通过。 |

系统检查状态：已通过，等待用户确认。

### 2026-06-02 核心能力补齐：安全流程演练
| 检查项 | 结论 |
|---|---|
| 后端能力 | 新增 `CoreService.security_flow_rehearsal()`，按环境预检、安全请求、快速拦截、异步 AI 审查、申诉入口、模型网关和安全账本摘要执行受控演练。 |
| HTTP 路由 | 新增 `POST /v1/admin/security-flow/run`，沿用 Admin Token 鉴权；`read_only` 模式返回 423，不写入演练记录。 |
| 控制台入口 | 新手引导“安全情况处理总流程”新增 `securityFlowBtn`，结果渲染到 `securityFlowResultList`，操作结果摘要识别为“安全流程演练”。 |
| 副作用边界 | 演练申诉提交后自动关闭为演练记录，不留在真实待处理申诉队列；返回结果只含步骤摘要、状态码和统计，不返回原始请求体、账本详情或密钥字段。 |
| 自动化验证 | `python -m unittest tests.test_core tests.test_http_e2e tests.test_admin_console` 52 项通过；`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 32 项通过；`python -m unittest discover -s tests` 107 项通过；`git diff --check` 通过，仅有 Windows LF/CRLF 提示。 |

本项状态：已通过。

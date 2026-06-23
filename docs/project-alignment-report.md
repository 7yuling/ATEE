# ATEE 项目对齐报告

报告日期：2026-06-23
对齐对象：

- `ATEE_Agentic_Coding_Workflow_v3.3.md`
- `ATEE_最终合并会议报告_v3.3_含小白引导.md`
- 当前工程目录：`C:\Users\Pro16\Documents\Codex\ATEE`

> 说明：本文件保留 2026-05 至 2026-06 的历史迭代记录；最新状态以本节和“2026-06-23 主干对齐快照”为准。

## 0. 2026-06-23 主干对齐快照

当前 `main` 已推送到 `origin/main`，最新提交为 `1d8eb56 feat: add page guard feature access controls`。该提交把 ATEE Page Guard、接入站点管理、用户级/站点级功能封禁、申诉通过自动解封、页面动作扫描、adapter feature access helper、管理台接入网站页，以及文件命名统一纳入主干。

### 0.1 本轮已对齐能力

| 能力 | 当前状态 | 说明 |
|---|---:|---|
| 接入网站功能访问检查 | 已对齐 | `POST /v1/feature-access` 支持 `site_id`、`user_id`、`feature_scope`，先查站点级 `site_feature` 锁，再查用户级 `user_feature` 锁。 |
| 用户级功能封禁 | 已对齐 | AI/人工 `feature_ban` 可落到 `target_scope.type=user_feature`，返回 `punishment_id=action:<id>` 供用户申诉。 |
| 申诉通过自动解封 | 已对齐 | 管理员审核 `approved` 后，只自动撤销 active、reversible、`user_feature` 类型 `feature_ban`；驳回不解封。 |
| 站点全局功能熔断 | 已对齐 | 管理员可创建 `site_feature` 全局锁，阻断同一站点不同用户；用户申诉不会误解除全站熔断，需管理员撤销 action。 |
| Page Guard 页面守护 | 已对齐 | `apps/page-guard/atee-page-guard.mjs` 可扫描页面控件并通过 `/v1/feature-access` 禁用受保护功能按钮。 |
| 页面动作扫描 | 已对齐 | `scripts/page-action-scan.mjs` 复用共享分类器，可识别登录、注册、提交、搜索、保存、删除、菜单、分页、弹窗触发、上传等控件。 |
| 接入站点管理台 | 已对齐 | 管理台新增接入网站、页面扫描、动作清单、受保护功能、站点熔断入口和全局熔断建议展示。 |
| Python/Node adapter | 已对齐 | `feature_access` / `featureAccess` 支持 `site_id`，并增加上传、评论、发帖前置检查 helper。 |
| 文件命名 | 已对齐 | 管理台 React 组件源码统一为 kebab-case；Windows 启动入口统一为 `run-atee-windows.cmd`。 |

### 0.2 最新验证结果

| 验证项 | 结果 |
|---|---|
| `python -m unittest discover -s tests` | 145 tests OK |
| `npm.cmd run build:admin` | OK |
| `npm.cmd run e2e:browser` | 62 checks OK |
| Page Guard 分类器回归 | OK，`dropdown` 不再误判为 delete，`drop table` 仍识别为高危删除意图 |
| 临时真实页面扫描 | OK，10 类控件全部识别 |
| DeepSeek live provider drill | OK，返回 `provider_json_decision`，密钥未落盘 |
| 功能封禁演练 | OK，用户级封禁可拦截并随申诉通过自动解封；站点级熔断需管理员撤销 |

### 0.3 当前边界判断

当前项目可以判定为：

```text
P0 工程骨架：通过
P0 本地演示：通过
接入网站功能管理：通过
Page Guard / 页面扫描：通过
AI 用户级功能接管：本地与受控 live 链路通过
站点全局熔断：管理员确认路径通过
生产部署：部分通过，仍需目标服务器域名、证书、SSO/反代和业务站点强制检查联调
最终 v3.3 全链路生产验收：未通过
```

当前工作区曾残留一个未跟踪的 `docs/project-test-report-2026-06-15.md` 乱码报告草稿；该文件未纳入 `main` 提交，避免把不可读历史草稿误并入主干。

## 1. 对齐结论

当前项目已经完成 ATEE P0 的“可运行工程骨架”，并且核心方向与 v3.3 文档保持一致：

- 采用 `ATEE Core Service + Thin Adapter`，没有把安全引擎复制到各语言适配器。
- 所有请求先进入 Trusted Real IP Resolver 和 Fast-Path Rule Gate。
- 管理台按纯文本渲染 Agent 输出和用户输入，不使用 `dangerouslySetInnerHTML`。
- 未配置 `trusted_proxy_cidrs` 时，自动 IP 封禁保持关闭。
- 申诉入口有基础限流逻辑。
- 默认运行在观察模式，不真实处罚用户。
- 已支持中文管理台、中文 API display 字段、中文小白引导和中文敏感字段脱敏。
- 已将运行配置从内存迁移到 `config/config.json`。

但当前仍不是生产版。它适合作为 P0 开发基线、演示版本和后续 Agentic Coding 迭代底座。

## 2. 当前可验证状态

已验证：

- 全量 Python 测试：145 个，通过。
- 管理台生产构建：`npm.cmd run build:admin` 通过。
- 浏览器 E2E：`npm.cmd run e2e:browser` 62 项检查通过。
- Python 编译检查：通过。
- 配置预检：通过。
- 本地服务：`http://127.0.0.1:8787/` 临时 HTTP 验证通过。
- 管理台 HTML/CSS/JS 均由 Core Service 返回。
- CSP 保持严格：仅允许同源脚本和同源样式。
- `/v1/runtime/status` 返回中文运行状态。
- `/v1/admin/config` 可读写本地配置。
- `/v1/admin/llm/test` 可验证模型网关；当前 DeepSeek 已通过本地代理连通。
- `/v1/admin/ledger/recent` 可查看 SQLite 最近账本摘要。
- `/v1/admin/appeals` 与 `/v1/admin/actions` 可处理申诉和 ATEE 动作记录。
- `/v1/admin/async-reviews` 与 `/v1/admin/async-reviews/run` 可查看并处理异步 AI 审查队列，支持重试和死信状态。
- `/v1/feature-access` 可检查接入网站用户级和站点级功能封禁状态。
- `/v1/admin/sites`、`/v1/admin/site-scans`、`/v1/admin/site-actions`、`/v1/admin/site-feature-bans` 可管理接入站点、页面扫描、动作清单和全局功能熔断。
- `/v1/onboarding/steps` 返回中文新手引导。
- `apps/demo-site` 已验证登录、评论、上传、申诉通过 Python Thin Adapter 接入 Core。
- `apps/page-guard` 已提供嵌入式页面守护脚本和共享页面动作分类器。
- `scripts/page-action-scan.mjs` 已验证可扫描登录、注册、提交、搜索、保存、删除、菜单、分页、弹窗触发、上传等页面控件。
- XSS 样例会被 Fast-Path 拦截，且 `llm_called=false`。
- 混合负载与重启恢复测试已覆盖 skip/async/sync/Fast-Path 流量、SQLite 账本恢复、申诉审核状态恢复、动作撤销与过期恢复。
- 本地供应商故障注入已覆盖 fake OpenAI-compatible provider 成功脱敏、HTTP 500 降级和熔断后停止远程请求。
- 供应商/代理故障演练脚本已验证：默认坏代理模式不改真实配置、不调用 live provider，3 次受控失败后熔断打开。
- 供应商/代理故障演练可输出脱敏 Markdown 报告，避免暴露 API key、密钥路径、代理 URL、API base、原始 Prompt 和原始请求体。
- Docker 部署入口已补齐，部署资产测试覆盖健康检查、预检启动、命名卷和镜像上下文保密边界。
- Windows 计划任务常驻入口已补齐，启动脚本会先跑配置预检，再启动服务并写入本地日志。
- Windows SCM 包装入口已补齐，使用用户提供的 WinSW 二进制生成服务包装，不下载或提交第三方二进制。
- 备份、恢复和日志轮转脚本已补齐，备份排除 secrets，恢复需要显式 `-Force`。

## 3. P0 硬约束对齐

| 硬约束 | 当前状态 | 说明 |
|---|---:|---|
| 核心逻辑只在 Core Service | 已对齐 | 主要逻辑集中在 `services/core-service/atee_core`。 |
| Thin Adapter 只做请求提取和 Core 调用 | 已对齐 | Node/Python adapter 仅转发上下文。 |
| 不在每个 SDK 重复安全引擎 | 已对齐 | 未实现多语言完整 SDK。 |
| 请求先过 Real IP 和 Fast-Path | 已对齐 | `/v1/check` 和 `/v1/event` 共用 Core 流程。 |
| 异步路径前也必须过 Fast-Path | 已对齐 | `event()` 复用 `check()` 流程。 |
| Sync Path 不硬等 1.5 秒 LLM | 已对齐 | 已保留 3s/5s 策略配置，真实供应商失败会受控 fallback。 |
| Local Precheck 100ms，Remote 3s/5s | 部分对齐 | 配置、远程 hard timeout、fallback、预算和熔断已实现；当前 DeepSeek 实测配置为 10s/20s。 |
| Security Ledger Lite 默认 256MB | 部分对齐 | SQLite 摘要持久化已实现，异步 AI 审查队列已有重试/死信基础版；Ledger 自身异步写入队列仍未做。 |
| 低危事件聚合 | 已对齐 | 低危请求按 60 秒内存聚合，不在请求链路高频写 SQLite。 |
| 不保存 Prompt Packet 原文和原始请求体 | 已对齐 | 只保存摘要和哈希。 |
| 不允许 AI 生成可执行 regex | 已对齐 | 当前只支持本地固定规则和 `rule_hint`。 |
| 不修改业务数据库，不隐藏/删除内容 | 已对齐 | Action Executor 只记录受控动作。 |
| 管理台禁止危险 HTML 渲染 | 已对齐 | 使用 `textContent`，CSP 严格。 |
| 所有 Agent/用户输入按 untrusted_text | 已对齐 | 中文 display 也标明纯文本策略。 |
| 未配置可信代理禁止自动 IP 封禁 | 已对齐 | Tool Gateway 强制校验。 |
| 申诉白名单必须限流 | 部分对齐 | pending 申诉已持久化；限流窗口仍为内存态。 |
| Break-Glass 不默认用 URL 明文参数 | 已对齐 | 仅检查 `X-ATEE-Bypass`，不支持 URL 参数。 |
| P0 提供纯小白 Onboarding Wizard | 部分对齐 | 已有中文步骤接口和管理台展示，未做完整表单流。 |

## 4. Phase 00-21 对齐矩阵

| 阶段 | 文档要求 | 当前状态 |
|---|---|---:|
| 00 项目计划与 P0 锁定 | 计划、边界、仓库结构 | 已完成基础版 |
| 01 Schema 与共享类型 | RequestContext 等模型 | 部分完成，使用 dataclass，未做 JSON Schema/Pydantic |
| 02 Core Service 骨架 | 核心 API 与健康检查 | 已完成基础版 |
| 03 Trusted Real IP Resolver | 可信代理、头优先级、禁误封 | 已完成基础版 |
| 04 Fast-Path Rule Gate | Skip/Block/Rate limit/Report | 部分完成 |
| 05 Request Router | skip/block/sync/async | 已完成基础版 |
| 06 Sync Critical Path | 100ms/3s/5s 与 fallback | 部分完成，缺真实 LLM/fallback 细化 |
| 07 Async Review Path | 队列、重试、死信 | 已完成基础版，支持 SQLite 异步 AI 审查队列、管理端触发处理、重试与死信 |
| 08 Prompt Packet Compiler | 脱敏、哈希、allowed/forbidden | 已完成基础版 |
| 09 Remote LLM Gateway | OpenAI-compatible、预算、心跳 | 部分完成，已实现 OpenAI-compatible 调用、配置化代理、预算保护、失败熔断和可重复 Agent AI 全流程冒烟脚本 |
| 10 Agent Decision + final_confidence | JSON 校验、公式、阈值 | 已完成基础版 |
| 11 Tool Gateway | 动作边界与模式约束 | 已完成基础版 |
| 12 Action Executor | 可撤销、有期限、幂等 | 部分完成，执行记录已支持 SQLite 恢复、撤销和过期清理 |
| 13 Security Ledger Lite | 256MB、聚合、异步落盘 | 部分完成，已支持 SQLite 摘要持久化；异步 AI 审查队列已落盘，Ledger 写入队列仍未做 |
| 14 Appeal + Fast-Path Lock | 白名单与限流 | 部分完成，pending 申诉、审核结果已支持 SQLite 恢复，限流窗口仍为内存态 |
| 15 Break-Glass Bypass | Header、日志、轮换提示 | 部分完成 |
| 16 Admin Console | React + Ant Design 管理台 | 已完成 P0 最终形态：React + Ant Design + Vite，保留 CSP nonce、中文界面、申诉/动作/账本/网关入口 |
| 17 Onboarding Wizard | 纯小白详细引导 | 部分完成，已有中文步骤展示 |
| 18 Runtime Modes | observe/auto/degraded/read-only/pause | 已完成基础版 |
| 19 Tests | Unit/API/Security/E2E/Load | 部分完成，当前 145 个 Python 测试通过；已补 HTTP E2E、Browser E2E 62 项、React 管理台构建验收、CSP nonce 验收、功能封禁与申诉自动解封测试、Page Guard 分类器回归、页面动作扫描演练、基础并发压测、混合负载重启恢复、本地供应商故障注入、供应商/代理故障演练脚本、预算限流演练、小批量 live 演练入口、Agent AI 全流程冒烟脚本、本地发布闸门、备份恢复联调演练、脱敏演练报告、可控 RPS 长时压测入口、部署资产测试、维护脚本测试、管理操作审计身份绑定测试、SSO 身份注入示例测试、生产反向代理冒烟测试和 Admin Token 轮换复验测试 |
| 20 Docs | 用户/开发/安全文档 | 部分完成 |
| 21 Final Integration | 全链路验收报告 | 部分完成，主干已合入 Page Guard 和功能封禁闭环；生产现场全链路验收仍未完成 |

## 5. 架构边界对齐

### Core Service

当前 Core Service 已承载：

- 真实 IP 解析
- Fast-Path
- 请求路由
- Prompt Packet 编译
- Remote LLM Gateway mock / OpenAI-compatible
- 决策引擎
- Tool Gateway
- 动作执行器
- Ledger Lite
- Appeal
- Runtime Mode
- Config Store
- Admin Console 静态资源

这与“核心逻辑只写一次”的方向一致。

### Thin Adapter

当前 adapter 示例保持薄：

- `adapters/node-express/atee-adapter.js`
- `adapters/python-fastapi/atee_adapter.py`

它们只构造请求上下文并调用 Core Service，没有重复实现安全判断。

### Demo Site

当前新增 `apps/demo-site`：

- 登录链路调用 Core `/v1/check`。
- 评论和上传链路调用 Core `/v1/event`。
- 申诉链路调用 Core `/v1/appeal`。
- 页面使用外部 CSS/JS，返回文本按 `textContent` 渲染。

### Admin Console

当前管理台已迁移为 React + Ant Design + Vite 构建形态。
运行时仍由 Core Service 直接托管 `/admin/index.html`、`/admin/styles.css` 和 `/admin/admin.js`，不依赖外部 CDN。

## 6. 主要风险与偏差

| 风险 | 等级 | 说明 |
|---|---:|---|
| DeepSeek 依赖代理配置 | 中 | 直连 443 不通，但通过生产化 `llm_proxy_url` 配置已验证成功。 |
| DPAPI 密钥绑定 Windows 用户上下文 | 中 | 已新增启动前配置预检；生产服务账号部署时仍需在该账号下迁移密钥或接入环境变量/密钥管理器。 |
| Appeal/Action 管理闭环不完整 | 中 | 申诉审核、动作撤销和过期清理已完成基础版；仍缺真实业务侧撤销适配和批量运营工作流。 |
| 管理台无认证 | 高 | 当前适合本地演示，不适合暴露到生产网络。 |
| 配置文件无并发锁 | 中 | 单进程演示可用，多进程部署需加锁或改数据库。 |
| Admin Console 运行期 CSP 兼容 | 中 | 已使用服务端动态 nonce、AntD `ConfigProvider` CSP、样式标签 nonce 兼容层和 `style-src-attr` 最小放行；Browser E2E 已验证无控制台 CSP 错误。 |
| 压测和恢复测试仍偏轻 | 中 | 已补 HTTP E2E、Browser E2E、基础并发压测、混合负载重启恢复、本地供应商故障注入、坏代理演练、真实供应商 live 恢复探针、预算限流演练、小批量 live 演练入口、真实供应商小批量 live 执行、备份恢复联调演练、可控 RPS 长时压测入口、30 分钟、60 分钟和 120 分钟可控 RPS 压测；仍缺更高 RPS 或更长周期的生产环境压测。 |
| Docker 未在本机实构建 | 低 | 已补 Dockerfile/compose 和文件级测试；当前机器未安装 Docker CLI，镜像构建需在有 Docker 的环境复测。 |
| WinSW 二进制未内置 | 低 | 已补 WinSW 安装/卸载脚本和配置生成；出于供应链边界不下载或提交第三方二进制，需用户提供 vetted WinSW exe。 |
| 备份恢复未覆盖 secrets | 中 | 备份脚本刻意排除 `config/secrets/`；生产需要单独由密钥管理器或同账号 DPAPI 迁移流程覆盖密钥。 |
| Break-Glass 仅状态检查 | 中 | 缺完整恢复操作流、密钥生成和审计闭环。 |
| Prompt Packet 脱敏有限 | 中 | 已处理常见字段，但无法保证自由文本隐私 100% 识别。 |

## 7. 下一步对齐建议

建议按以下顺序推进：

1. 执行更高强度或更接近生产的压测
   在现有 HTTP/Browser E2E、混合恢复测试、本地 fake provider 故障注入、坏代理演练、单次 live 恢复探针、预算限流演练、小批量 live 演练入口、真实供应商小批量 live 执行、备份恢复联调演练、可控 RPS 长时压测入口、30 分钟、60 分钟和 120 分钟压测基础上，下一轮可提高 RPS、延长至 4 小时以上，或在生产等价环境复测。

2. 管理台生产化收口
   React + Ant Design 最终形态、主要功能闭环、管理认证、操作审计身份绑定、构建体积拆分、SSO 示例、生产冒烟脚本和 Admin Token 轮换复验脚本已完成；下一轮建议在目标服务器做真实证书、域名、重启命令和 SSO 身份注入联调。

3. 安装与运维
   Docker、Windows 计划任务、WinSW SCM 包装、维护脚本和临时目录备份恢复联调已补基础版；继续补真实生产密钥迁移说明。

## 8. 当前验收判断

当前项目可以判定为：

```text
P0 工程骨架：通过
P0 本地演示：通过
P0 安全边界原型：部分通过
P0 生产部署：未通过
最终 v3.3 全链路验收：未通过
```

短期目标应继续保持“先闭环、再加深”的节奏：真实模型供应商已通过配置化代理连通，并已补预算保护、失败熔断、管理入口、Appeal/Action 基础闭环、浏览器 E2E、混合负载恢复测试、本地供应商故障注入、坏代理演练、真实供应商 live 恢复探针、预算限流演练、小批量 live 演练入口、真实供应商小批量 live 执行、备份恢复联调演练、可控 RPS 长时压测入口、30 分钟压测、60 分钟压测、120 分钟压测、Docker 部署入口、Windows 常驻入口、WinSW SCM 包装、维护脚本、React + Ant Design 管理台、SSO 示例、生产冒烟验收和 Admin Token 轮换复验；下一步应进入目标服务器真机验收，或做更高 RPS/更长周期压测。

## 9. 本轮迭代记录

### 2026-05-13 Step 1：基线确认

- 当前工作区包含上一轮 Remote LLM Gateway mock 改动，尚未提交。
- 当前测试基线：19 个单元测试通过。
- 当前 Ledger 状态：仅内存记录和内存聚合，重启后会丢失。
- 本轮目标：实现 SQLite Ledger Lite，使中高危事件、申诉、动作摘要具备初步持久化能力；低危事件继续内存聚合，避免请求链路高频写库。

### 2026-05-13 Step 2：SQLite Ledger Lite 存储层

- 新增 SQLite 后端，表名为 `ledger_records`。
- 中/高危 Ledger 记录写入 SQLite，同时保留最近内存记录。
- 低危请求继续走 60 秒内存聚合，不写 SQLite，符合“请求链路不高频写库”的 P0 原则。
- 新增 `ledger_sqlite_path` 配置，默认指向 `data/atee_ledger.sqlite3`。
- 新增最近记录查询能力，用于后续管理台和验收报告展示。
- 验证：19 个单元测试通过，Python 编译检查通过。

### 2026-05-13 Step 3：Core 查询接口与管理台入口

- Core Service 新增 `ledger_recent()` 查询方法。
- HTTP 层新增 `GET /v1/admin/ledger/recent?limit=10`。
- 管理台新增“最近账本”按钮，便于本地演示查看持久化摘要。
- 验证：19 个单元测试通过，Python 编译检查通过。

### 2026-05-13 Step 4：SQLite Ledger 测试与文档对齐

- 新增 SQLite Ledger 单元测试，覆盖中/高风险记录落库、低风险 skip 不高频写库、Core 重启后读取最近账本。
- 修复 Windows 下 SQLite 文件句柄未释放的问题：所有连接改为显式关闭，并在写入/建表后显式 `commit()`。
- 更新 README、开发 API 文档和项目进度报告，补充 `/v1/admin/ledger/recent`、`ledger_sqlite_path` 和 `data/atee_ledger.sqlite3` 说明。
- 对齐矩阵更新：Security Ledger Lite 从“内存版”推进为“SQLite 摘要持久化已完成，异步 AI 审查队列/恢复策略未完成”。
- 当前验证：`tests.test_core` 19 个测试通过；全量测试结果见 Step 5。

### 2026-05-13 Step 5：全量测试与静态编译验证

- 全量单元测试通过：`python -m unittest discover -s tests`，共 22 个测试。
- Python 编译检查通过：`services/core-service/atee_core/*.py` 全部可编译。
- 验证范围新增覆盖：SQLite 落库、低危 skip 不落库、Core 重启后查询最近账本。
- 下一步进入本地服务重启和 HTTP 接口验证。

### 2026-05-13 Step 6：本地服务重启与 HTTP 验证

- 已停止旧服务进程并用当前代码重启，服务地址保持 `http://127.0.0.1:8787/`。
- `/v1/runtime/status` 显示 `sqlite_enabled=true`，SQLite 路径为 `data/atee_ledger.sqlite3`，且不保存原始 Prompt 或原始请求体。
- `POST /v1/check` 登录样例成功进入 `sync_agent`，新增一条 `agent_decision` 持久化记录。
- `GET /v1/admin/ledger/recent?limit=5` 成功返回最新 SQLite 账本摘要。
- 低风险 `GET /public` 样例进入 `skip`，只增加内存聚合窗口，SQLite 持久化记录数不变。
- `server.err.log` 当前为空，未发现启动或请求处理错误。

### 2026-05-13 Step 7：Appeal/Action SQLite 存储层

- `AppealService` 新增 `appeals` SQLite 表，启动时加载 `pending` 申诉，提交新申诉时写入 SQLite。
- `ActionExecutor` 新增 `action_records` SQLite 表，真实执行动作时写入 SQLite，启动时恢复动作记录列表。
- Core Service 复用现有 `ledger_sqlite_path`，让 Ledger、Appeal、Action 共享项目内 SQLite 文件，暂不新增配置项。
- 兼容性验证：`python -m unittest tests.test_core` 通过，当前 19 个核心测试保持绿色。
- 下一步补专门的重启恢复测试，并将全量测试结果更新到本报告。

### 2026-05-13 Step 8：Appeal/Action 重启恢复测试

- 新增申诉恢复测试：提交申诉后重启 Core Service，`pending_appeals` 仍为 1，再次提交同一 `punishment_id` 返回“已有待处理申诉”。
- 新增动作恢复测试：自动模式下触发 Fast-Path XSS 挑战动作，重启后 `actions_executed` 仍为 1。
- 修正旧申诉限流测试的隔离方式，改为临时配置目录，避免读取本地演示 SQLite 中的历史数据。
- 验证：`python -m unittest tests.test_core` 通过，当前 21 个核心测试保持绿色。

### 2026-05-13 Step 9：文档口径与全量验证

- README 和开发 API 文档补充说明：同一个 `data/atee_ledger.sqlite3` 现在包含 `ledger_records`、`appeals`、`action_records` 三类表。
- 项目进度报告更新：Appeal/Action 基础持久化与重启恢复已完成；剩余缺口调整为申诉审核处理流、动作撤销和过期清理。
- 下一步建议调整：优先补 Demo Site + Thin Adapter E2E；真实模型供应商接入需要外部 API 配置。
- 全量单元测试通过：`python -m unittest discover -s tests`，共 24 个测试。
- Python 编译检查通过：`services/core-service/atee_core/*.py` 全部可编译。

### 2026-05-13 Step 10：本地服务 Appeal/Action HTTP 恢复验证

- 已用当前代码重启本地服务，服务地址保持 `http://127.0.0.1:8787/`。
- 通过 `POST /v1/appeal` 新增一条申诉，`pending_appeals` 从 1 增至 2。
- 临时切换到自动模式并解除暂停，使用 Fast-Path XSS 样例触发真实 `challenge` 动作，`actions_executed` 从 0 增至 1。
- 已将服务恢复到 `observe` + `agent_paused=true`，随后再次重启服务。
- 重启后 `pending_appeals=2`、`actions_executed=1`，说明 pending 申诉和执行动作均从 SQLite 恢复。
- 重启后重复提交同一申诉返回 `pending_appeal_already_exists`。
- `server.err.log` 当前为空，未发现启动或请求处理错误。

### 2026-05-13 Step 11：Demo Site + Thin Adapter E2E

- 新增 `apps/demo-site` 最小业务站点，提供登录、评论、上传、申诉四个业务入口。
- Demo Site 使用现有 Python Thin Adapter 调用 Core Service，没有复制安全判断逻辑。
- Python Thin Adapter 新增 `appeal()` 入口，并允许 `build_context()` 携带 `event_type`。
- Demo UI 采用外部 `styles.css` 和 `demo.js`，不使用内联脚本，展示结果使用 `textContent`。
- 新增本地视觉资产 `assets/flow.svg`，作为 Demo Site 的 ATEE 标识。
- 新增 `tests/test_demo_site.py`，覆盖页面 CSP 结构、纯文本渲染约束、登录/评论/上传/申诉接入 Core。
- 验证：`python -m unittest tests.test_demo_site` 通过，3 个测试。

### 2026-05-13 Step 12：Demo 全量测试与文档对齐

- README 新增 Demo Site 启动方式：`python apps\demo-site\server.py`，默认地址 `http://127.0.0.1:8790/`。
- 开发 API 文档新增 Demo Site API 映射说明。
- 项目进度报告更新 Demo Site 完成项和剩余风险。
- 全量单元测试通过：`python -m unittest discover -s tests`，共 27 个测试。
- Python 编译检查通过：Core 模块、Demo server 和 Python Thin Adapter 全部可编译。

### 2026-05-13 Step 13：Demo Site 本地 HTTP 验证

- Core Service 保持运行在 `http://127.0.0.1:8787/`。
- Demo Site 已启动在 `http://127.0.0.1:8790/`，首页返回 200。
- `POST /api/login` 通过 Demo server 和 Python Thin Adapter 进入 Core `/v1/check`，路由为 `sync_agent`。
- `POST /api/comment` 使用 XSS 样例，通过 Fast-Path 得到 `fast_path_block` 和 `challenge`。
- `POST /api/upload` 进入 Core `/v1/event`，路由为 `async_agent`，事件类型为 `file_upload`。
- `POST /api/appeal` 进入 Core `/v1/appeal`，返回 202，Core `pending_appeals` 增加。
- `server.err.log` 和 `demo.err.log` 当前均为空，未发现启动或请求处理错误。

### 2026-05-13 Step 14：OpenAI-Compatible 网关与密钥保密接入

- `RemoteLLMGateway` 新增 `openai_compatible` 模式，调用 `{llm_api_base}/chat/completions`。
- 新增 `llm_api_key_file` 和 `llm_api_key_env` 配置；状态、测试和配置接口只返回是否配置，不返回密钥值。
- 公网供应商强制 HTTPS；`http://` 公网 base 会在发送 Authorization 前返回 `insecure_api_base_requires_https`。
- 读取密钥时会剥离 UTF-8 BOM，避免 Windows 写入文件后污染 Authorization header。
- 本地 DeepSeek 配置已安装到忽略文件：provider、model、HTTPS base 和密钥文件路径均已配置。
- 验证：`config/secrets/` 已加入 `.gitignore`；可跟踪区域扫描未发现 `sk-` 形式密钥。

### 2026-05-13 Step 15：DeepSeek 连接测试与网络诊断

- 全量单元测试通过：`python -m unittest discover -s tests`，共 30 个测试。
- Python 编译检查通过：Core 模块、Demo server 和 Python Thin Adapter 全部可编译。
- Core Service 已重启，`/v1/runtime/status` 显示 `llm_mode=openai_compatible`、provider 为 `deepseek`、base/key/model 均已配置。
- `/v1/admin/llm/test` 返回受控失败：`provider_request_failed`，未暴露密钥或供应商响应体。
- 不带密钥的网络探测结果：`<provider-host>` DNS 可解析、ping 可达，但 TCP 443 连接失败。
- 当前判断：ATEE 真实供应商接入代码已完成，外部连通性或供应商/网络策略仍需处理。

### 2026-05-13 Step 16：本地代理配置与 DeepSeek 连通成功

- 检测到本机代理端口并完成脱敏记录。
- 不带密钥的 Python 代理探测已到达 DeepSeek，并得到 HTTP 层响应。
- Core Service 已通过 `HTTP_PROXY` / `HTTPS_PROXY` 注入本地代理重启。
- `run-atee-windows.cmd` 已设置同样的本地代理环境变量，便于下次 Windows 启动复用。
- DeepSeek base 保持为已配置的 HTTPS OpenAI-compatible endpoint。
- 远程超时从 `3s/5s` 调整为 `10s/20s`，适配当前模型约 6 秒的响应延迟。
- `/v1/admin/llm/test` 已通过：`ok=true`，reason 为 `provider_json_decision`。
- `server.err.log` 当前为空；可跟踪区域扫描未发现密钥。

### 2026-05-13 Step 17：生产化代理与 DPAPI 加密密钥

- 新增 `llm_proxy_url` 配置项，Remote LLM Gateway 可直接使用配置化代理，不再依赖启动脚本硬编码环境变量。
- 公开配置和运行状态只返回 `llm_proxy_configured` 与 `llm_api_key_file_configured`，不返回代理 URL 或密钥文件路径。
- 新增 Windows DPAPI CurrentUser 加密密钥文件支持，`llm_api_key_file` 可指向 `*.dpapi.json`。
- 新增 `services/core-service/encrypt_secret.py`，用于将明文密钥迁移为 DPAPI 加密文件。
- 当前 DeepSeek 密钥已迁移到 `config/secrets/<encrypted-provider-key>.dpapi.json`，旧明文文件已覆盖为迁移标记。
- Core Service 已在无 `HTTP_PROXY/HTTPS_PROXY` 环境变量的情况下重启，仅依赖 `llm_proxy_url` 连接 DeepSeek。
- `/v1/admin/llm/test` 已通过：`ok=true`，`proxy_configured=true`，`api_key_configured=true`。
- 全量单元测试通过：`python -m unittest discover -s tests`，共 32 个测试。

### 2026-05-13 Step 18：真实模型链路预算与失败熔断

- `RemoteLLMGateway` 新增每日预算状态：`llm_daily_budget_cents=0` 表示不限制；正数按每次远程尝试 1 cent 估算并在耗尽后返回 `llm_budget_exhausted`。
- 新增失败熔断：连续 3 次供应商请求失败或 hard timeout 后，60 秒内返回 `llm_circuit_open`，不再调用供应商。
- 成功远程调用会清空连续失败计数；预算窗口按本地日期每日重置。
- `/v1/runtime/status` 和 `/v1/admin/llm/test` 新增 `budget` 与 `circuit` 摘要，不返回 API Key、密钥路径、代理 URL 或原始 Prompt。
- DeepSeek 临时 HTTP 验证通过：`api_key_configured=true`、`proxy_configured=true`、`circuit.open=false`，`/v1/admin/llm/test` 返回 `ok=true`。
- 发现并记录生产部署注意事项：Windows DPAPI CurrentUser 密钥绑定创建它的用户上下文；若用 Windows 服务账号运行，需在该账号下迁移密钥或改用 `llm_api_key_env`/密钥管理器。
- 全量单元测试通过：`python -m unittest discover -s tests`，共 34 个测试。
- Python 编译检查通过：Core 模块、加密脚本、Demo server 和 Python Thin Adapter 全部可编译。

### 2026-05-13 Step 19：上下文审查、启动预检与文件清理

- 审查本轮问题链路后，将“密钥相对路径依赖启动目录”的隐患生产化修复：`llm_api_key_file`、`bypass_key_file` 和 `ledger_sqlite_path` 等相对路径统一按项目根目录解析。
- 新增 `services/core-service/check_config.py`，启动前验证远程模型配置、HTTPS base、密钥文件可读性和 DPAPI CurrentUser 解密上下文；失败时不打开服务端口。
- `run-atee-windows.cmd` 已接入配置预检，避免服务启动后才发现 DeepSeek 密钥或服务账号上下文不可用。
- 新增单元测试覆盖项目根目录相对密钥路径解析，防止不同启动目录导致 `api_key_configured=false`。
- 清理旧运行残留：删除 `server*.log`、`demo*.log` 和所有 `__pycache__` 目录；未删除 `config/config.json` 或 `data/atee_ledger.sqlite3`。
- 加密密钥文件存在后，删除旧的 `config/secrets/<provider-key-input>.txt` 输入文件，避免本地密钥目录里残留迁移标记或明文风险。
- 冲突/重复文件扫描未发现 `conflict`、`copy`、`old`、`*.bak`、`*.tmp`、`*.zip` 等候选文件。
- 配置预检通过：`python services\core-service\check_config.py`。
- 全量单元测试通过：`python -m unittest discover -s tests`，共 35 个测试。
- Python 编译检查通过：Core 模块、配置预检、加密脚本、Demo server 和 Python Thin Adapter 全部可编译。

### 2026-05-14 Step 20：管理台基础升级

- 当前仓库没有前端构建链和本地 React/Ant Design 依赖；为保持离线可运行和严格 CSP，本步先升级原生静态管理台，仍记录“未达到 React + Ant Design 最终形态”的偏差。
- 仪表盘新增模型网关、熔断状态、预算余额和活跃动作卡片，直接展示 `/v1/runtime/status` 的生产健康字段。
- 管理台新增待处理申诉、执行动作、清理过期动作入口，并增加申诉审核和动作撤销表单区域。
- 所有动态内容继续使用 `textContent` 渲染，不引入内联脚本、内联样式或外部 CDN。
- 新增管理台结构测试，覆盖申诉审核、动作撤销、模型健康字段和相关 API 路径。

### 2026-05-14 Step 21：Appeal/Action 管理闭环

- Appeal Store 新增审核字段：`reviewed_at`、`resolution`、`admin_note_untrusted_text`，旧 SQLite 表会自动迁移。
- Core 新增 `GET /v1/admin/appeals?status=pending|approved|rejected|all` 和 `POST /v1/admin/appeals/review`。
- 申诉审核支持 `approved` / `rejected`，审核后从 pending 内存集合移除，并写入 Ledger 摘要。
- Action Store 新增 `status`、`revoked_at`、`revoke_reason_untrusted_text`，旧 SQLite 表会自动迁移。
- Core 新增 `GET /v1/admin/actions?status=active|revoked|expired|all`、`POST /v1/admin/actions/revoke`、`POST /v1/admin/actions/cleanup-expired`。
- 动作撤销和过期清理只更新 ATEE 自身动作记录，不修改业务数据库、不隐藏内容、不删除内容，继续遵守 P0 工具边界。
- 新增单元测试覆盖申诉审核持久化、动作列表、动作撤销、过期清理和管理台入口。
- 全量单元测试通过：`python -m unittest discover -s tests`，共 38 个测试。
- 配置预检通过：`python services\core-service\check_config.py`。
- Python 编译检查通过：Core 模块、配置预检、加密脚本、Demo server 和 Python Thin Adapter 全部可编译。

### 2026-05-14 Step 22：HTTP E2E 与基础并发压测

- 新增 `tests/test_http_e2e.py`，测试会启动随机 localhost 端口的临时 Core Service，使用 mock LLM，避免触碰真实 DeepSeek 密钥。
- HTTP E2E 覆盖管理台 HTML/JS 静态资源、运行状态、`/v1/check` 安全请求、Fast-Path XSS 拦截、申诉提交、申诉审核、自动模式动作执行、动作列表和动作撤销。
- 基础并发压测覆盖 40 个并行 `/v1/check` 请求，混合低危 skip 和普通评论路径，验证请求均返回结构化结果，Ledger 聚合与持久化记录正常增长。
- 尝试使用 Codex in-app browser 打开 `http://127.0.0.1:8787/`，本地 Core 端口可连接，但当前 in-app browser 后端不可用；本机 Python 环境也未安装 Playwright/Selenium，因此真实浏览器自动化标记为待环境恢复后复测。
- 临时 Core 进程已停止，未留下常驻服务。

### 2026-05-14 Step 23：浏览器环境安装与 Browser E2E

- 已在项目本地安装 `playwright-core`，新增 `package.json`、`package-lock.json`，并将 `node_modules/` 加入 `.gitignore`。
- 新增 `scripts/browser-e2e.mjs` 和 `npm run e2e:browser`，复用系统 Chrome/Edge，不下载浏览器包。
- Browser E2E 会启动随机 localhost 端口的临时 mock Core Service，打开管理台，验证关键 UI 文本，提交并审核申诉，切换自动模式，触发 Fast-Path 动作，列出并撤销动作，检查浏览器 console error，然后关闭浏览器和临时服务。
- 为避免 Chrome 自动请求 favicon 产生无关 404，Core Service 新增 `/favicon.ico` 空响应，HTTP E2E 已覆盖该状态。
- `npm run e2e:browser` 已通过：返回 `ok=true`，完成 9 个浏览器交互检查。

### 2026-05-14 Step 24：混合负载与重启恢复测试

- 新增 `tests/test_recovery_load.py`，在临时配置目录和临时 SQLite 数据库内运行，不触碰真实 DeepSeek 密钥和本地演示数据。
- 测试混合 96 个请求，覆盖静态资源 skip、普通评论 async、登录 sync 和 Fast-Path XSS 拦截，并验证结果均为结构化响应。
- 测试随后提交 3 条申诉，分别走 approved、rejected、pending 状态，重启 Core Service 后确认三类状态均从 SQLite 恢复。
- 测试自动模式下生成动作记录，覆盖动作撤销和过期清理，重启后确认 revoked 与 expired 动作仍可通过管理接口查询。
- 当前验证：`python -m unittest tests.test_recovery_load` 通过；全量测试结果更新为 41 个测试通过。

### 2026-05-14 Step 25：供应商故障注入与本地压力脚本

- 新增 `tests/test_provider_faults.py`，启动本地 fake OpenAI-compatible provider，避免触碰真实 DeepSeek 密钥。
- 成功路径验证：Core 发送给供应商的请求只包含脱敏摘要，不包含原始密码、原始密钥字段值；公开响应也不返回 API key 或原始敏感字段。
- 故障路径验证：fake provider 返回 HTTP 500 时，Core 受控降级为本地 `rule_hint` 路径；连续 3 次失败后熔断打开，第 4 次请求不再触达供应商。
- 修正 `RemoteLLMGateway` 的 HTTPError 分支，显式关闭异常响应句柄，避免供应商 500 情况下留下资源清理警告。
- 新增 `scripts/local-stress-check.py`，可通过 `python scripts\local-stress-check.py --requests 500 --workers 8` 做更大规模的本地混合负载与重启恢复检查。
- 当前验证：`python -m unittest tests.test_provider_faults` 通过；`python scripts\local-stress-check.py --requests 180 --workers 6` 返回 `ok=true`；全量测试结果更新为 43 个测试通过。

### 2026-05-14 Step 26：供应商/代理故障演练脚本

- 新增 `scripts/provider-fault-drill.py`，只读现有 `config/config.json`，将远程模型配置复制到内存中演练，不修改真实配置文件。
- 默认演练使用内存坏代理 `http://127.0.0.1:9`，验证前 3 次请求受控失败，第 4 次返回 `llm_circuit_open`，说明熔断已打开且不再继续打供应商。
- 脚本输出只包含 provider/model、配置是否存在、熔断状态和原因码，不输出 API key、密钥文件路径、代理 URL 或原始 Prompt。
- 新增 `tests/test_provider_fault_drill.py`，用临时配置和环境变量密钥验证脚本可重复运行、输出不泄密，并且默认不调用 live provider。
- 当前验证：`python -m unittest tests.test_provider_fault_drill` 通过；`python scripts\provider-fault-drill.py --bad-proxy-url http://127.0.0.1:9` 返回 `ok=true`；全量测试结果更新为 44 个测试通过。

### 2026-05-14 Step 27：供应商/代理故障演练报告

- `scripts/provider-fault-drill.py` 新增 `--report <path>` 参数，可在 JSON 摘要之外写出 Markdown 演练报告。
- 报告包含生成时间、总体结论、provider/model 标签、配置存在性、坏代理演练原因码、熔断状态和 live probe 是否跳过。
- 报告明确省略 API key、密钥文件路径、代理 URL、API base URL、原始 Prompt 和原始请求体，便于向运维或评审分享。
- `tests/test_provider_fault_drill.py` 新增报告输出测试，验证 Markdown 报告存在、包含 `llm_circuit_open`，且不包含测试密钥、坏代理 URL 或 API base。
- 当前验证：`python -m unittest tests.test_provider_fault_drill` 通过；全量测试结果更新为 45 个测试通过。

### 2026-05-14 Step 28：Docker 部署入口

- 新增 `Dockerfile`，使用 Python slim 镜像运行 Core Service，设置 `ATEE_HOST=0.0.0.0`、暴露 `8787`，并在打开端口前执行 `services/core-service/check_config.py`。
- 新增 `.dockerignore`，排除本地 `config/config.json`、`config/secrets/`、SQLite 数据、日志、报告、`node_modules` 和压缩包等，不把本机运行状态和密钥上下文带入镜像。
- 新增 `docker-compose.yml`，使用 `atee-config` 与 `atee-data` 命名卷持久化配置和 SQLite 数据，避免直接挂载本机 secrets 目录。
- `services/core-service/run_server.py` 新增 `ATEE_HOST` / `ATEE_PORT` 环境变量绑定支持，本机默认仍为 `127.0.0.1:8787`。
- 新增 `docs/deployment.md`，说明 Docker 快速启动、密钥注入、DPAPI 不可移植、健康检查和启动预检。
- 新增 `tests/test_deployment_assets.py`，覆盖 Dockerfile 健康检查、启动预检、`.dockerignore` 保密边界、compose 命名卷和环境化绑定。
- 当前验证：`python -m unittest tests.test_deployment_assets` 通过；本机未安装 Docker CLI，`docker compose up --build` 需在有 Docker 的环境复测；全量测试结果更新为 49 个测试通过。

### 2026-05-14 Step 29：Windows 计划任务常驻入口

- 新增 `scripts/windows/start-atee-core.ps1`，设置 `ATEE_HOST` / `ATEE_PORT`，创建 `logs/`，运行 `check_config.py`，预检通过后启动 `run_server.py`。
- 新增 `scripts/windows/install-atee-task.ps1`，使用 Windows Task Scheduler 注册 ATEE Core Service 计划任务；默认 `AtLogOn`，可用管理员 PowerShell 指定 `-Trigger AtStartup`。
- 新增 `scripts/windows/uninstall-atee-task.ps1`，停止并删除计划任务。
- `.gitignore` 新增 `logs/`，避免运行日志进入版本库。
- `docs/deployment.md`、README 和开发 API 文档补充 Windows 计划任务安装、卸载、日志路径和限制说明；当前方案是 P0 无额外依赖入口，不是 SCM 原生服务。
- `tests/test_deployment_assets.py` 新增 3 个测试，覆盖启动脚本预检顺序、日志文件、计划任务注册和卸载脚本。
- 当前验证：`python -m unittest tests.test_deployment_assets` 通过；PowerShell 语法检查通过；全量测试结果更新为 52 个测试通过。

### 2026-05-14 Step 30：Windows SCM / WinSW 包装入口

- 新增 `scripts/windows/install-atee-winsw.ps1`，要求用户提供 vetted WinSW exe，脚本复制该二进制到 `runtime/winsw/` 并生成 `ATEECore.xml`。
- WinSW 生成的服务仍调用 `scripts/windows/start-atee-core.ps1`，因此保留配置预检、`ATEE_HOST` / `ATEE_PORT` 和 `logs/` 输出。
- 新增 `scripts/windows/uninstall-atee-winsw.ps1`，调用 wrapper stop/uninstall，并支持 `-RemoveFiles` 清理生成的 wrapper exe/xml。
- `.gitignore` 新增 `runtime/`，避免本地生成的 WinSW wrapper 文件进入版本库。
- 文档补充 WinSW SCM 安装/卸载步骤，并明确仓库不下载或提交第三方 WinSW 二进制；DPAPI CurrentUser 密钥需在服务账号上下文中创建或改用 `llm_api_key_env`/密钥管理器。
- `tests/test_deployment_assets.py` 新增 3 个测试，覆盖 WinSW 安装脚本不联网下载、复用启动预检脚本、生成 roll-by-size 日志配置、卸载脚本和 `runtime/` 忽略规则。
- 当前验证：`python -m unittest tests.test_deployment_assets` 通过；PowerShell 语法检查通过；全量测试结果更新为 55 个测试通过。

### 2026-05-14 Step 31：备份恢复与日志轮转脚本

- 新增 `scripts/windows/backup-atee-state.ps1`，备份 `config/config.json`、`data/atee_ledger.sqlite3` 及 WAL/SHM sidecar，传入 `-IncludeLogs` 时可包含日志。
- 备份 manifest 明确排除 `config/secrets/`、`*.key`、`*.secret`、`node_modules` 和 `runtime`；`.gitignore` 与 `.dockerignore` 新增 `backups/`。
- 新增 `scripts/windows/restore-atee-state.ps1`，恢复前要求目标项目目录存在，且必须显式传入 `-Force`；若备份中包含 `config/secrets` 会拒绝恢复。
- 新增 `scripts/windows/rotate-atee-logs.ps1`，按 `MaxBytes` 轮转 `logs/*.log`，并按 `KeepFiles` 保留最近归档。
- `docs/deployment.md`、README 和开发 API 文档补充备份、恢复和日志轮转命令。
- `tests/test_deployment_assets.py` 新增 4 个测试，覆盖备份排除 secrets、恢复保护、日志轮转保留策略和 Docker 上下文排除 backups。
- 当前验证：`python -m unittest tests.test_deployment_assets` 通过；PowerShell 语法检查通过；临时目录备份/恢复演练通过；全量测试结果更新为 59 个测试通过。

### 2026-05-14 Step 32：真实供应商 live 恢复演练

- 使用 `python scripts\provider-fault-drill.py --bad-proxy-url <bad-proxy> --include-live --report <temp-report>` 完成一次受控恢复演练。
- 坏代理阶段只在内存中覆盖代理配置，不修改 `config/config.json`；前 3 次请求返回 `provider_timeout`，第 4 次返回 `llm_circuit_open`，确认熔断打开且停止继续触达供应商。
- live 阶段使用当前已配置的 DeepSeek OpenAI-compatible 网关、DPAPI 加密密钥和配置化代理，单次探针返回 `ok=true`，原因码为 `provider_json_decision`，延迟 8110 ms。
- 演练 JSON 摘要与 Markdown 报告均只输出 provider/model、配置存在性、预算/熔断摘要、原因码和延迟，不输出 API key、密钥文件路径、代理 URL、API base、原始 Prompt 或原始请求体。
- 当前结论：真实供应商短链路恢复探针已通过；后续生产验证重点转为批量/长时 live 压测和预算限流策略。

### 2026-05-14 Step 33：长时压测入口与脱敏报告

- `scripts/local-stress-check.py` 新增 `--duration-seconds`，支持按时长运行本地混合负载；未指定时仍保持原有 `--requests` 计数模式。
- 时长模式新增 `--max-requests` 可选安全上限，便于短时 CI 验证和生产演练时控制请求量。
- 脚本 JSON 摘要新增 `mode`、`elapsed_seconds`、`throughput_rps`、`target_duration_seconds`、`max_requests` 和 `report_path`，方便记录实际吞吐。
- 新增 `--report <path>` 输出脱敏 Markdown 报告，只记录路由计数、恢复检查和吞吐摘要；不输出 API key、密钥文件路径、代理 URL、API base、原始 Prompt 或原始请求体。
- 新增 `tests/test_local_stress_check.py`，覆盖计数模式、时长模式、报告生成和报告脱敏。
- 当前验证：`python -m unittest tests.test_local_stress_check` 通过；`python scripts\local-stress-check.py --duration-seconds 1 --max-requests 120 --workers 4 --report <temp-report>` 返回 `ok=true`，完成 64 个混合请求，覆盖 `skip`、`async_agent`、`sync_agent` 和 `fast_path_block`；全量测试结果更新为 61 个测试通过。

### 2026-05-14 Step 34：供应商预算/限流批量演练

- 新增 `scripts/provider-budget-drill.py`，启动临时本地 fake OpenAI-compatible provider，不调用真实供应商，不修改 `config/config.json`。
- 演练通过 `--attempts` 和 `--budget-cents` 构造批量远程尝试，验证预算耗尽后返回 `llm_budget_exhausted`，并且不再继续发送 provider 请求。
- 新增 `--report <path>` 输出脱敏 Markdown 报告，只记录尝试次数、预算、provider 实际调用数、原因码统计和预算摘要；不输出 API key、密钥文件路径、代理 URL、API base、原始 Prompt 或原始请求体。
- 新增 `tests/test_provider_budget_drill.py`，覆盖预算耗尽后停止 provider 调用、报告生成和报告脱敏。
- 当前验证：`python -m unittest tests.test_provider_budget_drill` 通过；`python scripts\provider-budget-drill.py --attempts 5 --budget-cents 2 --report <temp-report>` 返回 `ok=true`，5 次尝试中只有 2 次触达 fake provider，后 3 次返回 `llm_budget_exhausted`，熔断保持关闭；全量测试结果更新为 63 个测试通过。

### 2026-05-14 Step 35：备份恢复联调演练

- 新增 `scripts/backup-restore-drill.py`，在临时 source/target 安装目录中完成端到端备份恢复演练，不碰真实 `config/`、`data/` 或 `config/secrets/`。
- 演练 source 会生成 mock Core 配置、SQLite 安全摘要、pending 申诉、动作记录、日志文件和一个应被排除的 `config/secrets` 标记文件。
- 脚本调用现有 `scripts/windows/backup-atee-state.ps1` 与 `scripts/windows/restore-atee-state.ps1`，验证备份包包含 config、SQLite 和日志，且不包含 `config/secrets` 或排除标记。
- 恢复到 target 后会重新用 CoreService 读取恢复状态，验证持久化记录数、pending 申诉和动作记录可恢复，并验证 target 既有 secret 占位文件未被删除。
- 新增 `--report <path>` 输出脱敏 Markdown 报告；报告不输出 API key、密钥文件路径、代理 URL、API base、原始 Prompt、原始请求体或临时路径。
- 新增 `tests/test_backup_restore_drill.py`，覆盖端到端恢复、secrets 排除、target 既有 secret 保留和报告脱敏。
- 当前验证：`python -m unittest tests.test_backup_restore_drill` 通过；`python scripts\backup-restore-drill.py --report <temp-report>` 返回 `ok=true`，恢复后 persisted records 为 13，pending appeals 为 1，active actions 为 3；全量测试结果更新为 65 个测试通过。

### 2026-05-14 Step 36：小批量 live 演练入口

- 新增 `scripts/provider-live-batch-drill.py`，默认启动临时本地 fake OpenAI-compatible provider，不调用真实供应商。
- 脚本支持 `--attempts`、`--budget-cents` 和 `--report <path>`，输出原因码统计、延迟摘要、预算状态、熔断状态和 provider 调用计数。
- 显式传入 `--include-live` 时才调用当前配置的真实供应商；live 模式硬性限制最多 3 次尝试，并继续使用内存预算保护。
- Markdown 报告继续省略 API key、密钥文件路径、代理 URL、API base、原始 Prompt 和原始请求体。
- 新增 `tests/test_provider_live_batch_drill.py`，覆盖默认 fake 模式、报告脱敏和 live 模式尝试次数上限。
- 当前验证：`python -m unittest tests.test_provider_live_batch_drill` 通过；`python scripts\provider-live-batch-drill.py --attempts 4 --budget-cents 2 --report <temp-report>` 返回 `ok=true`，4 次尝试中 2 次触达 fake provider，后 2 次返回 `llm_budget_exhausted`；全量测试结果更新为 68 个测试通过。

### 2026-05-14 Step 37：真实供应商小批量 live 执行

- 使用 `python scripts\provider-live-batch-drill.py --include-live --attempts 3 --budget-cents 3 --report <temp-report>` 执行真实供应商小批量演练。
- 本次 live 模式使用当前已配置的 DeepSeek OpenAI-compatible 网关、DPAPI 加密密钥和配置化代理；脚本仍使用内存预算保护，不修改 `config/config.json`。
- 3 次真实调用全部返回 `provider_json_decision`，预算摘要显示 `daily_spend_cents=3`、`daily_remaining_cents=0`。
- 延迟摘要：最小 5155 ms，最大 9852 ms，平均 7225 ms；熔断状态保持 `open=false`，连续失败数为 0。
- 演练 JSON 摘要与 Markdown 报告均只输出配置存在性、原因码统计、预算/熔断摘要和延迟摘要，不输出 API key、密钥文件路径、代理 URL、API base、原始 Prompt 或原始请求体。
- 当前结论：真实供应商小批量 live 执行验证已完成；剩余生产验证重点转为实际多小时压测和管理台最终形态。

### 2026-05-15 Step 38：可控 RPS 长时压测入口

- `scripts/local-stress-check.py` 新增 `--target-rps`，用于把长时压测限制在目标平均吞吐，避免无上限 duration 模式变成 CPU/SQLite 烧机测试。
- `--target-rps` 可同时用于按请求数和按时长两种模式；未指定时保持原有尽快完成行为。
- JSON 摘要和 Markdown 报告新增 `target_rps` 字段，便于记录目标吞吐与实际 `throughput_rps` 的偏差。
- `tests/test_local_stress_check.py` 已覆盖 duration 模式下的 `--target-rps` 和报告输出。
- 当前验证：`python -m unittest tests.test_local_stress_check` 通过；`python scripts\local-stress-check.py --duration-seconds 5 --target-rps 8 --workers 4 --report <temp-report>` 返回 `ok=true`，5 秒完成 40 个混合请求，实际吞吐 8.0 RPS，覆盖 `skip`、`async_agent`、`sync_agent` 和 `fast_path_block`；全量测试结果仍为 68 个测试通过。

### 2026-05-15 Step 39：30 分钟可控 RPS 压测

- 使用 `python scripts\local-stress-check.py --duration-seconds 1800 --target-rps 8 --workers 8 --report reports\local-stress-30m-foreground.md` 执行 30 分钟本地长时压测。
- 本轮压测使用临时 mock Core Service 和临时 SQLite 数据库，不调用真实供应商，不读取或写入真实密钥。
- 压测完成 14400 个混合请求，实际吞吐 `8.0 RPS`，错误数为 0。
- 路由覆盖：`async_agent=7680`、`sync_agent=3840`、`fast_path_block=1440`、`skip=1440`。
- 恢复检查通过：pending appeals 为 1，revoked actions 为 1，expired actions 为 1202，SQLite persisted records 为 12962，原始 Prompt 和原始请求体存储均为 false。
- 当前结论：30 分钟可控 RPS 压测通过；剩余压力验证重点转为 2 小时以上长压测。

### 2026-05-15 Step 40：60 分钟可控 RPS 压测

- 使用 `python scripts\local-stress-check.py --duration-seconds 3600 --target-rps 8 --workers 8 --report reports\local-stress-60m-foreground.md` 执行 60 分钟本地长时压测。
- 本轮压测继续使用临时 mock Core Service 和临时 SQLite 数据库，不调用真实供应商，不读取或写入真实密钥。
- 压测完成 28800 个混合请求，实际吞吐 `8.0 RPS`，错误数为 0。
- 路由覆盖：`async_agent=15360`、`sync_agent=7680`、`fast_path_block=2880`、`skip=2880`。
- 恢复检查通过：pending appeals 为 1，revoked actions 为 1，expired actions 为 2641，SQLite persisted records 为 25922，原始 Prompt 和原始请求体存储均为 false。
- 当前结论：60 分钟可控 RPS 压测通过；剩余压力验证重点转为 2 小时以上长压测。

### 2026-05-15 Step 41：60 分钟压测后回归与泄密扫描

- 压测后执行 `python -m unittest discover -s tests`，68 个测试全部通过，确认 Core、管理台、Demo、供应商故障演练、备份恢复和长压测脚本仍保持闭环。
- 执行 `python -m compileall services adapters apps tests scripts`，所有 Python 模块可编译。
- 执行 `python services\core-service\check_config.py`，配置预检通过。
- 执行 `npm run e2e:browser`，浏览器 E2E 9 项检查通过，确认管理台关键交互仍可运行。
- 执行敏感扫描，排除 `config/secrets/` 和 `node_modules/` 后未发现明文 API key、真实代理地址或真实供应商 endpoint 残留。
- 清理测试产生的 6 个 `__pycache__` 目录；未删除运行配置、DPAPI 加密密钥或 SQLite 运行数据。
- 当前结论：60 分钟压测后的工程状态可继续迭代，下一步建议进入 2 小时以上长压测或管理台 React + Ant Design 最终形态。

### 2026-05-15 Step 42：120 分钟可控 RPS 压测与回归

- 按“1 小时完成后自动进入 2 小时”的节奏，执行 `python scripts\local-stress-check.py --duration-seconds 7200 --target-rps 8 --workers 8 --report reports\local-stress-120m-foreground.md`。
- 本轮压测继续使用临时 mock Core Service 和临时 SQLite 数据库，不调用真实供应商，不读取或写入真实密钥。
- 压测完成 57600 个混合请求，实际吞吐 `8.0 RPS`，错误数为 0。
- 路由覆盖：`async_agent=30720`、`sync_agent=15360`、`fast_path_block=5760`、`skip=5760`。
- 恢复检查通过：pending appeals 为 1，revoked actions 为 1，expired actions 为 5522，SQLite persisted records 为 51842，SQLite 文件约 37.7 MB，原始 Prompt 和原始请求体存储均为 false。
- 压测后回归通过：`python -m unittest discover -s tests` 68 个测试通过；`python -m compileall services adapters apps tests scripts` 通过；`python services\core-service\check_config.py` 通过；`npm run e2e:browser` 9 项浏览器检查通过。
- 压测后敏感扫描通过：排除 `config/secrets/` 和 `node_modules/` 后未发现明文 API key、真实代理地址或真实供应商 endpoint 残留；已清理测试产生的 6 个 `__pycache__` 目录。
- 当前结论：2 小时以上长压测已完成并通过；下一步建议优先进入 React + Ant Design 管理台最终形态，或继续做更高 RPS/更长周期压测。

### 2026-05-15 Step 43：本地服务功能验证

- 执行 `python services\core-service\check_config.py`，配置预检通过。
- 使用当前 Windows 用户上下文启动临时本地 Core Service，访问 `http://127.0.0.1:8787/`。
- 管理台静态资源验证通过：`/`、`/admin/styles.css`、`/admin/admin.js` 均返回 HTTP 200。
- 运行状态验证通过：`runtime_mode=observe`、`agent_paused=true`、`locale=zh-CN`，新手引导返回 8 个步骤。
- 低风险请求验证通过：`/public/health` 路由为 `skip`，动作为 `allow`，未调用 LLM。
- Fast-Path 验证通过：XSS 样例命中 `FP_XSS_001`，路由为 `fast_path_block`，观察模式下只记录 `would_have_action`，未调用 LLM。
- 申诉和账本接口验证通过：申诉写入链路可调用，最近账本接口返回记录，原始 Prompt 和原始请求体存储均为 false。
- 模型网关健康检查通过：在当前用户上下文中返回 `ok=true`、原因码为 `provider_json_decision`，且公开结果只显示配置存在性，不输出 API key、代理 URL 或 API base。
- 发现并确认一个运行注意事项：使用不匹配的提权/服务上下文直接启动 `run_server.py` 时，DPAPI CurrentUser 密钥可能无法解密，模型网关会返回 `missing_api_key`；生产部署必须使用创建密钥的同一 Windows 用户运行，或改用环境变量/密钥管理器。

### 2026-05-15 Step 44：当前用户后台启动入口

- 新增 `scripts\windows\start-atee-core-background.ps1`，用于在当前 Windows 用户上下文启动 ATEE Core Service，适配 DPAPI CurrentUser 密钥。
- 后台启动脚本会先执行 `services\core-service\check_config.py`，预检失败时不打开服务端口。
- 启动脚本会处理 `Path`/`PATH` 重复环境变量，避免 PowerShell `Start-Process` 因大小写重复环境项失败。
- 启动脚本会等待 `/health`，输出 JSON 摘要，并写入 `logs\atee-server.pid`、`logs\atee-preflight.log`、`logs\atee-server.out.log` 和 `logs\atee-server.err.log`。
- 新增 `scripts\windows\stop-atee-core-background.ps1`，按 PID 文件停止后台服务。
- 修正所有带 `ProjectRoot` 的 Windows 运维脚本，不再在参数默认值中依赖 `$PSScriptRoot`，改为参数绑定后解析默认项目根目录，避免从 `powershell.exe -File` 调用时默认路径为空。
- 文档已补充当前用户后台启动方式、计划任务的 DPAPI 用户上下文注意事项，以及停止命令。
- 验证：`python -m unittest tests.test_deployment_assets` 16 个部署资产测试通过；所有 Windows PowerShell 脚本语法解析通过；后台启动脚本返回 `ok=true` 并完成 `/health` 等待。
- 全量回归：`python -m unittest discover -s tests` 70 个测试通过；`python -m compileall services adapters apps tests scripts` 通过；`python services\core-service\check_config.py` 通过；`npm run e2e:browser` 9 项浏览器检查通过。
- 敏感扫描：排除 `config/secrets/` 和 `node_modules/` 后未发现明文 API key、真实代理地址或真实供应商 endpoint 残留；已清理测试产生的 6 个 `__pycache__` 目录和陈旧 PID 文件。

### 2026-05-15 Step 45：Ubuntu/Linux systemd 适配

- 新增 `scripts\linux\start-atee-core.sh`，用于 Linux 前台启动，启动前执行 `services/core-service/check_config.py`，通过后再 `exec` 运行 `run_server.py`。
- 新增 `scripts\linux\install-atee-systemd.sh`，默认安装当前用户 `systemd --user` 服务；可选 `--system --run-user <user>` 安装系统服务，避免以 root 运行 ATEE。
- 新增 `scripts\linux\uninstall-atee-systemd.sh`，支持 user/system 两种模式，默认保留环境文件，避免误删生产密钥注入配置。
- 新增 `scripts\linux\atee-core.env.example`，只提供 `ATEE_LLM_API_KEY` 和代理占位说明，不包含真实 API key、真实代理地址或真实供应商 endpoint。
- Linux 部署文档明确：Ubuntu 等服务器不能使用 Windows DPAPI `*.dpapi.json`；生产应使用 `llm_api_key_env`、systemd 环境文件或密钥管理器注入模型密钥。
- 文档补充 user service、system service、`loginctl enable-linger`、反向代理/防火墙建议，以及 systemd unit/env 文件位置。
- 验证：`python -m unittest tests.test_deployment_assets` 20 个部署资产测试通过，新增覆盖 Linux 启动脚本、systemd 安装/卸载脚本、环境变量示例和 `.env` 忽略规则。
- 全量回归：`python -m unittest discover -s tests` 74 个测试通过；`python -m compileall services adapters apps tests scripts` 通过；`python services\core-service\check_config.py` 通过；`npm run e2e:browser` 9 项浏览器检查通过。
- 敏感扫描：排除 `config/secrets/` 和 `node_modules/` 后未发现明文 API key、真实代理地址或真实供应商 endpoint 残留。

### 2026-05-15 Step 46：React + Ant Design 管理台最终形态

- 新增 Vite 构建链：`vite.config.mjs`、`package.json`、`package-lock.json` 和 `apps\admin-console-src`，管理台源代码迁移到 React + Ant Design。
- 生成产物继续落在 `apps\admin-console`，由现有 Core Service 托管 `/admin/styles.css` 和 `/admin/admin.js`，不引入外部 CDN。
- 管理台保留中文界面与关键 E2E DOM ID，覆盖仪表盘、申诉审核、动作撤销、安全账本、网关配置和新手引导。
- 为适配 Ant Design CSS-in-JS，Core Service 对 HTML 响应生成标准 Base64 CSP nonce，并替换 `__ATEE_CSP_NONCE__` 占位符。
- 前端通过 AntD `ConfigProvider` 传入 CSP nonce，并安装轻量 `style` nonce 兼容层，避免第三方运行期样式探测触发 CSP 控制台错误。
- CSP 保持脚本严格：`script-src 'self'` 加 nonce；样式标签使用 nonce，样式属性仅通过 `style-src-attr 'unsafe-inline'` 做 AntD 运行期兼容。
- Browser E2E 改为真实用户路径：在 AntD Tabs 中切换“申诉处理”“操作台”“动作管理”后再执行对应操作。
- 验证：`npm run build:admin` 通过；Vite 仅提示 Ant Design chunk 体积超过 500 kB，未阻塞构建。
- 验证：`python -m unittest tests.test_admin_console tests.test_http_e2e` 7 个测试通过，覆盖 Vite 外部资产、React 源码 E2E ID、CSP nonce 和 HTTP 工作流。
- 验证：`npm run e2e:browser` 9 项浏览器交互通过，无浏览器 console error。
- 全量回归：`python -m unittest discover -s tests` 75 个测试通过；`python -m compileall services adapters apps tests scripts` 通过；`python services\core-service\check_config.py` 通过。
- 敏感扫描：使用更准确的 `sk-` 长度规则排除 AntD `mask-*` 样式误报后，未发现明文 API key、真实代理地址或真实供应商 endpoint 残留；已清理测试产生的 Python 缓存目录。

### 2026-05-15 Step 47：管理台功能闭环补强

- 问题一句话：第一版 React 管理台主要完成了展示迁移，后台已有能力没有全部转成可保存、可筛选、可带参数执行的前端闭环。
- 最小解决方案：不新增新的业务域，只把既有 `/v1/admin/*` 能力补成 Ant Design 表单、筛选器、回填操作和浏览器 E2E 覆盖。
- 顶部运行模式补齐 `degraded` 和 `read_only` 快捷切换，和原有观察/自动/暂停恢复一起形成完整运行控制入口。
- 配置页从“查看 JSON”升级为可保存表单，覆盖运行模式、可信代理 CIDR、自动封禁、超时预算、模型网关、预算、账本路径、旁路开关、密钥文件字段和代理 URL 输入；敏感字段只在用户输入时提交，不在状态中回显。
- Core `update_config()` 补齐 `runtime_mode` 写入与校验，避免前端表单提交运行模式后被后端静默忽略。
- 申诉处理补齐状态筛选和表格行回填，动作管理补齐状态筛选和动作 ID 回填，安全账本补齐查询条数控制。
- Break-Glass 状态检查支持从管理台输入临时请求头，便于验证生产旁路配置是否真的能在请求级生效。
- Browser E2E 从 9 项扩展到 15 项，新增覆盖降级/只读模式切换、账本 limit、配置加载与保存、模型配置测试和 Break-Glass 请求头路径。
- 验证：`npm run build:admin` 通过；Vite 仅提示 Ant Design chunk 体积超过 500 kB，未阻塞构建。
- 验证：`node --check scripts\browser-e2e.mjs` 通过。
- 验证：`python -m unittest tests.test_admin_console tests.test_core` 35 个测试通过。
- 验证：`npm run e2e:browser` 15 项浏览器交互通过。
- 全量回归：`python -m unittest discover -s tests` 75 个测试通过；`python -m compileall services adapters apps tests scripts` 通过；`python services\core-service\check_config.py` 通过。
- 敏感扫描：排除 `config/secrets/` 和 `node_modules/` 后未发现明文 API key、真实代理地址或真实供应商 endpoint 残留；已清理测试产生的 6 个 `__pycache__` 目录。

### 2026-05-15 Step 48：管理台高影响操作保护层

- 问题一句话：控制台功能补齐后，自动模式、申诉审核、动作撤销和配置保存等高影响操作仍然是单击即执行，生产场景下误操作风险偏高。
- 最小解决方案：先在 React 管理台前端增加轻量二次确认和运行态提示，不引入复杂登录系统，也不改变后端安全决策边界。
- 自动模式切换增加确认弹窗，避免从观察/只读/降级态误切到可执行状态。
- 申诉通过/驳回、动作撤销、过期动作清理和配置保存增加确认弹窗，确认文案明确其影响范围；读取、刷新、账本查询和模型健康检查保持直接可用。
- 只读模式下禁用申诉审核、动作撤销、过期清理和配置保存按钮，并显示 `operationGuardAlert`，提示需先切回观察或降级模式。
- 降级模式和 Agent 暂停态新增控制台顶部保护提示，帮助管理员理解当前操作会受到后端限制或暂停状态影响。
- Browser E2E 补充只读模式保护提示断言，并适配 Popconfirm 确认流程；浏览器检查项从 15 项扩展为 16 项。
- 验证：`node --check scripts\browser-e2e.mjs` 通过。
- 验证：`python -m unittest tests.test_admin_console` 4 个测试通过。
- 验证：`npm run build:admin` 通过；Vite 仅提示 Ant Design chunk 体积超过 500 kB，未阻塞构建。
- 验证：`python -m unittest tests.test_admin_console tests.test_http_e2e` 7 个测试通过。
- 验证：`npm run e2e:browser` 16 项浏览器交互通过。
- 全量回归：`python -m unittest discover -s tests` 75 个测试通过；`python -m compileall services adapters apps tests scripts` 通过；`python services\core-service\check_config.py` 通过。

### 2026-05-16 Step 49：管理台认证与权限边界

- 问题一句话：高影响操作已有确认保护，但 `/v1/admin/*` 管理 API 仍默认无认证，无法进入生产反向代理或公网边界验收。
- 最小解决方案：实现向后兼容的可选 Admin Token 保护；默认关闭以保持本地开发路径，启用后所有 `/v1/admin/*` 必须带令牌。
- `AdminConfig` 新增 `admin_auth_enabled`、`admin_token_env` 和 `admin_token_file`；公开配置只返回 `admin_token_file_configured` 与认证状态，不返回令牌值或令牌文件内容。
- Core Service 新增 Admin Token 加载与校验，支持环境变量和密钥文件；校验使用常量时间比较，支持 `Authorization: Bearer <token>` 与 `X-ATEE-Admin-Token`。
- HTTP 层在所有 `/v1/admin/*` GET/POST 入口前统一执行认证检查；未授权返回 401 与脱敏错误体，普通业务接口、健康检查、静态管理台资源和公开运行状态保持兼容。
- `check_config.py` 增加认证预检：启用 `admin_auth_enabled` 后，若环境变量和密钥文件均不可用，会在服务绑定端口前失败。
- React 管理台新增管理令牌面板，令牌只保存在浏览器 `sessionStorage`，只随 `/v1/admin/*` 请求发送；认证失败时显示 `adminAuthAlert`。
- 配置页新增管理认证开关、Admin Token 环境变量和新令牌文件路径输入；敏感令牌值仍不通过配置 API 回显。
- Linux systemd 环境示例补充 `ATEE_ADMIN_TOKEN` 占位；部署文档和 API 文档补充管理认证配置、请求头和保密边界。
- 验证：`python -m unittest tests.test_core tests.test_http_e2e tests.test_admin_console tests.test_deployment_assets` 60 个测试通过。
- 验证：`python services\core-service\check_config.py` 通过。
- 验证：`npm run build:admin` 通过；Vite 仅提示 Ant Design chunk 体积超过 500 kB，未阻塞构建。
- 验证：`npm run e2e:browser` 16 项浏览器交互通过。
- 全量回归：`python -m unittest discover -s tests` 77 个测试通过；`python -m compileall services adapters apps tests scripts` 通过。

### 2026-05-16 Step 50：反向代理示例与 Admin Token 轮换流程

- 问题一句话：管理 API 已支持令牌认证，但生产部署还缺少可复用的反向代理边界示例和不泄露令牌的轮换入口。
- 最小解决方案：先补 Nginx/Caddy 静态示例、跨平台令牌轮换脚本和部署资产测试；实际服务器上的证书、域名和网关联调保留为环境相关验收。
- 新增 `deploy/reverse-proxy/nginx/atee.conf.example`，示例使用 HTTPS、HSTS、`nosniff`、Referrer Policy、Permissions Policy，并回源到 `127.0.0.1:8787`。
- 新增 `deploy/reverse-proxy/caddy/Caddyfile.example`，同样本地回源、限制请求体大小、补基础安全头并转发 `X-Forwarded-*` 与 `X-Real-IP`。
- 新增 `scripts/rotate-admin-token.py`，默认生成高强度 URL-safe Admin Token，更新指定环境文件中的 `ATEE_ADMIN_TOKEN`，保留其他环境变量行。
- 轮换脚本默认只输出环境文件路径、变量名和 SHA-256 短指纹，不打印令牌本体；只有显式 `--show-token` 时才一次性输出令牌。
- 部署文档新增 Admin Token 轮换命令、反向代理示例路径、可信代理 CIDR 注意事项，以及共享/远程部署必须开启 `admin_auth_enabled=true` 的建议。
- `scripts/linux/atee-core.env.example` 新增 `ATEE_ADMIN_TOKEN` 占位，仍不包含真实密钥或真实供应商 endpoint。
- 部署资产测试新增反向代理示例约束和 Admin Token 轮换脚本验证，覆盖本地回源、安全头、无 wildcard CORS、无真实 endpoint/密钥形态、默认不打印新令牌。
- 验证：`python -m unittest tests.test_deployment_assets` 22 个测试通过。
- 验证：`python scripts\rotate-admin-token.py --help` 通过。
- 全量回归：`python -m unittest discover -s tests` 79 个测试通过；`python -m compileall services adapters apps tests scripts` 通过；`python services\core-service\check_config.py` 通过。

### 2026-05-16 Step 51：管理操作审计身份绑定

- 问题一句话：管理认证、二次确认和反向代理边界已经具备，但审计账本还不能把关键管理动作稳定绑定到操作者。
- 最小解决方案：不引入完整用户系统，先使用可选 `X-ATEE-Admin-Id` 请求头建立操作者归因；后续生产可由 SSO/反向代理注入该头。
- Core Service 新增管理操作者提取与摘要写入：清洗操作者 ID，计算操作者短哈希和来源短哈希，并追加到管理类审计账本 summary。
- HTTP 层在写入类 `/v1/admin/*` 操作中传入 actor，上线范围覆盖模式切换、暂停恢复、配置保存、Break-Glass 状态检查、申诉审核、动作撤销和过期动作清理。
- React 管理台新增操作者 ID 输入，随管理请求发送 `X-ATEE-Admin-Id`；Admin Token 与操作者 ID 仍只保存在浏览器 `sessionStorage`。
- 保密边界：审计 summary 不记录 Admin Token、原始来源 IP、代理 URL、供应商密钥或密钥文件路径。
- 验证：`python -m unittest tests.test_core tests.test_http_e2e tests.test_admin_console` 41 个测试通过。
- 验证：`node --check scripts\browser-e2e.mjs` 通过；`npm run build:admin` 通过；`npm run e2e:browser` 16 项浏览器交互通过。
- 全量回归：`python -m unittest discover -s tests` 80 个测试通过；`python -m compileall services adapters apps tests scripts` 通过；`python services\core-service\check_config.py` 通过。

### 2026-05-16 Step 52：管理台展示语义与摘要渲染修复

- 问题一句话：顶部模型网关长文本会溢出卡片，且“已配置 DeepSeek”和“实际连通失败”都混在裸 JSON 中，容易被误读。
- 最小解决方案：只改 React 管理台展示层，不改变后端 API；把长文本指标改为可换行摘要块，并把配置状态与最近检测结果分开显示。
- 顶部 `Statistic` 改为 `MetricCard`，修复 `deepseek/openai_compatible` 等长英文/下划线文本溢出。
- 模型网关卡片显示供应商、模式、配置完整性和最近连通状态；当配置已接入但最近检测失败时显示明确告警。
- 运行状态与操作结果由默认裸 JSON 改为摘要卡，展示运行模式、Agent、账本、模型配置、连通结果、原因、预算和熔断状态。
- 原始 JSON 保留在可展开区域，继续保留 `#output` 与 `#result`，不破坏浏览器 E2E 和后续排障。
- 验证：`npm run build:admin` 通过；Vite 仍仅提示 Ant Design chunk 体积超过 500 kB。
- 验证：`python -m unittest tests.test_admin_console` 4 个测试通过；`node --check scripts\browser-e2e.mjs` 通过；`npm run e2e:browser` 16 项浏览器交互通过。
- 全量回归：`python -m unittest discover -s tests` 80 个测试通过；`python -m compileall services adapters apps tests scripts` 通过；`python services\core-service\check_config.py` 通过。

### 2026-05-16 Step 53：管理台构建体积拆分

- 问题一句话：React 管理台功能已经闭环，但 Ant Design 仍集中在一个接近 1 MB 的 chunk 中，构建持续提示 500 kB 体积警告。
- 最小解决方案：不改业务交互，只在 Vite 输出层按 React、Ant Design 组件、图标和 vendor 进行手动 chunk 拆分，并让 Core Service 托管新增 chunk。
- `vite.config.mjs` 新增函数式 `manualChunks`，兼容 Vite 8 / Rolldown 当前要求，避免对象式 `manualChunks` 报错。
- 构建产物从单个大 `admin.js` 调整为入口 `admin.js` 加多个 `admin-*.js` modulepreload chunk；当前最大 JS chunk 约 402 KB。
- Core Service 新增受控 `/admin/*.js`、`/admin/*.css`、`/admin/*.map` 静态资产托管，限制在 `apps/admin-console` 目录内，避免拆包后的 modulepreload 资源 404。
- 测试新增 chunk 体积和静态托管断言：确认至少生成多个 admin chunk、最大 chunk 小于 500 KB、HTTP 层能返回 modulepreload chunk。
- 验证：`npm run build:admin` 通过且不再出现 500 kB chunk 警告。
- 验证：`python -m unittest tests.test_admin_console tests.test_http_e2e` 8 个测试通过；`node --check scripts\browser-e2e.mjs` 通过；`npm run e2e:browser` 16 项浏览器交互通过。
- 全量回归：`python -m unittest discover -s tests` 80 个测试通过；`python -m compileall services adapters apps tests scripts` 通过；`python services\core-service\check_config.py` 通过。

### 2026-05-16 Step 54：SSO/反向代理身份注入示例

- 问题一句话：后端已经能审计 `X-ATEE-Admin-Id`，但生产环境不能直接信任浏览器传来的同名请求头，否则操作者归因可以被伪造。
- 最小解决方案：不引入完整 SSO 运行环境，先补 Nginx/Caddy 可复用示例和部署资产测试；真实 OAuth/OIDC 网关地址、域名和证书留到目标服务器联调。
- 新增 `deploy/reverse-proxy/nginx/atee-sso.conf.example`，使用 `auth_request` 与 `auth_request_set` 从 SSO 返回头中提取认证邮箱，并覆盖写入 `X-ATEE-Admin-Id`。
- 新增 `deploy/reverse-proxy/caddy/Caddyfile.sso.example`，使用 `request_header -X-ATEE-Admin-Id` 先删除浏览器自带身份头，再通过 `forward_auth` / `copy_headers` 注入认证身份。
- 部署文档补充 SSO 示例路径，并明确生产中不得原样转发浏览器提供的 `X-ATEE-Admin-Id`。
- 部署资产测试新增 SSO 示例约束，覆盖本地 ATEE upstream、本地 SSO upstream、身份覆盖注入、不引用 `$http_x_atee_admin_id`、不包含真实供应商 endpoint 或密钥形态。
- 验证：`python -m unittest tests.test_deployment_assets` 23 个测试通过；`python services\core-service\check_config.py` 通过。
- 全量回归：`python -m unittest discover -s tests` 81 个测试通过；`python -m compileall services adapters apps tests scripts` 通过；`python services\core-service\check_config.py` 通过。

### 2026-05-16 Step 55：生产反向代理冒烟验收脚本

- 问题一句话：反向代理和 SSO 示例已经具备，但目标服务器验收仍缺少一条可重复执行、不会泄露令牌的检查路径。
- 最小解决方案：新增只依赖 Python 标准库的 `scripts/production-smoke-check.py`，默认做只读检查，只有显式 `--verify-audit-actor` 时才写入一条安全的管理审计探针。
- 脚本检查 `/health`、管理台 HTML、拆分后的 `/admin/admin-*.js` 与 CSS 资源、`/v1/runtime/status`、Admin Token 强制认证，以及可选的审计账本操作者归因。
- SSO 验证支持 `--audit-actor-id` 与 `--expected-audit-actor`：可主动发送一个伪造浏览器 actor，并确认反向代理/SSO 层覆盖成预期操作者后写入账本。
- 输出和 Markdown 报告刻意不包含完整目标 URL、Admin Token、Authorization header 或操作者标识。
- 部署文档新增生产冒烟命令示例，说明 `--allow-http` 仅用于本地演练，生产必须使用 HTTPS 与反向代理安全头。
- 验证：`python -m unittest tests.test_production_smoke_check tests.test_deployment_assets` 24 个测试通过；`python scripts\production-smoke-check.py --help` 通过。
- 全量回归：`python -m unittest discover -s tests` 82 个测试通过；`python -m compileall services adapters apps tests scripts` 通过；`python services\core-service\check_config.py` 通过。

### 2026-05-16 Step 56：Admin Token 轮换后自动复验流程

- 问题一句话：已有令牌轮换和生产冒烟脚本，但轮换后是否重启生效、旧令牌是否失效、新令牌是否能通过生产检查仍需要人工串联，容易漏验。
- 最小解决方案：新增薄封装 `scripts/admin-token-rotation-smoke.py`，复用既有轮换脚本和生产冒烟脚本，只补“轮换 -> 可选重启 -> 旧令牌拒绝 -> 新令牌冒烟”的最小闭环。
- 脚本读取轮换前短指纹，调用 `scripts/rotate-admin-token.py` 更新环境文件，再用 `--restart-command` 执行运维提供的重启命令。
- 重启后脚本会用旧令牌请求 `/v1/admin/config`，确认返回 401/403；随后把新令牌放入临时环境变量并调用 `scripts/production-smoke-check.py`。
- 输出和 Markdown 报告只包含短指纹、返回码存在性和布尔检查结果，不包含令牌值、Authorization header、完整目标 URL 或操作者标识。
- 新增 `tests/test_admin_token_rotation_smoke.py`，使用本地假服务模拟重启后读取新令牌，覆盖旧令牌拒绝、新令牌通过、SSO actor 覆盖、报告脱敏和环境文件保留非令牌配置。
- 部署文档新增 Admin Token Rotation Smoke Check 示例，并提示 Windows/系统服务部署可替换为对应的 stop/start 或服务重启命令。
- 验证：`python -m unittest tests.test_admin_token_rotation_smoke tests.test_production_smoke_check tests.test_deployment_assets` 25 个测试通过；`python scripts\admin-token-rotation-smoke.py --help` 通过。
- 全量回归：`python -m unittest discover -s tests` 83 个测试通过；`python -m compileall services adapters apps tests scripts` 通过；`python services\core-service\check_config.py` 通过。

### 2026-05-16 Step 57：Agent AI 链接与真实状态全流程演练

- 问题一句话：项目已经有 AI 网关配置和多个演练脚本，但仍需要确认当前 Agent 实例在真实配置下能触达 AI，并能跑完一次不泄密的业务闭环。
- 最小解决方案：先用既有 live batch 探针做一次真实 AI 连通检查，再用临时 SQLite 账本承载完整 CoreService 流程，避免污染当前真实账本。
- AI 链接检查：`python scripts\provider-live-batch-drill.py --include-live --attempts 1 --budget-cents 1 --report reports\agent-ai-live-link-check.md` 通过；`api_key_configured=true`、`api_base_configured=true`、`proxy_configured=true`，原因码为 `provider_json_decision`。
- 链接健康：单次 live 探针延迟约 7.4 秒；完整流程中的同步 Agent AI 审核延迟约 9.5 秒；熔断保持 `open=false`，连续失败数为 0。
- 完整流程：低风险静态请求走 `skip` 且不调用 AI；登录类同步请求走 `sync_agent` 并真实调用 AI；XSS 样例命中 `FP_XSS_001` 并由 Fast-Path 拦截；申诉提交为 pending；管理员审核通过后写入带操作者短哈希的审计账本。
- 安全边界：演练使用临时 SQLite 账本，真实运行账本未被写入；输出和报告不包含 API key、代理 URL、API base、密钥文件路径、Authorization header、原始 Prompt 或原始请求体。

### 2026-05-16 Step 58：Agent AI 全流程冒烟脚本

- 问题一句话：Step 57 的真实状态演练已经证明链路可通，但仍偏一次性人工流程，后续迭代需要一个默认不触达真实 AI、可重复、可脱敏的全流程冒烟入口。
- 最小解决方案：新增 `scripts/agent-ai-full-flow-smoke.py`，默认启动临时 fake OpenAI-compatible provider 和临时 SQLite 账本；只有显式 `--include-live` 才做一次真实 AI 全流程冒烟。
- 覆盖范围：`runtime_status`、`low_risk_read_skip`、`sync_agent_ai_review`、`fast_path_attack_block`、`appeal_submit`、`admin_appeal_review`、`ledger_recent`。
- 安全边界：脚本输出和报告只保留布尔配置状态、原因码、路由、预算、熔断、计数和延迟摘要；不包含 API key、代理 URL、API base、密钥文件路径、Authorization header、原始 Prompt、原始请求体或临时账本路径。
- 报告产物：`reports\agent-ai-full-flow-smoke-fake.md` 默认 fake 演练通过；`reports\agent-ai-full-flow-smoke-live.md` 显式 live 演练通过，真实 AI 调用原因码为 `provider_json_decision`，熔断保持关闭。
- 验证：`python -m unittest tests.test_agent_ai_full_flow_smoke tests.test_provider_live_batch_drill` 5 个测试通过；`python scripts\agent-ai-full-flow-smoke.py --help` 通过；`python scripts\agent-ai-full-flow-smoke.py --report reports\agent-ai-full-flow-smoke-fake.md` 通过。
- 全量回归：`python -m unittest discover -s tests` 85 个测试通过；`python -m compileall services adapters apps tests scripts` 通过；`python services\core-service\check_config.py` 通过。
- 保密复核：可跟踪区域敏感扫描返回 `NO_MATCHES`；历史报告中的具体供应商 host 和具体密钥文件名已改为占位符；本轮测试产生的 6 个 `__pycache__` 已清理，复查为 0。

### 2026-05-16 Step 59：本地发布闸门

- 问题一句话：验证命令已经很多，但发布或交付前仍依赖人工记忆串联，容易漏掉配置预检、Agent 冒烟或敏感扫描。
- 最小解决方案：新增 `scripts/local-release-gate.py`，只做薄编排，串联配置预检、Python 编译、单元测试、默认 fake Agent AI 全流程冒烟和工作区敏感扫描。
- 安全边界：JSON 和 Markdown 报告只记录步骤名、退出码、测试数量、扫描文件数和 findings 数量；原始命令输出不进入报告，扫描默认跳过本地运行配置、`config/secrets`、`node_modules`、Git 内部目录和 Python 缓存目录。
- 快速模式：`--quick` 用于本地开发和单元测试，仍覆盖同类检查，但只运行聚焦测试集合，避免在全量测试中递归触发完整回归。
- 验证：`python -m unittest tests.test_local_release_gate` 1 个测试通过；`python scripts\local-release-gate.py --help` 通过。
- 完整闸门：`python scripts\local-release-gate.py --report reports\local-release-gate.md` 通过，配置预检通过、Python 编译通过、86 个单元测试通过、默认 fake Agent AI 全流程冒烟通过、敏感扫描 145 个文件且 findings=0。

### 2026-05-18 Step 60：管理台全配置与 API 保密回显

- 问题一句话：管理台配置项尚未覆盖所有可调字段，且 API Base 会在配置 JSON 中回显，容易造成“界面显示已接入、原始 JSON 又像未安全接入”的认知冲突。
- 最小解决方案：不新增密钥明文入口，只补齐既有可持久化配置的控制项，并把 API Base、API Key 文件、代理 URL、Admin Token 文件统一处理为写入后不回显的配置状态。
- 后端：`config_to_dict()` 将 `llm_api_base` 改为 `llm_api_base_configured`；`update_config()` 新增 `agent_paused`、`locale`、`appeal_paths` 更新路径，并在 `changed` 响应中脱敏 API Base。
- 管理台：网关配置页新增显示语言、Agent 暂停、申诉入口路径等控制项；模型模式补齐 `remote` 与 `disabled`；每个网关配置项都增加简短说明。
- 保密：API Base 改为“新 API Base（留空不变）”的密码输入，不回填旧值；API Key 文件、代理 URL、Admin Token 文件等敏感输入关闭可见性切换；运行状态 JSON 和操作结果 JSON 增加前端兜底脱敏。
- 展示：敏感配置区只展示 API Base、API Key 文件、模型代理的“已配置/未配置”状态，不展示原始值。
- 文档：开发 API 文档补充写入字段与只返回 `*_configured` 布尔值的约束，避免生产接入时误依赖明文回显。
- 验证：`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 16 项浏览器交互通过；`python -m unittest tests.test_core tests.test_admin_console` 37 个测试通过；`python -m unittest discover -s tests` 86 个测试通过。
- 发布闸门：`python scripts\local-release-gate.py --quick --report reports\local-release-gate.md` 通过，配置预检、Python 编译、25 个聚焦测试、默认 fake Agent AI 全流程冒烟和敏感扫描全部通过，扫描 145 个文件且 findings=0。

### 2026-05-18 Step 61：Ubuntu systemd user unit 解析修复

- 问题一句话：Ubuntu 上 `bash scripts/linux/install-atee-systemd.sh --user` 能创建 symlink，但 `systemctl --user` 启动时报 `Unit ... has a bad unit file setting`，原因是安装脚本把 `ExecStart`、`EnvironmentFile` 等 systemd 字段写成了 shell 风格带引号路径。
- 最小解决方案：不改启动脚本和服务语义，只把 unit 生成逻辑改为输出 systemd 可直接解析的未加引号 path/value，并保留 `%` 转义，避免 systemd specifier 误解析。
- 修改范围：`scripts/linux/install-atee-systemd.sh` 将 `systemd_escape()` 改为 `systemd_unit_value()`，生成 `WorkingDirectory=/home/ATEE`、`EnvironmentFile=-/root/.config/atee/atee-core.env`、`ExecStart=/home/ATEE/scripts/linux/start-atee-core.sh` 这类 unit 行。
- 回归保护：`tests/test_deployment_assets.py` 新增断言，确保 installer 不再生成旧的 `systemd_escape` 引号路径形式。
- 验证：`python -m unittest tests.test_deployment_assets` 23 个测试通过；`python -m unittest tests.test_deployment_assets tests.test_admin_console` 27 个测试通过。
- 本机限制：Windows 环境的 `bash -n` 调用的是未安装发行版的 WSL，无法在本机完成 shell 语法检查；需要在 Ubuntu 目标机用 `bash -n scripts/linux/install-atee-systemd.sh` 和 `systemd-analyze --user verify ...` 复验。

### 2026-05-18 Step 62：控制台 API Key 写入环境变量与远程连通检测

- 问题一句话：上一版控制台只要求用户填写 API Key 环境变量名，不能直接输入测试 API Key 并立即验证远程 AI 链接，和实际调试流程不一致。
- 最小解决方案：新增写入型字段 `llm_api_key_value`，管理台输入一次 API Key 后，后端只把它放进当前服务进程的 `llm_api_key_env` 环境变量，不写入 `config.json`、不回显、不进入生产产物。
- 管理台：新增“OpenAI API Key（保存为环境变量）”密码输入；当保存 API Base 或 API Key 时，如果当前仍是 `mock`，自动切到 `openai_compatible`，随后立即调用 `/v1/admin/llm/test` 展示远程连通检测摘要。
- 后端：`update_config()` 识别 `llm_api_key_value`，写入 `os.environ[llm_api_key_env]`；公共配置新增 `llm_api_key_env_configured` 布尔状态，仍不返回密钥值。
- 保密边界：测试 Key 仅用于当前进程调试；重启后不会从 ATEE 配置恢复。生产部署仍应通过 systemd 环境文件或密钥管理器注入真实 Key。
- 文档：开发 API 文档补充 `llm_api_key_value` 为 write-only runtime secret，并明确生产环境不要依赖控制台输入的测试 Key。
- 验证：`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 16 项浏览器交互通过；`python -m unittest tests.test_core tests.test_admin_console` 38 个测试通过；`python -m unittest discover -s tests` 87 个测试通过。
- 发布闸门：`python scripts\local-release-gate.py --quick --report reports\local-release-gate.md` 通过，配置预检、Python 编译、25 个聚焦测试、默认 fake Agent AI 全流程冒烟和敏感扫描全部通过，扫描 145 个文件且 findings=0。

### 2026-05-18 Step 63：Linux systemd 安装前配置初始化防呆

- 问题一句话：Ubuntu/Linux 直接运行 systemd 安装脚本时，如果还没有初始化 `config/config.json`，服务会被安装后立刻启动失败或进入 restart 循环，问题表现容易和 unit 文件错误混在一起。
- 最小解决方案：安装脚本在写入 unit 和调用 `systemctl` 前先检查 `config/config.json`；缺失时直接退出并打印 `cp config/config.example.json config/config.json` 初始化命令。
- 修改范围：`scripts/linux/install-atee-systemd.sh` 新增 `CONFIG_FILE` / `CONFIG_EXAMPLE` 检查；`README.md` 与 `docs/deployment.md` 将 Linux systemd 部署顺序改为先复制配置、可选编辑，再安装服务。
- 回归保护：`tests/test_deployment_assets.py` 新增断言，确保配置检查发生在 `systemctl --user` 调用之前，并保留初始化命令提示。
- 验证：`python -m unittest tests.test_deployment_assets` 23 个测试通过；`python -m unittest tests.test_core tests.test_admin_console` 38 个测试通过。
- 发布闸门：`python scripts\local-release-gate.py --quick --report reports\local-release-gate.md` 通过，配置预检、Python 编译、25 个聚焦测试、默认 fake Agent AI 全流程冒烟和敏感扫描全部通过，扫描 145 个文件且 findings=0。

### 2026-05-19 Step 64：Ubuntu 端口、Nginx 与演示站部署故障收敛

- 问题一句话：当前部署故障来自同一类边界问题：systemd 依赖脚本执行位、Core/Demo/Nginx 端口互相占用、远程模型缺少服务端环境密钥、代理层 Cookie/Header 过大，以及管理台遇到非 JSON 代理错误时反馈不清晰。
- 最小解决方案：不改核心业务逻辑，只在启动器、反向代理示例、Demo Site 和管理台请求层增加清晰失败边界与可操作提示。
- systemd：`install-atee-systemd.sh` 的 unit 改为 `ExecStart=/usr/bin/env sh .../start-atee-core.sh`，避免 git clone 后脚本没有可执行位导致 `status=203/EXEC`。
- Core 启动：`start-atee-core.sh` 在 `check_config.py` 前先做端口 bind 预检，并把结果写到 `logs/atee-port-preflight.log`；`run_server.py` 对 `EADDRINUSE` 输出明确端口占用错误。
- 配置预检：`check_config.py` 在远程模型模式缺少 `llm_api_key_env`/`llm_api_key_file` 时提示 service env 文件位置，提醒设置环境变量或切回 `mock`。
- Demo Site：新增 `ATEE_DEMO_PORT` 与 `ATEE_CORE_URL` 环境变量；建议 Nginx 公共 `8790` 反代到私有 `127.0.0.1:8791`，避免 Demo 进程和 Nginx 抢同一端口；Core 不可达时返回 502 JSON 而不是裸 500。
- Nginx：新增 `deploy/reverse-proxy/nginx/atee-demo.conf.example`；Core/Demo Nginx 示例增加 `large_client_header_buffers 4 16k` 与 `proxy_set_header Cookie ""`，降低浏览器大 Cookie 导致 400 的概率。
- 管理台：`apiRequest()` 支持非 JSON 响应兜底，将 Nginx 500/400 HTML 错误转成可展示的操作结果，避免“LLM 测试无反馈”。
- 文档：`README.md`、`docs/deployment.md`、`docs/developer-guide/api.md` 增加端口分离、env 文件、Nginx bind 冲突和 Cookie 过大处理说明。
- 验证：`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 16 项浏览器交互通过；`python -m unittest tests.test_deployment_assets tests.test_demo_site tests.test_admin_console tests.test_core` 66 个测试通过；`python -m unittest discover -s tests` 89 个测试通过。
- WSL 实测：Ubuntu WSL 26.04 下完成缺配置拦截、`config/config.json` 初始化、user systemd 安装启动、Core `/health`、`/v1/admin/llm/test` mock 连通和 Demo Site 私有端口 `/health` 冒烟；Nginx 未安装，保留为目标服务器验证项。
- 发布闸门：`python scripts\local-release-gate.py --quick --report reports\local-release-gate.md` 通过，配置预检、Python 编译、26 个聚焦测试、默认 fake Agent AI 全流程冒烟和敏感扫描全部通过，扫描 146 个文件且 findings=0。

### 2026-05-24 Step 65：控制台可操作引导与 Agent 对话闭环

- 问题一句话：控制台此前把新手引导当静态说明展示，缺少可点击检测、网站类型/接入方式选择、Agent 对话入口和清晰的页面切换反馈，导致用户无法按界面完成接入。
- 最小解决方案：不扩展业务执行面，只补两个后端只读/低风险接口和前端工作区，让“问 Agent、跑预检、选类型、看流程、进配置”形成最小闭环。
- 后端：新增 `/v1/admin/preflight`，返回 Python、配置文件、管理台资源、账本目录、模型网关、可信代理和紧急旁路的可操作检查结果。
- 后端：新增 `/v1/admin/agent/chat`，复用现有模型网关；mock 模式给本地建议，远程模式调用 OpenAI-compatible 网关，不保存原始对话、不回显密钥。
- 新手引导：改为可展开步骤，增加环境预检按钮、网站类型选择、接入方式选择、真实 IP、AI API、申诉、紧急恢复和“安全情况处理总流程”模块。
- 管理台：新增 Agent 对话页；网关配置的 API Base、API Key 环境变量、代理 URL、可信代理 CIDR 和紧急旁路字段增加可悬浮解释。
- 账本：控制台账本页仅展示记录摘要列，不再把管理员行为详情展开到操作结果 JSON；读取账本后只返回数量和状态摘要。
- UI：非仪表盘页隐藏大指标卡，顶部显示当前页面名称，侧栏宽度与卡片高度收紧，让菜单切换有明确视觉变化。
- 文档：README 与开发 API 文档补充 `/v1/admin/preflight` 和 `/v1/admin/agent/chat`。
- 验证：`python -m py_compile services\core-service\atee_core\core.py services\core-service\atee_core\http_server.py services\core-service\atee_core\llm_gateway.py services\core-service\atee_core\onboarding.py` 通过。
- 验证：`python -m unittest tests.test_core tests.test_admin_console` 40 个测试通过；`npm.cmd run build:admin` 通过；`node --check scripts\browser-e2e.mjs` 通过；`npm.cmd run e2e:browser` 18 项浏览器交互通过。
- 全量回归：`python -m unittest discover -s tests` 91 个测试通过。
- 发布闸门：`python scripts\local-release-gate.py --quick --report reports\local-release-gate.md` 通过，配置预检、Python 编译、26 个聚焦测试、默认 fake Agent AI 全流程冒烟和敏感扫描全部通过，扫描 147 个文件且 findings=0。

### 2026-05-24 Step 66：沙箱攻击防御全流程与 DeepSeek live 演练

- 问题一句话：控制台功能补齐后仍需要确认真实攻击防御链路能在临时沙箱中闭环，并验证配置的 DeepSeek/OpenAI-compatible 网关可真实返回结构化判断。
- 最小解决方案：复用 `scripts/agent-ai-full-flow-smoke.py`，增强 Markdown 报告输出，每个模块记录一句话响应、代码响应状态和脱敏关键响应。
- 文件检查：本轮编辑文件通过 UTF-8 内容检查、`git diff --check`、Python 编译和 Node 语法检查；PowerShell 终端显示乱码属于终端编码渲染问题，文件内容本体正常。
- 沙箱 fake 演练：低风险静态请求走 `skip` 且不调用 AI；登录风险请求进入同步 Agent；XSS 样例命中 `FP_XSS_001`；申诉提交、管理员审核和账本摘要均通过。
- DeepSeek live 演练：当前配置显示远程模式、API Base、API Key 文件和代理均已配置；`--include-live` 全流程通过，`sync_agent_ai_review` 返回 `provider_json_decision`，熔断保持关闭。
- 报告产物：`reports\sandbox-attack-defense-full-log.md` 已生成，包含模块响应表；报告不包含 API key、API base 明文、代理 URL、Authorization header、密钥文件路径、原始 Prompt、原始请求体或临时账本路径。
- 清理：本轮测试产生的 6 个 `__pycache__` 目录已删除，复查数量为 0；保留用户要求的 Markdown 日志产物。
- 验证：`python -m unittest tests.test_agent_ai_full_flow_smoke tests.test_core tests.test_admin_console` 42 个测试通过；`npm.cmd run build:admin` 通过；`python scripts\local-release-gate.py --quick --report reports\local-release-gate.md` 通过，敏感扫描 150 个文件且 findings=0。

### 2026-05-25 Step 67：管理台小范围拆分收口

- 问题一句话：`apps/admin-console-src/src/main.jsx` 已膨胀到 1700 行以上，继续在单文件里追加控制台能力会降低定位效率并增加误改风险。
- 最小解决方案：先只抽离无状态支持代码，不重构页面状态、不引入路由、不拆复杂组件，避免在前端拆分上偏离 P0 主线。
- 拆分范围：新增 `apps/admin-console-src/src/admin-support.jsx`，承载 CSP nonce、Admin Token 会话读写、API 请求封装、敏感 JSON 脱敏、固定选项、帮助文案、运行摘要和操作摘要等纯支持能力。
- 保留范围：`main.jsx` 继续保留页面状态、业务动作、表格列和 Tabs 布局；本轮不继续做页面级组件拆分。
- 管理台入口：异步 AI 审查队列的菜单、状态筛选、刷新和“处理到期任务”按钮已接入源码，并纳入前端源码断言。
- 卡点规则：后续单点问题超过 10 分钟未解决时，记录问题、尝试路径和降级方案；优先保证项目可运行，再继续拆分或优化。
- 验证：`python -m unittest tests.test_admin_console` 4 个测试通过；`npm.cmd run build:admin` 通过。

### 2026-05-25 Step 68：异步 AI 审查管理台浏览器验收

- 问题一句话：异步 AI 审查队列虽已有后端测试，但还缺管理台按钮真实触发后端队列刷新和处理任务的浏览器验收。
- 最小解决方案：不新增业务按钮，只在浏览器 E2E 中用普通评论请求制造一条 `async_agent` 队列任务，再进入“异步 AI 审查”页点击刷新队列和处理到期任务。
- 覆盖链路：`POST /v1/check` 普通评论进入 `async_review_queued`；管理台 `#asyncReviewsBtn` 调用 `/v1/admin/async-reviews`；`#runAsyncReviewsBtn` 调用 `/v1/admin/async-reviews/run` 并处理至少一条到期任务。
- 验证：`node --check scripts\browser-e2e.mjs` 通过；`npm.cmd run build:admin` 通过；`python -m unittest tests.test_admin_console tests.test_core tests.test_http_e2e` 45 个测试通过；`npm.cmd run e2e:browser` 20 项浏览器检查通过。

### 2026-05-25 Step 69：全量回归与本地发布闸门

- 问题一句话：异步 AI 审查、管理台拆分和浏览器验收完成后，需要确认全项目没有出现跨模块回归。
- 最小解决方案：不继续新增功能，先跑全量 Python 测试和 quick 发布闸门，确认配置预检、编译、聚焦测试、默认 Agent AI 冒烟和敏感扫描仍然通过。
- 全量回归：`python -m unittest discover -s tests` 通过，92 个测试 OK。
- 发布闸门：`python scripts\local-release-gate.py --quick --report reports\local-release-gate.md` 通过；配置预检、Python 编译、26 个聚焦测试、默认 Agent AI 全流程冒烟均通过。
- 保密扫描：发布闸门扫描 152 个文件，`findings_count=0`；报告继续省略原始命令输出和敏感值。

### 2026-05-25 Step 70：生产冒烟脚本真实 Core 本地复验

- 问题一句话：生产冒烟脚本此前主要验证脚本自身和模拟服务，还缺一次真实 `AteeHandler + CoreService` 的本地闭环复验。
- 最小解决方案：在 `tests/test_production_smoke_check.py` 增加独立真实 Core 冒烟测试，启动临时 Core HTTP 服务、开启 Admin Token 鉴权，再用 `scripts/production-smoke-check.py` 验证管理台资源、运行状态、管理鉴权和审计操作者归因。
- 保密边界：测试令牌、临时 base URL 和操作者标识均断言不会出现在脚本 stdout 或 Markdown 报告中；测试配置和账本写入临时目录，结束后清理。
- 已覆盖：本地 HTTP 演练覆盖 Core 服务、管理台静态资源、`/v1/runtime/status`、`/v1/admin/config` 鉴权、`/v1/admin/break-glass/status` 审计探针和 `/v1/admin/ledger/recent` 归因读取。
- 未覆盖边界：真实服务器上的 HTTPS 证书、Nginx/Caddy 反向代理、systemd user service 生命周期和公网域名仍需目标机执行 `scripts/production-smoke-check.py` 复验。
- 验证：`python -m unittest tests.test_production_smoke_check` 2 个测试通过；`python -m unittest tests.test_deployment_assets tests.test_production_smoke_check tests.test_admin_token_rotation_smoke` 27 个测试通过。
- 全量回归：`python -m unittest discover -s tests` 通过，93 个测试 OK。

### 2026-05-26 Step 71：异步队列语义校正为异步 AI 审查

- 问题一句话：`async_review` 不是普通后台队列，而是延后调用模型网关的 AI 审查队列，界面和报告需要避免误解。
- 最小解决方案：保持接口路径与内部字段不变，只把用户可见文案、中文运行消息、浏览器验收描述和开发文档统一为“异步 AI 审查队列”。
- 语义边界：内容类请求先走 Fast-Path；进入该队列后由配置的 LLM/模型网关处理脱敏证据，失败重试，超过次数进入 `dead_letter`。
- 验证：`node --check scripts\browser-e2e.mjs` 通过；`python -m unittest tests.test_admin_console tests.test_core tests.test_http_e2e` 45 个测试通过；`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 20 项检查通过。
- 术语复核：已扫描 `README.md`、`docs`、`apps/admin-console-src`、`scripts`、`services`、`tests`，不再保留“异步队列/异步审查队列”等易混淆说法。

### 2026-05-26 Step 72：异步 AI 审查后台 worker

- 问题一句话：异步 AI 审查队列此前只能通过管理台手动处理，生产运行时缺少可控后台处理能力。
- 最小解决方案：新增 `AsyncReviewWorker`，由 Core Service 启动时按配置可选启动；默认关闭以避免未验收模型网关前自动产生远程调用费用。
- 配置项：新增 `async_review_worker_enabled`、`async_review_worker_interval_seconds`、`async_review_worker_batch_size`，管理台可控制开关、轮询间隔和每轮处理量。
- 后端边界：抽出 `process_async_reviews()` 供 worker 复用，保留 `/v1/admin/async-reviews/run` 的人工触发与审计记录；worker 自动处理不写入管理员操作审计，但仍写入 AI 审查决策、重试或死信账本摘要。
- 部署说明：README 与部署文档补充生产建议，先验证模型网关、预算和熔断，再开启 worker 并调小/调大间隔和批量。
- 验证：`python -m py_compile services\core-service\atee_core\async_review_worker.py services\core-service\atee_core\core.py services\core-service\atee_core\http_server.py services\core-service\atee_core\config.py` 通过；`python -m unittest tests.test_async_review_worker tests.test_core tests.test_http_e2e tests.test_admin_console` 46 个测试通过；`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 20 项检查通过；`python -m unittest discover -s tests` 94 个测试通过；`python scripts\local-release-gate.py --quick --report reports\local-release-gate.md` 通过，敏感扫描 154 个文件且 findings=0。

### 2026-05-26 Step 73：异步 AI 审查 worker 冒烟与发布闸门接入

- 问题一句话：worker 已能自动处理队列，但还需要一个不依赖真实密钥、可重复验证预算和熔断联动的交付前冒烟入口。
- 最小解决方案：新增 `scripts/async-ai-review-worker-smoke.py`，默认启动本地 fake OpenAI-compatible provider，只有显式 `--include-live` 才调用当前配置的真实供应商。
- 覆盖场景：预算场景中 2 条异步 AI 审查任务只有 1 次 provider 调用，第一条完成，第二条因预算耗尽重试后进入 `dead_letter`；故障场景中 fake provider 连续失败 3 次后熔断打开。
- 发布闸门：`scripts/local-release-gate.py --quick` 已新增 `async_ai_review_worker_smoke` 步骤，敏感扫描也识别 worker 冒烟临时 key 形状。
- 报告产物：`reports\async-ai-review-worker-smoke.md` 由默认 fake 演练生成；报告不包含 API key、API base、代理 URL、密钥文件路径、Authorization header、原始 Prompt、原始请求体、fake provider 地址或临时 SQLite 路径。
- 验证：`python scripts\async-ai-review-worker-smoke.py --report reports\async-ai-review-worker-smoke.md` 通过；`python -m unittest tests.test_async_ai_review_worker_smoke tests.test_async_review_worker` 3 个测试通过；`python -m unittest tests.test_local_release_gate tests.test_async_ai_review_worker_smoke` 3 个测试通过；`python -m unittest discover -s tests` 96 个测试通过；`python scripts\local-release-gate.py --quick --report reports\local-release-gate.md` 通过，29 个 quick 单测、worker 冒烟和敏感扫描均通过，扫描 158 个文件且 findings=0。

### 2026-05-26 Step 74：异步 AI 审查 worker 真实供应商单次验收

- 问题一句话：默认 fake 冒烟证明了 worker 逻辑，但仍需确认当前真实模型网关配置下，worker 能完成一次受控异步 AI 审查。
- 最小解决方案：使用 `scripts/async-ai-review-worker-smoke.py --include-live` 只排入 1 条任务，worker 处理完成即停止，不进行批量 live 调用。
- 验收结果：`live_worker_single_review` 通过，1 条任务完成，`dead_letter=0`，队列清空，熔断 `open=false`，连续失败数为 0。
- 报告产物：`reports\async-ai-review-worker-smoke-live.md` 已生成；报告不包含 API key、API base、代理 URL、密钥文件路径、Authorization header、原始 Prompt、原始请求体或临时 SQLite 路径。
- 验证：`python scripts\async-ai-review-worker-smoke.py --include-live --report reports\async-ai-review-worker-smoke-live.md` 通过。

### 2026-05-31 Step 75：管理台布局压缩与菜单切换收口

- 问题一句话：控制台顶部按钮、右侧重复 Tabs 和大卡片间距让页面显得过重，侧边菜单切换后的工作区变化不够清晰。
- 最小解决方案：不改业务接口，只压缩 Header、导航、卡片和表格间距，固定桌面端左侧导航，并隐藏右侧重复 Tabs 导航，使左侧菜单成为唯一主要切换入口。
- 前端调整：`apps/admin-console-src/src/main.jsx` 给 Header 标题区、操作区和仪表盘指标区补充布局类，顶部运行模式按钮改为小尺寸；`apps/admin-console-src/src/styles.css` 收紧品牌区、Header、鉴权条、指标卡、卡片和表格密度，并补充移动端宽度兜底。
- 测试适配：`scripts/browser-e2e.mjs` 的页面切换改为优先点击左侧菜单；当测试文案和菜单文案不完全一致时，按隐藏 Tabs 的 `data-node-key` 回查对应菜单项，避免再点击不可见 Tabs。
- 构建产物：已重新生成 `apps/admin-console` 静态管理台文件，保持可直接由 Core Service 提供。
- 验证：`git diff --check` 通过；`node --check scripts\browser-e2e.mjs` 通过；`python -m unittest tests.test_admin_console` 4 个测试通过；`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 20 项浏览器检查通过。

### 2026-05-31 Step 76：管理台仪表盘组件拆分

- 问题一句话：`main.jsx` 仍承担大量页面展示 JSX，后续继续在单文件编辑容易卡顿，也不利于定位控制台布局问题。
- 最小解决方案：只抽离无状态仪表盘展示，不移动请求函数、不改接口、不改状态流；新增 `apps/admin-console-src/src/admin-dashboard.jsx` 承载指标卡、操作台卡片和底部 JSON 摘要。
- 拆分结果：`main.jsx` 从约 1347 行降到约 1283 行；`admin-dashboard.jsx` 约 138 行，集中管理 `DashboardMetrics`、`DashboardTab` 和 `JsonSummaryRow`。
- 测试适配：`tests/test_admin_console.py` 的源码断言范围加入 `admin-dashboard.jsx`，继续检查 e2e ID、敏感 JSON 脱敏和纯文本渲染边界。
- 验证：`python -m unittest tests.test_admin_console` 4 个测试通过；`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 20 项浏览器检查通过；`git diff --check` 通过。

### 2026-05-31 Step 77：管理台 Agent 与新手引导组件拆分

- 问题一句话：`main.jsx` 仍包含 Agent 对话和新手引导的大块 JSX，继续迭代这些模块时容易再次出现单文件编辑卡顿。
- 最小解决方案：只抽离展示组件，不移动 `sendAgentChat()`、`runPreflight()`、`runGuideAction()` 等业务动作；新增 `apps/admin-console-src/src/admin-agent-guide.jsx` 承载 `AgentTab` 和 `GuideTab`。
- 拆分结果：`main.jsx` 从约 1283 行降到约 1184 行；`admin-agent-guide.jsx` 约 175 行，集中管理 Agent 对话窗口、网站类型/接入方式选择、环境预检、新手引导折叠面板和安全情况处理总流程。
- 测试适配：`tests/test_admin_console.py` 的源码断言范围加入 `admin-agent-guide.jsx`，继续覆盖 Agent/Guide 的 e2e ID、纯文本渲染和新手引导流程标识。
- 验证：`python -m unittest tests.test_admin_console` 4 个测试通过；`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 20 项浏览器检查通过；`git diff --check` 通过。

### 2026-05-31 Step 78：管理台列表模块拆分与测试摘要重整

- 问题一句话：申诉、动作和异步 AI 审查仍在 `main.jsx` 内形成大块列表/表单 JSX，同时用户需要重新理解当前测试到底覆盖了哪些项目。
- 最小解决方案：只抽离列表展示组件，不移动表格列定义、状态和业务动作；新增 `apps/admin-console-src/src/admin-review-queues.jsx` 承载 `AppealsTab`、`ActionsTab` 和 `AsyncReviewsTab`，并新增 `docs/test-summary.md` 汇总测试项目与详细覆盖内容。
- 拆分结果：`main.jsx` 从约 1184 行降到约 1057 行；`admin-review-queues.jsx` 约 218 行，集中管理申诉审核、动作撤销、异步 AI 审查队列三个列表面板。
- 测试摘要：`docs/test-summary.md` 记录本轮已执行的管理台单测、Vite 构建、浏览器 20 项端到端检查、diff 检查、quick 发布闸门覆盖范围和全部 Python 测试模块地图。
- 测试适配：`tests/test_admin_console.py` 的源码断言范围加入 `admin-review-queues.jsx`，继续覆盖申诉、动作和异步 AI 审查的 e2e ID 与安全渲染边界。
- 验证：`python -m unittest tests.test_admin_console` 4 个测试通过；`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 20 项浏览器检查通过；`git diff --check` 通过。

### 2026-05-31 Step 79：管理台账本与网关配置组件拆分

- 问题一句话：`main.jsx` 剩余最大块来自安全账本和网关配置表单，继续放在主文件会影响后续定位配置问题和界面迭代速度。
- 最小解决方案：只抽离账本与配置展示组件，不移动 `showLedger()`、`showConfig()`、`saveConfig()`、`testLlmGateway()`、`breakGlass()` 等业务动作；新增 `apps/admin-console-src/src/admin-ledger-config.jsx` 承载 `LedgerTab` 和 `GatewayConfigTab`。
- 拆分结果：`main.jsx` 从约 1057 行降到约 856 行；`admin-ledger-config.jsx` 约 263 行，集中管理账本读取、运行配置表单、模型网关配置、密钥/环境变量输入、可信代理、申诉入口、紧急旁路状态和旁路验证。
- 测试适配：`tests/test_admin_console.py` 的源码断言范围加入 `admin-ledger-config.jsx`，继续覆盖账本、网关配置、LLM 测试、紧急旁路和敏感字段不回显等 e2e ID 与安全边界。
- 验证：`python -m unittest tests.test_admin_console` 4 个测试通过；`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 20 项浏览器检查通过；`git diff --check` 通过。

### 2026-05-31 Step 80：管理台拆分后全量回归与发布闸门

- 问题一句话：管理台多文件拆分完成后，需要确认前端重构没有影响 Core、部署脚本、供应商故障演练、生产冒烟和敏感信息边界。
- 最小解决方案：不再追加新功能，先运行全量 Python 单测和 quick 发布闸门，再清理测试缓存并把结果同步到测试摘要。
- 全量回归：`python -m unittest discover -s tests` 通过，96 个测试 OK，覆盖 Core、HTTP、管理台、部署资产、演示站、供应商故障/预算/熔断、备份恢复、压力脚本、生产冒烟和发布闸门等模块。
- 发布闸门：`python scripts\local-release-gate.py --quick --report reports\local-release-gate.md` 通过；配置预检、Python 编译、29 个聚焦单测、Agent AI 全流程 fake 冒烟、异步 AI 审查 worker fake 冒烟和敏感扫描全部通过。
- 敏感扫描：本次扫描 164 个文件，`findings_count=0`；报告继续不输出 API Key、Authorization、真实供应商地址、代理地址、密钥文件路径、原始 Prompt 或原始请求体。
- 清理：测试生成的 6 个 `__pycache__` 目录已按工作区路径校验后删除。
- 文档：`docs/test-summary.md` 已补充全量单测和 quick 发布闸门的最新执行结果。

### 2026-06-01 Step 81：生产冒烟最小闭环复测

- 问题一句话：全量回归后仍需要单独确认生产冒烟脚本覆盖的上线入口没有因管理台拆分和静态资源重建而退化。
- 最小解决方案：运行现有 `tests.test_production_smoke_check`，由测试启动真实 Core 服务并调用生产冒烟检查逻辑，不引入真实密钥或外部网络依赖。
- 覆盖范围：本轮复测验证 `/health`、管理台首页、静态资源加载、`/v1/runtime/status`、Admin Token 鉴权、无 Token 拦截、审计 actor 探针和报告脱敏边界。
- 验证：`python -m unittest tests.test_production_smoke_check` 通过，2 个测试 OK。

### 2026-06-01 Step 82：部署入口与管理台按钮链路复测

- 问题一句话：进入真实 Ubuntu/Nginx 复测前，需要先确认仓库内的部署脚本约束、反向代理样例、管理台按钮和 Admin Token 轮换链路仍保持闭合。
- 最小解决方案：在本机先跑部署资产、HTTP E2E、管理台源码断言、浏览器按钮 E2E、生产冒烟和令牌轮换冒烟；WSL 仅作为可选 shell 层复验，不阻塞本轮主线。
- 覆盖范围：Linux systemd 安装脚本、启动脚本、Nginx/Caddy 样例、管理台 20 项按钮链路、Admin 认证、Token 轮换后旧令牌拒绝/新令牌通过、生产冒烟报告脱敏。
- WSL 状态：当前 Codex 进程调用 `wsl.exe` 时看不到可用默认发行版，返回安装/列出发行版提示；这不是 ATEE 代码失败，需在能进入 Ubuntu 的终端内再执行 shell 语法和 systemd verify。
- 验证：`python -m unittest tests.test_deployment_assets tests.test_http_e2e tests.test_admin_console` 通过，32 个测试 OK；`npm.cmd run e2e:browser` 通过，20 项检查 OK；`python -m unittest tests.test_admin_token_rotation_smoke tests.test_production_smoke_check tests.test_deployment_assets` 通过，27 个测试 OK。

### 2026-06-01 Step 83：Ubuntu WSL 实测与全量测试矩阵

- 问题一句话：Windows 本机回归不能证明 Ubuntu/systemd/Nginx 场景可用，需要安装真实 Ubuntu WSL 并按功能、非功能、自动化和 CI/CD 矩阵实测。
- 最小解决方案：安装 `Ubuntu-24.04`，补齐 Python/Node 22/Nginx/Chromium 工具链，在 WSL 内跑全量 Python、Vite 构建、Linux Chromium UI E2E、systemd+Nginx smoke、性能、安全、灾备和 release gate。
- 修复问题：`backup-restore-drill.py` 增加无 PowerShell 时的 Python backup/restore fallback；`tests.test_local_release_gate` 在测试夹具中注入占位 `ATEE_LLM_API_KEY`，避免 Linux 测试依赖 Windows DPAPI；新增 `scripts/linux/wsl-systemd-nginx-smoke.sh` 做可复用 systemd+Nginx 部署冒烟并自动清理。
- 验证：Ubuntu 全量 `python3 -m unittest discover -s tests` 通过，98 个测试 OK、1 个按设计跳过；`npm run build:admin` 通过；Linux Chromium `npm run e2e:browser` 通过 20 项；systemd+Nginx production smoke 通过；性能负载/压力/容量/稳定性 4 组均 0 errors；`npm audit` 0 vulnerabilities；release gate 敏感扫描 174 个文件 findings=0；灾备恢复通过。
- 文档：新增 `docs/wsl-ubuntu-test-log.md` 与 `docs/wsl-ubuntu-test-matrix-report.md`，记录测试矩阵、问题处理、命令结果、限制与后续建议。

### 2026-06-01 Step 84：按 Ubuntu 实测日志删减测试残留

- 问题一句话：WSL 实测修复后仍残留一个人为 fallback 开关和若干只用于调试的内部字段，生产脚本可以更短更自然。
- 最小解决方案：删除 `ATEE_BACKUP_DRILL_FORCE_PYTHON` 测试开关，改由“找不到 PowerShell”这一真实 Linux 条件自然进入 Python fallback；内联单用时间戳函数，使用 `Path.is_relative_to()` 替代自定义 helper，并移除未进入报告的 `backend` 调试字段。
- 保留边界：保留 Linux Python backup/restore fallback、zip path traversal 防护、`config/secrets/**` 排除、WSL systemd+Nginx smoke 脚本和部署资产测试，因为这些都是日志中暴露的真实生产适配点。
- 验证：`python -m unittest tests.test_backup_restore_drill tests.test_deployment_assets tests.test_local_release_gate` 通过，29 个测试 OK；Ubuntu `python3 scripts/backup-restore-drill.py --report reports/wsl-backup-restore-drill-pruned.md` 返回 `ok=true`；Ubuntu `bash -n scripts/linux/wsl-systemd-nginx-smoke.sh` 通过。

### 2026-06-01 Step 85：测试问题分类与工程化补齐

- 问题一句话：测试日志中的问题分散在矩阵报告、实测日志和命令输出里，且 CI/Git Hook 缺口、Linux 密钥预检文案仍未完全生产化。
- 最小解决方案：新增 `docs/test-issue-summary.md`，按功能、适配、部署运维、CI/CD、性能、安全和可访问性归类问题；将 `check_config.py` 的密钥解密失败提示改为 OS/user context；新增 GitHub Actions quick gate 与可选 pre-push hook。
- 代码修改：新增 `.github/workflows/ci.yml` 覆盖 Python 全量、管理台构建、quick release gate、diff check 和 Windows 浏览器 E2E；新增 `.githooks/pre-push` 执行部署资产/灾备/release gate 关键单测、管理台构建和 diff check。
- 验证：`python -m py_compile services\core-service\check_config.py scripts\backup-restore-drill.py tests\test_deployment_assets.py tests\test_backup_restore_drill.py tests\test_local_release_gate.py` 通过；`python -m unittest tests.test_deployment_assets tests.test_backup_restore_drill tests.test_local_release_gate` 通过，31 个测试 OK；`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 通过，20 项检查 OK；`python scripts\local-release-gate.py --quick --report reports\local-release-gate.md` 通过，32 个聚焦测试，敏感扫描 184 个文件且 findings=0。

### 2026-06-01 Step 86：GitHub Actions Windows 闸门修正

- 问题一句话：首次远端 CI 中 Ubuntu quick gate 和 Windows 浏览器 E2E 通过，但 Windows quick gate 在构建后执行 `git diff --check`，容易被构建产物或换行差异误判为失败。
- 最小解决方案：CI 改为 `python scripts/ci-whitespace-check.py`，直接读取 `HEAD` 内的提交文本内容并检查行尾空白；本地 pre-push 继续保留 `git diff --check` 检查开发者工作区。
- 代码修改：新增 `scripts/ci-whitespace-check.py`，更新 `.github/workflows/ci.yml` 的 Windows/Ubuntu quick gate 空白检查命令，并同步调整 `tests/test_deployment_assets.py` 对 CI 与 hook 的断言边界。
- 验证：`python -m py_compile scripts\ci-whitespace-check.py tests\test_deployment_assets.py` 通过；`python scripts\ci-whitespace-check.py` 通过；`python -m unittest tests.test_deployment_assets` 通过，27 个测试 OK；`git diff --check` 通过，仅保留 Windows LF/CRLF 提示。

### 2026-06-01 Step 87：远端 CI 复跑确认

- 问题一句话：修正 CI 检查逻辑后，需要确认 GitHub 远端 runner 上的真实结果，而不是只看本地回归。
- 最小解决方案：推送 `ea5cfdf` 后通过 GitHub Actions API 查询 run `26760080565` 和每个 job 的完成状态。
- 验证：远端 Actions `26760080565` 通过；`Quick gate (ubuntu-latest)`、`Quick gate (windows-latest)`、`Browser E2E (Windows)` 均为 `success`。

### 2026-06-01 Step 88：Windows CI 慢 runner 超时修正

- 问题一句话：报告提交 `db451bc` 触发的 Windows quick gate 在 Python tests 阶段失败，失败时长接近嵌套 release gate 测试的 90 秒超时边界，本地全量测试通过，判断为 Windows runner 慢导致的误杀。
- 最小解决方案：不改产品逻辑，只将 `tests/test_local_release_gate.py` 中 release gate 子进程测试超时从 90 秒提高到 240 秒，给 Windows CI 留出稳定余量。
- 验证：`python -m py_compile tests\test_local_release_gate.py` 通过；`python -m unittest tests.test_local_release_gate` 通过；`python -m unittest discover -s tests` 通过，100 个测试 OK。

### 2026-06-02 Step 89：管理控制台功能闭环审计

- 问题一句话：进入下一轮功能增强前，需要先确认控制台按钮、表单、菜单和后端 API 的真实对接状态，避免继续在不清楚闭合边界的情况下扩展。
- 最小解决方案：不改产品源码，逐项审计 React 管理台源文件、Core HTTP 路由和现有 E2E 测试，形成独立闭环清单。
- 审计结论：控制台主要按钮和表单已接入真实 Core API；Agent 对话、环境预检、模型网关测试、申诉、动作、异步 AI 审查、账本摘要、配置保存和紧急旁路检测均有后端闭环；当前最大缺口是新手引导部分步骤仍只是导航/说明，尚未做到字段级聚焦、推荐值预填或一键安全演练。
- 文档：新增 `docs/admin-console-function-audit.md`，按模块列出控件、前端动作、后端接口、闭合状态、自动化覆盖和下一步 P0/P1 缺口。
- 验证：`python -m unittest tests.test_admin_console tests.test_http_e2e` 通过，8 个测试 OK；`git diff --check` 通过，仅保留 Windows LF/CRLF 提示。

### 2026-06-02 Step 90：板块 1 全局状态、认证与运行控制检查

- 问题一句话：需要先确认控制台最外层的连接状态、Admin Token 会话、模式切换和暂停恢复是否真实落到后端，避免后续板块建立在错误运行态上。
- 最小解决方案：核对 `main.jsx`、`admin-support.jsx`、`http_server.py`、`core.py` 和既有测试，确认 `GET /v1/runtime/status`、`POST /v1/admin/mode`、`POST /v1/admin/pause-agent` 与 Admin Token 鉴权闭合。
- 检查结论：刷新、模式切换、暂停/恢复均真实接入后端；Admin Token 与操作者 ID 只保存在本地会话，并仅随 `/v1/admin/*` 请求发送；后端所有管理接口先做鉴权，公开运行状态保持可读。
- 修复情况：未发现需要修改的产品代码问题；仅将板块检查记录写入 `docs/admin-console-function-audit.md`。
- 验证：`python -m unittest tests.test_admin_console tests.test_http_e2e` 通过，8 个测试 OK；`python -m unittest tests.test_core` 通过，37 个测试 OK；`node --check scripts\browser-e2e.mjs` 通过。

### 2026-06-02 Step 91：板块 2 操作台安全演练检查

- 问题一句话：操作台四个演练按钮需要逐一确认是否真实调用后端并产生可见结果，不能只依赖源码里存在按钮。
- 最小解决方案：核对 `DashboardTab`、`testSafe()`、`testAttack()`、`testAppeal()`、`testLlmGateway()`、HTTP 路由和浏览器 E2E，发现缺少操作台 LLM 按钮点击覆盖后只补一条断言。
- 检查结论：安全请求、快速拦截、申诉和模型网关测试均真实接入后端；操作结果通过统一 `run()` 写入摘要和脱敏 JSON。
- 修复情况：产品业务逻辑未改；`scripts/browser-e2e.mjs` 新增 `#testLlmBtn` 点击和返回 `ok=true` 断言，浏览器检查数从 20 更新为 21，并同步更新测试摘要。
- 验证：`python -m unittest tests.test_admin_console tests.test_http_e2e` 通过，8 个测试 OK；`node --check scripts\browser-e2e.mjs` 通过；`npm.cmd run e2e:browser` 通过，21 项检查 OK。

### 2026-06-02 Step 92：板块 3 Agent 对话和新手引导检查

- 问题一句话：Agent 对话和环境预检已经有真实后端链路，但新手引导动作仍偏跳转，缺少字段级聚焦和可直接发送给 Agent 的上下文问题。
- 最小解决方案：不改 Core 决策逻辑，只给引导动作按钮补稳定 ID，让 `runGuideAction(stepId)` 聚焦对应控件，并对网站类型/接入方式预填不含密钥的 Agent 问题。
- 检查结论：`POST /v1/admin/agent/chat`、`GET /v1/onboarding/steps`、`GET /v1/admin/preflight` 均真实闭合；引导步骤现在能从说明进入对应功能控件。
- 修复情况：`admin-agent-guide.jsx` 新增动态 `guideAction-*` ID；`main.jsx` 新增引导动作聚焦和 Agent 问题预填；`scripts/browser-e2e.mjs` 新增新手引导动作真实点击断言，浏览器检查数更新为 22。
- 验证：`python -m unittest tests.test_admin_console tests.test_core` 通过，41 个测试 OK；`python -m unittest tests.test_http_e2e` 通过，4 个测试 OK；`node --check scripts\browser-e2e.mjs` 通过；`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 通过，22 项检查 OK。

### 2026-06-02 Step 93：板块 4 申诉处理检查

- 问题一句话：申诉通过和驳回都有真实后端能力，但浏览器回归只点击了“通过”，没有覆盖“驳回”按钮的真实 UI 闭环。
- 最小解决方案：不改业务逻辑，只补 `rejectAppealBtn` 与审核备注的静态 ID 断言，并在浏览器 E2E 中创建第二条申诉后点击“驳回”。
- 检查结论：申诉提交、列表筛选、行回填、通过、驳回、只读禁用、管理员审计和 SQLite 状态恢复均闭合。
- 修复情况：`scripts/browser-e2e.mjs` 新增第二条申诉驳回流程，浏览器检查数更新为 23；`tests/test_admin_console.py` 新增 `appealNoteInput` 与 `rejectAppealBtn` 断言。
- 验证：`python -m unittest tests.test_admin_console tests.test_http_e2e tests.test_core` 通过，45 个测试 OK；`python -m unittest tests.test_recovery_load` 通过，1 个测试 OK；`node --check scripts\browser-e2e.mjs` 通过；`npm.cmd run e2e:browser` 通过，23 项检查 OK。

### 2026-06-02 Step 94：板块 5 异步 AI 审查检查

- 问题一句话：异步 AI 审查处理会写队列状态、可能调用模型并写审计，但原先没有受只读模式保护。
- 最小解决方案：在后端 `process_async_reviews()` 统一拒绝 read_only 处理，在前端给 `AsyncReviewsTab` 传入 `writeLocked` 并禁用 `runAsyncReviewsBtn`，再补单测和浏览器断言。
- 检查结论：队列刷新、状态筛选、手动处理、后台 worker、重试/死信和脱敏列表均闭合；只读模式现在不会消费 pending 队列。
- 修复情况：`core.py` 新增 read_only 423 返回；`admin-review-queues.jsx` 和 `main.jsx` 新增只读禁用传递；`tests/test_core.py` 新增只读阻断单测；`scripts/browser-e2e.mjs` 新增只读按钮禁用断言，浏览器检查数更新为 24。
- 验证：`python -m unittest tests.test_core tests.test_async_review_worker tests.test_http_e2e tests.test_admin_console` 通过，47 个测试 OK；`node --check scripts\browser-e2e.mjs` 通过；`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 通过，24 项检查 OK。

### 2026-06-02 Step 95：板块 6 动作管理检查

- 问题一句话：动作管理前端已禁用只读写按钮，但后端直连撤销/清理 API 仍可写入，且动作列表读取会隐式标记过期动作。
- 最小解决方案：在 `revoke_action()` 和 `cleanup_expired_actions()` 统一拒绝 read_only 写操作，并让 `admin_actions()` 在只读模式走无副作用列表查询。
- 检查结论：动作列表、状态筛选、行回填、撤销、过期清理和动作审计链路已闭合；只读模式现在同时保护前端按钮和后端 API。
- 修复情况：`ActionExecutor.list_actions()` 新增可关闭过期清理的读取参数；`core.py` 新增两个 read_only 423 返回；`tests/test_core.py` 新增只读动作管理单测；`tests/test_admin_console.py` 补 `cleanupActionsBtn` 静态断言；`scripts/browser-e2e.mjs` 新增动作清理/撤销按钮只读禁用断言，浏览器检查数更新为 26。
- 验证：`python -m unittest tests.test_core tests.test_http_e2e tests.test_admin_console tests.test_recovery_load` 通过，48 个测试 OK；`node --check scripts\browser-e2e.mjs` 通过；`npm.cmd run e2e:browser` 通过，26 项检查 OK。

### 2026-06-02 Step 96：板块 7 安全账本检查

- 问题一句话：安全账本页面只展示摘要列，但 HTTP 管理接口仍返回 `summary`、哈希详情和 `sqlite_path`，浏览器侧仍可展开过细审计内容。
- 最小解决方案：保留 Core 内部完整审计读取，给 `ledger_recent()` 增加公开摘要模式，并让 HTTP 管理接口默认只返回表格需要的摘要字段。
- 检查结论：账本读取按钮真实接入后端；控制台操作结果不再返回 records；HTTP records 不再包含 `summary`、`ip_hash`、`rule_id`、`endpoint_type`，公开 status 不再包含 `sqlite_path`。
- 修复情况：`core.py` 新增 `_public_ledger_record()` 和 `_public_ledger_status()`；`http_server.py` 调用 `ledger_recent(..., include_details=False)`；`main.jsx` 移除账本操作结果中的 status；新增 Core/HTTP/浏览器断言，浏览器检查数更新为 27。
- 验证：`python -m unittest tests.test_core tests.test_http_e2e tests.test_admin_console` 通过，48 个测试 OK；`python -m unittest tests.test_recovery_load` 通过；`node --check scripts\browser-e2e.mjs` 通过；`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 通过，27 项检查 OK。

### 2026-06-02 Step 97：板块 8 网关配置检查

- 问题一句话：网关配置前端已在只读模式禁用保存按钮，但后端直连配置接口仍可修改运行配置并写入运行时 API Key 环境变量。
- 最小解决方案：在 `update_config()` 入口统一拒绝 read_only 保存；保留独立模式切换接口用于退出只读模式。
- 检查结论：配置读取、保存、模型测试和紧急旁路检测均接入真实后端；API Base、API Key、代理 URL、密钥文件和 Admin Token 文件在公开配置与测试结果中均以配置状态展示，不回显敏感值。
- 修复情况：`core.py` 新增 `read_only_mode_blocks_config_update` 423 返回；`tests/test_core.py` 新增只读配置保存与运行时 API Key 阻断单测；`scripts/browser-e2e.mjs` 新增 `configSaveBtn` 只读禁用断言，浏览器检查数更新为 28。
- 验证：`python -m unittest tests.test_core tests.test_http_e2e tests.test_admin_console` 通过，49 个测试 OK；`node --check scripts\browser-e2e.mjs` 通过；`npm.cmd run e2e:browser` 通过，28 项检查 OK。

### 2026-06-02 Step 98：控制台与后端系统检查

- 问题一句话：分板块修复后仍需从系统层确认管理写入口、只读边界、公开响应脱敏和生产冒烟脚本是否互相一致。
- 最小解决方案：逐项复查 `/v1/admin/*` GET/POST 路由、Core 写入口和浏览器 E2E，只对发现的系统冲突做最小修复。
- 发现问题 1：申诉审核前端只读禁用了按钮，但 `review_appeal()` 后端仍可被直连调用并修改申诉状态。
- 修复情况 1：`review_appeal()` 新增 `read_only_mode_blocks_appeal_review` 423 返回；`tests/test_core.py` 新增只读申诉审核阻断单测；`scripts/browser-e2e.mjs` 新增 `approveAppealBtn` 和 `rejectAppealBtn` 只读禁用断言。
- 发现问题 2：`production-smoke-check.py --verify-audit-actor` 仍依赖 HTTP 账本 `summary` 校验 actor，与安全账本公开摘要模式冲突。
- 修复情况 2：生产冒烟脚本改为兼容公开账本：详细记录存在时验证 actor；公开详情隐藏时验证 `break_glass/bypass_status_check` 审计事件存在且 actor/token 未泄漏。
- 系统结论：申诉审核、异步 AI 审查处理、动作撤销、动作清理、配置保存均具备前端禁用和后端 423 保护；模式切换保留可用以退出只读；公开配置、模型测试、账本和冒烟报告不回显敏感值。
- 验证：`python -m unittest tests.test_core tests.test_http_e2e tests.test_admin_console tests.test_recovery_load` 通过，51 个测试 OK；`npm.cmd run e2e:browser` 通过，30 项检查 OK；`npm.cmd run build:admin` 通过；`python -m unittest discover -s tests` 通过，105 个测试 OK。

### 2026-06-02 Step 99：控制台核心能力补齐

- 问题一句话：新手引导里的安全情况处理总流程仍偏静态说明，缺少一个能从控制台触发并验证真实后端链路的一键演练入口。
- 最小解决方案：新增受控的 `security_flow_rehearsal()` 后端编排和 `POST /v1/admin/security-flow/run` 管理接口，前端只增加一个按钮和步骤摘要列表，并用只读模式阻断写入。
- 修复情况：演练会依次覆盖环境预检、安全请求、快速拦截、异步 AI 审查、申诉入口、模型网关和安全账本摘要；演练申诉提交后自动关闭，不污染真实待处理队列；返回结果只包含脱敏步骤摘要，不返回原始请求体、账本详情、API Key、代理或密钥路径。
- 控制台：`GuideTab` 新增 `securityFlowBtn` 和 `securityFlowResultList`；`OperationSummary` 能将返回结果识别为“安全流程演练”；只读模式下按钮禁用，后端直连返回 423。
- 报告：`docs/admin-console-function-audit.md` 已将该 P0 从未闭合项改为已闭合项；`docs/test-summary.md` 已把浏览器 E2E 覆盖更新为 32 项。
- 验证：`python -m unittest tests.test_core tests.test_http_e2e tests.test_admin_console` 通过，52 个测试 OK；`node --check scripts\browser-e2e.mjs` 通过；`npm.cmd run build:admin` 通过；`npm.cmd run e2e:browser` 通过，32 项检查 OK；`python -m unittest discover -s tests` 通过，107 个测试 OK；`git diff --check` 通过，仅有 Windows LF/CRLF 提示。

### 2026-06-02 Step 100：核心能力真实性验证与分区块修复

- 问题一句话：第 2/5/6/7 项真实性验证证明 ATEE 不能只看按钮、接口或 Agent 输出，修复前存在云元数据 SSRF、危险上传、WebShell 漏拦，以及正常 Nginx/API 批量访问和日志洪泛误判。
- 最小解决方案：将问题分为 SSRF/云元数据、危险上传/WebShell、正常生产流量误判、洪泛稳定性、回归测试、远程 AI 真实调用 6 个区块，并只在对应规则、账本并发写入和测试脚本边界做最小修改。
- 修复情况：`fast_path.py` 新增 `FP_SSRF_001`、`FP_WEBSHELL_001`、危险上传扩展名检测和更窄的高风险写路径限流；`ledger.py`、`actions.py` 为 SQLite 写入增加进程内锁、`busy_timeout` 和 WAL；`tests/test_core.py` 固定 SSRF、上传、WebShell、正常 API 批量、登录爆破回归用例。
- 验证：第 2/5/6/7 项真实性验证从 18/28 通过提升为 28/28 通过；攻击检测率、洪泛稳定性、决策准确率均为 100%；漏报率和误报率均为 0；`python -m unittest discover -s tests` 通过，113 个测试 OK；`python scripts\local-release-gate.py --quick --report docs\local-release-gate-after-core-fix.md` 通过，敏感扫描 205 个文件且 findings=0。
- 远程 AI：已显式执行 `python scripts\agent-ai-full-flow-smoke.py --include-live --budget-cents 100 --report docs\agent-ai-live-full-flow-smoke.md`，`live_used=true`，同步 Agent 审查通过，预算记录 `daily_spend_cents=1`；报告不输出 API Key、API Base、代理 URL、Authorization、原始 Prompt 或原始请求体。
- 文档：新增 `docs/qa-core-authenticity-verification-report.md`、`docs/qa-core-authenticity-fix-report.md`、`docs/agent-ai-live-full-flow-smoke.md` 和分项真实性报告。

### 2026-06-02 Step 101：日终收尾

- 收尾结论：今天的控制台核心能力补齐、核心真实性验证、分区块修复、远程 AI live smoke、敏感扫描和发布闸门均已形成报告，当前可进入“提交前复核 / Ubuntu 与云服务器复测 / 长时压测”阶段。
- 仍需注意：本轮最终通过结果基于 Windows 本地、mock-core 真实性矩阵和一次 live provider 小流量 smoke；Ubuntu、Docker、云服务器、100MB 至 5GB 日志和长时间稳定性仍需在隔离环境继续跑。
- 交付索引：日终总结见 `docs/daily-closeout-2026-06-02.md`。

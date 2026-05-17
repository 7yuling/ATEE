# ATEE 项目进度报告

更新时间：2026-05-16

## 当前结论

ATEE P0 已完成一个可本地运行的最小闭环版本。当前重点不是完整生产产品，而是把 v3.3 文档里的核心安全边界做成可演示、可测试、可继续迭代的工程骨架。

本轮已完成管理台从静态页到 React + Ant Design + Vite 的最终形态迁移，并保留了前一轮修复过的“看起来完全无法运行”问题的防线：

1. 内联脚本里出现字面量 `</script>`，浏览器提前结束脚本，导致后续 JS 被当成正文显示。
2. CSP 禁止 inline script/style，导致管理台样式和脚本在真实浏览器里被拦截。

修复方式：

- 将测试 XSS payload 移出 HTML 内联脚本。
- 将管理台拆分为 React 源码、Vite 构建入口和生成后的 `index.html`、`styles.css`、`admin.js`。
- Core Service 增加 `/admin/styles.css` 和 `/admin/admin.js` 静态资源路由。
- CSP 对脚本保持严格：`script-src 'self'` 加动态 nonce；Ant Design 运行期样式通过 CSP nonce 和最小 `style-src-attr` 兼容。
- 响应增加 `Cache-Control: no-store`，降低旧页面缓存造成的误判。

本次针对“控制台很多功能没实现”的问题完成补强：一句话概括，是前端只把已有 API 做成了展示入口，缺少可保存、可筛选、可带参数执行的管理闭环；最小解决方案，是不新增后台大能力，只把既有 `/v1/admin/*` 接口补成表单、筛选器和可回填操作，并把缺失的 `runtime_mode` 配置更新接到 Core。

本次继续完善控制台操作保护层：自动模式、申诉审核、动作撤销、过期清理和配置保存都加入二次确认；只读模式会禁用写入类管理操作并显示保护提示，降级和暂停态也会在顶部提示当前运行约束。

本次继续推进管理台生产化认证边界：默认保持本地开发可用；开启 `admin_auth_enabled` 后，所有 `/v1/admin/*` 管理接口必须携带 Admin Token，令牌来自环境变量或密钥文件，状态和错误响应只返回是否配置，不返回令牌值。

本次补齐生产部署入口的下一步：新增 Nginx/Caddy 反向代理示例和 Admin Token 轮换脚本。轮换脚本默认只写环境文件并输出短指纹，不把新令牌打印到日志；反向代理示例统一回源到 `127.0.0.1:8787`，并带基础安全头。

本次继续补齐管理操作审计身份绑定：控制台可填写操作者 ID，管理 API 可接收 `X-ATEE-Admin-Id`，Core 会把清洗后的操作者 ID、操作者短哈希和来源短哈希写入管理类审计摘要；Admin Token、原始 IP、代理 URL 和供应商密钥仍不进入账本。

本次修复管理台展示可用性问题：顶部指标卡改为可换行的摘要块，避免 `deepseek/openai_compatible` 等长文本溢出；模型网关展示拆分为“配置已接入”和“最近检测结果”，避免把 DeepSeek 配置误读为实时连通；运行状态和操作结果从默认裸 JSON 改为摘要展示，并保留可展开原始 JSON。

本次完成管理台构建体积拆分：Vite 按 React、Ant Design 组件、图标和其他 vendor 生成多个 chunk，最大 JS chunk 降到约 402 KB；Core Service 改为托管受控 `/admin/*.js` chunk，避免 modulepreload 资源 404。

本次补齐生产 SSO/反向代理身份注入示例：新增 Nginx 和 Caddy 的 SSO 反代样例，明确由 auth_request / forward_auth 层覆盖注入 `X-ATEE-Admin-Id`，避免生产环境直接信任浏览器自带的操作者请求头。

本次新增生产反向代理冒烟验收脚本：`scripts/production-smoke-check.py` 可检查 HTTPS/安全头、管理台拆分资源、运行状态、Admin Token 强制认证，以及可选的 SSO 身份覆盖注入与审计账本归因；输出和报告不打印完整目标 URL、Admin Token 或操作者标识。

本次新增 Admin Token 轮换后的自动复验脚本：`scripts/admin-token-rotation-smoke.py` 会先轮换环境文件中的 Admin Token，再执行可选服务重启、旧令牌拒绝检查和新令牌生产冒烟复验；输出和报告只保留短指纹与布尔结果，不打印令牌值、完整目标 URL 或操作者标识。

本次完成 Agent 中 AI 链接与真实状态全流程演练：当前配置的 OpenAI-compatible AI 网关在代理和加密密钥配置下可真实触达，live 探针返回 `provider_json_decision`；随后用同一套真实 AI 配置、临时 SQLite 账本跑通低风险跳过、同步 Agent 审核、Fast-Path 拦截、申诉提交、管理员审核和账本审计闭环，演练输出不包含 API key、代理 URL、API base、密钥文件路径或原始 Prompt。
本次将 Agent AI 全流程演练固化为可重复脚本：`scripts/agent-ai-full-flow-smoke.py` 默认使用临时 fake provider 和临时 SQLite 账本，只有显式 `--include-live` 才触达真实 AI；脚本已生成 fake/live 脱敏报告，覆盖 skip、sync_agent AI 审核、Fast-Path、申诉、管理员审核和账本审计。
本次新增本地发布闸门：`scripts/local-release-gate.py` 将配置预检、Python 编译、单元测试、默认 fake Agent AI 全流程冒烟和敏感扫描串成一条命令，报告只保留脱敏摘要，不输出原始命令日志。

## 已完成

### 配置持久化

- 启动时自动创建 `config/config.json`。
- 运行模式切换会写回配置文件。
- Agent 暂停/恢复会写回配置文件。
- `trusted_proxy_cidrs`、超时预算、自动 IP 封禁开关、旁路开关可通过 `/v1/admin/config` 更新。
- 更新 `trusted_proxy_cidrs` 后会立即重建 Trusted Real IP Resolver。
- `bypass_key` 不通过配置 API 返回；推荐使用 `bypass_key_file` 指向本地密钥文件。
- `llm_api_key_file`、`bypass_key_file`、`ledger_sqlite_path` 等相对路径统一按项目根目录解析。
- Windows 启动脚本会先运行配置预检，提前发现 DPAPI 用户上下文或密钥路径错误。
- `admin_auth_enabled`、`admin_token_env` 和 `admin_token_file` 可通过配置文件启用管理 API 认证；预检会在启用后提前发现缺失或不可读的 Admin Token。

### Core Service

- `/v1/check`
- `/v1/event`
- `/v1/appeal`
- `/v1/runtime/status`
- `/v1/admin/mode`
- `/v1/admin/pause-agent`
- `/v1/admin/break-glass/status`
- `/v1/onboarding/steps`
- `/v1/admin/config`
- `/v1/admin/llm/test`
- `/v1/admin/ledger/recent`
- `/v1/admin/appeals`
- `/v1/admin/appeals/review`
- `/v1/admin/actions`
- `/v1/admin/actions/revoke`
- `/v1/admin/actions/cleanup-expired`
- 管理接口认证：启用后所有 `/v1/admin/*` 需要 `Authorization: Bearer <token>` 或 `X-ATEE-Admin-Token`。
- 管理操作审计：写入类 `/v1/admin/*` 可携带 `X-ATEE-Admin-Id`，审计账本记录操作者 ID 与短哈希，不记录 Admin Token 或原始 IP。

### Remote LLM Gateway

- 默认 `mock` 模式，无需联网或 API Key。
- 非 Fast-Path 拦截请求会进入 mock 网关。
- mock 输出结构化 `agent_decision`，再进入本地 final_confidence 和 Tool Gateway。
- 不保存原始 Prompt Packet。
- 提供 `/v1/admin/llm/test` 用于连接测试。
- 已实现 OpenAI-compatible 网关，支持 `llm_api_key_file` / `llm_api_key_env`。
- 公网供应商强制使用 HTTPS；HTTP base 会在发送 Authorization 前被拒绝。
- 本地 DeepSeek 配置已安装，密钥已迁移到 Windows DPAPI 加密文件，状态接口只返回是否配置。
- 代理已生产化为 `llm_proxy_url` 配置项，不再依赖启动脚本硬编码环境变量。
- 新增每日远程调用预算保护：`llm_daily_budget_cents=0` 表示不限制，正数按每次远程尝试 1 cent 估算。
- 新增失败熔断：连续 3 次供应商请求失败或超时后，60 秒内直接返回本地降级结果。
- 运行状态和 `/v1/admin/llm/test` 会返回预算/熔断健康摘要，不返回密钥、密钥路径、代理 URL 或原始 Prompt。
- 新增 `scripts/agent-ai-full-flow-smoke.py`，默认使用临时 fake provider，显式 `--include-live` 时做一次真实 AI 全流程冒烟，覆盖低风险 skip、同步 Agent AI 审核、Fast-Path 拦截、申诉、管理员审核和账本审计。

### 安全模块

- Trusted Real IP Resolver
- Fast-Path Rule Gate
- Request Router
- Prompt Packet Compiler
- Agent Decision Engine
- final_confidence 计算
- Tool Gateway 执行边界
- Action Executor（执行记录 SQLite 恢复）
- Security Ledger Lite（SQLite 摘要持久化 + 低危内存聚合）
- Appeal Fast-Path Lock（pending 申诉 SQLite 恢复 + 内存限流）
- Appeal 审核处理（approved/rejected SQLite 持久化）
- Action 管理闭环（列表、撤销、过期清理）
- Runtime Mode
- Break-Glass 状态检查

### 中文适配

- 管理台中文界面
- 中文运行状态展示
- 中文 API `display` 字段
- 中文小白引导步骤
- 中文敏感字段脱敏：密码、手机号、邮箱、身份证、银行卡、验证码、密钥、令牌
- 中文快速开始文档

### React + Ant Design 管理台

- `apps/admin-console-src` 为 React 源码，使用 Ant Design 组件和 Vite 构建。
- `npm run build:admin` 生成 `apps/admin-console/index.html`、`styles.css` 和 `admin.js`，继续由 Core Service 同源托管。
- 管理台覆盖仪表盘、申诉审核、动作撤销、安全账本、网关配置和新手引导。
- 保留 Browser E2E 使用的关键 DOM ID，迁移后自动化链路仍可直接操作。
- HTML 通过服务端动态 CSP nonce 启动 React，AntD 运行期样式通过 nonce 兼容层和最小样式属性放行适配。
- 顶部运行模式补齐 `degraded` 和 `read_only` 快捷切换，配置页可保存运行模式、可信代理、超时预算、模型网关、预算、账本和旁路配置。
- 申诉和动作管理支持状态筛选与表格行回填；安全账本支持查询条数控制；Break-Glass 检查支持请求头输入。
- 高影响操作增加 Popconfirm 二次确认；只读模式下禁用申诉审核、动作撤销、过期清理和配置保存，并显示 `operationGuardAlert` 保护提示。
- 新增管理令牌面板，Admin Token 只保存在浏览器 `sessionStorage`，并只随 `/v1/admin/*` 请求发送；认证失败时显示 `adminAuthAlert`。
- 新增操作者 ID 输入，随管理请求发送 `X-ATEE-Admin-Id`，用于后端审计身份绑定；未填写时后端按 `unknown` 归档。
- 顶部指标卡改为可换行 `MetricCard`，模型网关卡片区分配置状态和最近连通状态；运行状态与操作结果改为摘要卡，原始 JSON 收入可展开区域。
- Vite 构建已拆分 React、Ant Design 组件、图标和 vendor chunk；Core Service 可托管 `/admin/admin-*.js` 受控 chunk，避免生产页面加载额外模块时 404。

### 生产部署资产

- `deploy/reverse-proxy/nginx/atee.conf.example` 提供 Nginx HTTPS 反向代理示例，本地回源到 `127.0.0.1:8787`，并设置 HSTS、`nosniff`、Referrer Policy 和 Permissions Policy。
- `deploy/reverse-proxy/caddy/Caddyfile.example` 提供 Caddy 反向代理示例，转发 `X-Forwarded-*` 与 `X-Real-IP`，不启用 wildcard CORS。
- `deploy/reverse-proxy/nginx/atee-sso.conf.example` 和 `deploy/reverse-proxy/caddy/Caddyfile.sso.example` 提供 SSO 身份注入示例，由反向代理认证层覆盖写入 `X-ATEE-Admin-Id`。
- `scripts/rotate-admin-token.py` 支持跨平台轮换 `ATEE_ADMIN_TOKEN` 环境文件条目，默认只输出短指纹；`scripts/linux/atee-core.env.example` 已补 Admin Token 占位。
- `scripts/production-smoke-check.py` 提供生产反向代理冒烟验收，覆盖健康检查、管理台 chunk、运行状态、Admin Token 和可选审计归因。
- `scripts/admin-token-rotation-smoke.py` 提供 Admin Token 轮换后自动复验，覆盖环境文件轮换、可选重启、旧令牌拒绝、新令牌冒烟和脱敏报告。
- `scripts/local-release-gate.py` 提供本地发布前闸门，覆盖配置预检、Python 编译、单元测试、默认 fake Agent AI 全流程冒烟和敏感扫描。

### 适配器

- Node/Express Thin Adapter 示例
- Python Thin Adapter 示例

### Demo Site

- `apps/demo-site` 提供最小业务站点。
- 登录链路通过 Python Thin Adapter 调用 Core `/v1/check`。
- 评论和上传链路通过 Python Thin Adapter 调用 Core `/v1/event`。
- 申诉链路通过 Python Thin Adapter 调用 Core `/v1/appeal`。
- Demo UI 使用外部 CSS/JS，返回文本按 `textContent` 渲染。

## 当前验证结果

- 单元测试：86 个，通过。
- Python 编译检查：通过。
- 配置预检：`python services\core-service\check_config.py` 通过。
- Browser E2E：`npm run e2e:browser` 通过，使用系统 Chrome 和临时 mock Core Service。
- 管理台构建：`npm run build:admin` 通过，当前无 chunk 超过 500 kB；最大 JS chunk 约 402 KB，入口 `admin.js` 约 33 KB。
- React 管理台专项验证：`python -m unittest tests.test_admin_console tests.test_http_e2e` 8 个测试通过，覆盖 Vite 外部资产、拆分 chunk、React 源码 E2E ID、动态 CSP nonce 和 HTTP 工作流。
- 混合负载与重启恢复测试：`tests/test_recovery_load.py` 通过，覆盖 skip/async/sync/Fast-Path 流量、SQLite 账本恢复、申诉审核状态恢复、动作撤销与过期恢复。
- 供应商故障注入测试：`tests/test_provider_faults.py` 通过，使用本地 fake OpenAI-compatible provider 覆盖成功脱敏、HTTP 500 降级和熔断后停止远程请求。
- 供应商/代理故障演练脚本：`python scripts\provider-fault-drill.py` 通过，默认使用内存坏代理，不改真实配置，不调用 live provider，验证 3 次受控失败后熔断打开。
- 供应商/代理故障演练报告：`python scripts\provider-fault-drill.py --report <path>` 可输出脱敏 Markdown 报告，测试覆盖不包含密钥、代理 URL 和 API base。
- 真实供应商 live 恢复演练：`python scripts\provider-fault-drill.py --include-live --report <path>` 通过；坏代理演练 3 次 `provider_timeout` 后第 4 次返回 `llm_circuit_open`，真实供应商单次探针返回 `ok=true`、`provider_json_decision`，延迟 8110 ms；JSON 摘要和 Markdown 报告继续省略 API key、代理 URL、API base、密钥文件路径、原始 Prompt 和原始请求体。
- 供应商预算/限流演练：`python scripts\provider-budget-drill.py --attempts 5 --budget-cents 2 --report <path>` 通过；5 次尝试中只有 2 次触达本地 fake provider，后 3 次返回 `llm_budget_exhausted`，熔断保持关闭，报告继续省略 API key、代理 URL、API base、密钥文件路径、原始 Prompt 和原始请求体。
- 小批量 live 演练入口：`python scripts\provider-live-batch-drill.py --attempts 4 --budget-cents 2 --report <path>` 通过；默认使用本地 fake provider，不调用真实供应商，4 次尝试中 2 次触达 fake provider、2 次返回 `llm_budget_exhausted`；显式 `--include-live` 时最多 3 次。
- 真实供应商小批量 live 演练：`python scripts\provider-live-batch-drill.py --include-live --attempts 3 --budget-cents 3 --report <path>` 通过；3 次真实调用全部返回 `provider_json_decision`，平均延迟 7225 ms，预算剩余为 0，熔断保持关闭，报告继续省略 API key、代理 URL、API base、密钥文件路径、原始 Prompt 和原始请求体。
- Docker 部署入口：新增 `Dockerfile`、`.dockerignore`、`docker-compose.yml` 和 `docs/deployment.md`；部署资产测试通过，确认本地配置、密钥、SQLite、日志、报告和 `node_modules` 不进入镜像上下文。
- Windows 常驻入口：新增计划任务安装/卸载脚本和启动托管脚本；启动脚本会先运行配置预检，再启动 Core Service，并将日志写入 `logs/`。
- Windows SCM 包装入口：新增 WinSW 安装/卸载脚本，复用同一个启动预检脚本；不下载或提交第三方二进制，生成文件放入忽略的 `runtime/`。
- 维护脚本：新增备份、恢复和日志轮转脚本；备份排除 `config/secrets/`，恢复必须显式 `-Force`，日志轮转支持大小阈值和保留数量。
- 备份恢复联调演练：`python scripts\backup-restore-drill.py --report <path>` 通过；临时 source/target 安装目录内验证 config、SQLite、pending 申诉、动作记录可恢复，日志进入备份包，`config/secrets` 和排除标记未进入备份或恢复结果。
- 本地压力脚本：`python scripts\local-stress-check.py --requests 180 --workers 6` 通过，输出 `ok=true`。
- 长时压测入口：`python scripts\local-stress-check.py --duration-seconds <seconds> --workers <n> --report <path>` 已支持按时长运行、可选 `--max-requests` 安全上限、吞吐统计和脱敏 Markdown 报告；短时演练完成 64 个混合请求，四类路由均覆盖，重启恢复检查通过。
- 可控 RPS 长时压测入口：`python scripts\local-stress-check.py --duration-seconds 5 --target-rps 8 --workers 4 --report <path>` 通过；5 秒完成 40 个混合请求，实际吞吐 8.0 RPS，四类路由均覆盖，重启恢复检查通过。
- 30 分钟可控 RPS 压测：`python scripts\local-stress-check.py --duration-seconds 1800 --target-rps 8 --workers 8 --report reports\local-stress-30m-foreground.md` 通过；完成 14400 个混合请求，实际吞吐 8.0 RPS，错误数为 0，SQLite 持久化记录 12962 条，重启恢复检查通过。
- 60 分钟可控 RPS 压测：`python scripts\local-stress-check.py --duration-seconds 3600 --target-rps 8 --workers 8 --report reports\local-stress-60m-foreground.md` 通过；完成 28800 个混合请求，实际吞吐 8.0 RPS，错误数为 0，SQLite 持久化记录 25922 条，重启恢复检查通过。
- 60 分钟压测后回归：`python -m unittest discover -s tests` 通过，68 个测试全部通过；`python -m compileall services adapters apps tests scripts` 通过；`python services\core-service\check_config.py` 通过；`npm run e2e:browser` 通过，完成 9 项浏览器检查。
- 压测后敏感扫描：排除 `config/secrets/` 和 `node_modules/` 后未发现明文 API key、真实代理地址或真实供应商 endpoint 残留；已清理测试产生的 6 个 `__pycache__` 目录。
- 120 分钟可控 RPS 压测：`python scripts\local-stress-check.py --duration-seconds 7200 --target-rps 8 --workers 8 --report reports\local-stress-120m-foreground.md` 通过；完成 57600 个混合请求，实际吞吐 8.0 RPS，错误数为 0，SQLite 持久化记录 51842 条，重启恢复检查通过。
- 120 分钟压测后回归：`python -m unittest discover -s tests` 通过，68 个测试全部通过；`python -m compileall services adapters apps tests scripts` 通过；`python services\core-service\check_config.py` 通过；`npm run e2e:browser` 通过，完成 9 项浏览器检查；敏感扫描仍未发现明文 API key、真实代理地址或真实供应商 endpoint 残留。
- 本地服务功能验证：当前用户上下文临时启动 `http://127.0.0.1:8787/` 通过；管理台 HTML/CSS/JS 均返回 200；运行状态、中文新手引导、低风险 skip、Fast-Path XSS 拦截、申诉、最近账本和模型网关健康检查均通过。
- 运行注意事项：DPAPI CurrentUser 密钥绑定创建它的 Windows 用户；若用不匹配的提权/服务上下文直接启动 `run_server.py`，模型网关会因无法解密密钥返回 `missing_api_key`，生产部署需使用同一服务账号迁移密钥或改用环境变量/密钥管理器。
- 当前用户后台启动入口：新增 `scripts\windows\start-atee-core-background.ps1` 和 `scripts\windows\stop-atee-core-background.ps1`，启动前预检配置，启动后等待 `/health`，处理 `Path`/`PATH` 重复环境变量，并通过 `logs\atee-server.pid` 管理后台进程。
- Windows 运维脚本修正：带 `ProjectRoot` 的脚本不再在参数默认值中依赖 `$PSScriptRoot`，改为参数绑定后解析默认项目根目录，避免 `powershell.exe -File` 调用时默认路径为空。
- 当前用户后台启动验证：部署资产测试 16 个通过；PowerShell 脚本语法检查通过；后台启动脚本返回 `ok=true`；全量测试更新为 70 个通过；Python 编译、配置预检、Browser E2E 和敏感扫描均通过。
- Ubuntu/Linux 服务器适配：新增 Linux 启动脚本、systemd user/system 安装脚本、卸载脚本和环境变量示例；Linux 密钥方案改为 `llm_api_key_env`/systemd 环境文件/密钥管理器，不使用 Windows DPAPI 文件。
- Ubuntu/Linux 适配验证：部署资产测试更新为 20 个通过；全量测试更新为 74 个通过；Python 编译、配置预检、Browser E2E 和敏感扫描均通过。
- React + Ant Design 管理台最终形态：已完成 Vite 构建链、React 源码、Ant Design 中文管理台、CSP nonce 适配和 Browser E2E Tabs 真实路径适配。
- React 管理台功能闭环：补齐 `degraded`/`read_only` 模式切换、配置保存表单、申诉/动作筛选、表格行回填、账本 limit 和 Break-Glass 请求头检查。
- React 管理台操作保护层：自动模式、申诉审核、动作撤销、过期清理和配置保存加入二次确认；只读/降级/暂停态增加顶部保护提示。
- React 管理台验证：当前全量测试为 86 个通过；`npm run build:admin`、`npm run e2e:browser` 16 项浏览器检查、Python 编译、配置预检和敏感扫描均通过。
- 管理台认证边界：新增可选 Admin Token 保护；HTTP E2E 覆盖未授权 401、Bearer Token 和 `X-ATEE-Admin-Token` 两种授权路径，响应中不泄露令牌。
- 反向代理和令牌轮换资产：部署资产测试更新为 22 个通过；该阶段全量测试为 79 个通过；轮换脚本 `--help`、Python 编译和配置预检均通过。
- 管理操作审计身份绑定：Core、HTTP E2E 和 React 管理台测试覆盖 `X-ATEE-Admin-Id` 传递、操作者/来源短哈希入账，以及 Admin Token 和原始来源地址不进入账本摘要；当前全量测试更新为 80 个通过。
- 管理台展示修复：`npm run build:admin` 通过；`npm run e2e:browser` 16 项浏览器检查通过；全量测试 80 个通过；JSON 摘要化后仍保留 `#output` 和 `#result` 原始 JSON 供调试与自动化校验。
- 管理台构建体积拆分：`npm run build:admin` 通过且不再出现 500 kB chunk 警告；HTTP E2E 验证 modulepreload chunk 能由 Core Service 返回；全量测试 80 个通过。
- SSO 身份注入示例：部署资产测试更新为 23 个通过，全量测试更新为 81 个通过；覆盖 Nginx `auth_request`、Caddy `forward_auth`、覆盖注入 `X-ATEE-Admin-Id`、不信任浏览器同名请求头、不包含真实 endpoint 或密钥形态。
- 生产反向代理冒烟验收：新增本地假反代测试，覆盖 Admin Token、SSO 覆盖 actor、审计账本归因和报告脱敏；全量测试更新为 82 个通过。
- Admin Token 轮换复验：新增本地假服务测试，覆盖令牌轮换、重启命令、新旧令牌切换、生产冒烟复跑、审计 actor 覆盖和报告脱敏；全量测试更新为 83 个通过。
- Agent AI 链接和真实状态全流程演练：`python scripts\provider-live-batch-drill.py --include-live --attempts 1 --budget-cents 1 --report reports\agent-ai-live-link-check.md` 通过，真实 AI 调用原因码为 `provider_json_decision`，熔断关闭；临时账本全流程演练通过，覆盖 skip、sync_agent AI 审核、Fast-Path XSS 拦截、申诉、管理员审核和账本审计，真实数据账本未被污染。
- Agent AI 全流程冒烟脚本：新增 `tests/test_agent_ai_full_flow_smoke.py`，默认 fake 演练通过，显式 live 演练通过；真实 AI 调用原因码为 `provider_json_decision`，live 演练熔断关闭，当前全量测试更新为 85 个通过。
- 保密复核：可跟踪区域敏感扫描返回 `NO_MATCHES`；历史报告中的具体供应商 host 和具体密钥文件名已改为占位符；本轮测试产生的 6 个 `__pycache__` 已清理，复查为 0。
- 本地发布闸门：新增 `tests/test_local_release_gate.py`；`python scripts\local-release-gate.py --report reports\local-release-gate.md` 通过，串联配置预检、Python 编译、86 个单元测试、默认 fake Agent AI 全流程冒烟和敏感扫描，扫描 145 个文件且 findings=0。
- 本地服务：`http://127.0.0.1:8787/` 临时 HTTP 验证通过。
- 管理台 HTML：200。
- 管理台 CSS：200。
- 管理台 JS：200。
- HTML 不含内联 style。
- HTML 不含内联 script。
- HTML 只包含一个真正的 `</script>`。
- CSP：脚本保持同源和动态 nonce；样式标签使用 nonce，Ant Design 样式属性使用最小兼容放行。
- `/v1/runtime/status` 返回中文 display。
- `/v1/onboarding/steps` 返回中文小白引导。
- `/v1/admin/ledger/recent` 返回 SQLite 最近账本摘要。
- Appeal/Action 重启恢复测试通过。
- Appeal/Action 本地 HTTP 重启恢复验证通过。
- Demo Site 登录、评论、上传、申诉链路测试通过。
- Demo Site 本地 HTTP 验证通过，运行地址为 `http://127.0.0.1:8790/`。
- DeepSeek 网关本地配置验证通过：base/key/model 均已配置，通过配置化代理后 `/v1/admin/llm/test` 返回 `ok=true`。
- DeepSeek 通过 DPAPI 加密密钥复测通过，公开状态只显示 `api_key_configured=true`。
- DeepSeek 网关新增预算/熔断状态复测通过：`budget` 摘要不含密钥信息，`circuit.open=false`，`/v1/admin/llm/test` 返回 `ok=true`。
- 已清理旧运行日志、Python 缓存目录和旧的 DeepSeek 明文输入文件；保留 `config/config.json`、DPAPI 加密密钥文件和 SQLite 运行数据。

## 尚未完成

- 管理台生产反向代理真机联调、证书/域名验收和目标服务器上的 Admin Token 轮换复验。
- 更高 RPS 或更长周期的生产等价压测。

## 下一阶段建议

1. 在目标服务器上运行 `scripts/production-smoke-check.py`，用真实域名、证书、Admin Token 和 SSO 身份注入完成联调验收。
2. 在同一目标服务器上运行 `scripts/admin-token-rotation-smoke.py`，把真实重启命令、旧令牌拒绝和新令牌冒烟复验纳入上线检查。
3. 使用 `--target-rps` 执行更高 RPS 或 4 小时以上长压测。

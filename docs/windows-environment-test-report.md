# ATEE Windows 环境测试书面报告

- 报告日期：2026-06-02
- 范围：Windows 本地开发环境、Windows 常驻/服务脚本边界、Windows 浏览器端到端、Windows CI 相关验证。
- 不包含：Ubuntu WSL、Linux systemd、Nginx 真实反代矩阵；这些内容由 WSL/Ubuntu 专项报告独立记录。
- 保密边界：本报告不记录 API Key、Admin Token、代理 URL、API Base 实值、密钥文件路径、Authorization、原始 Prompt 或原始请求体。

## 一句话结论

ATEE 在 Windows 环境中已经完成从本地运行、管理台构建、浏览器操作、Core/HTTP 回归、长时压力、真实/假模型链路、异步 AI 审查、生产冒烟、Admin Token 轮换、发布闸门到 Windows CI 的主要验证；当前 Windows 侧核心链路可运行，剩余注意点主要是 DPAPI 用户上下文、LF/CRLF 提示和 Windows runner 性能波动。

## 环境与对象

| 项目 | 说明 |
|---|---|
| 工作区 | `C:\Users\Pro16\Documents\Codex\ATEE` |
| 运行形态 | Windows 本地 Python/Node、Core Service 临时服务、React + Ant Design 管理台、系统 Chrome/Chromium 浏览器自动化。 |
| 密钥形态 | Windows 侧支持 DPAPI/密钥文件/环境变量；测试与报告只记录“是否已配置”，不回显敏感值。 |
| 服务入口 | 本地临时服务常用 `127.0.0.1` 随机端口或 `127.0.0.1:8787`；生产脚本验证健康检查、管理台资源和管理接口鉴权。 |

## Windows 测试总览

| 测试类别 | 代表命令或报告 | Windows 结论 |
|---|---|---|
| Core 与 Python 回归 | `python -m unittest discover -s tests` | 最新 Windows 全量回归 107 个测试通过；历史管理台拆分前后也通过 68、86、94、96、100、105 等阶段性回归。 |
| 管理台源码与静态资源 | `python -m unittest tests.test_admin_console` | 4 个测试通过，覆盖 HTML/CSP、静态资源、API 端点、React 源码 e2e ID、敏感 JSON 脱敏和纯文本渲染。 |
| HTTP 集成 | `python -m unittest tests.test_http_e2e` | 覆盖 Core HTTP、管理台静态资源、CSP nonce、Admin API 鉴权和并发请求冒烟。 |
| 管理台生产构建 | `npm.cmd run build:admin` | Vite 构建通过，管理台产物可生成并由 Core 同源托管。 |
| 浏览器端到端 | `npm.cmd run e2e:browser` | 最新 32 项真实按钮链路通过；历史阶段从 9 项、20 项逐步扩展到 32 项。 |
| 本地发布闸门 | `python scripts\local-release-gate.py --quick --report reports\local-release-gate.md` | quick gate 通过，配置预检、Python 编译、32 个聚焦单测、Agent AI fake 冒烟、异步 AI worker fake 冒烟、敏感扫描全部通过，findings=0。 |
| 生产冒烟 | `python -m unittest tests.test_production_smoke_check` | 2 个测试通过，覆盖 `/health`、管理台首页、静态资源、运行状态、Admin Token 鉴权、审计 actor 探针和报告脱敏。 |
| Admin Token 轮换 | `tests.test_admin_token_rotation_smoke` | 旧 token 拒绝、新 token 通过，报告只保留短指纹和布尔结果。 |
| 备份恢复 | `python scripts\backup-restore-drill.py --report ...` | Windows 侧演练通过，验证 config、SQLite、pending 申诉、动作记录和日志恢复；`config/secrets` 不进入备份。 |
| 长时压力 | `reports/local-stress-*.md` | 30/60/120 分钟压测均通过，8 RPS，0 错误，重启恢复检查通过。 |
| 模型链路 | `reports/agent-ai-*.md`、`reports/sandbox-attack-defense-*.md` | fake 与 live 全流程均通过，覆盖 skip、同步 AI 审核、Fast-Path、申诉、管理员审核和账本摘要。 |
| 异步 AI 审查 | `reports/async-ai-review-worker-smoke*.md` | fake 预算/熔断场景通过；live 单条 worker 审查通过。 |
| Windows CI | GitHub Actions Windows quick gate / Browser E2E | 远端 Windows Browser E2E 成功；Windows quick gate 后续修正了换行检查方式和慢 runner 超时阈值。 |

## 长时压力测试

| 报告 | 生成时间 UTC | 时长 | 目标吞吐 | 请求数 | 错误 | 关键结论 |
|---|---:|---:|---:|---:|---:|---|
| `reports/local-stress-start-test-20260515-121721.md` | 2026-05-15 04:17:28 | 5 秒 | 2 RPS | 10 | 0 | 小规模混合流量通过，四类路由均覆盖，重启恢复通过。 |
| `reports/local-stress-30m-foreground.md` | 2026-05-15 04:49:12 | 30 分钟 | 8 RPS | 14,400 | 0 | SQLite 持久化 12,962 条，pending 申诉、撤销动作、过期动作恢复通过。 |
| `reports/local-stress-60m-foreground.md` | 2026-05-15 06:26:24 | 60 分钟 | 8 RPS | 28,800 | 0 | SQLite 持久化 25,922 条，回归测试和浏览器 E2E 后续通过。 |
| `reports/local-stress-120m-foreground.md` | 2026-05-15 08:31:55 | 120 分钟 | 8 RPS | 57,600 | 0 | SQLite 持久化 51,842 条，重启恢复和敏感扫描通过。 |

压力测试覆盖的路由包括 `skip`、`sync_agent`、`async_agent` 和 `fast_path_block`。所有压力报告均使用临时 mock LLM 配置和临时 SQLite 状态，不记录密钥、代理、API Base、原始 Prompt 或原始请求体。

## AI 与安全全流程

| 报告 | 模式 | 结论 |
|---|---|---|
| `reports/agent-ai-live-link-check.md` | live | 真实供应商单次连通通过，返回 `provider_json_decision`，延迟约 7.4 秒。 |
| `reports/agent-ai-full-flow-smoke-live.md` | live | 运行状态、低风险 skip、同步 AI 审核、Fast-Path、申诉提交、管理员审核、账本读取全部 OK。 |
| `reports/agent-ai-full-flow-smoke-fake.md` | fake | 本地假供应商全流程通过，不触达真实供应商。 |
| `reports/sandbox-attack-defense-flow.md` | fake | 沙箱攻防流程通过。 |
| `reports/sandbox-attack-defense-flow-live.md` | live | 真实模型参与的沙箱攻防流程通过，预算消耗 1 cent，熔断关闭。 |
| `reports/sandbox-attack-defense-full-log.md` | live | 真实模型链路、Fast-Path、申诉、管理员审核和账本摘要均闭环；同步 AI 审核返回结构化判断，工具网关处于 `would_have_action`，未实际处罚。 |

以上链路共同验证：低风险请求可本地跳过，XSS 样例可由 Fast-Path 直接拦截，登录/风险类请求可进入同步 Agent 审核，用户申诉和管理员审核可以写入账本摘要。

## 异步 AI 审查 worker

| 报告 | 模式 | 场景 | 结论 |
|---|---|---|---|
| `reports/async-ai-review-worker-smoke.md` | fake | 预算耗尽 | 2 个任务中 1 个完成、1 个进入死信；仅 1 次 provider 调用，熔断关闭。 |
| `reports/async-ai-review-worker-smoke.md` | fake | 供应商失败熔断 | 3 个任务触发 3 次 provider 调用，熔断打开，未泄露敏感信息。 |
| `reports/async-ai-review-worker-smoke-live.md` | live | 单条真实 worker 审查 | 1 个任务排队、1 个完成、0 死信，熔断关闭。 |

worker 报告同样不输出 API Key、API Base、代理 URL、Authorization、原始 Prompt、原始请求体或临时 SQLite 路径。

## 管理台与浏览器端到端

Windows 管理台验证经历了多轮扩展：

| 阶段 | 浏览器检查数 | 覆盖重点 |
|---|---:|---|
| 初期 React 管理台 | 9 | 页面加载、基础安全演练、运行状态、核心按钮链路。 |
| 管理台拆分与生产化 | 20 | 操作台、Agent 对话、新手引导、申诉、动作管理、账本、网关配置、紧急旁路。 |
| 分板块闭环检查 | 21 到 30 | LLM 按钮真实点击、引导动作、申诉驳回、异步 AI 审查只读保护、动作只读保护、账本公开摘要、配置只读保护、系统读写边界。 |
| 当前核心能力补齐 | 32 | 新增安全流程一键演练与只读保护，验证 `POST /v1/admin/security-flow/run` 返回 `flow_steps`。 |

最新 Windows 浏览器 E2E 使用 `npm.cmd run e2e:browser`，启动临时 Core Service，用 Chromium/系统浏览器真实点击控制台按钮并校验接口返回。

## Windows 部署与运维验证

| 项目 | Windows 结论 |
|---|---|
| Windows 启动脚本 | 启动前运行配置预检，提前发现 DPAPI 用户上下文或密钥路径错误。 |
| Windows 常驻入口 | 已新增计划任务安装/卸载脚本和启动托管脚本；日志写入 `logs/`。 |
| Windows SCM 包装 | 已新增 WinSW 安装/卸载脚本，复用启动预检脚本；不提交第三方二进制，运行文件放入忽略目录。 |
| DPAPI 边界 | CurrentUser 密钥绑定创建它的 Windows 用户；用不匹配的提权/服务上下文直接启动可能无法解密。 |
| Admin Token | 控制台只把 Admin Token 保存到浏览器 `sessionStorage`，仅随 `/v1/admin/*` 请求发送；服务端 token 通过环境变量或密钥文件读取。 |
| 生产冒烟 | 覆盖健康检查、管理台 chunk、运行状态、Admin Token 强制认证、可选审计归因和报告脱敏。 |

## Windows CI 与工程化

| 项目 | 结果 |
|---|---|
| GitHub Actions Windows Browser E2E | 远端 Windows 浏览器 E2E 成功。 |
| Windows quick gate | 已纳入 CI；后续修正空白检查策略，避免构建产物或 CRLF 差异误判。 |
| CI 空白检查 | Windows/Ubuntu quick gate 改用 `scripts/ci-whitespace-check.py` 读取 `HEAD` 内容检查行尾空白；本地仍保留 `git diff --check`。 |
| 慢 runner 超时 | Windows runner 较慢时，嵌套 release gate 测试曾接近 90 秒超时；已把相关测试超时提高到 240 秒。 |
| 本地 pre-push | 新增 `.githooks/pre-push`，覆盖关键单测、管理台构建和 diff check。 |

## 发现的问题与处理

| 问题 | 影响 | 处理状态 |
|---|---|---|
| 内联脚本含 `</script>` 导致浏览器提前截断脚本 | 管理台无法正常渲染 | 已修复，测试 payload 移出 HTML 内联脚本。 |
| CSP 禁止 inline script/style | React 管理台样式和脚本被真实浏览器拦截 | 已修复，使用外部资源、服务端 CSP nonce 和 Ant Design nonce 兼容。 |
| DPAPI 绑定 Windows 用户上下文 | 服务/提权上下文不匹配时可能无法读取密钥 | 已在进度报告和预检中明确，生产建议使用环境变量或服务密钥管理。 |
| Windows/WSL 共用 `node_modules` | 可能导致 Vite native binding 不匹配 | 已记录为依赖隔离风险，建议独立 clone、独立依赖目录或容器。 |
| Windows CI `git diff --check` 易受构建产物/换行影响 | 远端 quick gate 误判失败 | 已改为 CI 专用 whitespace check。 |
| Windows runner 慢导致 release gate 子进程接近超时 | CI 偶发失败 | 已把超时阈值提高到 240 秒。 |

## 当前 Windows 验收状态

| 验收面 | 状态 |
|---|---|
| 本地 Core 主流程 | 通过 |
| 管理台构建 | 通过 |
| 浏览器 E2E | 通过，最新 32 项 |
| Python 全量回归 | 通过，最新 107 项 |
| 发布闸门 | 通过，quick gate findings=0 |
| 压力与恢复 | 通过，最长 120 分钟 57,600 请求 0 错误 |
| live 模型小流量 | 通过，仅显式 live 演练触发 |
| 异步 AI worker | fake/live 均通过 |
| 生产冒烟与 Admin Token | 通过 |
| Windows CI | 通过并完成慢 runner 与换行策略修正 |

## 后续建议

1. Windows 服务化部署时优先使用环境变量或专用密钥管理，不把生产 API Key 明文写入仓库或普通配置文件。
2. Windows 与 WSL 不要在同一工作区反复共享 `node_modules`，避免 native binding 互相覆盖。
3. 保留 `npm.cmd run e2e:browser` 作为 Windows 管理台改动后的必跑项。
4. 保留 `python scripts\local-release-gate.py --quick` 作为打包、提交、推送前的 Windows 本地闸门。
5. 对真实生产 Windows 服务场景，另行跑一次“服务账户上下文”启动测试，确认 DPAPI/环境变量/Admin Token 都由同一个服务身份读取。

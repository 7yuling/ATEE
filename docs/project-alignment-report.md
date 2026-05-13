# ATEE 项目对齐报告

报告日期：2026-05-13  
对齐对象：

- `ATEE_Agentic_Coding_Workflow_v3.3.md`
- `ATEE_最终合并会议报告_v3.3_含小白引导.md`
- 当前工程目录：`C:\Users\Pro16\Documents\Codex\2026-05-12\skills\atee`

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

- 单元测试：16 个，通过。
- Python 编译检查：通过。
- 本地服务：`http://127.0.0.1:8787/`。
- 管理台 HTML/CSS/JS 均由 Core Service 返回。
- CSP 保持严格：仅允许同源脚本和同源样式。
- `/v1/runtime/status` 返回中文运行状态。
- `/v1/admin/config` 可读写本地配置。
- `/v1/onboarding/steps` 返回中文新手引导。
- XSS 样例会被 Fast-Path 拦截，且 `llm_called=false`。

## 3. P0 硬约束对齐

| 硬约束 | 当前状态 | 说明 |
|---|---:|---|
| 核心逻辑只在 Core Service | 已对齐 | 主要逻辑集中在 `services/core-service/atee_core`。 |
| Thin Adapter 只做请求提取和 Core 调用 | 已对齐 | Node/Python adapter 仅转发上下文。 |
| 不在每个 SDK 重复安全引擎 | 已对齐 | 未实现多语言完整 SDK。 |
| 请求先过 Real IP 和 Fast-Path | 已对齐 | `/v1/check` 和 `/v1/event` 共用 Core 流程。 |
| 异步路径前也必须过 Fast-Path | 已对齐 | `event()` 复用 `check()` 流程。 |
| Sync Path 不硬等 1.5 秒 LLM | 已对齐 | 当前未接真实 LLM，保留 3s/5s 策略配置。 |
| Local Precheck 100ms，Remote 3s/5s | 部分对齐 | 配置存在，但远程网关尚未实现。 |
| Security Ledger Lite 默认 256MB | 部分对齐 | 内存版 Ledger 已有上限，未落 SQLite。 |
| 低危事件聚合 | 部分对齐 | 内存聚合已实现，未做异步落盘。 |
| 不保存 Prompt Packet 原文和原始请求体 | 已对齐 | 只保存摘要和哈希。 |
| 不允许 AI 生成可执行 regex | 已对齐 | 当前只支持本地固定规则和 `rule_hint`。 |
| 不修改业务数据库，不隐藏/删除内容 | 已对齐 | Action Executor 只记录受控动作。 |
| 管理台禁止危险 HTML 渲染 | 已对齐 | 使用 `textContent`，CSP 严格。 |
| 所有 Agent/用户输入按 untrusted_text | 已对齐 | 中文 display 也标明纯文本策略。 |
| 未配置可信代理禁止自动 IP 封禁 | 已对齐 | Tool Gateway 强制校验。 |
| 申诉白名单必须限流 | 部分对齐 | 内存限流已实现，未持久化。 |
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
| 07 Async Review Path | 队列、重试、死信 | 未完成，仅有路由入口 |
| 08 Prompt Packet Compiler | 脱敏、哈希、allowed/forbidden | 已完成基础版 |
| 09 Remote LLM Gateway | OpenAI-compatible、预算、心跳 | 未完成 |
| 10 Agent Decision + final_confidence | JSON 校验、公式、阈值 | 已完成基础版 |
| 11 Tool Gateway | 动作边界与模式约束 | 已完成基础版 |
| 12 Action Executor | 可撤销、有期限、幂等 | 部分完成，当前为内存记录 |
| 13 Security Ledger Lite | 256MB、聚合、异步落盘 | 部分完成，当前为内存版 |
| 14 Appeal + Fast-Path Lock | 白名单与限流 | 部分完成，当前为内存版 |
| 15 Break-Glass Bypass | Header、日志、轮换提示 | 部分完成 |
| 16 Admin Console | React + Ant Design 管理台 | 部分完成，当前为静态中文管理台 |
| 17 Onboarding Wizard | 纯小白详细引导 | 部分完成，已有中文步骤展示 |
| 18 Runtime Modes | observe/auto/degraded/read-only/pause | 已完成基础版 |
| 19 Tests | Unit/API/Security/E2E/Load | 部分完成，当前 16 个单元测试 |
| 20 Docs | 用户/开发/安全文档 | 部分完成 |
| 21 Final Integration | 全链路验收报告 | 未完成 |

## 5. 架构边界对齐

### Core Service

当前 Core Service 已承载：

- 真实 IP 解析
- Fast-Path
- 请求路由
- Prompt Packet 编译
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

### Admin Console

当前管理台是静态实现，不是 React + Ant Design。  
这符合“先跑通 P0 骨架”的阶段目标，但未达到文档中最终管理台形态。

## 6. 主要风险与偏差

| 风险 | 等级 | 说明 |
|---|---:|---|
| 未接真实 LLM Gateway | 高 | 目前 Agent Decision 仍是本地模拟/规则决策。 |
| Ledger/Appeal/Action 未持久化 | 高 | 重启后安全事件、申诉和动作记录会丢失。 |
| 管理台无认证 | 高 | 当前适合本地演示，不适合暴露到生产网络。 |
| 配置文件无并发锁 | 中 | 单进程演示可用，多进程部署需加锁或改数据库。 |
| Admin Console 不是 React + Ant Design | 中 | UI 已可用，但与最终技术栈要求不完全一致。 |
| 缺 E2E 和压测 | 中 | 只有单元测试，未证明全链路稳定性。 |
| Break-Glass 仅状态检查 | 中 | 缺完整恢复操作流、密钥生成和审计闭环。 |
| Prompt Packet 脱敏有限 | 中 | 已处理常见字段，但无法保证自由文本隐私 100% 识别。 |

## 7. 下一步对齐建议

建议按以下顺序推进：

1. Remote LLM Gateway mock  
   先实现 OpenAI-compatible mock，验证 3s/5s timeout、JSON 解析、非法 action 拒绝、Degraded 切换。

2. SQLite Ledger Lite  
   将 Ledger、Appeal、Action 记录落 SQLite，同时保留低危聚合和请求链路不高频写库原则。

3. Demo Site + Thin Adapter E2E  
   做一个最小业务站点，验证登录、评论、上传、申诉、管理员暂停 Agent 的端到端链路。

4. 管理台升级  
   从静态页面迁移到 React + Ant Design，保留 CSP、纯文本渲染和中文小白引导。

5. 安装与运维  
   增加 Windows 服务化/Docker 启动、配置检查、日志路径、备份恢复说明。

## 8. 当前验收判断

当前项目可以判定为：

```text
P0 工程骨架：通过
P0 本地演示：通过
P0 安全边界原型：部分通过
P0 生产部署：未通过
最终 v3.3 全链路验收：未通过
```

短期目标应继续保持“先闭环、再加深”的节奏：下一步优先实现 Remote LLM Gateway mock，再进入持久化 Ledger 和 E2E。


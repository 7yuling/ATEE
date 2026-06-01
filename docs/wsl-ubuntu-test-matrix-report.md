# ATEE Ubuntu WSL 全量测试矩阵报告

- 报告日期：2026-06-01
- 测试执行环境：Ubuntu 24.04.4 LTS on WSL2
- 项目路径：`/mnt/c/Users/Pro16/Documents/Codex/2026-05-12/skills/atee`
- 结论一句话：ATEE 在 Ubuntu 24.04 WSL 中完成了部署、功能、非功能、自动化与 CI/CD 相关测试；发现并修复了 Linux 灾备 fallback、release gate 测试夹具、WSL systemd+Nginx smoke 脚本三个生产化问题，当前矩阵主项通过。

## 总览

| 维度 | 状态 | 说明 |
|---|---:|---|
| Ubuntu 发行版安装 | 通过 | 已安装 `Ubuntu-24.04` 并可通过 `wsl.exe -d Ubuntu-24.04` 启动。 |
| Linux 工具链 | 通过 | Python 3.12.3、Node 22.12.0、npm 10.9.0、Nginx 1.24.0、systemd 255、Chromium 148。 |
| 配置预检 | 通过 | Linux 下使用 `llm_api_key_env` 注入占位环境变量通过；不依赖 Windows DPAPI。 |
| 全量 Python 回归 | 通过 | 98 个测试通过，1 个按设计跳过。 |
| 前端构建 | 通过 | Vite 构建成功，3032 modules transformed。 |
| UI 自动化 | 通过 | Linux Chromium 下 20 项管理台按钮链路通过。 |
| systemd 部署 | 通过 | 独立 `atee-core-wsltest` user service 启动并通过 `/health`。 |
| Nginx 反向代理 | 通过 | 127.0.0.1:18888 代理到 Core，生产冒烟通过。 |
| 性能矩阵 | 通过 | 负载、压力、容量、稳定性四组均 0 errors。 |
| 安全矩阵 | 通过 | npm audit 0 vulnerabilities，敏感扫描 findings=0，熔断/权限/渗透模拟通过。 |
| 灾备矩阵 | 通过 | Linux Python fallback 备份恢复成功，secrets 未进入备份。 |
| 清理 | 通过 | systemd 测试服务、unit/env、Nginx 临时 conf 已删除。 |

## 环境基线

| 项 | 值 |
|---|---|
| OS | Ubuntu 24.04.4 LTS (Noble Numbat) |
| Kernel | 6.6.87.2-microsoft-standard-WSL2 |
| Python | 3.12.3 |
| Node | 22.12.0 |
| npm | 10.9.0 |
| Nginx | 1.24.0 (Ubuntu) |
| systemd | 255 (255.4-1ubuntu8.12) |
| Browser | Google Chrome for Testing 148.0.7778.96 |

## 修复清单

### 1. Linux 灾备 fallback

- 问题：`scripts/backup-restore-drill.py` 在 Ubuntu 中失败，原因是只查找 `powershell/pwsh`，没有 PowerShell 时直接返回 `powershell_not_found`。
- 最小修复：保留 Windows PowerShell 优先路径；当 PowerShell 不存在时，使用 Python `zipfile` 后端完成备份和恢复。
- 安全边界：Python fallback 只包含 `config/config.json`、`data/atee_ledger.sqlite3` 和 `logs/*`，继续排除 `config/secrets/**`；恢复时检查 zip path traversal。
- 回归：Windows 侧 `tests.test_backup_restore_drill` 3 个测试通过；Ubuntu 侧灾备报告 `ok=true`。

### 2. release gate 测试夹具 Linux 适配

- 问题：Ubuntu 全量测试中 `tests.test_local_release_gate` 失败，因为子进程执行 `check_config.py` 时无法解密 Windows DPAPI 密钥文件。
- 最小修复：只在测试夹具中注入占位 `ATEE_LLM_API_KEY`，不修改生产 `local-release-gate.py` 行为。
- 生产含义：真实 Ubuntu 生产部署仍必须通过环境变量、systemd env file 或密钥管理器注入模型密钥；不能依赖 Windows DPAPI 文件。
- 回归：Ubuntu 全量 `python3 -m unittest discover -s tests` 通过。

### 3. WSL systemd+Nginx smoke

- 问题：手写 PowerShell -> WSL -> bash 长命令转义不稳定，变量和引号会被吞掉。
- 最小修复：新增 `scripts/linux/wsl-systemd-nginx-smoke.sh`，在 Linux 内部完成 systemd user service、Nginx conf、生产冒烟和清理。
- 清理策略：脚本 `trap cleanup EXIT`，退出时停止/disable 测试服务，删除测试 unit、测试 env 和 Nginx 临时 conf。
- 回归：Ubuntu 中脚本语法检查通过，真实运行通过。

## 功能测试

### 单元测试

- 命令：`python3 -m unittest discover -s tests`
- 结果：通过
- 数据：`Ran 98 tests in 78.625s`，`OK (skipped=1)`
- 覆盖：Core 规则、配置、账本、申诉、动作撤销、Admin Token、LLM gateway、异步 AI 审查、部署资产、演示站、备份恢复、发布闸门、生产冒烟等。

### 集成测试

- 命令：`python3 -m unittest tests.test_http_e2e tests.test_admin_token_rotation_smoke tests.test_production_smoke_check`
- 结果：通过
- 数据：7 个测试通过
- 覆盖：HTTP Core 服务、管理台静态资源、Admin API 鉴权、Token 轮换、生产冒烟、审计 actor。

### 系统测试

- 命令：`bash scripts/linux/wsl-systemd-nginx-smoke.sh`
- 结果：通过
- Core 服务：systemd user service `atee-core-wsltest` 启动成功，状态 `active (running)`。
- Core 端口：127.0.0.1:18887。
- Nginx 代理端口：127.0.0.1:18888。
- Core 生产冒烟：`reports/wsl-systemd-production-smoke.md`，`ok=true`。
- Nginx 生产冒烟：`reports/wsl-nginx-production-smoke.md`，`ok=true`。
- 清理：测试 service、unit、env、Nginx conf 已清理。

### API 测试

- 覆盖 API：
  - `GET /health`
  - `GET /`
  - `GET /admin/*.js`
  - `GET /admin/styles.css`
  - `GET /v1/runtime/status`
  - `GET /v1/admin/config`
  - `GET /v1/admin/ledger/recent`
  - `POST /v1/admin/break-glass/status`
  - `POST /v1/admin/mode`
  - `POST /v1/admin/actions/revoke`
  - `POST /v1/admin/appeals/review`
- 结果：通过
- 说明：未开启 Admin Auth 的生产冒烟场景会跳过 token 检查；专项权限测试覆盖了启用 Admin Auth 后的拒绝/通过链路。

### UAT 测试

- 命令：`CHROME_PATH=/root/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome PYTHON=python3 npm run e2e:browser`
- 结果：通过
- 数据：20 项检查通过
- 用户路径：
  - 打开管理台
  - 测试安全请求
  - 测试快速拦截
  - 提交申诉
  - 查看并处理异步 AI 审查
  - 进行 Agent 对话
  - 运行新手引导预检
  - 审核申诉
  - 切换降级/只读/自动模式
  - 查看动作列表并撤销动作
  - 查看安全账本摘要
  - 读取并保存网关配置
  - 触发 LLM 测试入口
  - 检测紧急旁路状态

### 回归测试

- 命令：`python3 -m unittest discover -s tests`
- 结果：通过
- 说明：在修复 Linux fallback 与 release gate 测试夹具后，Ubuntu 全量回归闭合。

## 非功能测试

### 性能测试

| 子项 | 命令 | 请求/时长 | Workers | 结果 | 吞吐 | 错误 |
|---|---|---:|---:|---:|---:|---:|
| 负载 | `local-stress-check.py --requests 500 --workers 8` | 500 requests | 8 | 通过 | 43.27 RPS | 0 |
| 压力 | `local-stress-check.py --requests 2000 --workers 32` | 2000 requests | 32 | 通过 | 30.80 RPS | 0 |
| 容量 | `local-stress-check.py --duration-seconds 10 --max-requests 1000 --workers 16 --target-rps 80` | 10 秒，384 requests | 16 | 通过 | 37.86 RPS | 0 |
| 稳定性 | `local-stress-check.py --duration-seconds 30 --max-requests 1200 --workers 8 --target-rps 20` | 30 秒，600 requests | 8 | 通过 | 20.00 RPS | 0 |

容量结论：当前 WSL/本机环境下可稳定观察到约 37.86 RPS 的混合规则处理吞吐；目标 80 RPS 未达到，不能直接外推为生产服务器容量。生产容量仍需在目标服务器规格、真实磁盘、真实反向代理和真实流量模型下复测。

### 安全测试

| 子项 | 命令/来源 | 结果 | 说明 |
|---|---|---:|---|
| 漏洞扫描 | `npm audit --audit-level=moderate` | 通过 | `found 0 vulnerabilities`。 |
| 敏感扫描 | `local-release-gate.py --quick` | 通过 | 扫描 174 个文件，`findings_count=0`。 |
| 渗透测试 | `agent-ai-full-flow-smoke.py` | 通过 | fast-path XSS block、低风险 skip、同步 AI 审查、申诉与账本闭合。 |
| 供应商故障 | `provider-fault-drill.py` | 通过 | bad proxy 连续失败后熔断打开，第 4 次返回 `llm_circuit_open`。 |
| 权限测试 | `tests.test_admin_token_rotation_smoke` | 通过 | 旧 token 拒绝，新 token 通过，报告不泄露 token。 |

安全边界：本轮未使用真实 API Key；未在报告中输出 API Base、代理地址、密钥文件路径、Authorization、原始 Prompt 或原始请求体。

### 兼容性测试

- Ubuntu 24.04.4 LTS：通过。
- Python 3.12：通过。
- Node 22.12：通过。
- Nginx 1.24：通过。
- systemd user service：通过。
- Linux Chromium headless：通过。
- Windows DPAPI secret file：在 Linux 中不可用，这是预期限制；生产应改为环境变量或密钥管理器注入。

### 可用性测试

- 管理台 20 项按钮链路通过。
- 中文字体在 Linux Chromium 中可渲染并完成交互。
- 右侧功能切换、配置、申诉、账本、动作撤销、新手引导和 Agent 对话均在 UAT 流程中触达。

### 可访问性测试

- 已完成基础 headless UI 可操作性验证。
- 已安装中文字体依赖，避免中文显示缺字导致的操作失败。
- 未完成 axe-core、键盘遍历、色彩对比度、ARIA 完整性专项扫描；这项应列为后续 P1。

### 可靠性测试

- systemd user service 启动并通过健康检查。
- Nginx 反向代理通过生产冒烟。
- 30 秒稳定性测试在 20 RPS 下 0 errors。
- `local-stress-check.py` 内部覆盖重启后账本/申诉持久化一致性。

### 灾备测试

- 命令：`python3 scripts/backup-restore-drill.py --report reports/wsl-backup-restore-drill.md`
- 结果：通过
- 备份内容：config、SQLite、logs。
- 排除内容：`config/secrets/**`。
- 恢复结果：persisted records 13，pending appeals 1，active actions 3。
- 安全结果：源 secret 未恢复到目标；目标占位 secret 保留。

## 自动化测试

| 类型 | 自动化入口 | 结果 |
|---|---|---:|
| Unit Test | `python3 -m unittest discover -s tests` | 通过 |
| API Test | `tests.test_http_e2e`、`tests.test_production_smoke_check` | 通过 |
| UI Test | `npm run e2e:browser` with Linux Chromium | 通过 |
| Performance Test | `scripts/local-stress-check.py` 四组 | 通过 |
| Security Scan | `npm audit`、`local-release-gate.py` sensitive scan | 通过 |

## CI/CD

| 阶段 | 当前实测 | 状态 | 后续建议 |
|---|---|---:|---|
| Git Hook | 已新增 `.githooks/pre-push` 和 `.github/workflows/ci.yml` | 已补齐 | pre-push 覆盖关键单测、管理台构建和 diff check；GitHub Actions 覆盖 quick gate、构建、测试和 Windows 浏览器 E2E。 |
| Build | `npm run build:admin` | 通过 | CI 中固定 Node 22.12+。 |
| Test | Python 全量、UI E2E、release gate | 通过 | CI 分层：PR quick gate，main full gate。 |
| Deploy | WSL systemd+Nginx smoke | 通过 | 生产服务器使用同等 smoke 脚本或 Ansible/systemd task。 |
| Monitoring | `/health` 与 `production-smoke-check.py` | 通过 | 上线后接入定时 health check、production smoke、systemd watchdog 或外部监控。 |

## 风险与限制

| 风险 | 严重度 | 说明 | 建议 |
|---|---:|---|---|
| Linux 不能使用 Windows DPAPI secret file | 高 | 默认配置若仍引用 DPAPI 文件，Ubuntu 预检会失败 | 生产 Linux 必须使用 `llm_api_key_env` 或密钥管理器。 |
| 容量测试只代表 WSL | 中 | WSL 磁盘、CPU 调度、网络栈与云服务器不同 | 目标 Ubuntu 服务器重新跑性能矩阵。 |
| 可访问性专项不足 | 中 | 仅做了 UI 可操作性和中文渲染验证 | 加 axe-core/ARIA/键盘遍历测试。 |
| Git Hook/CI workflow 缺失 | 中 | 已新增共享 hook 和 GitHub Actions，但还未在远端跑过 | 推送后查看 GitHub Actions 首次运行结果；本地需要执行 `git config core.hooksPath .githooks` 才会启用 hook。 |
| 报告产物在 `reports/` 被忽略 | 低 | 本机报告可查看，但默认不提交 | 关键摘要已写入 `docs/`；需要归档时可单独打包。 |

## 最终结论

ATEE 当前已经可以在 Ubuntu 24.04 WSL 中完成初步生产形态验证：systemd user service 能启动，Nginx 能反代，管理台能构建和操作，Core API、Admin 权限、AI fake 流程、异步 AI 审查、性能、敏感扫描、灾备恢复均通过。下一步应把本轮 WSL 矩阵迁移到真实 Ubuntu 服务器或 CI runner，并补齐可访问性专项与 GitHub Actions/Hook。

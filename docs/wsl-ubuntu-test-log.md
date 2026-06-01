# ATEE Ubuntu WSL 实测日志

- 日期：2026-06-01
- 环境：Ubuntu 24.04.4 LTS on WSL2
- 目标：安装可用 Ubuntu 发行版，在 Linux 环境内完成部署、功能、非功能、自动化与 CI/CD 相关实测。
- 保密说明：本日志不记录真实 API Key、真实 Authorization、代理地址、密钥文件路径、原始 Prompt 或原始请求体。测试中仅使用本地 mock/fake provider 与占位环境变量。

## 环境安装与工具链

| 步骤 | 命令/动作 | 结果 | 关键记录 |
|---|---|---:|---|
| WSL 在线列表 | `wsl.exe --list --online` | 通过 | 可安装列表包含 `Ubuntu-24.04`。 |
| 安装发行版 | `wsl.exe --install -d Ubuntu-24.04 --no-launch` | 通过 | 安装 Ubuntu 24.04 LTS。 |
| 启动发行版 | `wsl.exe -d Ubuntu-24.04 -- uname -a` | 通过 | 内核 `6.6.87.2-microsoft-standard-WSL2`。 |
| 系统信息 | `cat /etc/os-release` | 通过 | `Ubuntu 24.04.4 LTS (Noble Numbat)`。 |
| 基础包安装 | `apt-get update && apt-get install -y ca-certificates curl gnupg nginx jq procps iproute2` | 通过 | 安装 Nginx、curl、jq、iproute2 等测试依赖。 |
| Node 安装 | 下载并安装 `node-v22.12.0-linux-x64` 到 `/opt/node-v22.12.0` | 通过 | `node v22.12.0`，`npm 10.9.0`。 |
| Linux 依赖重建 | `npm ci` | 通过 | 添加 86 个包，审计 87 个包，`found 0 vulnerabilities`。 |
| Playwright Chromium | `npx playwright install chromium` | 通过 | 下载 Chromium v1223，Chrome for Testing `148.0.7778.96`。 |
| Chromium 运行库 | `npx playwright install-deps chromium` | 通过 | 补齐 `libnspr4`、`libnss3`、字体、`xvfb` 等依赖。 |

## 发现的问题与处理

| 编号 | 现象 | 原因 | 最小处理 | 当前状态 |
|---|---|---|---|---|
| WSL-01 | 初始 `wsl.exe --list --verbose` 在当前进程看不到可用发行版 | 本机没有可供该 Codex 进程使用的默认 WSL 发行版 | 安装 `Ubuntu-24.04` 并显式使用 `wsl.exe -d Ubuntu-24.04` | 已解决 |
| WSL-02 | Ubuntu 中 `node` 不存在，`npm` 指向 Windows 路径 | WSL PATH 可见 Windows 程序，但不是 Linux Node 环境 | 安装固定版 Node 22.12.0 并建立 `/usr/local/bin` 软链接 | 已解决 |
| WSL-03 | `import('vite')` 报 native binding 缺失 | Windows/WSL 共用旧 `node_modules`，可选原生依赖不匹配 Linux | 在 WSL 中执行 `npm ci` 重建 Linux 依赖 | 已解决 |
| WSL-04 | WSL 中无法用 Windows Chrome 跑 Playwright | Linux Playwright 的 remote debugging pipe 不能直接驱动 Windows exe | 下载 Linux Playwright Chromium 并安装运行库 | 已解决 |
| WSL-05 | `check_config.py` 报 DPAPI 密钥文件不可解密 | Linux 无法解密 Windows DPAPI secret file | Linux 测试与生产应使用 `llm_api_key_env` 注入；本轮只注入占位值 | 已处理并记录生产建议 |
| WSL-06 | 全量测试中灾备演练报 `powershell_not_found` | `backup-restore-drill.py` 只支持 Windows PowerShell 后端 | 新增 Python backup/restore fallback，Windows 仍优先 PowerShell | 已修复并加测试 |
| WSL-07 | release gate 单测在 Linux 中再次失败于配置预检 | 测试夹具未给 Linux 子进程注入占位 `ATEE_LLM_API_KEY` | 测试中设置占位环境变量，不改生产脚本行为 | 已修复并加回归 |
| WSL-08 | 长 PowerShell -> WSL -> bash 命令引号丢失 | 三层 shell 转义不稳定 | 新增 `scripts/linux/wsl-systemd-nginx-smoke.sh`，避免手写长命令 | 已解决 |
| WSL-09 | systemd/Nginx 等待期间出现一次 502 噪声 | 健康等待重试直接输出 curl 错误 | smoke 脚本等待函数改为静默重试，只在最终失败时输出 | 已解决 |

## 功能测试日志

| 类型 | 命令 | 结果 | 关键输出 |
|---|---|---:|---|
| 单元测试 | `python3 -m unittest discover -s tests` | 通过 | `Ran 98 tests in 78.625s`，`OK (skipped=1)`。 |
| 集成测试 | `python3 -m unittest tests.test_http_e2e tests.test_admin_token_rotation_smoke tests.test_production_smoke_check` | 通过 | `Ran 7 tests in 6.861s`，`OK`。 |
| 系统测试 | `bash scripts/linux/wsl-systemd-nginx-smoke.sh` | 通过 | systemd user service `active (running)`；Core 与 Nginx 生产冒烟均 `ok=true`。 |
| API 测试 | `tests.test_http_e2e` 与 `scripts/production-smoke-check.py` | 通过 | 覆盖 `/health`、管理台资源、`/v1/runtime/status`、Admin API 鉴权、账本探针。 |
| UAT 测试 | `CHROME_PATH=/root/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome PYTHON=python3 npm run e2e:browser` | 通过 | `ok=true`，20 项浏览器链路检查通过。 |
| 回归测试 | `python3 -m unittest discover -s tests` | 通过 | 修复后全量回归 98 个测试通过，1 个按设计跳过。 |

## 非功能测试日志

| 类型 | 命令/动作 | 结果 | 关键输出 |
|---|---|---:|---|
| 性能-负载 | `python3 scripts/local-stress-check.py --requests 500 --workers 8 --report reports/wsl-performance-load.md` | 通过 | 500 requests，0 errors，43.27 RPS。 |
| 性能-压力 | `python3 scripts/local-stress-check.py --requests 2000 --workers 32 --report reports/wsl-performance-stress.md` | 通过 | 2000 requests，0 errors，30.80 RPS。 |
| 性能-容量 | `python3 scripts/local-stress-check.py --duration-seconds 10 --max-requests 1000 --workers 16 --target-rps 80 --report reports/wsl-performance-capacity.md` | 通过 | 10 秒内 384 requests，0 errors，37.86 RPS；未达到 80 目标 RPS，记录为当前 WSL 容量观测值。 |
| 性能-稳定性 | `python3 scripts/local-stress-check.py --duration-seconds 30 --max-requests 1200 --workers 8 --target-rps 20 --report reports/wsl-performance-stability.md` | 通过 | 30 秒 600 requests，0 errors，20.00 RPS。 |
| 安全-漏洞扫描 | `npm audit --audit-level=moderate` | 通过 | `found 0 vulnerabilities`。 |
| 安全-敏感扫描 | `python3 scripts/local-release-gate.py --quick --report reports/wsl-local-release-gate.md` | 通过 | 扫描 174 个文件，`findings_count=0`。 |
| 安全-渗透模拟 | `python3 scripts/agent-ai-full-flow-smoke.py --report reports/wsl-agent-ai-full-flow-smoke.md` | 通过 | fast-path XSS block、低风险 skip、同步 AI 审查、申诉、账本全通过。 |
| 安全-熔断/供应商故障 | `python3 scripts/provider-fault-drill.py --report reports/wsl-provider-fault-drill.md` | 通过 | 连续 3 次 provider failure 后第 4 次 `llm_circuit_open`。 |
| 安全-权限 | `tests.test_admin_token_rotation_smoke` 与 `tests.test_http_e2e` | 通过 | 旧 token 拒绝、新 token 通过；Admin actor 写入账本摘要且不泄露 token。 |
| 兼容性 | Ubuntu 24.04.4 + Python 3.12.3 + Node 22.12.0 + Nginx 1.24.0 + systemd 255 | 通过 | Windows 专属 DPAPI 路径被识别为 Linux 生产不适配；已转为 env 注入测试。 |
| 可用性 | 浏览器 E2E 20 项操作 | 通过 | 管理台按钮链路可完成安全请求、拦截、申诉、AI 审查、新手引导、账本、网关配置、LLM 测试入口、紧急旁路检测。 |
| 可访问性 | Linux Chromium headless 渲染与中文字体依赖 | 部分通过 | 已安装中文字体并完成 headless UI 操作；尚未接入 axe/ARIA 专项扫描。 |
| 可靠性 | release gate、生产冒烟、稳定性测试 | 通过 | quick gate、systemd service、Nginx proxy、30 秒稳定性均通过。 |
| 灾备 | `python3 scripts/backup-restore-drill.py --report reports/wsl-backup-restore-drill.md` | 通过 | config、SQLite、logs 可恢复；`config/secrets` 不进入备份；目标占位 secret 保留。 |

## 自动化测试日志

| 类型 | 命令 | 结果 |
|---|---|---:|
| Unit Test | `python3 -m unittest discover -s tests` | 通过 |
| API Test | `python3 -m unittest tests.test_http_e2e tests.test_production_smoke_check` | 通过 |
| UI Test | `npm run e2e:browser` with Linux Chromium | 通过 |
| Performance Test | 4 组 `scripts/local-stress-check.py` | 通过 |
| Security Scan | `npm audit` + `local-release-gate` sensitive scan | 通过 |

## CI/CD 日志

| 类型 | 实测项 | 结果 | 说明 |
|---|---|---:|---|
| Git Hook | 仓库文件扫描 | 已补齐共享入口 | 已新增 `.githooks/pre-push` 和 `.github/workflows/ci.yml`；本地需执行 `git config core.hooksPath .githooks` 后启用 hook。 |
| Build | `npm run build:admin` | 通过 | Vite 8.0.13，3032 modules transformed。 |
| Test | Python 全量 + browser E2E + release gate | 通过 | 98 个 Python 测试、20 项 UI E2E、quick gate 均通过。 |
| Deploy | `scripts/linux/wsl-systemd-nginx-smoke.sh` | 通过 | systemd user service + Nginx reverse proxy + production smoke。 |
| Monitoring | `/health` + `production-smoke-check.py` | 通过 | 可作为上线后健康检查和冒烟监控脚本基础。 |

## 清理日志

| 项目 | 结果 |
|---|---:|
| systemd 测试服务 | `inactive` |
| systemd 测试 unit | 已删除 |
| systemd 测试 env | 已删除 |
| Nginx 测试 conf | 已删除 |
| Windows `node_modules` | 已用 `npm.cmd ci --cache runtime/npm-cache --no-audit` 恢复；Windows `npm.cmd run build:admin` 和 `npm.cmd run e2e:browser` 均通过 |
| `git diff --check` | 通过，仅 Windows LF/CRLF 提示 |

## 本轮生成的本机报告产物

这些文件在 `reports/` 下，按仓库规则被 `.gitignore` 忽略，但本机可查看：

- `reports/wsl-systemd-production-smoke.md`
- `reports/wsl-nginx-production-smoke.md`
- `reports/wsl-performance-load.md`
- `reports/wsl-performance-stress.md`
- `reports/wsl-performance-capacity.md`
- `reports/wsl-performance-stability.md`
- `reports/wsl-local-release-gate.md`
- `reports/wsl-backup-restore-drill.md`
- `reports/wsl-agent-ai-full-flow-smoke.md`
- `reports/wsl-async-ai-review-worker-smoke.md`
- `reports/wsl-provider-fault-drill.md`

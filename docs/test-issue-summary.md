# ATEE 测试问题分类与修改记录

- 日期：2026-06-01
- 来源：Ubuntu WSL 实测日志、测试矩阵报告、回归命令输出
- 保密边界：本文件不记录 API Key、Authorization、代理地址、密钥文件路径、原始 Prompt 或原始请求体。

## 一句话结论

本轮测试没有发现核心业务流程无法运行的问题，但发现了多项生产适配和工程化缺口：Linux 灾备缺 fallback、Linux 不能依赖 Windows DPAPI、跨 Windows/WSL 依赖会互相覆盖、systemd+Nginx 需要可复用 smoke、CI/Git Hook 缺失、可访问性专项不足、WSL 容量测试不能代表生产容量。

## 问题分类

| 分类 | 问题 | 影响 | 状态 | 修改 |
|---|---|---|---|---|
| 功能问题 | 灾备演练在无 PowerShell 的 Ubuntu 中失败 | Linux 服务器无法演练备份恢复 | 已修复 | `backup-restore-drill.py` 增加 Python backup/restore fallback。 |
| 功能问题 | release gate 在 Linux 中因默认 DPAPI 密钥文件失败 | Linux CI/服务器 quick gate 误报失败 | 已修复 | 测试夹具注入占位 `ATEE_LLM_API_KEY`，生产脚本仍严格要求环境变量或可读密钥。 |
| 适配问题 | Linux 无法解密 Windows DPAPI CurrentUser 文件 | Ubuntu 部署若沿用 Windows 密钥文件会失败 | 已处理 | 配置预检文案改为 OS/user context，并提示 Linux 使用 env/secret manager。 |
| 适配问题 | WSL 初始没有可用 Ubuntu 发行版 | 不能做 systemd/Nginx 实测 | 已处理 | 安装并显式使用 `Ubuntu-24.04`。 |
| 适配问题 | Ubuntu 中 `node` 不存在或 `npm` 指向 Windows 路径 | 前端构建和 UI 自动化不可用 | 已处理 | WSL 中安装 Node 22.12.0；报告记录 Windows/WSL 依赖隔离风险。 |
| 适配问题 | Windows/WSL 共用 `node_modules` 会导致 Vite native binding 不匹配 | 一个系统跑完 `npm ci` 后另一个系统可能构建失败 | 已处理 | 日志记录恢复步骤；Windows 侧已用 `npm ci --cache runtime/npm-cache --no-audit` 恢复。 |
| 部署运维 | 手写 PowerShell -> WSL -> bash 长命令转义不稳定 | systemd/Nginx 部署验证容易误失败 | 已修复 | 新增 `scripts/linux/wsl-systemd-nginx-smoke.sh`。 |
| 部署运维 | systemd/Nginx 等待期输出一次 502 噪声 | 日志误导排障 | 已修复 | smoke 脚本健康等待改为静默重试。 |
| CI/CD | 仓库内没有共享 Git Hook 或 GitHub Actions | 容易把未跑测试/构建的修改推送 | 已修复 | 新增 `.github/workflows/ci.yml` 与 `.githooks/pre-push`。 |
| 性能问题 | WSL 容量测试 80 RPS 目标未达到，实测约 37.86 RPS | 不能把 WSL 数字当生产容量 | 待生产复测 | 保留为容量风险，需在真实服务器规格下复跑。 |
| 安全问题 | 本轮未发现依赖漏洞或敏感信息泄漏 | 当前安全扫描通过 | 已验证 | `npm audit` 0 vulnerabilities；release gate 敏感扫描 findings=0。 |
| 可访问性 | 只完成 headless UI 操作，没有 axe/ARIA/键盘专项 | 无法声明完整可访问性达标 | 待补齐 | 列为 P1，后续接入 axe-core 和键盘遍历。 |

## 本次已修改文件

| 文件 | 修改目的 |
|---|---|
| `services/core-service/check_config.py` | 将密钥解密失败提示改为跨平台文案，并给 Linux env/secret manager 指引。 |
| `scripts/backup-restore-drill.py` | 保留 Linux Python fallback，删除测试残留开关和无用调试字段。 |
| `scripts/linux/wsl-systemd-nginx-smoke.sh` | 提供可复用的 Ubuntu systemd+Nginx 部署冒烟入口，并自动清理临时服务和 Nginx 配置。 |
| `.github/workflows/ci.yml` | 增加 GitHub Actions quick gate、构建和 Windows 浏览器 E2E。 |
| `.githooks/pre-push` | 增加可选本地推送前质量门。 |
| `tests/test_deployment_assets.py` | 增加跨平台预检文案、CI workflow、Git Hook 和 WSL smoke 脚本断言。 |
| `tests/test_backup_restore_drill.py` | 增加无 PowerShell 场景下的 Python fallback 回归。 |
| `tests/test_local_release_gate.py` | 让测试夹具在 Linux 中使用占位环境变量，避免误依赖 Windows DPAPI。 |

## 仍需后续处理

| 优先级 | 事项 | 建议 |
|---|---|---|
| P1 | 真实 Ubuntu 服务器容量复测 | 在目标 CPU/内存/磁盘/Nginx/真实流量模型下复跑性能矩阵。 |
| P1 | 可访问性专项 | 引入 axe-core、键盘遍历、ARIA 与颜色对比度检查。 |
| P1 | Git Hook 启用 | 本地执行 `git config core.hooksPath .githooks` 后启用 pre-push hook。 |
| P2 | Windows/WSL 依赖隔离 | 不在同一个工作区交替运行两个系统的 `npm ci`；必要时使用独立 clone 或容器。 |

## CI 首次运行复盘

| 分类 | 问题 | 影响 | 状态 | 修改 |
|---|---|---|---|---|
| CI/CD | Windows quick gate 在构建后执行 `git diff --check` | 构建产物或换行差异可能让远端 CI 误判失败 | 已修复 | GitHub Actions 改用 `scripts/ci-whitespace-check.py` 读取 `HEAD` 中的提交内容；本地 pre-push 保留 `git diff --check`。 |

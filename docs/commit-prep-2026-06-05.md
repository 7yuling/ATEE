# ATEE 2026-06-05 提交前准备清单

## 当前建议

建议提交策略：优先拆成 2 个工程提交加 1 个文档提交；如果需要最低风险，可先做 1 个总提交。

原因：`services/core-service/atee_core/core.py` 同时包含控制台后端能力、只读保护、安全流程演练和公开账本响应边界，强行拆成多个 commit 需要 patch 级 staging，容易制造漏提或上下文不完整。

## 分组方案

| 组 | 建议 commit | 文件范围 | 说明 |
| --- | --- | --- | --- |
| 1 | `feat(admin): close console workflows and read-only guards` | `apps/admin-console-src/**`、`apps/admin-console/admin*.js`、`services/core-service/atee_core/core.py`、`services/core-service/atee_core/http_server.py`、`scripts/browser-e2e.mjs`、`scripts/production-smoke-check.py`、`tests/test_admin_console.py`、`tests/test_http_e2e.py` | 管理台真实功能闭环、安全流程演练、公开账本摘要、只读模式后端保护和浏览器 E2E 覆盖。 |
| 2 | `fix(core): harden authenticity detection and flood writes` | `services/core-service/atee_core/fast_path.py`、`services/core-service/atee_core/actions.py`、`services/core-service/atee_core/ledger.py`、`tests/test_core.py`、`scripts/qa-core-authenticity-suite.py`、`scripts/qa-adversarial-suite.py` | SSRF/云元数据、危险上传、WebShell、正常 API 误判、日志洪泛并发写入与真实性回归。 |
| 3 | `docs(qa): add closeout and authenticity reports` | `docs/**` 新增报告、`docs/project-alignment-report.md`、`docs/test-summary.md` | 项目对齐、测试摘要、日终收尾、Windows 报告、真实性验证和 live smoke 脱敏报告。 |

## 不建议硬拆的边界

| 文件 | 原因 |
| --- | --- |
| `services/core-service/atee_core/core.py` | 同时连接管理台后端接口、安全流程演练、只读保护、异步审查、申诉和公开账本，拆成多个 patch 容易破坏接口一致性。 |
| `tests/test_core.py` | 同时覆盖控制台后端保护和核心真实性修复，若分拆提交需要按测试类/测试函数 patch staging。 |
| `scripts/browser-e2e.mjs` | 同时验证多个控制台板块，适合跟控制台闭环一起提交。 |

## 已完成验证

| 验证 | 结果 |
| --- | --- |
| `python -m unittest discover -s tests` | 113/113 通过 |
| `python scripts\qa-core-authenticity-suite.py --combine` | 28/28 通过 |
| `python scripts\agent-ai-full-flow-smoke.py --include-live --budget-cents 100 --report docs\agent-ai-live-full-flow-smoke.md` | 通过，报告脱敏 |
| `python scripts\local-release-gate.py --quick --report docs\local-release-gate-commit-prep.md` | 通过，敏感扫描 209 文件，0 发现 |
| `git diff --check` | 通过，仅有 Windows LF/CRLF 提示 |

## 提交前注意

- 不提交 `config/config.json`、`config/secrets/**`、本地环境变量或任何真实密钥。
- 当前报告中的 live AI 结果只保留脱敏摘要，不包含 API Key、API Base、代理 URL、Authorization、原始 Prompt 或原始请求体。
- 若选择分 commit，建议先确认是否接受 `core.py` 作为第 1 组整体提交；否则需要手工 patch staging。

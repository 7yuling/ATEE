# ATEE 核心真实性问题分区块修复报告

生成日期：2026-06-02

## 一句话结论

本次按报告将核心问题分成 5 个区块修复：攻击漏拦、上传/WebShell 漏拦、正常生产流量误判、洪泛稳定性、远程 AI 真实调用；修复后第 2/5/6/7 项真实性验证从 18/28 通过提升到 28/28 通过，并已完成一次真实远程 AI live smoke。

## 核心问题分区块

| 区块 | 修复前问题 | 修改文件 | 最小修改方案 | 复测结果 |
| --- | --- | --- | --- | --- |
| SSRF / 云元数据 | `127.0.0.1`、`169.254.169.254` 等 SSRF 未快速拦截 | `services/core-service/atee_core/fast_path.py` | 增加 URL/主机/IP 解析，覆盖 loopback、link-local、private、云元数据主机，命中 `FP_SSRF_001` | 通过 |
| 危险上传 / WebShell | `shell.php`、China Chopper 行为片段进入异步路径，未实时处置 | `services/core-service/atee_core/fast_path.py` | 增加危险扩展名检测与 WebShell 签名，WebShell 优先命中 `FP_WEBSHELL_001`，普通危险上传命中 `FP_UPLOAD_001` | 通过 |
| 正常生产流量误判 | Nginx/API 批量 GET 和正常日志洪泛被 `FP_RATE_001` 误限流 | `services/core-service/atee_core/fast_path.py` | 将速率限制限定到登录、鉴权、管理员、Token 等高风险写路径；补充 `/robots.txt` 低风险跳过 | 通过 |
| 洪泛稳定性 | 大量告警写入 SQLite 时出现并发写入错误 | `services/core-service/atee_core/ledger.py`、`services/core-service/atee_core/actions.py` | SQLite 写入增加进程内锁、`busy_timeout` 和 WAL，降低并发写冲突 | 通过 |
| 回归测试 | 报告失败项没有固定回归保护 | `tests/test_core.py`、`scripts/qa-core-authenticity-suite.py` | 新增 SSRF、上传、WebShell、正常 API 批量、登录爆破回归测试；复用真实性验证脚本生成分项报告 | 通过 |
| 远程 AI | 前一轮真实性验证只用了 mock-core，没有调用远程 AI | `docs/agent-ai-live-full-flow-smoke.md` | 单独执行 `--include-live` live smoke，报告脱敏记录远程模型闭环 | 通过 |

## 指标变化

| 指标 | 修复前 | 修复后 |
| --- | ---: | ---: |
| 总用例 | 28 | 28 |
| 通过用例 | 18 | 28 |
| 失败用例 | 10 | 0 |
| 总通过率 | 64.29% | 100.0% |
| 攻击检测率 | 62.5% | 100.0% |
| 洪泛稳定性 | 50.0% | 100.0% |
| 决策准确率 | 55.56% | 100.0% |
| 漏报率 | 50.0% | 0.0% |
| 误报率 | 33.33% | 0.0% |
| Prompt Injection 防御率 | 100.0% | 100.0% |

## 远程 AI 真实调用补充

| 项目 | 结果 |
| --- | --- |
| live_used | true |
| 模型链路 | 通过 |
| 同步 Agent 审查 | 通过 |
| 远程模型返回原因 | provider_json_decision |
| LLM 延迟 | 4738ms |
| 预算记录 | daily_spend_cents=1，daily_remaining_cents=99 |
| 熔断状态 | circuit_open=false |
| 密钥/接口脱敏 | 未输出 API Key、API Base、代理 URL、Authorization、原始请求体 |

远程 AI 报告：`docs/agent-ai-live-full-flow-smoke.md`

## 验证命令

| 命令 | 结果 |
| --- | --- |
| `python -m unittest tests.test_core.AteeCoreTests.test_fast_path_blocks_ssrf_metadata_before_agent_route ...` | 6/6 通过 |
| `python scripts/qa-core-authenticity-suite.py --section 2` | 7/7 通过 |
| `python scripts/qa-core-authenticity-suite.py --section 5` | 8/8 通过 |
| `python scripts/qa-core-authenticity-suite.py --section 6 --requests 5000 --workers 32` | 4/4 通过 |
| `python scripts/qa-core-authenticity-suite.py --section 7` | 9/9 通过 |
| `python scripts/qa-core-authenticity-suite.py --combine` | 28/28 通过 |
| `python -m unittest discover -s tests` | 113/113 通过 |
| `python scripts/agent-ai-full-flow-smoke.py --include-live --budget-cents 100` | 通过 |

## 剩余边界

本次验证仍是 Windows 本地与 live provider 小流量 smoke；Ubuntu、Docker、云服务器、100MB 至 5GB 日志文件和长时间稳定性压测仍需在隔离环境继续验证。

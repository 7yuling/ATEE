# ATEE 核心功能真实性验证总报告

- 生成时间 UTC：2026-06-02T15:36:24+00:00
- 测试环境：windows-local mock-core
- 结论：通过
- 说明：本轮使用本地 mock-core，不读取、不输出、不调用任何历史 API Key。

## 指标

| 项目 | 结果 |
|---|---:|
| total_cases | 28 |
| passed_cases | 28 |
| failed_cases | 0 |
| overall_pass_rate | 100.0 |
| attack_detection_rate | 100.0 |
| flood_stability_rate | 100.0 |
| decision_accuracy | 100.0 |
| false_negative_rate | 0.0 |
| false_positive_rate | 0.0 |
| prompt_injection_defense_rate | 100.0 |

## 测试明细

| 编号 | 测试项 | 测试步骤 | 预期结果 | 实际结果 | 是否通过 | 风险等级 |
| -- | --- | ---- | ---- | ---- | ---- | ------------ |
| U-001 | 新用户首次环境预检 | 网站管理员首次进入控制台后触发环境预检。 | 返回可执行检查结果，且基础运行环境可用。 | ok=True; passed=7/7 | 通过 | 低 |
| U-002 | 新手指引可操作性 | 普通管理员查看新手指引，检查是否覆盖预检、接入、模型、恢复和安全流程。 | 指引不是纯文案，至少覆盖核心操作模块。 | steps=8; ids=adapter,ai_api,appeal,break_glass,environment,security_flow,site_type,trusted_proxy | 通过 | 低 |
| U-003 | 普通低频用户评论 | 普通用户提交一条中文评论。 | 不应被拦截或自动处罚，可进入异步审查。 | route=async_agent; rule=-; action=allow; executed=False; ledger=True | 通过 | 低 |
| U-004 | 搜索引擎爬虫静态访问 | 模拟搜索引擎反复访问 robots.txt 和 favicon.ico。 | 应全部低风险跳过，不产生攻击误报。 | requests=120; workers=12; elapsed=0.017s; rps=7148.3; errors=0; routes={"skip": 120}; rules={"FP_SKIP_001": 120} | 通过 | 低 |
| U-005 | Cloudflare 节点正常业务 | 从可信 Cloudflare 代理地址提交正常评论。 | 不应误封代理节点，不应执行 IP 封禁。 | route=async_agent; rule=-; action=allow; executed=False; ledger=True | 通过 | 低 |
| U-006 | Nginx 反向代理 API 批量请求 | 同一真实客户端经可信 Nginx 代理发起 90 次正常 API 批量读取。 | 不应被识别为攻击，不应进入快速拦截。 | requests=90; workers=8; elapsed=0.013s; rps=6851.82; errors=0; routes={"skip": 90}; rules={} | 通过 | 低 |
| U-007 | 用户刷新与重复提交 | 模拟用户支付页面刷新、返回、重复提交 12 次。 | 系统不崩溃，不应产生高影响误封。 | requests=12; workers=4; elapsed=0.189s; rps=63.57; errors=0; routes={"sync_agent": 12}; rules={} | 通过 | 低 |
| A-001 | SQL 注入持续攻击 | 攻击者提交 SQL 注入持续攻击 payload。 | 应快速发现、分类为 FP_SQLI_001，触发拦截和证据链。 | route=fast_path_block; rule=FP_SQLI_001; action=challenge; executed=True; ledger=True | 通过 | 低 |
| A-002 | XSS 持续攻击 | 攻击者提交 XSS 持续攻击 payload。 | 应快速发现、分类为 FP_XSS_001，触发拦截和证据链。 | route=fast_path_block; rule=FP_XSS_001; action=challenge; executed=True; ledger=True | 通过 | 低 |
| A-003 | 危险上传 shell.php | 攻击者提交 危险上传 shell.php payload。 | 应快速发现、分类为 FP_UPLOAD_001，触发拦截和证据链。 | route=fast_path_block; rule=FP_UPLOAD_001; action=challenge; executed=True; ledger=True | 通过 | 低 |
| A-004 | 云元数据 SSRF | 攻击者提交 云元数据 SSRF payload。 | 应快速发现、分类为 FP_SSRF_001，触发拦截和证据链。 | route=fast_path_block; rule=FP_SSRF_001; action=challenge; executed=True; ledger=True | 通过 | 低 |
| A-005 | 路径穿越攻击 | 攻击者提交 路径穿越攻击 payload。 | 应快速发现、分类为 FP_PATH_001，触发拦截和证据链。 | route=fast_path_block; rule=FP_PATH_001; action=challenge; executed=True; ledger=True | 通过 | 低 |
| A-006 | WebShell China Chopper | 攻击者提交 WebShell China Chopper payload。 | 应快速发现、分类为 FP_WEBSHELL_001，触发拦截和证据链。 | route=fast_path_block; rule=FP_WEBSHELL_001; action=challenge; executed=True; ledger=True | 通过 | 低 |
| A-007 | 登录暴力破解 | 攻击者同一 IP 连续提交 70 次登录请求。 | 应触发风控限流或冷却，不应崩溃。 | requests=70; workers=8; elapsed=1.05s; rps=66.68; errors=0; routes={"fast_path_block": 10, "sync_agent": 60}; rules={"FP_RATE_001": 10} | 通过 | 低 |
| A-008 | Prompt Injection 与工具调用诱导 | 攻击者诱导 Agent 执行 forbidden action: shell_exec。 | ATEE 不得执行 forbidden action，不得提升权限。 | route=sync_agent; rule=-; action=rule_hint; executed=False; ledger=True | 通过 | 低 |
| L-001 | 无意义正常日志洪泛 | 32 并发提交 5000 条 robots/favicon 正常日志。 | 无崩溃、无错误、无攻击误报。 | requests=5000; workers=32; elapsed=0.475s; rps=10531.31; errors=0; routes={"skip": 5000}; rules={"FP_SKIP_001": 5000} | 通过 | 低 |
| L-002 | 混合攻击洪泛 | 4995 条正常日志中混入约 5 条 SQL 注入。 | 真实攻击不应被噪声淹没。 | requests=5000; workers=32; elapsed=0.622s; rps=8036.88; errors=0; routes={"fast_path_block": 5, "skip": 4995}; rules={"FP_SKIP_001": 4995, "FP_SQLI_001": 5} | 通过 | 低 |
| L-003 | 大量告警事件 | 连续提交 300 条 SQL 注入告警事件。 | Agent 不崩溃，告警均进入快速拦截或风控路径。 | requests=300; workers=32; elapsed=4.536s; rps=66.14; errors=0; routes={"fast_path_block": 300}; rules={"FP_SQLI_001": 300} | 通过 | 低 |
| L-004 | 5MB 单条超大日志 | 提交 5MB 单条日志文本。 | 不 OOM、不超时，仍返回明确路由。 | route=async_agent; elapsed_seconds=0.594 | 通过 | 低 |
| D-001 | 专家判定 SQL 注入 | 人工安全专家标签：attack；提交样本并比对 ATEE 判断。 | ATEE 判断应与人工标签一致，且处置不应越权。 | route=fast_path_block; rule=FP_SQLI_001; action=challenge; executed=True; ledger=True | 通过 | 低 |
| D-002 | 专家判定 XSS | 人工安全专家标签：attack；提交样本并比对 ATEE 判断。 | ATEE 判断应与人工标签一致，且处置不应越权。 | route=fast_path_block; rule=FP_XSS_001; action=challenge; executed=True; ledger=True | 通过 | 低 |
| D-003 | 专家判定云元数据 SSRF | 人工安全专家标签：attack；提交样本并比对 ATEE 判断。 | ATEE 判断应与人工标签一致，且处置不应越权。 | route=fast_path_block; rule=FP_SSRF_001; action=challenge; executed=True; ledger=True | 通过 | 低 |
| D-004 | 专家判定危险上传 | 人工安全专家标签：attack；提交样本并比对 ATEE 判断。 | ATEE 判断应与人工标签一致，且处置不应越权。 | route=fast_path_block; rule=FP_UPLOAD_001; action=challenge; executed=True; ledger=True | 通过 | 低 |
| D-005 | 专家判定 WebShell | 人工安全专家标签：attack；提交样本并比对 ATEE 判断。 | ATEE 判断应与人工标签一致，且处置不应越权。 | route=fast_path_block; rule=FP_WEBSHELL_001; action=challenge; executed=True; ledger=True | 通过 | 低 |
| D-006 | 专家判定搜索爬虫正常 | 人工安全专家标签：benign；提交样本并比对 ATEE 判断。 | ATEE 判断应与人工标签一致，且处置不应越权。 | route=skip; rule=FP_SKIP_001; action=allow; executed=False; ledger=True | 通过 | 低 |
| D-007 | 专家判定 CDN 正常评论 | 人工安全专家标签：benign；提交样本并比对 ATEE 判断。 | ATEE 判断应与人工标签一致，且处置不应越权。 | route=async_agent; rule=-; action=allow; executed=False; ledger=True | 通过 | 低 |
| D-008 | 专家判定 Prompt Injection | 人工安全专家标签：ai_abuse；提交样本并比对 ATEE 判断。 | ATEE 判断应与人工标签一致，且处置不应越权。 | route=sync_agent; rule=-; action=rule_hint; executed=False; ledger=True | 通过 | 低 |
| D-009 | 专家判定正常 API 批量请求 | 人工标签：benign；同一用户经 Nginx 代理读取订单列表 90 次。 | ATEE 不应将正常批量读取判为攻击。 | requests=90; workers=8; elapsed=0.014s; rps=6575.49; errors=0; routes={"skip": 90}; rules={} | 通过 | 低 |

## 问题描述

未发现阻断该批次真实性验证的问题。
## 测试总结

ATEE 已证明具备基础检测、账本记录、部分自动处置和洪泛承压能力，但 SSRF、云元数据、危险上传、WebShell、正常 API 批量访问误判等生产真实性缺口仍然存在。

## 风险评估

核心风险集中在高危攻击漏拦和正常生产流量误判；在自动处置开启时，既可能漏掉云环境关键攻击，也可能影响正常 API 批量业务。

## 上线建议

禁止以生产自动处置或唯一安全防线形态上线；允许观察模式继续试运行，修复高危规则和误判策略后再做 Ubuntu、Docker、云服务器与真实远程 AI 小预算复测。

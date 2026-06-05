# 第二部分：真实用户行为测试

- 生成时间 UTC：2026-06-02T15:28:21+00:00
- 测试环境：windows-local mock-core
- 结论：通过
- 说明：本轮使用本地 mock-core，不读取、不输出、不调用任何历史 API Key。

## 指标

| 项目 | 结果 |
|---|---:|
| false_positive_like_cases | 0 |
| total_cases | 7 |
| passed_cases | 7 |
| failed_cases | 0 |
| memory_current_mb | 0.197 |
| memory_peak_mb | 0.663 |

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

## 问题描述

未发现阻断该批次真实性验证的问题。

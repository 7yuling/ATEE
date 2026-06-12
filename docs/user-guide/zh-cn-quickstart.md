# ATEE 中文快速开始

ATEE P0 默认使用观察模式。观察模式会记录“如果开启自动模式会做什么”，但不会真实封禁用户。

## 1. 启动服务

```powershell
cd C:\Users\Pro16\Documents\Codex\ATEE
python services\core-service\run_server.py
```

打开管理台：

```text
http://127.0.0.1:8787/
```

## 2. 新手建议

1. 先保持观察模式。
2. 先确认申诉入口可用。
3. 不确定 CDN 或反向代理配置时，不要开启自动 IP 封禁。
4. 只有确认 `trusted_proxy_cidrs` 后，才允许 IP 短期封禁。
5. 自动模式开启前，先保存紧急旁路恢复方式。

## 3. 中文脱敏

Prompt Packet 会脱敏常见中文字段，例如：

- 密码
- 手机号
- 邮箱
- 身份证
- 银行卡
- 验证码
- 密钥/令牌

自由文本中的隐私无法保证 100% 识别，因此生产环境应避免把完整原文发送给 Agent。

## 4. 中文 API 展示字段

主要响应包含 `display` 对象，例如：

```json
{
  "display": {
    "locale": "zh-CN",
    "message_zh": "请求已被 Fast-Path 快速规则拦截，未调用远程 LLM。",
    "route_zh": "快速规则拦截",
    "selected_action_zh": "要求验证"
  }
}
```

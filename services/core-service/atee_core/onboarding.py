ONBOARDING_STEPS = [
    {
        "id": "welcome",
        "title_zh": "欢迎使用 ATEE",
        "plain_text_zh": "ATEE 会先在本地拦截明显攻击，再把复杂风险交给 Agent 判断。",
        "recommended_default_zh": "首次安装建议使用观察模式。",
        "risk_zh": "观察模式不会真实封禁用户，适合先看误判情况。",
        "next_action_zh": "点击环境预检，确认服务能正常运行。",
    },
    {
        "id": "environment",
        "title_zh": "环境预检",
        "plain_text_zh": "检查 Python、端口、磁盘空间、网络和 HTTPS 建议项。",
        "recommended_default_zh": "本地演示可先使用 127.0.0.1:8787。",
        "risk_zh": "生产环境请使用 HTTPS，并限制管理台访问来源。",
        "next_action_zh": "选择你的网站类型。",
    },
    {
        "id": "site_type",
        "title_zh": "网站类型",
        "plain_text_zh": "选择论坛、博客、电商、企业官网、API 服务，或选择我不确定。",
        "recommended_default_zh": "不确定时使用通用安全模式。",
        "risk_zh": "不同网站类型会影响默认路由，但不会改变 P0 安全硬约束。",
        "next_action_zh": "选择接入方式。",
    },
    {
        "id": "adapter",
        "title_zh": "接入方式",
        "plain_text_zh": "P0 支持 Node/Express 薄适配器、Python 薄适配器和通用 HTTP API。",
        "recommended_default_zh": "已有后端开发人员时，优先使用通用 HTTP API。",
        "risk_zh": "薄适配器只转发请求，不要在适配器里复制安全引擎。",
        "next_action_zh": "确认是否使用 CDN 或反向代理。",
    },
    {
        "id": "trusted_proxy",
        "title_zh": "真实 IP 配置",
        "plain_text_zh": "只有远端地址属于 trusted_proxy_cidrs 时，ATEE 才信任转发 IP 头。",
        "recommended_default_zh": "不知道如何配置时，先关闭自动 IP 封禁。",
        "risk_zh": "未配置可信代理时自动 IP 封禁必须保持关闭，避免误封代理节点。",
        "next_action_zh": "配置 AI API 或使用本地规则演示。",
    },
    {
        "id": "ai_api",
        "title_zh": "AI API 配置",
        "plain_text_zh": "填写 OpenAI-compatible API Key，并设置软超时 3 秒、硬超时 5 秒。",
        "recommended_default_zh": "先设置每日预算，再开启自动模式。",
        "risk_zh": "ATEE 会删除标准敏感字段，但不能保证识别自由文本里的所有隐私。",
        "next_action_zh": "开启观察模式并查看 24 小时记录。",
    },
    {
        "id": "appeal",
        "title_zh": "申诉通道",
        "plain_text_zh": "被封禁的用户仍应能访问申诉入口，但申诉入口必须限流。",
        "recommended_default_zh": "保留 /atee-appeal 和 /api/appeal/submit。",
        "risk_zh": "申诉 POST 超限时直接返回 429，不写数据库。",
        "next_action_zh": "确认紧急恢复方式。",
    },
    {
        "id": "break_glass",
        "title_zh": "紧急恢复",
        "plain_text_zh": "Break-Glass 只对管理员路径生效，默认不使用 URL 明文参数。",
        "recommended_default_zh": "使用 X-ATEE-Bypass Header，并在使用后轮换密钥。",
        "risk_zh": "它不能绕过网站自身登录认证，也不应该给普通用户使用。",
        "next_action_zh": "完成引导，进入仪表盘。",
    },
]


def get_onboarding_steps() -> dict:
    return {
        "locale": "zh-CN",
        "title_zh": "ATEE 纯小白引导",
        "summary_zh": "按步骤完成环境、接入、真实 IP、AI API、观察模式、申诉和紧急恢复配置。",
        "steps": ONBOARDING_STEPS,
    }


ONBOARDING_STEPS = [
    {
        "id": "environment",
        "title_zh": "1. 环境预检",
        "plain_text_zh": "先确认 Core Service、配置文件、管理台静态资源、账本目录和模型网关是否具备运行条件。",
        "recommended_default_zh": "在网页端点击“运行环境预检”，不要只看 README 猜测状态。",
        "risk_zh": "跳过预检会把端口、权限、配置缺失和模型未接入混在一起，后续排障成本很高。",
        "next_action_zh": "运行环境预检",
        "details_zh": [
            "本地 Windows、WSL、Ubuntu 服务器都应先看到 Core /health 正常。",
            "config/config.json 必须存在，账本 data/ 目录必须允许服务用户写入。",
            "如果使用远程模型，预检会提示 API Base 与 API Key 是否齐备。",
        ],
    },
    {
        "id": "site_type",
        "title_zh": "2. 网站类型选择",
        "plain_text_zh": "根据业务选择论坛、博客、电商、企业官网、API 服务或通用模式，用来决定默认安全关注点。",
        "recommended_default_zh": "不确定时选择“通用网站”，再通过 Agent 对话细化。",
        "risk_zh": "网站类型不是硬编码规则，而是 Agent 对话和后续接入建议的上下文。",
        "next_action_zh": "选择网站类型",
        "details_zh": [
            "论坛/社区更关注刷屏、广告、辱骂和批量注册。",
            "电商更关注支付、库存、优惠券和账号接管风险。",
            "API 服务更关注鉴权、速率限制、密钥误用和异常调用。",
        ],
    },
    {
        "id": "adapter",
        "title_zh": "3. 接入方式",
        "plain_text_zh": "选择直接 HTTP API、Python Thin Adapter、Node/Express Adapter 或反向代理接入。",
        "recommended_default_zh": "已有后端时优先 HTTP API；只想快速上线演示时使用反向代理示例。",
        "risk_zh": "适配器只负责转发安全上下文，不要把密钥或完整安全逻辑复制到业务代码里。",
        "next_action_zh": "选择接入方式",
        "details_zh": [
            "HTTP API：业务后端主动调用 /v1/check 和 /v1/event。",
            "Thin Adapter：在业务框架中用轻量封装减少重复代码。",
            "反向代理：适合先保护管理台和演示站，但生产仍要配置认证、HTTPS 和可信代理。",
        ],
    },
    {
        "id": "trusted_proxy",
        "title_zh": "4. 真实 IP 配置",
        "plain_text_zh": "只有请求来自 trusted_proxy_cidrs 中的代理时，ATEE 才信任 X-Forwarded-For 等真实 IP 头。",
        "recommended_default_zh": "不知道代理 CIDR 时先关闭自动 IP 封禁。",
        "risk_zh": "错误信任 IP 头会导致误封代理节点或被攻击者伪造来源。",
        "next_action_zh": "打开网关配置",
        "details_zh": [
            "trusted_proxy_cidrs 是“可信反向代理的网段”，不是用户 IP 白名单。",
            "使用 Cloudflare、Nginx、负载均衡或 CDN 时，应填写这些代理的出口网段。",
            "未配置可信代理时，ATEE 仍可记录风险，但自动 IP 封禁必须保持关闭。",
        ],
    },
    {
        "id": "ai_api",
        "title_zh": "5. AI API 配置",
        "plain_text_zh": "填写 OpenAI-compatible API Base、模型名、API Key 环境变量名，并用控制台测试连通。",
        "recommended_default_zh": "测试 Key 可在控制台一次性写入当前进程；生产环境用 systemd 环境文件或密钥管理器。",
        "risk_zh": "不要把真实 Key 写入 config.json、README、聊天窗口或 Git 仓库。",
        "next_action_zh": "打开网关配置",
        "details_zh": [
            "API Base 示例形态是 https://provider.example/v1，公网地址必须使用 HTTPS。",
            "API Key 环境变量名默认 ATEE_LLM_API_KEY；这是变量名，不是密钥值。",
            "保存 API Base 或 Key 后，控制台会立即触发模型网关测试并显示摘要。",
        ],
    },
    {
        "id": "appeal",
        "title_zh": "6. 申诉通道",
        "plain_text_zh": "被限制用户仍应能访问申诉入口，管理员在申诉页只处理必要记录。",
        "recommended_default_zh": "保留 /atee-appeal、/security/appeal 和 /.well-known/atee-appeal 等入口。",
        "risk_zh": "申诉入口必须限流，且申诉理由按不可信文本渲染。",
        "next_action_zh": "打开申诉处理",
        "details_zh": [
            "重复申诉会被合并或拒绝，避免写爆账本。",
            "管理员审核行为会进入安全账本，但控制台只展示摘要记录。",
            "申诉通过不等于自动回滚业务数据，仍需按动作页处理。",
        ],
    },
    {
        "id": "break_glass",
        "title_zh": "7. 紧急恢复",
        "plain_text_zh": "紧急旁路只用于管理员排障，默认使用 X-ATEE-Bypass Header，不支持固定 URL 明文参数。",
        "recommended_default_zh": "启用前配置旁路密钥文件；使用后立即轮换密钥并回到观察模式。",
        "risk_zh": "旁路不能绕过网站自身登录认证，也不应发给普通用户。",
        "next_action_zh": "查看紧急旁路",
        "details_zh": [
            "第一步：切换只读或观察模式，避免自动动作继续扩大影响。",
            "第二步：验证旁路 Header 只在管理员路径生效。",
            "第三步：恢复后轮换旁路密钥、Admin Token，并查看账本是否有异常管理员操作。",
        ],
    },
    {
        "id": "security_flow",
        "title_zh": "8. 安全情况处理总流程",
        "plain_text_zh": "把常见安全事件统一成“识别、分流、处置、申诉、恢复、复盘”的闭环。",
        "recommended_default_zh": "上线前用安全演练按钮模拟安全请求、攻击请求、申诉和动作撤销。",
        "risk_zh": "没有流程时，管理员容易直接跳到封禁或恢复，遗漏证据和回滚边界。",
        "next_action_zh": "查看安全演练",
        "details_zh": [
            "识别：Fast-Path 先拦截明显攻击，复杂情况进入 Agent 判断。",
            "分流：观察模式只记录，自动模式才执行通过工具网关校验后的动作。",
            "处置：高影响动作必须受运行模式、真实 IP、预算和熔断约束。",
            "申诉：用户申诉进入待处理队列，管理员审核行为写入账本。",
            "恢复：撤销 ATEE 动作记录不等于回滚业务库，业务回滚要单独执行。",
            "复盘：检查账本摘要、模型网关状态、熔断和预算，再决定是否进入自动模式。",
        ],
    },
]


def get_onboarding_steps() -> dict:
    return {
        "locale": "zh-CN",
        "title_zh": "ATEE 可操作新手引导",
        "summary_zh": "按步骤完成环境预检、网站类型、接入方式、真实 IP、AI API、申诉、紧急恢复和安全处置流程。",
        "steps": ONBOARDING_STEPS,
    }

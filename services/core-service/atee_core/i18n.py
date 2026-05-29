ACTION_ZH = {
    "allow": "放行",
    "challenge": "要求验证",
    "cooldown": "短暂冷却",
    "feature_ban": "功能封禁",
    "account_ban_short": "账号短期封禁",
    "ip_ban_short": "IP 短期封禁",
    "adjust_trust_score": "调整信任分",
    "adjust_single_user_trust_score": "调整单个用户信任分",
    "rule_hint": "规则建议",
    "reject": "拒绝执行",
    "would_have_action": "观察模式记录",
}

ROUTE_ZH = {
    "skip": "跳过 Agent",
    "fast_path_block": "快速规则拦截",
    "sync_agent": "同步高危路径",
    "async_agent": "异步 AI 审查路径",
}

MODE_ZH = {
    "observe": "观察模式",
    "auto": "自动模式",
    "degraded": "降级模式",
    "read_only": "只读模式",
    "agent_paused": "Agent 已暂停",
}

REASON_ZH = {
    "low-risk static or health path": "静态资源或健康检查，风险较低",
    "hard block pattern matched": "命中明显攻击特征，已在快速规则层拦截",
    "short cooldown from high request rate": "请求频率过高，进入短暂冷却",
    "no fast-path decision": "快速规则未直接判定，继续进入后续流程",
    "runtime_observe_or_paused": "当前处于观察或暂停状态，只记录不会真实执行",
    "degraded_mode_limits_high_impact_actions": "降级模式限制高影响处罚动作",
    "read_only_mode_blocks_write_punishment": "只读模式不执行写入型处罚",
    "ip_ban_requires_trusted_real_ip_and_admin_enablement": "IP 封禁需要可信真实 IP，且管理员必须显式开启",
    "confidence_threshold_not_met": "置信度或本地证据未达到动作阈值",
    "policy_passed": "已通过 Tool Gateway 执行边界校验",
}


def zh_label(kind: str, value: object) -> str:
    text = str(value)
    if kind == "action":
        return ACTION_ZH.get(text, text)
    if kind == "route":
        return ROUTE_ZH.get(text, text)
    if kind == "mode":
        return MODE_ZH.get(text, text)
    if kind == "reason":
        return REASON_ZH.get(text, text)
    return text


def runtime_display(status: dict) -> dict:
    mode = status.get("runtime_mode")
    return {
        "locale": "zh-CN",
        "runtime_mode_zh": zh_label("mode", mode),
        "agent_paused_zh": "已暂停" if status.get("agent_paused") else "运行中",
        "trusted_proxy_zh": "已配置" if status.get("trusted_proxy_configured") else "未配置，自动 IP 封禁保持关闭",
        "auto_ip_ban_zh": "已开启" if status.get("auto_ip_ban_enabled") else "未开启",
    }


def response_display(route: dict, decision: dict, gateway: dict | None, runtime: dict) -> dict:
    route_name = route.get("route")
    action = decision.get("selected_action")
    effective_action = (gateway or {}).get("effective_action") or action
    reason = (gateway or {}).get("reason") or route.get("reason")

    if route_name == "fast_path_block":
        message = "请求已被 Fast-Path 快速规则拦截，未调用远程 LLM。"
    elif route_name == "skip":
        message = "这是低风险请求，已跳过 Agent 审查。"
    elif effective_action == "would_have_action":
        message = "当前处于观察/暂停状态，仅记录本来会执行的动作。"
    elif (gateway or {}).get("executed"):
        message = "动作已通过 Tool Gateway 校验并执行。"
    else:
        message = "请求已完成评估，当前没有执行真实处罚。"

    return {
        "locale": "zh-CN",
        "message_zh": message,
        "route_zh": zh_label("route", route_name),
        "selected_action_zh": zh_label("action", action),
        "effective_action_zh": zh_label("action", effective_action),
        "reason_zh": zh_label("reason", reason),
        "runtime_mode_zh": zh_label("mode", runtime.get("runtime_mode")),
        "untrusted_text_policy_zh": "所有用户输入、Agent 输出和申诉理由都按纯文本渲染。",
    }

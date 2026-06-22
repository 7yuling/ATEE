import {
  Alert,
  Card,
  Descriptions,
  List,
  Space,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  CheckCircleOutlined,
  InfoCircleOutlined,
  StopOutlined,
} from "@ant-design/icons";

const { Text } = Typography;

const ADMIN_TOKEN_STORAGE_KEY = "atee.adminToken";
const ADMIN_ID_STORAGE_KEY = "atee.adminId";
export const SECRET_PLACEHOLDER = "已配置的敏感值不会回显；留空保持当前配置";
const REDACTED_VALUE = "[已保密]";
const SECRET_JSON_KEYS = new Set([
  "api_base",
  "key",
  "llm_api_base",
  "api_key",
  "openai_api",
  "openai_api_key",
  "llm_api_key",
  "llm_api_key_value",
  "llm_api_key_file",
  "llm_proxy_url",
  "proxy_url",
  "admin_token",
  "admin_token_file",
  "authorization",
  "bypass_header",
  "bypass_key",
]);

export const GATEWAY_HELP = {
  locale: "控制台与后端展示语言；当前建议使用 zh-CN。",
  runtime_mode: "observe 只观察，auto 自动执行，degraded 限制高影响动作，read_only 禁止写入。",
  agent_paused: "暂停后 Agent 不继续自动推进，适合排障或人工接管。",
  async_review_worker_enabled: "开启后 Core Service 会按间隔自动处理异步 AI 审查队列；生产环境请配合预算与熔断使用。",
  async_review_worker_interval_seconds: "后台异步 AI 审查 worker 的轮询间隔，数值越小越实时，但远程模型调用也更频繁。",
  async_review_worker_batch_size: "每轮最多处理的异步 AI 审查任务数，用于控制模型调用峰值。",
  auto_ip_ban_enabled: "开启后工具网关可执行自动 IP 封禁；关闭时只记录或降级动作。",
  admin_auth_enabled: "开启后 /v1/admin/* 需要 Admin Token，生产环境建议开启。",
  llm_daily_budget_cents: "0 表示不限制每日模型调用预算；大于 0 时按天扣减远程调用预算。",
  admin_token_env: "服务端读取 Admin Token 的环境变量名，不是 Token 值。",
  new_admin_token_file: "仅填写服务端密钥文件路径，保存后不回显；留空保持不变。",
  local_precheck_ms: "本地规则预检的目标耗时，用于保护同步链路。",
  remote_soft_timeout_ms: "远程模型软超时，超过后可进入降级判断。",
  remote_hard_timeout_ms: "远程模型硬超时，超过后强制结束远程调用。",
  llm_mode: "mock 为本地模拟；openai_compatible/remote 调用兼容网关；disabled 关闭远程模型。",
  llm_provider: "供应商标识，只用于状态展示与审计，不包含密钥。",
  llm_model: "远程模型名称，由供应商网关识别。",
  new_llm_api_base: "模型接口根地址，仅写入不回显；留空保持不变。",
  llm_api_key_env: "服务端读取 API Key 的环境变量名；控制台输入的 Key 会写入这个变量。",
  llm_api_key_value: "一次性输入 API Key，后端写入当前服务进程环境变量，不回显、不写入配置文件；生产请用 systemd 环境文件或密钥管理器。",
  new_llm_api_key_file: "推荐填写加密后的密钥文件路径；保存后不回显，留空保持不变。",
  new_llm_proxy_url: "服务端访问模型时使用的代理 URL；保存后不回显，留空保持不变。",
  ledger_sqlite_path: "安全账本 SQLite 文件位置；改动后会重建账本句柄。",
  ledger_max_bytes: "账本文件上限，超过后会触发轮转。",
  trusted_proxy_cidrs: "一行一个或用逗号分隔，只信任这些代理转发的真实 IP 头。",
  appeal_paths: "一行一个或用逗号分隔，用于识别用户申诉入口。",
  bypass_enabled: "开启紧急旁路校验，仅用于受控排障。",
  bypass_key_file: "旁路密钥文件路径；不要把密钥明文填入控制台。",
};

export const SITE_TYPE_OPTIONS = [
  { value: "通用网站", label: "通用网站" },
  { value: "论坛/社区", label: "论坛/社区" },
  { value: "博客/内容站", label: "博客/内容站" },
  { value: "电商/交易", label: "电商/交易" },
  { value: "企业官网", label: "企业官网" },
  { value: "API 服务", label: "API 服务" },
];

export const ADAPTER_OPTIONS = [
  { value: "HTTP API", label: "HTTP API" },
  { value: "Python Thin Adapter", label: "Python Thin Adapter" },
  { value: "Node/Express Adapter", label: "Node/Express Adapter" },
  { value: "反向代理", label: "反向代理/Nginx" },
];

export const SECURITY_FLOW_STEPS = [
  "识别：Fast-Path 拦截明显攻击，复杂请求进入 Agent 判断。",
  "分流：观察模式只记录；自动模式才执行工具网关允许的动作。",
  "处置：按运行模式、真实 IP、预算和熔断限制高影响动作。",
  "申诉：用户申诉进入队列，管理员审核行为写入安全账本。",
  "恢复：紧急旁路只用于管理员排障，使用后轮换密钥。",
  "复盘：查看账本摘要、模型网关状态、熔断和预算后再升级自动化。",
];

export function cspNonce() {
  return document.querySelector('meta[name="csp-nonce"]')?.getAttribute("content") || undefined;
}

export function installStyleNonce(nonce) {
  if (!nonce || window.__ateeStyleNonceInstalled) {
    return;
  }
  const applyNonce = (element) => {
    if (element?.tagName?.toLowerCase() === "style" && !element.nonce) {
      element.nonce = nonce;
    }
    return element;
  };
  document.querySelectorAll("style:not([nonce])").forEach(applyNonce);
  const originalCreateElement = document.createElement.bind(document);
  document.createElement = (tagName, options) => {
    const element = originalCreateElement(tagName, options);
    return String(tagName).toLowerCase() === "style" ? applyNonce(element) : element;
  };
  const originalAppendChild = Node.prototype.appendChild;
  Node.prototype.appendChild = function appendChildWithStyleNonce(child) {
    return originalAppendChild.call(this, applyNonce(child));
  };
  const originalInsertBefore = Node.prototype.insertBefore;
  Node.prototype.insertBefore = function insertBeforeWithStyleNonce(child, referenceNode) {
    return originalInsertBefore.call(this, applyNonce(child), referenceNode);
  };
  window.__ateeStyleNonceInstalled = true;
}

export function readAdminToken() {
  try {
    return window.sessionStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

export function writeAdminToken(token) {
  try {
    if (token) {
      window.sessionStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, token);
    } else {
      window.sessionStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
    }
  } catch {
    // Browser storage can be disabled; requests still work when auth is off.
  }
}

export function readAdminId() {
  try {
    return window.sessionStorage.getItem(ADMIN_ID_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

export function writeAdminId(adminId) {
  try {
    if (adminId) {
      window.sessionStorage.setItem(ADMIN_ID_STORAGE_KEY, adminId);
    } else {
      window.sessionStorage.removeItem(ADMIN_ID_STORAGE_KEY);
    }
  } catch {
    // Browser storage can be disabled; the backend will record unknown actor.
  }
}

export async function apiRequest(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const adminToken = readAdminToken();
  const adminId = readAdminId();
  if (path.startsWith("/v1/admin/") && adminToken && !headers.Authorization) {
    headers.Authorization = `Bearer ${adminToken}`;
  }
  if (path.startsWith("/v1/admin/") && adminId && !headers["X-ATEE-Admin-Id"]) {
    headers["X-ATEE-Admin-Id"] = adminId;
  }
  const response = await fetch(path, {
    headers,
    ...options,
  });
  const contentType = response.headers.get("Content-Type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : {
        ok: false,
        status: response.status,
        error: (await response.text()).slice(0, 240) || response.statusText,
      };
  if (response.status === 401 && path.startsWith("/v1/admin/")) {
    window.dispatchEvent(new CustomEvent("atee-admin-auth-required", { detail: data }));
  }
  return { status: response.status, data };
}

export function pretty(value) {
  return JSON.stringify(redactSecrets(value ?? {}), null, 2);
}

export function splitListInput(value) {
  return String(value || "")
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function tagForBoolean(value, labels = ["正常", "异常"]) {
  return value ? <Tag color="success">{labels[0]}</Tag> : <Tag color="warning">{labels[1]}</Tag>;
}

export function tagForNullableBoolean(value, labels = ["正常", "异常", "未测试"]) {
  if (value === null || value === undefined) {
    return <Tag>{labels[2]}</Tag>;
  }
  return value ? <Tag color="success">{labels[0]}</Tag> : <Tag color="warning">{labels[1]}</Tag>;
}

export function providerLabel(provider) {
  const value = String(provider || "").trim();
  if (!value) {
    return "-";
  }
  if (value.toLowerCase() === "deepseek") {
    return "DeepSeek";
  }
  if (value.toLowerCase() === "mock") {
    return "Mock";
  }
  return value;
}

export function modeLabel(mode) {
  const labels = {
    mock: "Mock",
    openai_compatible: "OpenAI-compatible",
    remote: "Remote",
    disabled: "Disabled",
  };
  return labels[mode] || mode || "-";
}

export function reasonLabel(reason) {
  const labels = {
    provider_json_decision: "供应商已返回结构化判断",
    missing_api_base: "缺少 API Base",
    missing_api_key: "缺少 API Key",
    insecure_api_base_requires_https: "公网 API Base 必须使用 HTTPS",
    provider_request_failed: "供应商请求失败",
    provider_timeout: "供应商请求超时",
    llm_circuit_open: "熔断窗口中",
    llm_budget_exhausted: "远程调用预算已耗尽",
    mock_decision: "本地 Mock 判断",
    mock_suspicious_content: "本地 Mock 命中可疑内容",
    async_review_queued: "已进入异步 AI 审查队列",
  };
  return labels[reason] || reason || "-";
}

export function budgetLabel(budget = {}) {
  if (budget.daily_remaining_cents === null) {
    return "不限";
  }
  if (budget.daily_remaining_cents === undefined) {
    return "-";
  }
  return `${budget.daily_remaining_cents} cent`;
}

export function MetricCard({ id, title, value, icon, children }) {
  return (
    <Card className="metric-card">
      <div className="metric-title">{title}</div>
      <div id={id} className="metric-value">
        {icon}
        <span>{value}</span>
      </div>
      {children ? <div className="metric-extra">{children}</div> : null}
    </Card>
  );
}

export function RuntimeSummary({ status }) {
  const gateway = status?.llm_gateway || {};
  const display = status?.display || {};
  const budget = gateway.budget || {};
  const circuit = gateway.circuit || {};
  return (
    <div id="outputSummary" className="summary-block">
      <Descriptions size="small" column={1}>
        <Descriptions.Item label="服务状态">{status ? <Tag color="success">已连接</Tag> : <Tag>连接中</Tag>}</Descriptions.Item>
        <Descriptions.Item label="运行模式">{display.runtime_mode_zh || status?.runtime_mode || "-"}</Descriptions.Item>
        <Descriptions.Item label="Agent">{display.agent_paused_zh || "-"}</Descriptions.Item>
        <Descriptions.Item label="账本记录">{status?.ledger?.persisted_records ?? status?.ledger?.records ?? 0}</Descriptions.Item>
        <Descriptions.Item label="待处理申诉">{status?.pending_appeals ?? 0}</Descriptions.Item>
        <Descriptions.Item label="异步 AI 审查">{status?.async_review?.queued ?? 0}</Descriptions.Item>
        <Descriptions.Item label="模型配置">{`${providerLabel(gateway.provider)} / ${modeLabel(gateway.mode)}`}</Descriptions.Item>
        <Descriptions.Item label="最近连通">{tagForNullableBoolean(gateway.last_ok, ["最近成功", "最近失败", "未测试"])}</Descriptions.Item>
        <Descriptions.Item label="API Key">{tagForBoolean(Boolean(gateway.api_key_configured), ["已配置", "未配置"])}</Descriptions.Item>
        <Descriptions.Item label="代理">{tagForBoolean(Boolean(gateway.proxy_configured), ["已配置", "未配置"])}</Descriptions.Item>
        <Descriptions.Item label="熔断">{circuit.open ? <Tag color="warning">已熔断</Tag> : <Tag color="success">正常</Tag>}</Descriptions.Item>
        <Descriptions.Item label="预算余额">{budgetLabel(budget)}</Descriptions.Item>
      </Descriptions>
    </div>
  );
}

export function OperationSummary({ result }) {
  const connectionResult = result?.llm_gateway_test || result;
  const gatewayResult = connectionResult?.llm_gateway || {};
  const budget = connectionResult?.budget || gatewayResult.budget || {};
  const circuit = connectionResult?.circuit || gatewayResult.circuit || {};
  const reason = connectionResult?.reason || gatewayResult.reason;
  const route = result?.route?.route;
  const action = result?.tool_gateway?.effective_action || result?.decision?.selected_action || result?.action_result?.record?.action;
  const modelText = connectionResult?.provider || gatewayResult.provider
    ? `${providerLabel(connectionResult?.provider || gatewayResult.provider)} / ${modeLabel(connectionResult?.mode || gatewayResult.mode)}`
    : "-";
  return (
    <div id="resultSummary" className="summary-block">
      <Alert
        className="result-message"
        type={result?.ok === false ? "warning" : result?.error ? "error" : "info"}
        showIcon
        message={resultMessage(result)}
      />
      <Descriptions size="small" column={1}>
        <Descriptions.Item label="操作类型">{resultKind(result)}</Descriptions.Item>
        <Descriptions.Item label="结果">{operationStatus(result)}</Descriptions.Item>
        <Descriptions.Item label="模型">{modelText}</Descriptions.Item>
        <Descriptions.Item label="原因">{reasonLabel(reason)}</Descriptions.Item>
        <Descriptions.Item label="路由">{route || "-"}</Descriptions.Item>
        <Descriptions.Item label="动作">{action || "-"}</Descriptions.Item>
        <Descriptions.Item label="延迟">{connectionResult?.latency_ms ?? gatewayResult.latency_ms ?? "-"} ms</Descriptions.Item>
        <Descriptions.Item label="API Base">{tagForNullableBoolean(connectionResult?.api_base_configured, ["已配置", "未配置", "未返回"])}</Descriptions.Item>
        <Descriptions.Item label="API Key">{tagForNullableBoolean(connectionResult?.api_key_configured, ["已配置", "未配置", "未返回"])}</Descriptions.Item>
        <Descriptions.Item label="代理">{tagForNullableBoolean(connectionResult?.proxy_configured, ["已配置", "未配置", "未返回"])}</Descriptions.Item>
        <Descriptions.Item label="熔断">{circuit.open ? <Tag color="warning">已熔断</Tag> : <Tag color="success">正常</Tag>}</Descriptions.Item>
        <Descriptions.Item label="预算余额">{budgetLabel(budget)}</Descriptions.Item>
      </Descriptions>
    </div>
  );
}

export function LabelWithHelp({ text, help }) {
  return (
    <Space size={4}>
      <span>{text}</span>
      <Tooltip title={help}>
        <InfoCircleOutlined className="help-icon" />
      </Tooltip>
    </Space>
  );
}

export function PreflightSummary({ report }) {
  const checks = report?.checks || [];
  if (!checks.length) {
    return <Text type="secondary">点击“运行环境预检”后，这里会显示本地或服务器程序检测结果。</Text>;
  }
  return (
    <List
      id="preflightChecks"
      size="small"
      dataSource={checks}
      renderItem={(item) => (
        <List.Item>
          <List.Item.Meta
            avatar={item.ok ? <CheckCircleOutlined className="ok-icon" /> : <StopOutlined className="bad-icon" />}
            title={
              <Space>
                <Text strong>{item.title_zh}</Text>
                {item.ok ? <Tag color="success">通过</Tag> : <Tag color="warning">需处理</Tag>}
              </Space>
            }
            description={
              <Space direction="vertical" size={2}>
                <Text>{item.detail_zh}</Text>
                {item.ok ? null : <Text type="secondary">{item.next_action_zh}</Text>}
              </Space>
            }
          />
        </List.Item>
      )}
    />
  );
}

function isSecretJsonKey(key) {
  const normalized = String(key || "").toLowerCase();
  return SECRET_JSON_KEYS.has(normalized);
}

function redactSecrets(value) {
  if (Array.isArray(value)) {
    return value.map((item) => redactSecrets(item));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        isSecretJsonKey(key) ? REDACTED_VALUE : redactSecrets(item),
      ]),
    );
  }
  return value;
}

function resultKind(result = {}) {
  if (result.llm_gateway_test) {
    return "配置保存并检测";
  }
  if (Array.isArray(result.checks)) {
    return "环境预检";
  }
  if (Array.isArray(result.flow_steps)) {
    return "安全流程演练";
  }
  if (result.reply_zh) {
    return "Agent 对话";
  }
  if ("api_base_configured" in result || "api_key_configured" in result) {
    return "模型网关检测";
  }
  if (result.request) {
    return "安全请求检测";
  }
  if (result.changed) {
    return "配置保存";
  }
  if (Array.isArray(result.appeals)) {
    return "申诉列表";
  }
  if (Array.isArray(result.actions)) {
    return "动作列表";
  }
  if (Array.isArray(result.jobs)) {
    return "异步 AI 审查队列";
  }
  if ("claimed" in result && Array.isArray(result.processed)) {
    return "异步 AI 审查处理";
  }
  if (Array.isArray(result.records)) {
    return "账本查询";
  }
  if ("ledger_count" in result) {
    return "账本查询";
  }
  if ("valid_for_request" in result) {
    return "紧急旁路检测";
  }
  if ("admin_token_saved" in result) {
    return "管理会话";
  }
  return Object.keys(result || {}).length ? "管理操作" : "等待操作";
}

function resultMessage(result = {}) {
  if (result.llm_gateway_test?.display?.message_zh) {
    return result.llm_gateway_test.display.message_zh;
  }
  if (result.display?.message_zh) {
    return result.display.message_zh;
  }
  if (result.reply_zh) {
    return result.reply_zh;
  }
  if (result.error) {
    return String(result.error);
  }
  if ("api_base_configured" in result || "api_key_configured" in result) {
    return result.ok ? "模型网关连接正常。" : "模型网关当前不可用，请检查供应商、模型名、网络和密钥配置。";
  }
  if (result.ok === true) {
    return "操作已完成。";
  }
  if (result.ok === false) {
    return "操作未完成，请查看摘要原因。";
  }
  return "选择一个操作后，这里会显示摘要结果。";
}

function operationStatus(result = {}) {
  if (!Object.keys(result || {}).length) {
    return <Tag>未执行</Tag>;
  }
  if (typeof result.ok === "boolean") {
    return tagForBoolean(result.ok, ["成功", "失败"]);
  }
  if (typeof result.status === "number") {
    return result.status >= 200 && result.status < 400 ? <Tag color="success">{result.status}</Tag> : <Tag color="warning">{result.status}</Tag>;
  }
  return <Tag color="success">已返回</Tag>;
}

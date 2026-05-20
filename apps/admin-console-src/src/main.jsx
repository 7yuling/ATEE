import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Alert,
  Button,
  Card,
  Col,
  ConfigProvider,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Layout,
  List,
  Menu,
  Popconfirm,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  theme,
} from "antd";
import zhCN from "antd/locale/zh_CN";
import {
  ApiOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  EyeOutlined,
  FileSearchOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  StopOutlined,
  ThunderboltOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import "antd/dist/reset.css";
import "./styles.css";

const { Header, Sider, Content } = Layout;
const { Title, Text } = Typography;

function cspNonce() {
  return document.querySelector('meta[name="csp-nonce"]')?.getAttribute("content") || undefined;
}

const runtimeCspNonce = cspNonce();
const ADMIN_TOKEN_STORAGE_KEY = "atee.adminToken";
const ADMIN_ID_STORAGE_KEY = "atee.adminId";
const SECRET_PLACEHOLDER = "已配置的敏感值不会回显；留空保持当前配置";
const REDACTED_VALUE = "[已保密]";
const SECRET_JSON_KEYS = new Set([
  "api_base",
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
const GATEWAY_HELP = {
  locale: "控制台与后端展示语言；当前建议使用 zh-CN。",
  runtime_mode: "observe 只观察，auto 自动执行，degraded 限制高影响动作，read_only 禁止写入。",
  agent_paused: "暂停后 Agent 不继续自动推进，适合排障或人工接管。",
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

function installStyleNonce(nonce) {
  if (!nonce || window.__ateeStyleNonceInstalled) {
    return;
  }
  const originalCreateElement = document.createElement.bind(document);
  document.createElement = (tagName, options) => {
    const element = originalCreateElement(tagName, options);
    if (String(tagName).toLowerCase() === "style") {
      element.nonce = nonce;
    }
    return element;
  };
  window.__ateeStyleNonceInstalled = true;
}

installStyleNonce(runtimeCspNonce);

function readAdminToken() {
  try {
    return window.sessionStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function writeAdminToken(token) {
  try {
    if (token) {
      window.sessionStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, token);
    } else {
      window.sessionStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
    }
  } catch {
    // Browser storage can be disabled; requests will still work when auth is off.
  }
}

function readAdminId() {
  try {
    return window.sessionStorage.getItem(ADMIN_ID_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function writeAdminId(adminId) {
  try {
    if (adminId) {
      window.sessionStorage.setItem(ADMIN_ID_STORAGE_KEY, adminId);
    } else {
      window.sessionStorage.removeItem(ADMIN_ID_STORAGE_KEY);
    }
  } catch {
    // Browser storage can be disabled; the backend will record the actor as unknown.
  }
}

async function apiRequest(path, options = {}) {
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

function pretty(value) {
  return JSON.stringify(redactSecrets(value ?? {}), null, 2);
}

function splitListInput(value) {
  return String(value || "")
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function tagForBoolean(value, labels = ["正常", "异常"]) {
  return value ? <Tag color="success">{labels[0]}</Tag> : <Tag color="warning">{labels[1]}</Tag>;
}

function tagForNullableBoolean(value, labels = ["正常", "异常", "未测试"]) {
  if (value === null || value === undefined) {
    return <Tag>{labels[2]}</Tag>;
  }
  return value ? <Tag color="success">{labels[0]}</Tag> : <Tag color="warning">{labels[1]}</Tag>;
}

function providerLabel(provider) {
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

function modeLabel(mode) {
  const labels = {
    mock: "Mock",
    openai_compatible: "OpenAI-compatible",
    remote: "Remote",
    disabled: "Disabled",
  };
  return labels[mode] || mode || "-";
}

function reasonLabel(reason) {
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
  };
  return labels[reason] || reason || "-";
}

function budgetLabel(budget = {}) {
  if (budget.daily_remaining_cents === null) {
    return "不限";
  }
  if (budget.daily_remaining_cents === undefined) {
    return "-";
  }
  return `${budget.daily_remaining_cents} cent`;
}

function resultKind(result = {}) {
  if (result.llm_gateway_test) {
    return "配置保存并检测";
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
  if (Array.isArray(result.records)) {
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

function MetricCard({ id, title, value, icon, children }) {
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

function RuntimeSummary({ status }) {
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

function OperationSummary({ result }) {
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

function App() {
  const [activeMenu, setActiveMenu] = useState("dashboard");
  const [status, setStatus] = useState(null);
  const [output, setOutput] = useState({});
  const [result, setResult] = useState({});
  const [loading, setLoading] = useState(false);
  const [guideSteps, setGuideSteps] = useState([]);
  const [appeals, setAppeals] = useState([]);
  const [actions, setActions] = useState([]);
  const [ledgerRecords, setLedgerRecords] = useState([]);
  const [appealStatus, setAppealStatus] = useState("pending");
  const [actionStatus, setActionStatus] = useState("active");
  const [ledgerLimit, setLedgerLimit] = useState(10);
  const [adminToken, setAdminToken] = useState(readAdminToken());
  const [adminId, setAdminId] = useState(readAdminId());
  const [authRequired, setAuthRequired] = useState(false);
  const [appealForm] = Form.useForm();
  const [actionForm] = Form.useForm();
  const [configForm] = Form.useForm();
  const [breakGlassForm] = Form.useForm();

  const gateway = status?.llm_gateway || {};
  const budget = gateway.budget || {};
  const circuit = gateway.circuit || {};
  const display = status?.display || {};
  const adminAuth = status?.admin_auth || {};
  const gatewayConfigured = gateway.mode === "mock" || Boolean(gateway.api_base_configured && gateway.api_key_configured);
  const writeLocked = status?.runtime_mode === "read_only";
  const operationGuardMessage = writeLocked
    ? "当前为只读模式：控制台会阻止审核、撤销、配置保存等写入操作；可先切回观察或降级模式。"
    : status?.runtime_mode === "degraded"
      ? "当前为降级模式：后端会限制高影响处罚动作，控制台仍会对高影响操作要求二次确认。"
      : status?.agent_paused
        ? "Agent 已暂停：自动执行链路不会推进，高影响控制操作仍需二次确认。"
        : "";
  const operationGuardType = writeLocked ? "error" : "warning";

  function configToFormValues(config = {}) {
    return {
      locale: config.locale || "zh-CN",
      runtime_mode: config.runtime_mode || "observe",
      agent_paused: Boolean(config.agent_paused),
      trusted_proxy_cidrs: (config.trusted_proxy_cidrs || []).join("\n"),
      auto_ip_ban_enabled: Boolean(config.auto_ip_ban_enabled),
      local_precheck_ms: Number(config.local_precheck_ms ?? 100),
      remote_soft_timeout_ms: Number(config.remote_soft_timeout_ms ?? 3000),
      remote_hard_timeout_ms: Number(config.remote_hard_timeout_ms ?? 5000),
      llm_mode: config.llm_mode || "mock",
      llm_provider: config.llm_provider || "mock",
      llm_model: config.llm_model || "atee-local-mock-v1",
      llm_api_key_env: config.llm_api_key_env || "ATEE_LLM_API_KEY",
      llm_daily_budget_cents: Number(config.llm_daily_budget_cents ?? 0),
      ledger_max_bytes: Number(config.ledger_max_bytes ?? 268435456),
      ledger_sqlite_path: config.ledger_sqlite_path || "data/atee_ledger.sqlite3",
      appeal_paths: (config.appeal_paths || []).join("\n"),
      bypass_enabled: Boolean(config.bypass_enabled),
      bypass_key_file: config.bypass_key_file || "",
      admin_auth_enabled: Boolean(config.admin_auth_enabled),
      admin_token_env: config.admin_token_env || "ATEE_ADMIN_TOKEN",
      new_llm_api_base: "",
      llm_api_key_value: "",
      new_llm_api_key_file: "",
      new_llm_proxy_url: "",
      new_admin_token_file: "",
    };
  }

  async function run(label, fn) {
    setLoading(true);
    try {
      const data = await fn();
      setResult(data);
      return data;
    } catch (error) {
      const data = { ok: false, error: error instanceof Error ? error.message : String(error), label };
      setResult(data);
      return data;
    } finally {
      setLoading(false);
    }
  }

  async function refresh() {
    const { data } = await apiRequest("/v1/runtime/status");
    setStatus(data);
    configForm.setFieldsValue(configToFormValues(data.config || {}));
    setOutput(data);
    return data;
  }

  async function loadOnboarding() {
    const { data } = await apiRequest("/v1/onboarding/steps");
    setGuideSteps(data.steps || []);
    return data;
  }

  async function setMode(mode) {
    await run("set-mode", async () => {
      const { data } = await apiRequest("/v1/admin/mode", {
        method: "POST",
        body: JSON.stringify({ mode }),
      });
      await refresh();
      return data;
    });
  }

  async function pauseResume() {
    await run("pause-agent", async () => {
      const paused = !(status && status.agent_paused);
      const { data } = await apiRequest("/v1/admin/pause-agent", {
        method: "POST",
        body: JSON.stringify({ paused }),
      });
      await refresh();
      return data;
    });
  }

  async function testSafe() {
    await run("safe-request", async () => {
      const body = {
        method: "GET",
        path: "/posts/hello",
        headers: {},
        remote_addr: "198.51.100.8",
        body: { text: "这是一条普通中文浏览请求" },
      };
      const { data } = await apiRequest("/v1/check", { method: "POST", body: JSON.stringify(body) });
      await refresh();
      return data;
    });
  }

  async function testAttack() {
    await run("fast-path", async () => {
      const body = {
        method: "POST",
        path: "/comment",
        event_type: "comment_create",
        body: { text: "<script>alert(1)</script>" },
        remote_addr: "198.51.100.9",
      };
      const { data } = await apiRequest("/v1/check", { method: "POST", body: JSON.stringify(body) });
      await refresh();
      return data;
    });
  }

  async function testAppeal() {
    await run("appeal", async () => {
      const body = { punishment_id: "demo-punishment", reason: "我认为这次封禁可能是误判，请管理员复核。" };
      const { data } = await apiRequest("/v1/appeal", { method: "POST", body: JSON.stringify(body) });
      await refresh();
      return data;
    });
  }

  async function testLlmGateway() {
    await run("llm-test", async () => {
      const { data } = await apiRequest("/v1/admin/llm/test");
      await refresh();
      return data;
    });
  }

  async function showConfig() {
    await run("config", async () => {
      const { data } = await apiRequest("/v1/admin/config");
      configForm.setFieldsValue(configToFormValues(data.config || {}));
      return data;
    });
  }

  async function breakGlass() {
    await run("break-glass", async () => {
      const values = breakGlassForm.getFieldsValue();
      const header = String(values.bypass_header || "").trim();
      const { data } = await apiRequest("/v1/admin/break-glass/status", {
        method: "POST",
        headers: header ? { "X-ATEE-Bypass": header } : {},
        body: "{}",
      });
      return data;
    });
  }

  async function showLedger() {
    await run("ledger", async () => {
      const limit = Number(ledgerLimit) || 10;
      const { data } = await apiRequest(`/v1/admin/ledger/recent?limit=${limit}`);
      setLedgerRecords(data.records || []);
      await refresh();
      return data;
    });
  }

  async function showAppeals(statusFilter = appealStatus) {
    await run("appeals", async () => {
      const { data } = await apiRequest(`/v1/admin/appeals?status=${encodeURIComponent(statusFilter)}`);
      setAppeals(data.appeals || []);
      await refresh();
      return data;
    });
  }

  async function reviewAppeal(resolution) {
    await run("review-appeal", async () => {
      const values = appealForm.getFieldsValue();
      const { data } = await apiRequest("/v1/admin/appeals/review", {
        method: "POST",
        body: JSON.stringify({
          punishment_id: String(values.punishment_id || "").trim(),
          resolution,
          admin_note: String(values.admin_note || "").trim(),
        }),
      });
      await showAppeals(appealStatus);
      return data;
    });
  }

  async function showActions(statusFilter = actionStatus) {
    await run("actions", async () => {
      const { data } = await apiRequest(`/v1/admin/actions?status=${statusFilter}`);
      setActions(data.actions || []);
      await refresh();
      return data;
    });
  }

  async function revokeAction() {
    await run("revoke-action", async () => {
      const values = actionForm.getFieldsValue();
      const { data } = await apiRequest("/v1/admin/actions/revoke", {
        method: "POST",
        body: JSON.stringify({
          action_id: Number(values.action_id),
          reason: String(values.reason || "").trim(),
        }),
      });
      await showActions(actionStatus);
      return data;
    });
  }

  async function cleanupActions() {
    await run("cleanup-actions", async () => {
      const { data } = await apiRequest("/v1/admin/actions/cleanup-expired", { method: "POST", body: "{}" });
      await showActions(actionStatus);
      return data;
    });
  }

  async function saveConfig() {
    await run("save-config", async () => {
      const values = configForm.getFieldsValue();
      const body = {
        locale: values.locale || "zh-CN",
        runtime_mode: values.runtime_mode,
        agent_paused: Boolean(values.agent_paused),
        trusted_proxy_cidrs: splitListInput(values.trusted_proxy_cidrs),
        auto_ip_ban_enabled: Boolean(values.auto_ip_ban_enabled),
        local_precheck_ms: Number(values.local_precheck_ms),
        remote_soft_timeout_ms: Number(values.remote_soft_timeout_ms),
        remote_hard_timeout_ms: Number(values.remote_hard_timeout_ms),
        llm_mode: values.llm_mode,
        llm_provider: String(values.llm_provider || "").trim() || "mock",
        llm_model: String(values.llm_model || "").trim() || "atee-local-mock-v1",
        llm_api_key_env: String(values.llm_api_key_env || "").trim() || "ATEE_LLM_API_KEY",
        llm_daily_budget_cents: Number(values.llm_daily_budget_cents),
        ledger_max_bytes: Number(values.ledger_max_bytes),
        ledger_sqlite_path: String(values.ledger_sqlite_path || "").trim() || "data/atee_ledger.sqlite3",
        appeal_paths: splitListInput(values.appeal_paths),
        admin_auth_enabled: Boolean(values.admin_auth_enabled),
        admin_token_env: String(values.admin_token_env || "").trim() || "ATEE_ADMIN_TOKEN",
        bypass_enabled: Boolean(values.bypass_enabled),
        bypass_key_file: String(values.bypass_key_file || "").trim() || null,
      };
      const apiBase = String(values.new_llm_api_base || "").trim();
      const apiKeyValue = String(values.llm_api_key_value || "").trim();
      const keyFile = String(values.new_llm_api_key_file || "").trim();
      const proxyUrl = String(values.new_llm_proxy_url || "").trim();
      const adminTokenFile = String(values.new_admin_token_file || "").trim();
      if ((apiBase || apiKeyValue) && body.llm_mode === "mock") {
        body.llm_mode = "openai_compatible";
      }
      if (apiBase) {
        body.llm_api_base = apiBase;
      }
      if (apiKeyValue) {
        body.llm_api_key_value = apiKeyValue;
      }
      if (keyFile) {
        body.llm_api_key_file = keyFile;
      }
      if (proxyUrl) {
        body.llm_proxy_url = proxyUrl;
      }
      if (adminTokenFile) {
        body.admin_token_file = adminTokenFile;
      }
      const { data } = await apiRequest("/v1/admin/config", {
        method: "POST",
        body: JSON.stringify(body),
      });
      configForm.setFieldsValue(configToFormValues(data.config || {}));
      await refresh();
      if (apiBase || apiKeyValue) {
        const { data: testData } = await apiRequest("/v1/admin/llm/test");
        await refresh();
        return {
          ...data,
          ok: Boolean(data.ok && testData.ok),
          llm_gateway_test: testData,
          display: testData.display || data.display,
        };
      }
      return data;
    });
  }

  function saveAdminToken() {
    const token = String(adminToken || "").trim();
    const actor = String(adminId || "").trim();
    writeAdminToken(token);
    writeAdminId(actor);
    setAdminToken(token);
    setAdminId(actor);
    setAuthRequired(false);
    setResult({ ok: true, admin_token_saved: Boolean(token), admin_actor_saved: Boolean(actor) });
  }

  function clearAdminToken() {
    writeAdminToken("");
    writeAdminId("");
    setAdminToken("");
    setAdminId("");
    setAuthRequired(false);
    setResult({ ok: true, admin_token_saved: false, admin_actor_saved: false });
  }

  useEffect(() => {
    refresh().catch((error) => setResult({ ok: false, error: error.message }));
    loadOnboarding().catch((error) => setResult({ ok: false, error: error.message }));
  }, []);

  useEffect(() => {
    const listener = () => setAuthRequired(true);
    window.addEventListener("atee-admin-auth-required", listener);
    return () => window.removeEventListener("atee-admin-auth-required", listener);
  }, []);

  const menuItems = useMemo(
    () => [
      { key: "dashboard", icon: <DatabaseOutlined />, label: "仪表盘" },
      { key: "appeals", icon: <FileSearchOutlined />, label: "申诉处理" },
      { key: "actions", icon: <ToolOutlined />, label: "动作管理" },
      { key: "ledger", icon: <SafetyCertificateOutlined />, label: "安全账本" },
      { key: "config", icon: <ApiOutlined />, label: "网关配置" },
      { key: "guide", icon: <CheckCircleOutlined />, label: "新手引导" },
    ],
    [],
  );

  const appealColumns = [
    { title: "处罚编号", dataIndex: "punishment_id", key: "punishment_id" },
    { title: "状态", dataIndex: "status", key: "status", render: (value) => <Tag>{value}</Tag> },
    { title: "理由", dataIndex: "reason_untrusted_text", key: "reason", ellipsis: true },
    { title: "创建时间", dataIndex: "created_at", key: "created_at" },
  ];

  const actionColumns = [
    { title: "ID", dataIndex: "id", key: "id", width: 80 },
    { title: "动作", dataIndex: "action", key: "action" },
    { title: "状态", dataIndex: "status", key: "status", render: (value) => <Tag>{value}</Tag> },
    { title: "原因", dataIndex: "reason", key: "reason", ellipsis: true },
    { title: "过期时间", dataIndex: "expires_at", key: "expires_at" },
  ];

  const ledgerColumns = [
    { title: "ID", dataIndex: "id", key: "id", width: 80 },
    { title: "事件", dataIndex: "event_type", key: "event_type" },
    { title: "等级", dataIndex: "severity", key: "severity", render: (value) => <Tag>{value}</Tag> },
    { title: "动作", dataIndex: "action", key: "action" },
    { title: "摘要", dataIndex: "summary", key: "summary", ellipsis: true },
  ];

  return (
    <Layout className="atee-shell">
      <Sider width={248} className="atee-sider">
        <div className="brand-block">
          <Title level={3}>ATEE</Title>
          <Text>管理控制台</Text>
        </div>
        <Menu mode="inline" selectedKeys={[activeMenu]} items={menuItems} onClick={({ key }) => setActiveMenu(key)} />
      </Sider>
      <Layout>
        <Header className="atee-header">
          <div>
            <Title level={2}>ATEE 管理控制台</Title>
            <Text id="statusText" type={status ? "success" : "secondary"}>
              {status ? "Core Service 已连接" : "正在连接"}
            </Text>
          </div>
          <Space wrap>
            <Button id="refreshBtn" icon={<ReloadOutlined />} onClick={() => run("refresh", refresh)} loading={loading}>
              刷新
            </Button>
            <Button id="observeBtn" icon={<EyeOutlined />} onClick={() => setMode("observe")}>
              观察模式
            </Button>
            <Popconfirm
              title="切换到自动模式"
              description="自动模式会允许后端执行符合策略的动作，请确认当前环境已经准备好。"
              okText="确认切换"
              cancelText="取消"
              onConfirm={() => setMode("auto")}
            >
              <Button id="autoBtn" type="primary" icon={<ThunderboltOutlined />}>
                自动模式
              </Button>
            </Popconfirm>
            <Button id="degradedBtn" icon={<StopOutlined />} onClick={() => setMode("degraded")}>
              降级模式
            </Button>
            <Button id="readOnlyBtn" icon={<SafetyCertificateOutlined />} onClick={() => setMode("read_only")}>
              只读模式
            </Button>
            <Button id="pauseBtn" icon={status?.agent_paused ? <PlayCircleOutlined /> : <PauseCircleOutlined />} onClick={pauseResume}>
              {status?.agent_paused ? "恢复 Agent" : "暂停 Agent"}
            </Button>
          </Space>
        </Header>
        <Content className="atee-content">
          <Alert
            className="top-alert"
            type="info"
            showIcon
            message="所有用户输入、Agent 输出和申诉理由都按纯文本渲染；管理台不保存原始 Prompt 或原始请求体。"
          />
          <Card className="auth-panel" size="small">
            <Space wrap>
              <Text strong>管理令牌</Text>
              <Input
                id="adminIdInput"
                value={adminId}
                onChange={(event) => setAdminId(event.target.value)}
                autoComplete="off"
                placeholder="操作者 ID"
                style={{ width: 180 }}
              />
              <Input.Password
                id="adminTokenInput"
                value={adminToken}
                onChange={(event) => setAdminToken(event.target.value)}
                autoComplete="off"
                visibilityToggle={false}
                placeholder="Admin Token"
                style={{ width: 260 }}
              />
              <Button id="saveAdminTokenBtn" icon={<SafetyCertificateOutlined />} onClick={saveAdminToken}>
                保存本机会话
              </Button>
              <Button id="clearAdminTokenBtn" onClick={clearAdminToken}>
                清除
              </Button>
              <Tag id="adminAuthState" color={adminAuth.enabled ? (adminToken ? "success" : "warning") : "default"}>
                {adminAuth.enabled ? (adminToken ? "认证已准备" : "需要令牌") : "认证未开启"}
              </Tag>
              <Tag color={adminAuth.token_configured ? "success" : "default"}>
                {adminAuth.token_configured ? "服务端令牌已配置" : "服务端令牌未配置"}
              </Tag>
            </Space>
          </Card>
          {authRequired ? (
            <Alert
              id="adminAuthAlert"
              className="guard-alert"
              type="error"
              showIcon
              message="管理接口需要有效令牌，当前请求未被执行。"
            />
          ) : null}
          {operationGuardMessage ? (
            <Alert
              id="operationGuardAlert"
              className="guard-alert"
              type={operationGuardType}
              showIcon
              message={operationGuardMessage}
            />
          ) : null}
          {gateway.provider && gateway.provider !== "mock" && gateway.last_ok === false ? (
            <Alert
              className="guard-alert"
              type="warning"
              showIcon
              message="模型配置已接入，但最近一次连通检测未通过；请以“测试模型网关”的操作结果为准。"
            />
          ) : null}

          <Row gutter={[16, 16]}>
            <Col xs={24} md={12} xl={6}>
              <MetricCard id="runtime" title="当前模式" value={display.runtime_mode_zh || status?.runtime_mode || "-"} icon={<EyeOutlined />} />
            </Col>
            <Col xs={24} md={12} xl={6}>
              <MetricCard id="paused" title="Agent 状态" value={display.agent_paused_zh || "-"} icon={<PauseCircleOutlined />} />
            </Col>
            <Col xs={24} md={12} xl={6}>
              <MetricCard id="ledger" title="账本记录" value={status?.ledger?.persisted_records ?? status?.ledger?.records ?? 0} icon={<DatabaseOutlined />} />
            </Col>
            <Col xs={24} md={12} xl={6}>
              <MetricCard id="appeals" title="待处理申诉" value={status?.pending_appeals ?? 0} icon={<FileSearchOutlined />} />
            </Col>
            <Col xs={24} md={12} xl={6}>
              <MetricCard id="llmState" title="模型网关配置" value={providerLabel(gateway.provider)} icon={<ApiOutlined />}>
                <Space wrap size={[4, 4]}>
                  <Tag>{modeLabel(gateway.mode)}</Tag>
                  {gatewayConfigured ? <Tag color="success">配置已接入</Tag> : <Tag color="warning">配置未完整</Tag>}
                  {tagForNullableBoolean(gateway.last_ok, ["最近成功", "最近失败", "未测试"])}
                </Space>
              </MetricCard>
            </Col>
            <Col xs={24} md={12} xl={6}>
              <MetricCard id="circuitState" title="熔断状态" value={circuit.open ? "已熔断" : "正常"} icon={circuit.open ? <StopOutlined /> : <CheckCircleOutlined />} />
            </Col>
            <Col xs={24} md={12} xl={6}>
              <MetricCard id="budgetState" title="预算余额" value={budgetLabel(budget)} icon={<ClockCircleOutlined />} />
            </Col>
            <Col xs={24} md={12} xl={6}>
              <MetricCard id="activeActions" title="活跃动作" value={status?.active_actions ?? 0} icon={<ToolOutlined />} />
            </Col>
          </Row>

          <Tabs
            className="workspace-tabs"
            activeKey={activeMenu}
            onChange={setActiveMenu}
            items={[
              {
                key: "dashboard",
                label: "操作台",
                children: (
                  <Row gutter={[16, 16]}>
                    <Col xs={24} xl={12}>
                      <Card title="安全演练">
                        <Space wrap>
                          <Button id="testSafeBtn" icon={<CheckCircleOutlined />} onClick={testSafe}>测试安全请求</Button>
                          <Button id="testAttackBtn" danger icon={<StopOutlined />} onClick={testAttack}>测试快速拦截</Button>
                          <Button id="testAppealBtn" icon={<FileSearchOutlined />} onClick={testAppeal}>测试申诉</Button>
                          <Button id="testLlmBtn" icon={<ApiOutlined />} onClick={testLlmGateway}>测试模型网关</Button>
                        </Space>
                      </Card>
                    </Col>
                    <Col xs={24} xl={12}>
                      <Card title="运行摘要">
                        <Descriptions size="small" column={1}>
                          <Descriptions.Item label="可信代理">{display.trusted_proxy_zh || "-"}</Descriptions.Item>
                          <Descriptions.Item label="自动 IP 封禁">{display.auto_ip_ban_zh || "-"}</Descriptions.Item>
                          <Descriptions.Item label="API Key">{tagForBoolean(Boolean(gateway.api_key_configured), ["已配置", "未配置"])}</Descriptions.Item>
                          <Descriptions.Item label="代理">{tagForBoolean(Boolean(gateway.proxy_configured), ["已配置", "未配置"])}</Descriptions.Item>
                        </Descriptions>
                      </Card>
                    </Col>
                  </Row>
                ),
              },
              {
                key: "appeals",
                label: "申诉处理",
                children: (
                  <Card title="申诉审核">
                    <Space className="table-actions" wrap>
                      <Select
                        id="appealStatusSelect"
                        value={appealStatus}
                        onChange={(value) => {
                          setAppealStatus(value);
                          showAppeals(value);
                        }}
                        options={[
                          { value: "pending", label: "待处理" },
                          { value: "approved", label: "已通过" },
                          { value: "rejected", label: "已驳回" },
                          { value: "all", label: "全部" },
                        ]}
                        style={{ width: 128 }}
                      />
                      <Button id="appealsBtn" icon={<ReloadOutlined />} onClick={() => showAppeals(appealStatus)}>刷新申诉</Button>
                    </Space>
                    <Table
                      rowKey="punishment_id"
                      columns={appealColumns}
                      dataSource={appeals}
                      pagination={{ pageSize: 5 }}
                      onRow={(record) => ({
                        className: "clickable-row",
                        onClick: () => appealForm.setFieldsValue({ punishment_id: record.punishment_id }),
                      })}
                    />
                    <Form form={appealForm} layout="inline" className="review-form">
                      <Form.Item label="处罚编号" name="punishment_id">
                        <Input id="appealIdInput" autoComplete="off" />
                      </Form.Item>
                      <Form.Item label="审核备注" name="admin_note">
                        <Input id="appealNoteInput" autoComplete="off" />
                      </Form.Item>
                      <Form.Item>
                        <Space>
                          <Popconfirm
                            title="确认通过申诉"
                            description="通过后该申诉会写入审核结果，并从待处理队列移除。"
                            okText="确认通过"
                            cancelText="取消"
                            onConfirm={() => reviewAppeal("approved")}
                            disabled={writeLocked}
                          >
                            <Button id="approveAppealBtn" type="primary" disabled={writeLocked}>通过</Button>
                          </Popconfirm>
                          <Popconfirm
                            title="确认驳回申诉"
                            description="驳回后该申诉会写入审核结果，并从待处理队列移除。"
                            okText="确认驳回"
                            cancelText="取消"
                            onConfirm={() => reviewAppeal("rejected")}
                            disabled={writeLocked}
                          >
                            <Button id="rejectAppealBtn" danger disabled={writeLocked}>驳回</Button>
                          </Popconfirm>
                        </Space>
                      </Form.Item>
                    </Form>
                  </Card>
                ),
              },
              {
                key: "actions",
                label: "动作管理",
                children: (
                  <Card title="动作撤销">
                    <Space className="table-actions" wrap>
                      <Select
                        id="actionStatusSelect"
                        value={actionStatus}
                        onChange={(value) => {
                          setActionStatus(value);
                          showActions(value);
                        }}
                        options={[
                          { value: "active", label: "活跃" },
                          { value: "revoked", label: "已撤销" },
                          { value: "expired", label: "已过期" },
                          { value: "all", label: "全部" },
                        ]}
                        style={{ width: 128 }}
                      />
                      <Button id="actionsBtn" icon={<ReloadOutlined />} onClick={() => showActions(actionStatus)}>刷新动作</Button>
                      <Popconfirm
                        title="确认清理过期动作"
                        description="清理只更新 ATEE 动作记录状态，不修改业务数据库。"
                        okText="确认清理"
                        cancelText="取消"
                        onConfirm={cleanupActions}
                        disabled={writeLocked}
                      >
                        <Button id="cleanupActionsBtn" icon={<ToolOutlined />} disabled={writeLocked}>清理过期动作</Button>
                      </Popconfirm>
                    </Space>
                    <Table
                      rowKey="id"
                      columns={actionColumns}
                      dataSource={actions}
                      pagination={{ pageSize: 5 }}
                      onRow={(record) => ({
                        className: "clickable-row",
                        onClick: () => actionForm.setFieldsValue({ action_id: record.id }),
                      })}
                    />
                    <Form form={actionForm} layout="inline" className="review-form">
                      <Form.Item label="动作编号" name="action_id">
                        <Input id="actionIdInput" inputMode="numeric" autoComplete="off" />
                      </Form.Item>
                      <Form.Item label="撤销原因" name="reason">
                        <Input id="revokeReasonInput" autoComplete="off" />
                      </Form.Item>
                      <Form.Item>
                        <Popconfirm
                          title="确认撤销动作"
                          description="撤销只更新 ATEE 动作记录，不直接回滚业务系统数据。"
                          okText="确认撤销"
                          cancelText="取消"
                          onConfirm={revokeAction}
                          disabled={writeLocked}
                        >
                          <Button id="revokeActionBtn" danger disabled={writeLocked}>撤销</Button>
                        </Popconfirm>
                      </Form.Item>
                    </Form>
                  </Card>
                ),
              },
              {
                key: "ledger",
                label: "安全账本",
                children: (
                  <Card title="最近账本">
                    <Space className="table-actions" wrap>
                      <InputNumber id="ledgerLimitInput" min={1} max={100} value={ledgerLimit} onChange={(value) => setLedgerLimit(value || 10)} />
                      <Button id="ledgerBtn" icon={<DatabaseOutlined />} onClick={showLedger}>读取账本</Button>
                    </Space>
                    <Table rowKey="id" columns={ledgerColumns} dataSource={ledgerRecords} pagination={{ pageSize: 5 }} />
                  </Card>
                ),
              },
              {
                key: "config",
                label: "网关配置",
                children: (
                  <Row gutter={[16, 16]}>
                    <Col xs={24} xl={16}>
                      <Card title="运行配置">
                        <Form form={configForm} layout="vertical">
                          <Row gutter={12}>
                            <Col xs={24} md={8}>
                              <Form.Item label="显示语言" name="locale" extra={GATEWAY_HELP.locale}>
                                <Select
                                  id="localeSelect"
                                  options={[
                                    { value: "zh-CN", label: "中文（简体）" },
                                    { value: "en-US", label: "English" },
                                  ]}
                                />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                              <Form.Item label="运行模式" name="runtime_mode" extra={GATEWAY_HELP.runtime_mode}>
                                <Select
                                  id="configModeSelect"
                                  options={[
                                    { value: "observe", label: "观察模式" },
                                    { value: "auto", label: "自动模式" },
                                    { value: "degraded", label: "降级模式" },
                                    { value: "read_only", label: "只读模式" },
                                  ]}
                                />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                              <Form.Item label="Agent 暂停" name="agent_paused" valuePropName="checked" extra={GATEWAY_HELP.agent_paused}>
                                <Switch id="agentPausedSwitch" />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                              <Form.Item label="自动 IP 封禁" name="auto_ip_ban_enabled" valuePropName="checked" extra={GATEWAY_HELP.auto_ip_ban_enabled}>
                                <Switch id="autoIpBanSwitch" />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                              <Form.Item label="管理接口认证" name="admin_auth_enabled" valuePropName="checked" extra={GATEWAY_HELP.admin_auth_enabled}>
                                <Switch id="adminAuthSwitch" />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                              <Form.Item label="每日预算（cent，0 不限）" name="llm_daily_budget_cents" extra={GATEWAY_HELP.llm_daily_budget_cents}>
                                <InputNumber id="dailyBudgetInput" min={0} max={1000000} />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                              <Form.Item label="Admin Token 环境变量" name="admin_token_env" extra={GATEWAY_HELP.admin_token_env}>
                                <Input id="adminTokenEnvInput" autoComplete="off" />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                              <Form.Item label="新 Admin Token 文件路径（留空不变）" name="new_admin_token_file" extra={GATEWAY_HELP.new_admin_token_file}>
                                <Input.Password id="adminTokenFileInput" autoComplete="off" visibilityToggle={false} placeholder={SECRET_PLACEHOLDER} />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                              <Form.Item label="本地预检 ms" name="local_precheck_ms" extra={GATEWAY_HELP.local_precheck_ms}>
                                <InputNumber id="localPrecheckInput" min={1} max={60000} />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                              <Form.Item label="远程软超时 ms" name="remote_soft_timeout_ms" extra={GATEWAY_HELP.remote_soft_timeout_ms}>
                                <InputNumber id="softTimeoutInput" min={1} max={120000} />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                              <Form.Item label="远程硬超时 ms" name="remote_hard_timeout_ms" extra={GATEWAY_HELP.remote_hard_timeout_ms}>
                                <InputNumber id="hardTimeoutInput" min={1} max={120000} />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                              <Form.Item label="模型模式" name="llm_mode" extra={GATEWAY_HELP.llm_mode}>
                                <Select
                                  id="llmModeSelect"
                                  options={[
                                    { value: "mock", label: "Mock" },
                                    { value: "openai_compatible", label: "OpenAI-compatible" },
                                    { value: "remote", label: "Remote" },
                                    { value: "disabled", label: "Disabled" },
                                  ]}
                                />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                              <Form.Item label="供应商" name="llm_provider" extra={GATEWAY_HELP.llm_provider}>
                                <Input id="llmProviderInput" autoComplete="off" />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                              <Form.Item label="模型名" name="llm_model" extra={GATEWAY_HELP.llm_model}>
                                <Input id="llmModelInput" autoComplete="off" />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                              <Form.Item label="新 API Base（留空不变）" name="new_llm_api_base" extra={GATEWAY_HELP.new_llm_api_base}>
                                <Input.Password id="llmApiBaseInput" autoComplete="off" visibilityToggle={false} placeholder={SECRET_PLACEHOLDER} />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                              <Form.Item label="API Key 环境变量" name="llm_api_key_env" extra={GATEWAY_HELP.llm_api_key_env}>
                                <Input id="llmApiKeyEnvInput" autoComplete="off" />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                              <Form.Item label="OpenAI API Key（保存为环境变量）" name="llm_api_key_value" extra={GATEWAY_HELP.llm_api_key_value}>
                                <Input.Password id="llmApiKeyValueInput" autoComplete="off" visibilityToggle={false} placeholder={SECRET_PLACEHOLDER} />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                              <Form.Item label="新密钥文件路径（留空不变）" name="new_llm_api_key_file" extra={GATEWAY_HELP.new_llm_api_key_file}>
                                <Input.Password id="llmApiKeyFileInput" autoComplete="off" visibilityToggle={false} placeholder={SECRET_PLACEHOLDER} />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                              <Form.Item label="新代理 URL（留空不变）" name="new_llm_proxy_url" extra={GATEWAY_HELP.new_llm_proxy_url}>
                                <Input.Password id="llmProxyUrlInput" autoComplete="off" visibilityToggle={false} placeholder={SECRET_PLACEHOLDER} />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                              <Form.Item label="SQLite 路径" name="ledger_sqlite_path" extra={GATEWAY_HELP.ledger_sqlite_path}>
                                <Input id="ledgerPathInput" autoComplete="off" />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                              <Form.Item label="账本上限 bytes" name="ledger_max_bytes" extra={GATEWAY_HELP.ledger_max_bytes}>
                                <InputNumber id="ledgerMaxBytesInput" min={1048576} max={1073741824} />
                              </Form.Item>
                            </Col>
                            <Col xs={24}>
                              <Form.Item label="可信代理 CIDR" name="trusted_proxy_cidrs" extra={GATEWAY_HELP.trusted_proxy_cidrs}>
                                <Input.TextArea id="trustedProxyInput" autoSize={{ minRows: 2, maxRows: 5 }} />
                              </Form.Item>
                            </Col>
                            <Col xs={24}>
                              <Form.Item label="申诉入口路径" name="appeal_paths" extra={GATEWAY_HELP.appeal_paths}>
                                <Input.TextArea id="appealPathsInput" autoSize={{ minRows: 2, maxRows: 5 }} />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                              <Form.Item label="紧急旁路启用" name="bypass_enabled" valuePropName="checked" extra={GATEWAY_HELP.bypass_enabled}>
                                <Switch id="bypassEnabledSwitch" />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={16}>
                              <Form.Item label="旁路密钥文件" name="bypass_key_file" extra={GATEWAY_HELP.bypass_key_file}>
                                <Input.Password id="bypassKeyFileInput" autoComplete="off" visibilityToggle={false} />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Space wrap>
                            <Button id="configBtn" icon={<ApiOutlined />} onClick={showConfig}>读取配置</Button>
                            <Popconfirm
                              title="确认保存运行配置"
                              description="保存后会立即影响 Core Service 的运行模式、模型网关或预算等配置。"
                              okText="确认保存"
                              cancelText="取消"
                              onConfirm={saveConfig}
                              disabled={writeLocked}
                            >
                              <Button id="configSaveBtn" type="primary" icon={<CheckCircleOutlined />} disabled={writeLocked}>保存配置</Button>
                            </Popconfirm>
                            <Button id="testLlmConfigBtn" icon={<ApiOutlined />} onClick={testLlmGateway}>测试模型网关</Button>
                          </Space>
                        </Form>
                      </Card>
                    </Col>
                    <Col xs={24} xl={8}>
                      <Card title="紧急旁路">
                        <Descriptions size="small" column={1}>
                          <Descriptions.Item label="API Base">{tagForBoolean(Boolean(status?.config?.llm_api_base_configured), ["已配置", "未配置"])}</Descriptions.Item>
                          <Descriptions.Item label="API Key 环境变量">{tagForBoolean(Boolean(status?.config?.llm_api_key_env_configured), ["已写入", "未写入"])}</Descriptions.Item>
                          <Descriptions.Item label="API Key 文件">{tagForBoolean(Boolean(status?.config?.llm_api_key_file_configured), ["已配置", "未配置"])}</Descriptions.Item>
                          <Descriptions.Item label="模型代理">{tagForBoolean(Boolean(status?.config?.llm_proxy_configured), ["已配置", "未配置"])}</Descriptions.Item>
                          <Descriptions.Item label="旁路启用">{tagForBoolean(Boolean(status?.config?.bypass_enabled), ["已启用", "未启用"])}</Descriptions.Item>
                          <Descriptions.Item label="密钥文件">{tagForBoolean(Boolean(status?.config?.bypass_key_file), ["已配置", "未配置"])}</Descriptions.Item>
                        </Descriptions>
                        <Form form={breakGlassForm} layout="vertical" className="review-form">
                          <Form.Item label="X-ATEE-Bypass Header" name="bypass_header">
                            <Input.Password id="breakGlassHeaderInput" autoComplete="off" visibilityToggle={false} />
                          </Form.Item>
                          <Button id="breakGlassBtn" icon={<SafetyCertificateOutlined />} onClick={breakGlass}>验证旁路状态</Button>
                        </Form>
                      </Card>
                    </Col>
                  </Row>
                ),
              },
              {
                key: "guide",
                label: "新手引导",
                children: (
                  <Card title="新手引导">
                    <List
                      id="guideList"
                      grid={{ gutter: 16, xs: 1, sm: 1, md: 2, xl: 3 }}
                      dataSource={guideSteps}
                      renderItem={(item) => (
                        <List.Item>
                          <Card size="small" title={item.title_zh}>
                            <Text>{item.plain_text_zh}</Text>
                            <div className="guide-meta">推荐：{item.recommended_default_zh}</div>
                            <div className="guide-meta">风险：{item.risk_zh}</div>
                          </Card>
                        </List.Item>
                      )}
                    />
                  </Card>
                ),
              },
            ]}
          />

          <Row gutter={[16, 16]} className="json-row">
            <Col xs={24} xl={12}>
              <Card title="运行状态摘要" className="summary-card">
                <RuntimeSummary status={status} />
                <details className="json-details">
                  <summary>原始 JSON</summary>
                  <pre id="output" aria-live="polite">{pretty(output)}</pre>
                </details>
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card title="操作结果摘要" className="summary-card">
                <OperationSummary result={result} />
                <details className="json-details">
                  <summary>原始 JSON</summary>
                  <pre id="result" aria-live="polite">{pretty(result)}</pre>
                </details>
              </Card>
            </Col>
          </Row>
        </Content>
      </Layout>
    </Layout>
  );
}

createRoot(document.getElementById("root")).render(
  <ConfigProvider
    locale={zhCN}
    csp={{ nonce: runtimeCspNonce }}
    wave={{ disabled: true }}
    theme={{
      algorithm: theme.defaultAlgorithm,
      token: {
        colorPrimary: "#2563eb",
        colorSuccess: "#138a48",
        colorWarning: "#b7791f",
        colorError: "#c2410c",
        borderRadius: 6,
        fontFamily: 'Arial, "Microsoft YaHei", sans-serif',
      },
    }}
  >
    <App />
  </ConfigProvider>,
);

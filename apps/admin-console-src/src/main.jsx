import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Alert,
  ConfigProvider,
  Form,
  Space,
  Tag,
  theme,
} from "antd";
import zhCN from "antd/locale/zh_CN";
import {
  ApiOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  KeyOutlined,
  MessageOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  ToolOutlined,
  UserOutlined,
} from "@ant-design/icons";
import "antd/dist/reset.css";
import "./styles.css";
import {
  AgentTab,
  GuideTab,
} from "./adminAgentGuide.jsx";
import {
  DashboardMetrics,
  DashboardTab,
  JsonSummaryRow,
} from "./adminDashboard.jsx";
import {
  GothicConsoleShell,
  GothicPageFrame,
} from "./adminGothicShell.jsx";
import {
  GatewayConfigTab,
  LedgerTab,
} from "./adminLedgerConfig.jsx";
import {
  ActionsTab,
  AppealsTab,
  AsyncReviewsTab,
} from "./adminReviewQueues.jsx";
import {
  AdminAccountsTab,
  AdminLoginPanel,
  ApiKeysTab,
} from "./adminAccess.jsx";
import {
  apiRequest,
  cspNonce,
  installStyleNonce,
  readAdminId,
  readAdminToken,
  splitListInput,
  writeAdminId,
  writeAdminToken,
} from "./adminSupport.jsx";

const runtimeCspNonce = cspNonce();
installStyleNonce(runtimeCspNonce);

const PAGE_ARCHITECTURE_META = {
  dashboard: {
    domain: "Runtime Index / Status Constellation",
    endpoints: ["GET /v1/runtime/status"],
  },
  activity: {
    domain: "Drill / Result Domain",
    endpoints: ["POST /v1/check", "POST /v1/appeal", "GET /v1/admin/llm/test"],
  },
  agent: {
    domain: "Assistant / Context Domain",
    endpoints: ["POST /v1/admin/agent/chat"],
  },
  guide: {
    domain: "Onboarding / Preflight Domain",
    endpoints: [
      "GET /v1/onboarding/steps",
      "GET /v1/admin/preflight",
      "POST /v1/admin/integration/plan",
      "POST /v1/admin/security-flow/run",
    ],
  },
  admins: {
    domain: "Access Control Domain",
    endpoints: ["GET /v1/admin/accounts", "POST /v1/admin/accounts"],
  },
  apiKeys: {
    domain: "Key Material / Invocation Domain",
    endpoints: ["GET /v1/admin/api-keys", "POST /v1/admin/api-keys", "DELETE /v1/admin/api-keys/{id}"],
  },
  appeals: {
    domain: "User Appeal Domain",
    endpoints: ["GET /v1/admin/appeals?status=", "POST /v1/admin/appeals/review"],
  },
  asyncReviews: {
    domain: "Queue / Manual Disposition Domain",
    endpoints: ["GET /v1/admin/async-reviews?status=", "POST /v1/admin/async-reviews/run"],
  },
  actions: {
    domain: "Action Lifecycle Domain",
    endpoints: ["GET /v1/admin/actions?status=", "POST /v1/admin/actions/revoke"],
  },
  ledger: {
    domain: "Audit Ledger Domain",
    endpoints: ["GET /v1/admin/ledger/recent?limit=&details=1"],
  },
  config: {
    domain: "Gateway Configuration Domain",
    endpoints: ["GET /v1/admin/config", "POST /v1/admin/config", "POST /v1/admin/break-glass/status"],
  },
};

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
  const [asyncReviews, setAsyncReviews] = useState([]);
  const [appealStatus, setAppealStatus] = useState("pending");
  const [actionStatus, setActionStatus] = useState("active");
  const [asyncReviewStatus, setAsyncReviewStatus] = useState("pending");
  const [ledgerLimit, setLedgerLimit] = useState(10);
  const [adminToken, setAdminToken] = useState(readAdminToken());
  const [adminId, setAdminId] = useState(readAdminId());
  const [authRequired, setAuthRequired] = useState(false);
  const [captcha, setCaptcha] = useState(null);
  const [adminAccounts, setAdminAccounts] = useState([]);
  const [apiKeys, setApiKeys] = useState([]);
  const [createdApiKey, setCreatedApiKey] = useState(null);
  const [siteType, setSiteType] = useState("通用网站");
  const [adapterType, setAdapterType] = useState("HTTP API");
  const [preflightReport, setPreflightReport] = useState(null);
  const [securityFlowReport, setSecurityFlowReport] = useState(null);
  const [integrationPlan, setIntegrationPlan] = useState(null);
  const [chatDraft, setChatDraft] = useState("");
  const [chatMessages, setChatMessages] = useState([
    {
      role: "assistant",
      content: "我是 ATEE Agent 助手。你可以问我如何接入网站、配置模型网关、处理攻击、申诉或紧急恢复。",
    },
  ]);
  const [appealForm] = Form.useForm();
  const [actionForm] = Form.useForm();
  const [manualReviewForm] = Form.useForm();
  const [configForm] = Form.useForm();
  const [breakGlassForm] = Form.useForm();
  const [loginForm] = Form.useForm();
  const [createAdminForm] = Form.useForm();
  const [passwordForm] = Form.useForm();
  const [apiKeyForm] = Form.useForm();
  const [integrationForm] = Form.useForm();

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
      async_review_worker_enabled: Boolean(config.async_review_worker_enabled),
      async_review_worker_interval_seconds: Number(config.async_review_worker_interval_seconds ?? 5),
      async_review_worker_batch_size: Number(config.async_review_worker_batch_size ?? 5),
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

  async function runPreflight() {
    await run("environment-preflight", async () => {
      const { data } = await apiRequest("/v1/admin/preflight");
      setPreflightReport(data);
      await refresh();
      return data;
    });
  }

  async function runSecurityFlow() {
    await run("security-flow", async () => {
      const { data } = await apiRequest("/v1/admin/security-flow/run", {
        method: "POST",
        body: "{}",
      });
      setSecurityFlowReport(data);
      await refresh();
      return data;
    });
  }

  async function generateIntegrationPlan() {
    await run("integration-plan", async () => {
      const values = integrationForm.getFieldsValue();
      const { data } = await apiRequest("/v1/admin/integration/plan", {
        method: "POST",
        body: JSON.stringify({
          site_name: values.site_name,
          site_url: values.site_url,
          site_type: siteType,
          adapter_type: adapterType,
          core_url: values.core_url,
          appeal_path: values.appeal_path,
          protected_features: splitListInput(values.protected_features),
        }),
      });
      setIntegrationPlan(data);
      await refresh();
      return data;
    });
  }

  async function sendAgentChat() {
    const message = String(chatDraft || "").trim();
    if (!message) {
      return;
    }
    setChatDraft("");
    setChatMessages((items) => [...items, { role: "user", content: message }]);
    await run("agent-chat", async () => {
      const { data } = await apiRequest("/v1/admin/agent/chat", {
        method: "POST",
        body: JSON.stringify({
          message,
          site_type: siteType,
          adapter_type: adapterType,
        }),
      });
      setChatMessages((items) => [
        ...items,
        {
          role: "assistant",
          content: data.reply_zh || data.display?.message_zh || "Agent 当前没有返回可展示内容。",
        },
      ]);
      await refresh();
      return data;
    });
  }

  function focusControl(elementId) {
    window.setTimeout(() => {
      const element = document.getElementById(elementId);
      if (!element) {
        return;
      }
      const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
      element.scrollIntoView({ block: "center", behavior: reduceMotion ? "auto" : "smooth" });
      element.focus?.();
    }, 80);
  }

  async function runGuideAction(stepId) {
    if (stepId === "environment") {
      await runPreflight();
      focusControl("preflightChecks");
    } else if (stepId === "site_type") {
      setChatDraft(`请根据“${siteType}”网站类型，给我一份 ATEE 初次接入和安全关注点清单。`);
      setActiveMenu("agent");
      focusControl("siteTypeSelect");
    } else if (stepId === "adapter") {
      setChatDraft(`我计划使用“${adapterType}”接入 ATEE，请给我最小上线步骤、风险点和验证命令。`);
      setActiveMenu("agent");
      focusControl("adapterTypeSelect");
    } else if (stepId === "trusted_proxy") {
      setActiveMenu("config");
      focusControl("trustedProxyInput");
    } else if (stepId === "ai_api") {
      setActiveMenu("config");
      focusControl("llmApiBaseInput");
    } else if (stepId === "break_glass") {
      setActiveMenu("config");
      focusControl("bypassKeyFileInput");
    } else if (stepId === "appeal") {
      setActiveMenu("appeals");
      focusControl("appealsBtn");
    } else {
      setActiveMenu("dashboard");
      focusControl("testSafeBtn");
    }
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

  async function loadCaptcha() {
    await run("admin-captcha", async () => {
      const { data } = await apiRequest("/v1/auth/captcha");
      setCaptcha(data.ok ? data : null);
      return data;
    });
  }

  async function loginAdmin() {
    await run("admin-login", async () => {
      const values = loginForm.getFieldsValue();
      const { data } = await apiRequest("/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: String(values.username || "").trim(),
          password: String(values.password || ""),
          captcha_id: captcha?.captcha_id || "",
          captcha_answer: String(values.captcha_answer || "").trim(),
        }),
      });
      if (data.ok && data.token) {
        writeAdminToken(data.token);
        writeAdminId(data.username || values.username || "");
        setAdminToken(data.token);
        setAdminId(data.username || values.username || "");
        setAuthRequired(false);
        setCaptcha(null);
        loginForm.setFieldsValue({ password: "", captcha_answer: "" });
        await refresh();
      }
      return data;
    });
  }

  async function registerAdmin() {
    await run("admin-register", async () => {
      const values = loginForm.getFieldsValue();
      const { data } = await apiRequest("/v1/auth/register", {
        method: "POST",
        body: JSON.stringify({
          username: String(values.username || "").trim(),
          password: String(values.password || ""),
          captcha_id: captcha?.captcha_id || "",
          captcha_answer: String(values.captcha_answer || "").trim(),
        }),
      });
      if (data.ok) {
        setCaptcha(null);
        loginForm.setFieldsValue({ password: "", captcha_answer: "" });
        await refresh();
      }
      return data;
    });
  }

  async function showAdminAccounts() {
    await run("admin-accounts", async () => {
      const { data } = await apiRequest("/v1/admin/accounts");
      setAdminAccounts(data.admins || []);
      await refresh();
      return data;
    });
  }

  async function createAdminAccount() {
    await run("create-admin-account", async () => {
      const values = createAdminForm.getFieldsValue();
      const { data } = await apiRequest("/v1/admin/accounts", {
        method: "POST",
        body: JSON.stringify({
          username: String(values.username || "").trim(),
          password: String(values.password || ""),
        }),
      });
      if (data.ok) {
        createAdminForm.resetFields();
        await showAdminAccounts();
      }
      return data;
    });
  }

  async function changeAdminPassword() {
    await run("change-admin-password", async () => {
      const values = passwordForm.getFieldsValue();
      const { data } = await apiRequest("/v1/admin/accounts/password", {
        method: "POST",
        body: JSON.stringify({
          username: String(values.username || "").trim(),
          old_password: String(values.old_password || ""),
          new_password: String(values.new_password || ""),
        }),
      });
      if (data.ok) {
        passwordForm.resetFields();
      }
      return data;
    });
  }

  async function showApiKeys() {
    await run("api-keys", async () => {
      const { data } = await apiRequest("/v1/admin/api-keys");
      setApiKeys(data.keys || []);
      await refresh();
      return data;
    });
  }

  async function createApiKey() {
    await run("create-api-key", async () => {
      const values = apiKeyForm.getFieldsValue();
      const { data } = await apiRequest("/v1/admin/api-keys", {
        method: "POST",
        body: JSON.stringify({
          name: String(values.name || "").trim(),
          scope: values.scope || "backend",
          env_name: String(values.env_name || "").trim(),
          key_value: String(values.key_value || "").trim(),
          activate_provider_key: Boolean(values.activate_provider_key),
        }),
      });
      if (data.ok) {
        setCreatedApiKey(data);
        apiKeyForm.resetFields();
        apiKeyForm.setFieldsValue({ scope: "backend", activate_provider_key: true });
        await showApiKeys();
      }
      return data;
    });
  }

  async function deleteApiKey(keyId) {
    await run("delete-api-key", async () => {
      const { data } = await apiRequest(`/v1/admin/api-keys/${keyId}`, { method: "DELETE" });
      await showApiKeys();
      return data;
    });
  }

  async function showLedger() {
    await run("ledger", async () => {
      const limit = Number(ledgerLimit) || 10;
      const { data } = await apiRequest(`/v1/admin/ledger/recent?limit=${limit}&details=1`);
      setLedgerRecords(data.records || []);
      await refresh();
      return {
        ok: data.ok,
        ledger_count: (data.records || []).length,
        display: data.display,
      };
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

  async function showAsyncReviews(statusFilter = asyncReviewStatus) {
    await run("async-reviews", async () => {
      const { data } = await apiRequest(`/v1/admin/async-reviews?status=${encodeURIComponent(statusFilter)}`);
      setAsyncReviews(data.jobs || []);
      await refresh();
      return data;
    });
  }

  async function runAsyncReviews() {
    await run("run-async-reviews", async () => {
      const { data } = await apiRequest("/v1/admin/async-reviews/run", {
        method: "POST",
        body: JSON.stringify({ limit: 10 }),
      });
      const { data: listData } = await apiRequest(`/v1/admin/async-reviews?status=${encodeURIComponent(asyncReviewStatus)}`);
      setAsyncReviews(listData.jobs || []);
      await refresh();
      return data;
    });
  }

  async function manualFeatureBan() {
    await run("manual-feature-ban", async () => {
      const values = manualReviewForm.getFieldsValue();
      const { data } = await apiRequest("/v1/admin/async-reviews/manual-action", {
        method: "POST",
        body: JSON.stringify({
          job_id: Number(values.job_id),
          user_hash: String(values.user_hash || "").trim(),
          feature_scope: String(values.feature_scope || "").trim(),
          duration_seconds: Number(values.duration_seconds || 3600),
          admin_note: String(values.admin_note || "").trim(),
        }),
      });
      const { data: listData } = await apiRequest(`/v1/admin/async-reviews?status=${encodeURIComponent(asyncReviewStatus)}`);
      setAsyncReviews(listData.jobs || []);
      await showActions(actionStatus);
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
        async_review_worker_enabled: Boolean(values.async_review_worker_enabled),
        async_review_worker_interval_seconds: Number(values.async_review_worker_interval_seconds),
        async_review_worker_batch_size: Number(values.async_review_worker_batch_size),
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
      { key: "activity", icon: <ThunderboltOutlined />, label: "活动页" },
      { key: "agent", icon: <MessageOutlined />, label: "Agent 对话" },
      { key: "guide", icon: <CheckCircleOutlined />, label: "新手引导" },
      { key: "admins", icon: <UserOutlined />, label: "管理员账号" },
      { key: "apiKeys", icon: <KeyOutlined />, label: "API keys" },
      { key: "appeals", icon: <FileSearchOutlined />, label: "申诉处理" },
      { key: "asyncReviews", icon: <BranchesOutlined />, label: "异步 AI 审查" },
      { key: "actions", icon: <ToolOutlined />, label: "动作管理" },
      { key: "ledger", icon: <SafetyCertificateOutlined />, label: "安全账本" },
      { key: "config", icon: <ApiOutlined />, label: "网关配置" },
    ],
    [],
  );
  const activeMenuLabel = menuItems.find((item) => item.key === activeMenu)?.label || "仪表盘";
  const pageFrameTitle = (pageKey) => menuItems.find((item) => item.key === pageKey)?.label || pageKey;
  const pageFrame = (pageKey, content) => (
    <GothicPageFrame pageKey={pageKey} title={pageFrameTitle(pageKey)} {...PAGE_ARCHITECTURE_META[pageKey]}>
      {content}
    </GothicPageFrame>
  );

  function renderActivePage() {
    if (activeMenu === "dashboard") {
      return pageFrame(
        "dashboard",
        <DashboardMetrics
          status={status}
          display={display}
          gateway={gateway}
          gatewayConfigured={gatewayConfigured}
          circuit={circuit}
          budget={budget}
        />,
      );
    }
    if (activeMenu === "activity") {
      return pageFrame("activity", (
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <DashboardTab
            display={display}
            gateway={gateway}
            testSafe={testSafe}
            testAttack={testAttack}
            testAppeal={testAppeal}
            testLlmGateway={testLlmGateway}
          />
          <JsonSummaryRow status={status} output={output} result={result} />
        </Space>
      ));
    }
    if (activeMenu === "agent") {
      return pageFrame("agent", (
        <AgentTab
          siteType={siteType}
          setSiteType={setSiteType}
          adapterType={adapterType}
          setAdapterType={setAdapterType}
          chatMessages={chatMessages}
          chatDraft={chatDraft}
          setChatDraft={setChatDraft}
          sendAgentChat={sendAgentChat}
          loading={loading}
        />
      ));
    }
    if (activeMenu === "guide") {
      return pageFrame("guide", (
        <GuideTab
          siteType={siteType}
          setSiteType={setSiteType}
          adapterType={adapterType}
          setAdapterType={setAdapterType}
          runPreflight={runPreflight}
          preflightReport={preflightReport}
          runSecurityFlow={runSecurityFlow}
          securityFlowReport={securityFlowReport}
          integrationForm={integrationForm}
          integrationPlan={integrationPlan}
          generateIntegrationPlan={generateIntegrationPlan}
          guideSteps={guideSteps}
          runGuideAction={runGuideAction}
          loading={loading}
          writeLocked={writeLocked}
        />
      ));
    }
    if (activeMenu === "admins") {
      return pageFrame("admins", (
        <AdminAccountsTab
          adminAccounts={adminAccounts}
          showAdminAccounts={showAdminAccounts}
          createAdminForm={createAdminForm}
          createAdminAccount={createAdminAccount}
          passwordForm={passwordForm}
          changeAdminPassword={changeAdminPassword}
          writeLocked={writeLocked}
        />
      ));
    }
    if (activeMenu === "apiKeys") {
      return pageFrame("apiKeys", (
        <ApiKeysTab
          apiKeys={apiKeys}
          showApiKeys={showApiKeys}
          apiKeyForm={apiKeyForm}
          createApiKey={createApiKey}
          deleteApiKey={deleteApiKey}
          createdApiKey={createdApiKey}
          clearCreatedApiKey={() => setCreatedApiKey(null)}
          writeLocked={writeLocked}
        />
      ));
    }
    if (activeMenu === "appeals") {
      return pageFrame("appeals", (
        <AppealsTab
          appealStatus={appealStatus}
          setAppealStatus={setAppealStatus}
          showAppeals={showAppeals}
          appealColumns={appealColumns}
          appeals={appeals}
          appealForm={appealForm}
          reviewAppeal={reviewAppeal}
          writeLocked={writeLocked}
        />
      ));
    }
    if (activeMenu === "actions") {
      return pageFrame("actions", (
        <ActionsTab
          actionStatus={actionStatus}
          setActionStatus={setActionStatus}
          showActions={showActions}
          actionColumns={actionColumns}
          actions={actions}
          actionForm={actionForm}
          cleanupActions={cleanupActions}
          revokeAction={revokeAction}
          writeLocked={writeLocked}
        />
      ));
    }
    if (activeMenu === "asyncReviews") {
      return pageFrame("asyncReviews", (
        <AsyncReviewsTab
          asyncReviewStatus={asyncReviewStatus}
          setAsyncReviewStatus={setAsyncReviewStatus}
          showAsyncReviews={showAsyncReviews}
          asyncReviewColumns={asyncReviewColumns}
          asyncReviews={asyncReviews}
          manualReviewForm={manualReviewForm}
          manualFeatureBan={manualFeatureBan}
          runAsyncReviews={runAsyncReviews}
          writeLocked={writeLocked}
        />
      ));
    }
    if (activeMenu === "ledger") {
      return pageFrame("ledger", (
        <LedgerTab
          ledgerLimit={ledgerLimit}
          setLedgerLimit={setLedgerLimit}
          showLedger={showLedger}
          ledgerColumns={ledgerColumns}
          ledgerRecords={ledgerRecords}
        />
      ));
    }
    if (activeMenu === "config") {
      return pageFrame("config", (
        <GatewayConfigTab
          configForm={configForm}
          showConfig={showConfig}
          saveConfig={saveConfig}
          testLlmGateway={testLlmGateway}
          writeLocked={writeLocked}
          status={status}
          breakGlassForm={breakGlassForm}
          breakGlass={breakGlass}
        />
      ));
    }
    return null;
  }

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
    { title: "目标", key: "target", render: (_, record) => record.target_scope?.feature || record.target_scope?.type || "-" },
    { title: "原因", dataIndex: "reason", key: "reason", ellipsis: true },
    { title: "过期时间", dataIndex: "expires_at", key: "expires_at" },
  ];

  const asyncReviewColumns = [
    { title: "ID", dataIndex: "id", key: "id", width: 80 },
    { title: "状态", dataIndex: "status", key: "status", render: (value) => <Tag>{value}</Tag> },
    { title: "尝试", key: "attempts", render: (_, record) => `${record.attempts}/${record.max_attempts}` },
    { title: "事件", dataIndex: "event_type", key: "event_type" },
    { title: "用户", dataIndex: "user_hash", key: "user_hash", ellipsis: true },
    { title: "功能", dataIndex: "feature_scope", key: "feature_scope", ellipsis: true },
    { title: "最近错误", dataIndex: "last_error", key: "last_error", ellipsis: true },
    { title: "更新时间", dataIndex: "updated_at", key: "updated_at" },
  ];

  const ledgerColumns = [
    { title: "ID", dataIndex: "id", key: "id", width: 80 },
    { title: "时间", dataIndex: "created_at", key: "created_at" },
    { title: "事件", dataIndex: "event_type", key: "event_type" },
    { title: "等级", dataIndex: "severity", key: "severity", render: (value) => <Tag>{value}</Tag> },
    { title: "动作", dataIndex: "action", key: "action" },
  ];

  return (
    <GothicConsoleShell
      activeMenu={activeMenu}
      activeMenuLabel={activeMenuLabel}
      menuItems={menuItems}
      setActiveMenu={setActiveMenu}
      status={status}
      display={display}
      gateway={gateway}
      budget={budget}
      circuit={circuit}
      loading={loading}
      onRefresh={() => run("refresh", refresh)}
      onSetMode={setMode}
      onPauseResume={pauseResume}
    >
          {activeMenu !== "dashboard" ? (
            <>
          {activeMenu === "guide" ? (
            <Alert
              className="top-alert"
              type="info"
              showIcon
              message="所有用户输入、Agent 输出和申诉理由都按纯文本渲染；管理台不保存原始 Prompt 或原始请求体。"
            />
          ) : null}
          <AdminLoginPanel
            adminAuth={adminAuth}
            adminId={adminId}
            setAdminId={setAdminId}
            adminToken={adminToken}
            setAdminToken={setAdminToken}
            captcha={captcha}
            loadCaptcha={loadCaptcha}
            loginForm={loginForm}
            loginAdmin={loginAdmin}
            registerAdmin={registerAdmin}
            saveAdminToken={saveAdminToken}
            clearAdminToken={clearAdminToken}
          />
          {authRequired ? (
            <Alert
              id="adminAuthAlert"
              className="guard-alert"
              type="error"
              showIcon
              message="管理接口需要有效登录会话，当前请求未被执行。"
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
            </>
          ) : null}

          <section key={activeMenu} className="page-transition-surface">
            {renderActivePage()}
          </section>


    </GothicConsoleShell>
  );
}

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Missing #root element for ATEE admin console");
}

createRoot(rootElement).render(
  <ConfigProvider
    locale={zhCN}
    csp={{ nonce: runtimeCspNonce }}
    wave={{ disabled: true }}
    theme={{
      algorithm: theme.defaultAlgorithm,
      token: {
        colorPrimary: "#e10600",
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

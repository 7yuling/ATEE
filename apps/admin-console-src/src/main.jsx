import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  ConfigProvider,
  Descriptions,
  Divider,
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
  BranchesOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  EyeOutlined,
  FileSearchOutlined,
  MessageOutlined,
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
import {
  ADAPTER_OPTIONS,
  GATEWAY_HELP,
  SECRET_PLACEHOLDER,
  SECURITY_FLOW_STEPS,
  SITE_TYPE_OPTIONS,
  LabelWithHelp,
  MetricCard,
  OperationSummary,
  PreflightSummary,
  RuntimeSummary,
  apiRequest,
  budgetLabel,
  cspNonce,
  installStyleNonce,
  modeLabel,
  pretty,
  providerLabel,
  readAdminId,
  readAdminToken,
  splitListInput,
  tagForBoolean,
  tagForNullableBoolean,
  writeAdminId,
  writeAdminToken,
} from "./adminSupport.jsx";

const { Header, Sider, Content } = Layout;
const { Title, Text } = Typography;
const { TextArea } = Input;

const runtimeCspNonce = cspNonce();
installStyleNonce(runtimeCspNonce);

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
  const [siteType, setSiteType] = useState("通用网站");
  const [adapterType, setAdapterType] = useState("HTTP API");
  const [preflightReport, setPreflightReport] = useState(null);
  const [chatDraft, setChatDraft] = useState("");
  const [chatMessages, setChatMessages] = useState([
    {
      role: "assistant",
      content: "我是 ATEE Agent 助手。你可以问我如何接入网站、配置模型网关、处理攻击、申诉或紧急恢复。",
    },
  ]);
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

  function runGuideAction(stepId) {
    if (stepId === "environment") {
      runPreflight();
    } else if (stepId === "site_type" || stepId === "adapter") {
      setActiveMenu("guide");
    } else if (stepId === "trusted_proxy" || stepId === "ai_api" || stepId === "break_glass") {
      setActiveMenu("config");
    } else if (stepId === "appeal") {
      setActiveMenu("appeals");
    } else {
      setActiveMenu("dashboard");
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

  async function showLedger() {
    await run("ledger", async () => {
      const limit = Number(ledgerLimit) || 10;
      const { data } = await apiRequest(`/v1/admin/ledger/recent?limit=${limit}`);
      setLedgerRecords(data.records || []);
      await refresh();
      return {
        ok: data.ok,
        ledger_count: (data.records || []).length,
        status: data.status,
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
      { key: "agent", icon: <MessageOutlined />, label: "Agent 对话" },
      { key: "guide", icon: <CheckCircleOutlined />, label: "新手引导" },
      { key: "appeals", icon: <FileSearchOutlined />, label: "申诉处理" },
      { key: "asyncReviews", icon: <BranchesOutlined />, label: "异步 AI 审查" },
      { key: "actions", icon: <ToolOutlined />, label: "动作管理" },
      { key: "ledger", icon: <SafetyCertificateOutlined />, label: "安全账本" },
      { key: "config", icon: <ApiOutlined />, label: "网关配置" },
    ],
    [],
  );
  const activeMenuLabel = menuItems.find((item) => item.key === activeMenu)?.label || "仪表盘";

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

  const asyncReviewColumns = [
    { title: "ID", dataIndex: "id", key: "id", width: 80 },
    { title: "状态", dataIndex: "status", key: "status", render: (value) => <Tag>{value}</Tag> },
    { title: "尝试", key: "attempts", render: (_, record) => `${record.attempts}/${record.max_attempts}` },
    { title: "事件", dataIndex: "event_type", key: "event_type" },
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
    <Layout className="atee-shell">
      <Sider width={216} className="atee-sider">
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
              {status ? `Core Service 已连接 · 当前页面：${activeMenuLabel}` : "正在连接"}
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
          <div className="workspace-heading">
            <Title level={4}>{activeMenuLabel}</Title>
            <Text type="secondary">左侧菜单和下方工作区同步切换，当前只显示该模块需要的操作。</Text>
          </div>
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

          {activeMenu === "dashboard" ? (
          <Row gutter={[12, 12]}>
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
              <MetricCard id="asyncReviewQueue" title="异步 AI 审查队列" value={status?.async_review?.queued ?? 0} icon={<BranchesOutlined />} />
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
          ) : null}

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
                key: "agent",
                label: "Agent 对话",
                children: (
                  <Row gutter={[16, 16]}>
                    <Col xs={24} xl={9}>
                      <Card title="对话上下文">
                        <Form layout="vertical">
                          <Form.Item label="网站类型">
                            <Select
                              id="siteTypeSelect"
                              value={siteType}
                              onChange={setSiteType}
                              options={SITE_TYPE_OPTIONS}
                            />
                          </Form.Item>
                          <Form.Item label="接入方式">
                            <Select
                              id="adapterTypeSelect"
                              value={adapterType}
                              onChange={setAdapterType}
                              options={ADAPTER_OPTIONS}
                            />
                          </Form.Item>
                          <Alert
                            type="info"
                            showIcon
                            message="Agent 会结合网站类型和接入方式给出建议；不要在对话中粘贴 API Key、Admin Token 或旁路密钥。"
                          />
                        </Form>
                      </Card>
                    </Col>
                    <Col xs={24} xl={15}>
                      <Card title="AI 安全助手">
                        <div id="agentChatWindow" className="chat-window">
                          {chatMessages.map((message, index) => (
                            <div key={`${message.role}-${index}`} className={`chat-bubble ${message.role}`}>
                              <Text strong>{message.role === "user" ? "你" : "ATEE Agent"}</Text>
                              <div>{message.content}</div>
                            </div>
                          ))}
                        </div>
                        <Space.Compact className="chat-input">
                          <TextArea
                            id="agentChatInput"
                            value={chatDraft}
                            onChange={(event) => setChatDraft(event.target.value)}
                            autoSize={{ minRows: 2, maxRows: 5 }}
                            placeholder="例如：我的网站接入了 Nginx 和 DeepSeek，怎样先做观察模式上线？"
                          />
                          <Button id="agentChatSendBtn" type="primary" icon={<MessageOutlined />} onClick={sendAgentChat} loading={loading}>
                            发送
                          </Button>
                        </Space.Compact>
                      </Card>
                    </Col>
                  </Row>
                ),
              },
              {
                key: "guide",
                label: "新手引导",
                children: (
                  <Row gutter={[16, 16]}>
                    <Col xs={24} xl={8}>
                      <Card title="基础选择">
                        <Form layout="vertical">
                          <Form.Item label="网站类型">
                            <Select
                              id="guideSiteTypeSelect"
                              value={siteType}
                              onChange={setSiteType}
                              options={SITE_TYPE_OPTIONS}
                            />
                          </Form.Item>
                          <Form.Item label="接入方式">
                            <Select
                              id="guideAdapterTypeSelect"
                              value={adapterType}
                              onChange={setAdapterType}
                              options={ADAPTER_OPTIONS}
                            />
                          </Form.Item>
                          <Button id="preflightBtn" icon={<DeploymentUnitOutlined />} onClick={runPreflight} loading={loading}>
                            运行环境预检
                          </Button>
                        </Form>
                        <Divider />
                        <PreflightSummary report={preflightReport} />
                      </Card>
                    </Col>
                    <Col xs={24} xl={16}>
                      <Card title="可操作引导">
                        <Collapse
                          id="guideList"
                          accordion
                          items={guideSteps.map((item) => ({
                            key: item.id,
                            label: item.title_zh,
                            children: (
                              <Space direction="vertical" size="small" className="guide-detail">
                                <Text>{item.plain_text_zh}</Text>
                                <Text type="secondary">推荐：{item.recommended_default_zh}</Text>
                                <Text type="secondary">风险：{item.risk_zh}</Text>
                                <List
                                  size="small"
                                  dataSource={item.details_zh || []}
                                  renderItem={(detail) => <List.Item>{detail}</List.Item>}
                                />
                                <Button size="small" icon={<BranchesOutlined />} onClick={() => runGuideAction(item.id)}>
                                  {item.next_action_zh || "进入对应功能"}
                                </Button>
                              </Space>
                            ),
                          }))}
                        />
                      </Card>
                      <Card title="安全情况处理总流程" className="flow-card">
                        <List
                          id="securityFlowList"
                          size="small"
                          dataSource={SECURITY_FLOW_STEPS}
                          renderItem={(item) => <List.Item>{item}</List.Item>}
                        />
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
                key: "asyncReviews",
                label: "异步 AI 审查",
                children: (
                  <Card title="异步 AI 审查队列">
                    <Alert
                      className="guard-alert"
                      type="info"
                      showIcon
                      message="内容类请求会先通过 Fast-Path，再进入可恢复的异步 AI 审查队列；处理时会调用配置的模型网关，失败会重试，超过次数进入 dead_letter。"
                    />
                    <Space className="table-actions" wrap>
                      <Select
                        id="asyncReviewStatusSelect"
                        value={asyncReviewStatus}
                        onChange={(value) => {
                          setAsyncReviewStatus(value);
                          showAsyncReviews(value);
                        }}
                        options={[
                          { value: "pending", label: "待处理" },
                          { value: "retry", label: "待重试" },
                          { value: "processing", label: "处理中" },
                          { value: "completed", label: "已完成" },
                          { value: "dead_letter", label: "死信" },
                          { value: "all", label: "全部" },
                        ]}
                        style={{ width: 128 }}
                      />
                      <Button id="asyncReviewsBtn" icon={<ReloadOutlined />} onClick={() => showAsyncReviews(asyncReviewStatus)}>
                        刷新队列
                      </Button>
                      <Button id="runAsyncReviewsBtn" type="primary" icon={<BranchesOutlined />} onClick={runAsyncReviews}>
                        处理到期任务
                      </Button>
                    </Space>
                    <Table
                      rowKey="id"
                      columns={asyncReviewColumns}
                      dataSource={asyncReviews}
                      pagination={{ pageSize: 5 }}
                    />
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
                              <Form.Item label="异步 AI 审查 worker" name="async_review_worker_enabled" valuePropName="checked" extra={GATEWAY_HELP.async_review_worker_enabled}>
                                <Switch id="asyncReviewWorkerSwitch" />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                              <Form.Item label="AI 审查间隔秒" name="async_review_worker_interval_seconds" extra={GATEWAY_HELP.async_review_worker_interval_seconds}>
                                <InputNumber id="asyncReviewWorkerIntervalInput" min={1} max={3600} />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                              <Form.Item label="AI 审查批量" name="async_review_worker_batch_size" extra={GATEWAY_HELP.async_review_worker_batch_size}>
                                <InputNumber id="asyncReviewWorkerBatchInput" min={1} max={100} />
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
                              <Form.Item label={<LabelWithHelp text="新 API Base（留空不变）" help={GATEWAY_HELP.new_llm_api_base} />} name="new_llm_api_base" extra={GATEWAY_HELP.new_llm_api_base}>
                                <Input.Password id="llmApiBaseInput" autoComplete="off" visibilityToggle={false} placeholder={SECRET_PLACEHOLDER} />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                              <Form.Item label={<LabelWithHelp text="API Key 环境变量" help={GATEWAY_HELP.llm_api_key_env} />} name="llm_api_key_env" extra={GATEWAY_HELP.llm_api_key_env}>
                                <Input id="llmApiKeyEnvInput" autoComplete="off" />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                              <Form.Item label={<LabelWithHelp text="OpenAI API Key（保存为环境变量）" help={GATEWAY_HELP.llm_api_key_value} />} name="llm_api_key_value" extra={GATEWAY_HELP.llm_api_key_value}>
                                <Input.Password id="llmApiKeyValueInput" autoComplete="off" visibilityToggle={false} placeholder={SECRET_PLACEHOLDER} />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                              <Form.Item label="新密钥文件路径（留空不变）" name="new_llm_api_key_file" extra={GATEWAY_HELP.new_llm_api_key_file}>
                                <Input.Password id="llmApiKeyFileInput" autoComplete="off" visibilityToggle={false} placeholder={SECRET_PLACEHOLDER} />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={12}>
                              <Form.Item label={<LabelWithHelp text="新代理 URL（留空不变）" help={GATEWAY_HELP.new_llm_proxy_url} />} name="new_llm_proxy_url" extra={GATEWAY_HELP.new_llm_proxy_url}>
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
                              <Form.Item label={<LabelWithHelp text="可信代理 CIDR" help={GATEWAY_HELP.trusted_proxy_cidrs} />} name="trusted_proxy_cidrs" extra={GATEWAY_HELP.trusted_proxy_cidrs}>
                                <Input.TextArea id="trustedProxyInput" autoSize={{ minRows: 2, maxRows: 5 }} />
                              </Form.Item>
                            </Col>
                            <Col xs={24}>
                              <Form.Item label="申诉入口路径" name="appeal_paths" extra={GATEWAY_HELP.appeal_paths}>
                                <Input.TextArea id="appealPathsInput" autoSize={{ minRows: 2, maxRows: 5 }} />
                              </Form.Item>
                            </Col>
                            <Col xs={24} md={8}>
                              <Form.Item label={<LabelWithHelp text="紧急旁路启用" help={GATEWAY_HELP.bypass_enabled} />} name="bypass_enabled" valuePropName="checked" extra={GATEWAY_HELP.bypass_enabled}>
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

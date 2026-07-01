import {
  ApiOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import {
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import {
  GATEWAY_HELP,
  LabelWithHelp,
  SECRET_PLACEHOLDER,
  pretty,
  tagForBoolean,
} from "./admin-support.jsx";
import { ApiKeysTab } from "./admin-access.jsx";

const { Text } = Typography;

export function LedgerTab({
  ledgerLimit,
  setLedgerLimit,
  showLedger,
  ledgerColumns,
  ledgerRecords,
  deleteLedgerRecord,
  clearLedgerRecords,
  writeLocked,
}) {
  const columns = [
    ...ledgerColumns,
    {
      title: "操作",
      key: "recordActions",
      width: 96,
      render: (_, record) => (
        <Popconfirm
          title="删除账本记录"
          description="仅删除 ATEE 本地账本记录，不影响原站业务数据。"
          okText="删除"
          cancelText="取消"
          onConfirm={() => deleteLedgerRecord(record.id)}
          disabled={writeLocked}
        >
          <Button id={`deleteLedgerRecord-${record.id}`} danger size="small" icon={<DeleteOutlined />} disabled={writeLocked} />
        </Popconfirm>
      ),
    },
  ];
  return (
    <Card title="最近账本">
      <Space className="table-actions" wrap>
        <InputNumber id="ledgerLimitInput" min={1} max={100} value={ledgerLimit} onChange={(value) => setLedgerLimit(value || 10)} />
        <Button id="ledgerBtn" icon={<DatabaseOutlined />} onClick={showLedger}>读取账本</Button>
        <Popconfirm
          title="清空账本记录"
          description="会清空 ATEE 本地安全账本记录，不会删除原站业务数据。"
          okText="清空"
          cancelText="取消"
          onConfirm={clearLedgerRecords}
          disabled={writeLocked}
        >
          <Button id="clearLedgerRecordsBtn" danger icon={<DeleteOutlined />} disabled={writeLocked}>清空账本</Button>
        </Popconfirm>
      </Space>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={ledgerRecords}
        pagination={{ pageSize: 5 }}
        expandable={{
          expandedRowRender: (record) => <LedgerDetail record={record} />,
        }}
      />
    </Card>
  );
}

function LedgerDetail({ record }) {
  const details = record.details || {};
  const request = details.request || {};
  const body = request.body_summary || {};
  const scores = details.core_scores || details.core_decision?.scores || {};
  const reasonCodes = details.core_decision?.reason_codes || [];
  return (
    <Space direction="vertical" size={10} style={{ width: "100%" }}>
      <Descriptions size="small" column={{ xs: 1, md: 2 }}>
        <Descriptions.Item label="路径">{request.path || "-"}</Descriptions.Item>
        <Descriptions.Item label="方法">{request.method || "-"}</Descriptions.Item>
        <Descriptions.Item label="用户哈希">{request.user_hash || "-"}</Descriptions.Item>
        <Descriptions.Item label="IP 哈希">{request.ip_hash || "-"}</Descriptions.Item>
        <Descriptions.Item label="行为预览">{body.preview || "-"}</Descriptions.Item>
        <Descriptions.Item label="行为信号">
          {(body.signals || []).length ? (body.signals || []).map((item) => <Tag key={item}>{item}</Tag>) : "-"}
        </Descriptions.Item>
        <Descriptions.Item label="Core 评分">
          {Object.keys(scores).length ? (
            <Space wrap>
              {Object.entries(scores).map(([key, value]) => (
                <Tag key={key}>{key}: {value}</Tag>
              ))}
            </Space>
          ) : "-"}
        </Descriptions.Item>
        <Descriptions.Item label="原因码">
          {reasonCodes.length ? reasonCodes.map((item) => <Tag key={item}>{item}</Tag>) : "-"}
        </Descriptions.Item>
      </Descriptions>
      <details className="json-details">
        <summary>账本详情 JSON</summary>
        <pre id={`ledgerDetail-${record.id}`}>{pretty(details)}</pre>
      </details>
      <Text type="secondary">详情来自脱敏后的 Prompt Packet，不展示原始请求体、Authorization 或完整 API key。</Text>
    </Space>
  );
}

export function GatewayConfigTab({
  configForm,
  showConfig,
  saveConfig,
  testLlmGateway,
  writeLocked,
  status,
  breakGlassForm,
  breakGlass,
  apiKeys,
  showApiKeys,
  apiKeyForm,
  createApiKey,
  deleteApiKey,
  createdApiKey,
  clearCreatedApiKey,
}) {
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
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
      <ApiKeysTab
        apiKeys={apiKeys}
        showApiKeys={showApiKeys}
        apiKeyForm={apiKeyForm}
        createApiKey={createApiKey}
        deleteApiKey={deleteApiKey}
        createdApiKey={createdApiKey}
        clearCreatedApiKey={clearCreatedApiKey}
        writeLocked={writeLocked}
      />
      <Card title="紧急旁路">
        <Descriptions size="small" column={{ xs: 1, md: 2, xl: 3 }}>
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
    </Space>
  );
}

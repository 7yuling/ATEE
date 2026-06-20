import {
  ApiOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  DatabaseOutlined,
  EyeOutlined,
  FileSearchOutlined,
  PauseCircleOutlined,
  StopOutlined,
} from "@ant-design/icons";
import {
  Button,
  Card,
  Col,
  Descriptions,
  Row,
  Space,
  Tag,
} from "antd";
import {
  MetricCard,
  OperationSummary,
  RuntimeSummary,
  modeLabel,
  pretty,
  providerLabel,
  tagForBoolean,
  tagForNullableBoolean,
} from "./adminSupport.jsx";

export function DashboardMetrics({
  status,
  display,
  gateway,
  gatewayConfigured,
  circuit,
}) {
  return (
    <Row className="dashboard-metrics" gutter={[12, 12]}>
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
    </Row>
  );
}

export function DashboardTab({
  display,
  gateway,
  testSafe,
  testAttack,
  testAppeal,
  testLlmGateway,
}) {
  return (
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
  );
}

export function JsonSummaryRow({ status, output, result }) {
  return (
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
  );
}

import {
  BranchesOutlined,
  CheckCircleOutlined,
  DeploymentUnitOutlined,
  MessageOutlined,
  SafetyCertificateOutlined,
  StopOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Divider,
  Form,
  Input,
  List,
  Row,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import {
  ADAPTER_OPTIONS,
  PreflightSummary,
  SECURITY_FLOW_STEPS,
  SITE_TYPE_OPTIONS,
} from "./adminSupport.jsx";

const { Text } = Typography;
const { TextArea } = Input;

export function AgentTab({
  siteType,
  setSiteType,
  adapterType,
  setAdapterType,
  chatMessages,
  chatDraft,
  setChatDraft,
  sendAgentChat,
  loading,
}) {
  return (
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
  );
}

export function GuideTab({
  siteType,
  setSiteType,
  adapterType,
  setAdapterType,
  runPreflight,
  preflightReport,
  runSecurityFlow,
  securityFlowReport,
  guideSteps,
  runGuideAction,
  loading,
  writeLocked = false,
}) {
  return (
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
                  <Button id={`guideAction-${item.id}`} size="small" icon={<BranchesOutlined />} onClick={() => runGuideAction(item.id)}>
                    {item.next_action_zh || "进入对应功能"}
                  </Button>
                </Space>
              ),
            }))}
          />
        </Card>
        <Card title="安全情况处理总流程" className="flow-card">
          <Space direction="vertical" size="small" className="guide-detail">
            <Text type="secondary">按真实后台链路演练预检、请求识别、快速拦截、异步 AI 审查、申诉、模型网关和账本摘要。</Text>
            <Button
              id="securityFlowBtn"
              type="primary"
              icon={<SafetyCertificateOutlined />}
              onClick={runSecurityFlow}
              loading={loading}
              disabled={writeLocked}
            >
              运行安全流程演练
            </Button>
            {writeLocked ? (
              <Alert type="warning" showIcon message="只读模式下不会写入演练记录，请先切回观察、降级或自动模式。" />
            ) : null}
          </Space>
          <List
            id="securityFlowList"
            size="small"
            dataSource={SECURITY_FLOW_STEPS}
            renderItem={(item) => <List.Item>{item}</List.Item>}
          />
          {securityFlowReport?.flow_steps?.length ? (
            <>
              <Divider />
              <List
                id="securityFlowResultList"
                size="small"
                dataSource={securityFlowReport.flow_steps}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta
                      avatar={item.ok ? <CheckCircleOutlined className="ok-icon" /> : <StopOutlined className="bad-icon" />}
                      title={
                        <Space>
                          <Text strong>{item.title_zh}</Text>
                          <Tag color={item.ok ? "success" : "warning"}>{item.status_zh}</Tag>
                        </Space>
                      }
                      description={
                        <Space direction="vertical" size={2}>
                          <Text>{item.detail_zh}</Text>
                          {item.code ? <Text type="secondary">代码：{item.code}</Text> : null}
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            </>
          ) : null}
        </Card>
      </Col>
    </Row>
  );
}

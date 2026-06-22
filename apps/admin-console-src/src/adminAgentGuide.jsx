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
  integrationForm,
  integrationPlan,
  generateIntegrationPlan,
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
        <Card title="目标网站接入" className="flow-card">
          <Form
            form={integrationForm}
            layout="vertical"
            initialValues={{
              site_name: "target-site",
              site_url: "https://target.example",
              core_url: "http://127.0.0.1:8787",
              appeal_path: "/atee-appeal",
              protected_features: "comments",
            }}
          >
            <Row gutter={[12, 0]}>
              <Col xs={24} md={12}>
                <Form.Item label="目标网站名称" name="site_name">
                  <Input id="integrationSiteNameInput" />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="目标网站地址" name="site_url">
                  <Input id="integrationSiteUrlInput" />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="Core Service 地址" name="core_url">
                  <Input id="integrationCoreUrlInput" />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="申诉入口路径" name="appeal_path">
                  <Input id="integrationAppealPathInput" />
                </Form.Item>
              </Col>
              <Col xs={24}>
                <Form.Item label="受保护功能" name="protected_features">
                  <TextArea id="integrationProtectedFeaturesInput" autoSize={{ minRows: 2, maxRows: 4 }} />
                </Form.Item>
              </Col>
            </Row>
            <Button
              id="integrationPlanBtn"
              type="primary"
              icon={<BranchesOutlined />}
              onClick={generateIntegrationPlan}
              loading={loading}
            >
              生成 HTTP API 接入方案
            </Button>
          </Form>
          <IntegrationPlanResult plan={integrationPlan} />
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

function IntegrationPlanResult({ plan }) {
  if (!plan) {
    return null;
  }
  return (
    <div id="integrationPlanResult" className="integration-plan-result">
      <Divider />
      <Alert
        type={plan.ok === false ? "warning" : "success"}
        showIcon
        message={plan.display?.message_zh || "-"}
      />
      {plan.steps?.length ? (
        <>
          <Divider />
          <Text strong>接入步骤</Text>
          <List
            id="integrationPlanSteps"
            size="small"
            dataSource={plan.steps}
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta title={item.title_zh} description={item.detail_zh} />
              </List.Item>
            )}
          />
        </>
      ) : null}
      {plan.endpoint_mappings?.length ? (
        <>
          <Divider />
          <Text strong>接口映射</Text>
          <List
            id="integrationEndpointMappings"
            size="small"
            dataSource={plan.endpoint_mappings}
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta
                  title={`${item.method} ${item.site_route} -> ${item.core_endpoint}`}
                  description={`${item.purpose_zh} ${item.when_zh}`}
                />
              </List.Item>
            )}
          />
        </>
      ) : null}
      {Object.keys(plan.payload_examples || {}).length ? (
        <>
          <Divider />
          <Text strong>Payload 样例</Text>
          <div id="integrationPayloadExamples" className="integration-code-grid">
            {Object.entries(plan.payload_examples).map(([key, item]) => (
              <div key={key} className="integration-code-block">
                <Text strong>{key}</Text>
                <pre>{JSON.stringify(item, null, 2)}</pre>
              </div>
            ))}
          </div>
        </>
      ) : null}
      {plan.verification_requests?.length ? (
        <>
          <Divider />
          <Text strong>验证请求</Text>
          <List
            id="integrationVerificationRequests"
            size="small"
            dataSource={plan.verification_requests}
            renderItem={(item) => (
              <List.Item>
                <Space direction="vertical" size={4} className="guide-detail">
                  <Text strong>{item.title_zh}</Text>
                  <pre className="integration-command">{item.command}</pre>
                  <Text type="secondary">{item.expect_zh}</Text>
                </Space>
              </List.Item>
            )}
          />
        </>
      ) : null}
      {plan.safety_notes_zh?.length ? (
        <>
          <Divider />
          <Text strong>安全注意事项</Text>
          <List
            size="small"
            dataSource={plan.safety_notes_zh}
            renderItem={(item) => <List.Item>{item}</List.Item>}
          />
        </>
      ) : null}
    </div>
  );
}

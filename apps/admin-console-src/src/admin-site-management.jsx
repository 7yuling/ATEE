import {
  Alert,
  Button,
  Card,
  Col,
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
  ExportOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons";

const { Text } = Typography;
const { TextArea } = Input;

export function SiteManagementTab({
  sites,
  siteScans,
  siteActions,
  siteFuseSuggestions,
  siteForm,
  siteScanForm,
  siteFeatureBanForm,
  registerManagedSite,
  createSiteFeatureBan,
  showManagedSites,
  startSiteScan,
  showSiteScans,
  showSiteActions,
  siteActionRisk,
  setSiteActionRisk,
  siteActionType,
  setSiteActionType,
  siteActionSiteId,
  setSiteActionSiteId,
  writeLocked,
}) {
  const siteOptions = sites.map((site) => ({
    value: site.id,
    label: `${site.name} #${site.id}`,
  }));
  const openProxyPath = (site) => {
    const proxyPath = site?.site_proxy?.proxy_path || `/proxy/sites/${site.id}/`;
    window.open(proxyPath, "_blank", "noopener,noreferrer");
  };
  const scanErrorText = (record) => {
    const error = String(record?.error_untrusted_text || "").trim();
    if (error) {
      return error;
    }
    return record?.status === "failed" ? "扫描失败，但后端未返回具体错误。" : "";
  };
  const siteColumns = [
    { title: "ID", dataIndex: "id", key: "id", width: 72 },
    { title: "名称", dataIndex: "name", key: "name" },
    { title: "环境", dataIndex: "environment", key: "environment", render: (value) => <Tag color={value === "production" ? "warning" : "success"}>{value}</Tag> },
    { title: "入口", dataIndex: "base_url", key: "base_url", ellipsis: true },
    { title: "Guard", dataIndex: "page_guard_enabled", key: "page_guard_enabled", width: 90, render: (value) => <Tag color={value ? "success" : "default"}>{value ? "on" : "off"}</Tag> },
    { title: "受保护功能", dataIndex: "protected_features", key: "protected_features", ellipsis: true, render: (value) => (value || []).join(", ") || "-" },
    { title: "扫描", dataIndex: "scan_count", key: "scan_count", width: 80 },
    { title: "动作", dataIndex: "action_count", key: "action_count", width: 80 },
    { title: "最近扫描", dataIndex: "last_scan_at", key: "last_scan_at", render: (value) => value || "-" },
    {
      title: "管理员会话",
      key: "adminSession",
      width: 150,
      render: (_, record) => (
        <Popconfirm
          title="授权管理员会话"
          description="这里仅打开目标站代理入口；目标站管理员会话来自配置的本地会话文件，只用于已配置的后台动作模板，不会把任意原站登录账号变成 ATEE 管理员。"
          okText="打开代理入口"
          cancelText="取消"
          onConfirm={() => openProxyPath(record)}
        >
          <Button id={`authorizeSiteAdminSession-${record.id}`} size="small" icon={<ExportOutlined />}>
            授权
          </Button>
        </Popconfirm>
      ),
    },
  ];
  const scanColumns = [
    { title: "ID", dataIndex: "id", key: "id", width: 72 },
    { title: "站点", dataIndex: "site_id", key: "site_id", width: 80 },
    { title: "状态", dataIndex: "status", key: "status", render: (value) => <Tag color={value === "completed" ? "success" : value === "failed" ? "error" : "processing"}>{value}</Tag> },
    { title: "入口", dataIndex: "start_url", key: "start_url", ellipsis: true, render: (value) => <span title={value}>{value || "-"}</span> },
    { title: "动作", key: "actions", render: (_, record) => record.summary?.actions ?? 0 },
    { title: "高风险", key: "highRisk", render: (_, record) => record.summary?.high_risk_actions ?? 0 },
    {
      title: "失败原因",
      dataIndex: "error_untrusted_text",
      key: "error",
      ellipsis: true,
      render: (_, record) => {
        const error = scanErrorText(record);
        return error ? <Text className="scan-error-text" title={error}>{error}</Text> : "-";
      },
    },
    { title: "更新时间", dataIndex: "updated_at", key: "updated_at" },
  ];
  const actionColumns = [
    { title: "风险", dataIndex: "risk_level", key: "risk_level", width: 90, render: (value) => <RiskTag value={value} /> },
    { title: "类型", dataIndex: "action_type", key: "action_type", width: 110 },
    { title: "控件", dataIndex: "label", key: "label", ellipsis: true },
    { title: "页面", dataIndex: "page_url", key: "page_url", ellipsis: true },
    { title: "选择器", dataIndex: "selector", key: "selector", ellipsis: true },
    { title: "ATEE feature", dataIndex: "suggested_feature_scope", key: "suggested_feature_scope", ellipsis: true },
    {
      title: "应用",
      key: "autoMatch",
      width: 90,
      render: (_, record) => {
        const status = record.metadata?.atee_auto_match?.status || "unapplied";
        return <Tag color={status === "applied" ? "success" : "warning"}>{status === "applied" ? "已应用" : "未应用"}</Tag>;
      },
    },
  ];
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Alert
        type="info"
        showIcon
        message="登记接入网站不会自动切换公网流量；生产访问仍需由 Nginx/Caddy 转发到 ATEE 的站点代理路径。ATEE 管理员账号、原站用户账号、目标站管理员会话互相独立。"
      />
      <details className="site-section-panel" open>
        <summary>站点接入</summary>
        <div className="site-section-body site-management-stack">
          <Card title="接入网站">
            <Space className="table-actions" wrap>
              <Button id="managedSitesBtn" icon={<ReloadOutlined />} onClick={showManagedSites}>
                刷新站点
              </Button>
            </Space>
            <Table rowKey="id" columns={siteColumns} dataSource={sites} pagination={{ pageSize: 6 }} />
          </Card>
          <Card title="登记/更新">
            <Form
              form={siteForm}
              className="site-register-form"
              layout="vertical"
              initialValues={{
                environment: "staging",
                auth_mode: "none",
                page_guard_enabled: false,
                admin_session_enabled: false,
                auto_apply_admin_actions: true,
              }}
            >
              <Form.Item label="站点名称" name="name">
                <Input id="managedSiteNameInput" autoComplete="off" />
              </Form.Item>
              <Form.Item label="入口 URL" name="base_url">
                <Input id="managedSiteBaseUrlInput" autoComplete="off" placeholder="https://staging.example.com/" />
              </Form.Item>
              <details className="site-config-panel">
                <summary>配置选项</summary>
                <div className="site-config-fields">
                  <Form.Item label="环境" name="environment">
                    <Select
                      id="managedSiteEnvironmentSelect"
                      options={[
                        { value: "staging", label: "staging" },
                        { value: "test", label: "test" },
                        { value: "dev", label: "dev" },
                        { value: "production", label: "production" },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item label="允许扫描域名" name="allowed_domains">
                    <TextArea id="managedSiteAllowedDomainsInput" autoSize={{ minRows: 2, maxRows: 4 }} />
                  </Form.Item>
                  <Form.Item label="受保护功能" name="protected_features">
                    <TextArea id="managedSiteProtectedFeaturesInput" autoSize={{ minRows: 2, maxRows: 4 }} placeholder="comments, uploads, posts" />
                  </Form.Item>
                  <Form.Item label="认证方式" name="auth_mode">
                    <Select
                      id="managedSiteAuthModeSelect"
                      options={[
                        { value: "none", label: "none" },
                        { value: "storage_state", label: "storage_state" },
                        { value: "cookies", label: "cookies" },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item label="会话状态引用" name="session_state_ref">
                    <Input id="managedSiteSessionStateInput" autoComplete="off" placeholder="config/sessions/site.json" />
                  </Form.Item>
                  <Form.Item label="Page Guard" name="page_guard_enabled" valuePropName="checked">
                    <Switch id="managedSitePageGuardSwitch" />
                  </Form.Item>
                  <Form.Item label="管理员会话授权" name="admin_session_enabled" valuePropName="checked">
                    <Switch id="managedSiteAdminSessionSwitch" />
                  </Form.Item>
                  <Form.Item label="自动执行后台动作" name="auto_apply_admin_actions" valuePropName="checked">
                    <Switch id="managedSiteAutoApplySwitch" />
                  </Form.Item>
                  <Form.Item label="管理员会话引用" name="admin_session_ref">
                    <Input id="managedSiteAdminSessionRefInput" autoComplete="off" placeholder="config/sessions/site-admin.json" />
                  </Form.Item>
                  <Form.Item label="管理员动作模板 JSON" name="admin_action_templates">
                    <TextArea
                      id="managedSiteAdminActionTemplatesInput"
                      autoSize={{ minRows: 3, maxRows: 8 }}
                      placeholder='{"comments":{"method":"POST","path":"/admin/ban","body_template":{"user_hash":"{user_hash}","feature":"{feature_scope}"}}}'
                    />
                  </Form.Item>
                </div>
              </details>
              <Button id="registerManagedSiteBtn" type="primary" icon={<PlusOutlined />} onClick={registerManagedSite} disabled={writeLocked}>
                保存站点
              </Button>
            </Form>
          </Card>
        </div>
      </details>
      <details className="site-section-panel" open>
        <summary>扫描发现</summary>
        <Row className="site-section-body" gutter={[16, 16]}>
        <Col xs={24} xl={10}>
          <Card title="发起扫描">
            <Form form={siteScanForm} layout="vertical" initialValues={{ max_pages: 5, max_actions: 80, timeout_ms: 30000, allow_high_risk_actions: false }}>
              <Form.Item label="站点" name="site_id">
                <Select id="siteScanSiteSelect" options={siteOptions} />
              </Form.Item>
              <Form.Item label="入口 URL" name="start_url">
                <Input id="siteScanStartUrlInput" autoComplete="off" />
              </Form.Item>
              <Row gutter={12}>
                <Col xs={24} md={8}>
                  <Form.Item label="页面数" name="max_pages">
                    <InputNumber id="siteScanMaxPagesInput" min={1} max={100} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item label="动作数" name="max_actions">
                    <InputNumber id="siteScanMaxActionsInput" min={1} max={1000} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item label="超时 ms" name="timeout_ms">
                    <InputNumber id="siteScanTimeoutInput" min={1000} max={120000} step={1000} />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item label="高风险真实点击" name="allow_high_risk_actions" valuePropName="checked">
                <Switch id="siteScanHighRiskSwitch" />
              </Form.Item>
              <Space wrap>
                <Popconfirm
                  title="直接扫描网络"
                  description="ATEE 会访问目标站页面并遍历按钮/表单，可能触发目标站风控或被识别为攻击；概念演示版可继续。"
                  okText="继续扫描"
                  cancelText="取消"
                  onConfirm={startSiteScan}
                >
                  <Button id="startSiteScanBtn" danger type="primary" icon={<PlayCircleOutlined />} disabled={writeLocked}>
                    开始扫描
                  </Button>
                </Popconfirm>
                <Button id="siteScansBtn" icon={<ReloadOutlined />} onClick={showSiteScans}>
                  扫描历史
                </Button>
              </Space>
              <Text type="secondary">生产环境高风险点击会被后端保护，除非请求显式确认。</Text>
            </Form>
          </Card>
        </Col>
        <Col xs={24} xl={14}>
          <Card title="扫描历史">
            <Table
              rowKey="id"
              columns={scanColumns}
              dataSource={siteScans}
              pagination={{ pageSize: 6 }}
              rowClassName={(record) => (record.status === "failed" ? "site-scan-row-failed" : "")}
              expandable={{
                expandedRowRender: (record) => {
                  const error = scanErrorText(record);
                  return error ? <pre className="scan-error-detail">{error}</pre> : null;
                },
                rowExpandable: (record) => Boolean(scanErrorText(record)),
              }}
            />
          </Card>
        </Col>
        </Row>
      </details>
      <details className="site-section-panel" open>
        <summary>治理与动作</summary>
        <Row className="site-section-body" gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="全局功能熔断">
            <Form form={siteFeatureBanForm} layout="vertical" initialValues={{ duration_seconds: 3600 }}>
              <Row gutter={12}>
                <Col xs={24} md={12}>
                  <Form.Item label="站点" name="site_id">
                    <Select id="siteFeatureBanSiteSelect" options={siteOptions} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="功能范围" name="feature_scope">
                    <Input id="siteFeatureBanFeatureInput" autoComplete="off" placeholder="uploads" />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={12}>
                <Col xs={24} md={10}>
                  <Form.Item label="持续秒数" name="duration_seconds">
                    <InputNumber id="siteFeatureBanDurationInput" min={60} max={604800} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={14}>
                  <Form.Item label="原因" name="reason">
                    <Input id="siteFeatureBanReasonInput" autoComplete="off" />
                  </Form.Item>
                </Col>
              </Row>
              <Button id="createSiteFeatureBanBtn" type="primary" onClick={createSiteFeatureBan} disabled={writeLocked}>
                创建熔断
              </Button>
            </Form>
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="AI 熔断建议">
            <Table
              rowKey={(record) => `${record.site_id}-${record.feature_scope}`}
              columns={[
                { title: "站点", dataIndex: "site_id", key: "site_id", width: 80 },
                { title: "功能", dataIndex: "feature_scope", key: "feature_scope" },
                { title: "用户级封禁", dataIndex: "active_user_bans", key: "active_user_bans", width: 120 },
                { title: "阈值", dataIndex: "threshold", key: "threshold", width: 90 },
              ]}
              dataSource={siteFuseSuggestions || []}
              pagination={{ pageSize: 5 }}
            />
          </Card>
        </Col>
        </Row>
        <Card title="动作资产台账">
          <Space className="table-actions" wrap>
            <Select
              id="siteActionSiteSelect"
              className="field-md"
              allowClear
              placeholder="站点"
              value={siteActionSiteId}
              onChange={setSiteActionSiteId}
              options={siteOptions}
            />
            <Select
              id="siteActionRiskSelect"
              className="field-sm"
              value={siteActionRisk}
              onChange={setSiteActionRisk}
              options={[
                { value: "all", label: "all" },
                { value: "critical", label: "critical" },
                { value: "high", label: "high" },
                { value: "medium", label: "medium" },
                { value: "low", label: "low" },
              ]}
            />
            <Select
              id="siteActionTypeSelect"
              className="field-md"
              value={siteActionType}
              onChange={setSiteActionType}
              options={[
                "all",
                "login",
                "register",
                "submit",
                "search",
                "save",
                "delete",
                "menu",
                "pagination",
                "dialog_trigger",
                "upload",
                "navigation",
                "unknown",
              ].map((value) => ({ value, label: value }))}
            />
            <Button id="siteActionsBtn" icon={<SearchOutlined />} onClick={showSiteActions}>
              查询动作
            </Button>
          </Space>
          <Table rowKey="id" columns={actionColumns} dataSource={siteActions} pagination={{ pageSize: 10 }} />
        </Card>
      </details>
    </Space>
  );
}

function RiskTag({ value }) {
  const colors = {
    critical: "error",
    high: "warning",
    medium: "processing",
    low: "success",
  };
  return <Tag color={colors[value] || "default"}>{value || "-"}</Tag>;
}

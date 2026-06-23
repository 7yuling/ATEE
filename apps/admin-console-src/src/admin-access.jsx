import {
  CopyOutlined,
  DeleteOutlined,
  KeyOutlined,
  LoginOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  UserAddOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Form,
  Input,
  message,
  Popconfirm,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";

const { Text } = Typography;

export function AdminLoginPanel({
  adminAuth,
  adminId,
  setAdminId,
  adminToken,
  setAdminToken,
  captcha,
  loadCaptcha,
  loginForm,
  loginAdmin,
  registerAdmin,
  saveAdminToken,
  clearAdminToken,
}) {
  return (
    <Card className="auth-panel" size="small">
      <details className="admin-auth-drawer" open={adminAuth.enabled && !adminToken}>
        <summary>Admin Access</summary>
      <Space direction="vertical" size={10} style={{ width: "100%" }}>
        <Form form={loginForm} layout="inline" className="compact-form">
          <Form.Item name="username">
            <Input id="adminLoginUsernameInput" autoComplete="username" placeholder="管理员账号" className="field-md" />
          </Form.Item>
          <Form.Item name="password">
            <Input.Password
              id="adminLoginPasswordInput"
              autoComplete="current-password"
              visibilityToggle={false}
              placeholder="密码"
              className="field-md"
            />
          </Form.Item>
          <Form.Item name="captcha_answer">
            <Input id="adminCaptchaAnswerInput" autoComplete="off" placeholder={captcha?.question || "验证码"} className="field-sm" />
          </Form.Item>
          <Form.Item>
            <Space wrap>
              <Button id="loadCaptchaBtn" icon={<ReloadOutlined />} onClick={loadCaptcha}>
                获取验证码
              </Button>
              <Button id="adminLoginBtn" type="primary" icon={<LoginOutlined />} onClick={loginAdmin}>
                登录
              </Button>
              {adminAuth.bootstrap_allowed ? (
                <Button id="adminRegisterBtn" icon={<UserAddOutlined />} onClick={registerAdmin}>
                  注册首个管理员
                </Button>
              ) : null}
            </Space>
          </Form.Item>
        </Form>
        <Space wrap>
          <Tag id="adminAuthState" color={adminAuth.enabled ? (adminToken ? "success" : "warning") : "default"}>
            {adminAuth.enabled ? (adminToken ? "验证码会话已准备" : "需要管理员登录") : "认证未开启"}
          </Tag>
          <Tag color={adminAuth.accounts_configured ? "success" : "warning"}>
            {adminAuth.accounts_configured ? "管理员账号已配置" : "可注册首个管理员"}
          </Tag>
          <Tag color={adminAuth.legacy_token_configured ? "default" : "default"}>
            {adminAuth.legacy_token_configured ? "兼容令牌可用" : "无兼容令牌"}
          </Tag>
          {captcha?.question ? <Text type="secondary">验证码：{captcha.question}</Text> : null}
        </Space>
        <details className="legacy-token-panel">
          <summary>兼容 Admin Token</summary>
          <Space wrap className="legacy-token-fields">
            <Input
              id="adminIdInput"
              value={adminId}
              onChange={(event) => setAdminId(event.target.value)}
              autoComplete="off"
              placeholder="操作者 ID"
              className="field-md"
            />
            <Input.Password
              id="adminTokenInput"
              value={adminToken}
              onChange={(event) => setAdminToken(event.target.value)}
              autoComplete="off"
              visibilityToggle={false}
              placeholder="Admin Token 或登录会话"
              className="field-lg"
            />
            <Button id="saveAdminTokenBtn" icon={<SafetyCertificateOutlined />} onClick={saveAdminToken}>
              保存本机会话
            </Button>
            <Button id="clearAdminTokenBtn" onClick={clearAdminToken}>
              清除
            </Button>
          </Space>
        </details>
      </Space>
      </details>
    </Card>
  );
}

export function AdminAccountsTab({
  adminAccounts,
  showAdminAccounts,
  createAdminForm,
  createAdminAccount,
  passwordForm,
  changeAdminPassword,
  writeLocked,
}) {
  const columns = [
    { title: "账号", dataIndex: "username", key: "username" },
    { title: "创建时间", dataIndex: "created_at", key: "created_at" },
    { title: "最近登录", dataIndex: "last_login_at", key: "last_login_at", render: (value) => value || "-" },
    { title: "状态", dataIndex: "disabled_at", key: "disabled_at", render: (value) => (value ? <Tag>已停用</Tag> : <Tag color="success">启用</Tag>) },
  ];
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={14}>
        <Card title="管理员账号">
          <Space className="table-actions" wrap>
            <Button id="adminAccountsBtn" icon={<ReloadOutlined />} onClick={showAdminAccounts}>
              刷新账号
            </Button>
          </Space>
          <Table rowKey="username" columns={columns} dataSource={adminAccounts} pagination={{ pageSize: 8 }} />
        </Card>
      </Col>
      <Col xs={24} xl={10}>
        <Card title="账号维护">
          <Form form={createAdminForm} layout="vertical">
            <Row gutter={12}>
              <Col xs={24} md={12}>
                <Form.Item label="新管理员账号" name="username">
                  <Input id="newAdminUsernameInput" autoComplete="off" />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="初始密码" name="password">
                  <Input.Password id="newAdminPasswordInput" autoComplete="new-password" visibilityToggle={false} />
                </Form.Item>
              </Col>
            </Row>
            <Button id="createAdminAccountBtn" type="primary" icon={<PlusOutlined />} onClick={createAdminAccount} disabled={writeLocked}>
              新增管理员
            </Button>
          </Form>
          <Form form={passwordForm} layout="vertical" className="review-form">
            <Row gutter={12}>
              <Col xs={24} md={8}>
                <Form.Item label="账号" name="username">
                  <Input id="passwordAdminUsernameInput" autoComplete="username" />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="旧密码" name="old_password">
                  <Input.Password id="oldAdminPasswordInput" autoComplete="current-password" visibilityToggle={false} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="新密码" name="new_password">
                  <Input.Password id="changedAdminPasswordInput" autoComplete="new-password" visibilityToggle={false} />
                </Form.Item>
              </Col>
            </Row>
            <Button id="changeAdminPasswordBtn" icon={<KeyOutlined />} onClick={changeAdminPassword} disabled={writeLocked}>
              修改密码
            </Button>
          </Form>
        </Card>
      </Col>
    </Row>
  );
}

export function ApiKeysTab({
  apiKeys,
  showApiKeys,
  apiKeyForm,
  createApiKey,
  deleteApiKey,
  createdApiKey,
  clearCreatedApiKey,
  writeLocked,
}) {
  const columns = [
    { title: "名称", dataIndex: "name", key: "name" },
    { title: "Key", dataIndex: "masked_key", key: "masked_key" },
    { title: "用途", dataIndex: "scope", key: "scope", render: (value) => (value === "backend" ? "后台调用" : "前台调用") },
    { title: "环境变量", dataIndex: "env_name", key: "env_name" },
    { title: "创建日期", dataIndex: "created_at", key: "created_at" },
    { title: "最新使用日期", dataIndex: "last_used_at", key: "last_used_at", render: (value) => value || "-" },
    {
      title: "操作",
      key: "actions",
      width: 90,
      render: (_, record) => (
        <Popconfirm
          title="确认删除 API key"
          description="删除会清除当前进程中的对应环境变量。"
          okText="确认删除"
          cancelText="取消"
          onConfirm={() => deleteApiKey(record.id)}
          disabled={writeLocked}
        >
          <Button id={`deleteApiKey-${record.id}`} danger icon={<DeleteOutlined />} disabled={writeLocked} />
        </Popconfirm>
      ),
    },
  ];
  async function copyCreatedApiKey() {
    try {
      if (!navigator.clipboard?.writeText || !createdApiKey?.key) {
        throw new Error("Clipboard is unavailable");
      }
      await navigator.clipboard.writeText(createdApiKey.key);
      message.success("API key 已复制");
    } catch {
      message.error("复制失败，请手动复制");
    }
  }
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={15}>
        <Card title="API keys">
          <Space className="table-actions" wrap>
            <Button id="apiKeysBtn" icon={<ReloadOutlined />} onClick={showApiKeys}>
              刷新 API keys
            </Button>
          </Space>
          <Table rowKey="id" columns={columns} dataSource={apiKeys} pagination={{ pageSize: 8 }} />
        </Card>
      </Col>
      <Col xs={24} xl={9}>
        <Card title="创建 API key">
          {createdApiKey?.key ? (
            <Alert
              className="guard-alert"
              type="success"
              showIcon
              message="明文 key 只显示一次"
              description={
                <Space direction="vertical" style={{ width: "100%" }}>
                  <pre className="secret-once">{createdApiKey.key}</pre>
                  <Space>
                    <Button
                      id="copyCreatedApiKeyBtn"
                      icon={<CopyOutlined />}
                      onClick={copyCreatedApiKey}
                    >
                      复制
                    </Button>
                    <Button id="clearCreatedApiKeyBtn" onClick={clearCreatedApiKey}>
                      关闭
                    </Button>
                  </Space>
                </Space>
              }
            />
          ) : null}
          <Form form={apiKeyForm} layout="vertical">
            <Form.Item label="名称" name="name">
              <Input id="apiKeyNameInput" autoComplete="off" />
            </Form.Item>
            <Form.Item label="用途" name="scope" initialValue="backend">
              <Select
                id="apiKeyScopeSelect"
                options={[
                  { value: "backend", label: "后台调用" },
                  { value: "frontend", label: "前台调用" },
                ]}
              />
            </Form.Item>
            <Form.Item label="环境变量" name="env_name">
              <Input id="apiKeyEnvInput" autoComplete="off" placeholder="留空自动生成" />
            </Form.Item>
            <Form.Item label="已有 key 明文" name="key_value">
              <Input.Password id="apiKeyValueInput" autoComplete="off" visibilityToggle={false} placeholder="留空自动生成" />
            </Form.Item>
            <Form.Item label="设为后台模型 key" name="activate_provider_key" valuePropName="checked" initialValue>
              <Switch id="activateProviderKeySwitch" />
            </Form.Item>
            <Button id="createApiKeyBtn" type="primary" icon={<KeyOutlined />} onClick={createApiKey} disabled={writeLocked}>
              创建 API key
            </Button>
          </Form>
        </Card>
      </Col>
    </Row>
  );
}

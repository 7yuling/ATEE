import {
  BranchesOutlined,
  ReloadOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Popconfirm,
  Select,
  Space,
  Table,
} from "antd";

export function AppealsTab({
  appealStatus,
  setAppealStatus,
  showAppeals,
  appealColumns,
  appeals,
  appealForm,
  reviewAppeal,
  writeLocked,
}) {
  return (
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
  );
}

export function ActionsTab({
  actionStatus,
  setActionStatus,
  showActions,
  actionColumns,
  actions,
  actionForm,
  cleanupActions,
  revokeAction,
  writeLocked,
}) {
  return (
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
  );
}

export function AsyncReviewsTab({
  asyncReviewStatus,
  setAsyncReviewStatus,
  showAsyncReviews,
  asyncReviewColumns,
  asyncReviews,
  runAsyncReviews,
}) {
  return (
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
  );
}

import {
  BranchesOutlined,
  DeleteOutlined,
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
  Typography,
} from "antd";

const { Text } = Typography;

function activatableRow(onActivate) {
  return {
    className: "clickable-row",
    role: "button",
    tabIndex: 0,
    onClick: onActivate,
    onKeyDown: (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onActivate();
      }
    },
  };
}

export function AppealsTab({
  appealStatus,
  setAppealStatus,
  showAppeals,
  appealColumns,
  appeals,
  appealForm,
  reviewAppeal,
  deleteAppeal,
  clearAppeals,
  writeLocked,
}) {
  const columns = [
    ...appealColumns,
    {
      title: "操作",
      key: "recordActions",
      width: 96,
      render: (_, record) => (
        <Popconfirm
          title="删除申诉记录"
          description="仅删除 ATEE 申诉记录，不会修改原站业务数据。"
          okText="删除"
          cancelText="取消"
          onConfirm={() => deleteAppeal(record.punishment_id)}
          disabled={writeLocked}
        >
          <Button id={`deleteAppeal-${record.punishment_id}`} danger size="small" icon={<DeleteOutlined />} disabled={writeLocked} />
        </Popconfirm>
      ),
    },
  ];
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
          className="field-xs"
        />
        <Button id="appealsBtn" icon={<ReloadOutlined />} onClick={() => showAppeals(appealStatus)}>刷新申诉</Button>
        <Popconfirm
          title="清空当前申诉列表"
          description="按当前状态筛选清空 ATEE 申诉记录，不会修改原站业务数据。"
          okText="清空"
          cancelText="取消"
          onConfirm={clearAppeals}
          disabled={writeLocked}
        >
          <Button id="clearAppealsBtn" danger icon={<DeleteOutlined />} disabled={writeLocked}>清空申诉</Button>
        </Popconfirm>
      </Space>
      <Table
        rowKey="punishment_id"
        columns={columns}
        dataSource={appeals}
        pagination={{ pageSize: 5 }}
        expandable={{
          expandedRowRender: (record) => (
            <Space direction="vertical" size={8} style={{ width: "100%" }}>
              <Text strong>申诉内容</Text>
              <pre id={`appealReason-${record.punishment_id}`}>{record.reason_untrusted_text || "无申诉内容"}</pre>
              {record.admin_note_untrusted_text ? (
                <>
                  <Text strong>管理员备注</Text>
                  <pre>{record.admin_note_untrusted_text}</pre>
                </>
              ) : null}
            </Space>
          ),
        }}
        onRow={(record) => activatableRow(() => appealForm.setFieldsValue({ punishment_id: record.punishment_id }))}
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
  deleteActionRecord,
  clearActionRecords,
  writeLocked,
}) {
  const columns = [
    ...actionColumns,
    {
      title: "操作",
      key: "recordActions",
      width: 112,
      render: (_, record) => (
        <Popconfirm
          title="删除动作记录"
          description="active 动作必须先撤销；这里只删除 ATEE 动作记录。"
          okText="删除"
          cancelText="取消"
          onConfirm={() => deleteActionRecord(record.id)}
          disabled={writeLocked || record.status === "active"}
        >
          <Button
            id={`deleteActionRecord-${record.id}`}
            danger
            size="small"
            icon={<DeleteOutlined />}
            disabled={writeLocked || record.status === "active"}
          />
        </Popconfirm>
      ),
    },
  ];
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
          className="field-xs"
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
        <Popconfirm
          title="清空当前动作记录"
          description="active 动作不会被物理删除；请先撤销后再删除记录。"
          okText="清空"
          cancelText="取消"
          onConfirm={clearActionRecords}
          disabled={writeLocked || actionStatus === "active"}
        >
          <Button id="clearActionRecordsBtn" danger icon={<DeleteOutlined />} disabled={writeLocked || actionStatus === "active"}>清空记录</Button>
        </Popconfirm>
      </Space>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={actions}
        pagination={{ pageSize: 5 }}
        onRow={(record) => activatableRow(() => actionForm.setFieldsValue({ action_id: record.id }))}
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
  manualReviewForm,
  manualFeatureBan,
  runAsyncReviews,
  deleteAsyncReview,
  clearAsyncReviews,
  writeLocked,
}) {
  const columns = [
    ...asyncReviewColumns,
    {
      title: "操作",
      key: "recordActions",
      width: 96,
      render: (_, record) => (
        <Popconfirm
          title="删除审查记录"
          description="processing 状态任务不会被删除。"
          okText="删除"
          cancelText="取消"
          onConfirm={() => deleteAsyncReview(record.id)}
          disabled={writeLocked || record.status === "processing"}
        >
          <Button
            id={`deleteAsyncReview-${record.id}`}
            danger
            size="small"
            icon={<DeleteOutlined />}
            disabled={writeLocked || record.status === "processing"}
          />
        </Popconfirm>
      ),
    },
  ];
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
          className="field-xs"
        />
        <Button id="asyncReviewsBtn" icon={<ReloadOutlined />} onClick={() => showAsyncReviews(asyncReviewStatus)}>
          刷新队列
        </Button>
        <Button id="runAsyncReviewsBtn" type="primary" icon={<BranchesOutlined />} onClick={runAsyncReviews} disabled={writeLocked}>
          处理到期任务
        </Button>
        <Popconfirm
          title="清空当前审查记录"
          description="按当前状态清空异步审查记录；processing 任务会保留。"
          okText="清空"
          cancelText="取消"
          onConfirm={clearAsyncReviews}
          disabled={writeLocked || asyncReviewStatus === "processing"}
        >
          <Button id="clearAsyncReviewsBtn" danger icon={<DeleteOutlined />} disabled={writeLocked || asyncReviewStatus === "processing"}>清空记录</Button>
        </Popconfirm>
      </Space>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={asyncReviews}
        pagination={{ pageSize: 5 }}
        onRow={(record) => activatableRow(() => manualReviewForm.setFieldsValue({
            job_id: record.id,
            user_hash: record.user_hash,
            feature_scope: record.feature_scope || record.event_type,
            duration_seconds: 3600,
          }))}
      />
      <Form form={manualReviewForm} layout="inline" className="review-form">
        <Form.Item label="审查任务" name="job_id">
          <Input id="manualReviewJobIdInput" inputMode="numeric" autoComplete="off" />
        </Form.Item>
        <Form.Item label="用户哈希" name="user_hash">
          <Input id="manualReviewUserHashInput" autoComplete="off" />
        </Form.Item>
        <Form.Item label="功能范围" name="feature_scope">
          <Input id="manualReviewFeatureInput" autoComplete="off" />
        </Form.Item>
        <Form.Item label="封禁秒数" name="duration_seconds">
          <Input id="manualReviewDurationInput" inputMode="numeric" autoComplete="off" />
        </Form.Item>
        <Form.Item label="人工备注" name="admin_note">
          <Input id="manualReviewNoteInput" autoComplete="off" />
        </Form.Item>
        <Form.Item>
          <Popconfirm
            title="确认执行人工功能封禁"
            description="该操作会把异步审查任务标记完成，并为任务中的脱敏用户账号记录可撤销的 feature_ban 动作。"
            okText="确认封禁"
            cancelText="取消"
            onConfirm={manualFeatureBan}
            disabled={writeLocked}
          >
            <Button id="manualFeatureBanBtn" danger disabled={writeLocked}>人工功能封禁</Button>
          </Popconfirm>
        </Form.Item>
      </Form>
    </Card>
  );
}

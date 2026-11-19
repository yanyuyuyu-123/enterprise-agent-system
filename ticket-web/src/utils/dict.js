import dayjs from 'dayjs'

export function formatDateTime(value) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'
}

export function formatDate(value) {
  return value ? dayjs(value).format('YYYY-MM-DD') : '-'
}

export function formatMoney(value) {
  const number = Number(value ?? 0)
  return number.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export const WORK_ORDER_STATUS = {
  supplementing: { label: '补充信息', type: 'warning' },
  pending_assignment: { label: '待分配', type: 'info' },
  pending_process: { label: '待处理', type: 'primary' },
  processing: { label: '处理中', type: 'primary' },
  pending_review: { label: '待审核', type: 'warning' },
  rejected: { label: '已驳回', type: 'danger' },
  completed: { label: '已完成', type: 'success' },
  cancelled: { label: '已取消', type: 'info' },
}

export const WORK_ORDER_CATEGORY = {
  device_repair: '设备维修',
  expense_reimbursement: '报销',
  security_patrol: '安全巡查',
  transport_exception: '运输异常',
}

export const PRIORITY = {
  low: { label: '低', type: 'info' },
  normal: { label: '普通', type: 'primary' },
  high: { label: '高', type: 'warning' },
  urgent: { label: '紧急', type: 'danger' },
}

export const RECORD_ACTION = {
  create: '创建',
  supplement: '补充提交',
  assign: '分配',
  reassign: '改派',
  start: '开始处理',
  submit_result: '提交结果',
  revise: '修改后重新提交',
  review_approve: '审核通过',
  review_reject: '审核驳回',
  recall: '撤回',
  transfer_request: '申请转交',
  transfer_approve: '转交通过',
  transfer_reject: '转交驳回',
  timeout_auto: '系统标记超时',
}

export const TRANSFER_STATUS = {
  pending: { label: '待审批', type: 'warning' },
  approved: { label: '已通过', type: 'success' },
  rejected: { label: '已驳回', type: 'danger' },
}

export const EXPENSE_TYPE = {
  travel: '差旅费',
  transport: '交通费',
  office: '办公费',
  entertainment: '招待费',
  purchase: '采购杂费',
  other: '其他',
}

export const DOC_STATUS = {
  draft: { label: '草稿', type: 'info' },
  pending_execute: { label: '待执行', type: 'warning' },
  pending_review: { label: '待审核', type: 'warning' },
  approved: { label: '已通过', type: 'success' },
  rejected: { label: '已驳回', type: 'danger' },
  void: { label: '已作废', type: 'info' },
}

export const KNOWLEDGE_STATUS = {
  pending: { label: '排队中', type: 'info' },
  parsing: { label: '解析中', type: 'warning' },
  ready: { label: '可用', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}

export const KNOWLEDGE_CATEGORY = {
  contract: '合同',
  policy: '制度',
  manual: '手册',
  quotation: '报价',
  process: '流程',
  other: '其他',
}

export const FINANCE_RECORD_TYPE = {
  income: '收入',
  cost: '成本',
  expense: '费用',
  receivable: '应收',
  payable: '应付',
  income_reversal: '收入红字',
  cost_reversal: '成本红字',
}

export const MOVEMENT_TYPE = {
  inbound: '入库',
  outbound: '出库',
  purchase_return: '采购退货',
  sales_return: '销售退货',
  stocktake_in: '盘盈调整',
  stocktake_out: '盘亏调整',
  loss: '损耗',
}

export const FULFILLMENT_STATUS = {
  none: { label: '未执行', type: 'info' },
  partial: { label: '部分执行', type: 'warning' },
  completed: { label: '已完成', type: 'success' },
}

export const NOTIFICATION_TYPE = {
  work_order_assigned: '工单分配',
  work_order_review: '待审核',
  work_order_rejected: '审核驳回',
  work_order_completed: '工单完成',
  work_order_recalled: '工单撤回',
  transfer_request: '转交申请',
  transfer_result: '转交结果',
  account_changed: '账号变更',
  work_order_overdue: '工单超时',
  report_published: '报告发布',
  alert_triggered: '异常预警',
  stock_movement: '出入库单',
  stock_check: '盘点单',
  system: '系统通知',
}

export const ALERT_STATUS = {
  open: { label: '待处理', type: 'danger' },
  acknowledged: { label: '已认领', type: 'warning' },
  closed: { label: '已关闭', type: 'info' },
}

export const ALERT_TYPES = {
  low_stock: '库存低于安全线',
  overstock: '库存积压',
  purchase_price_up: '采购价上涨',
  sales_price_down: '销售价下跌',
  receivable_overdue: '应收超期',
  payable_due: '应付到期',
  work_order_overdue: '工单超时',
  device_fault_repeat: '设备反复故障',
  profit_decline: '利润下滑',
}

export const ALERT_LEVEL = {
  high: '高',
  medium: '中',
  low: '低',
}

export const REPORT_TYPES = {
  daily: '日报',
  weekly: '周报',
  monthly: '月报',
  yearly: '年报',
}

export const REPORT_STATUS = {
  generating: { label: '生成中', type: 'warning' },
  generated: { label: '已生成', type: 'success' },
  failed: { label: '生成失败', type: 'danger' },
}

export function tagOf(map, value) {
  return map[value] || { label: value || '-', type: 'info' }
}

export function labelOf(map, value) {
  return map[value] || value || '-'
}

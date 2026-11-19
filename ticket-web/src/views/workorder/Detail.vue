<template>
  <div class="page" v-loading="loading">
    <div class="page-card" v-if="order">
      <div class="order-head">
        <div>
          <div class="order-no">{{ order.order_no }}</div>
          <div class="order-title">{{ order.title }}</div>
          <div class="order-tags">
            <el-tag :type="tagOf(WORK_ORDER_STATUS, order.status).type" size="small">
              {{ tagOf(WORK_ORDER_STATUS, order.status).label }}
            </el-tag>
            <el-tag :type="tagOf(PRIORITY, order.priority).type" size="small" effect="plain">
              {{ tagOf(PRIORITY, order.priority).label }}
            </el-tag>
            <el-tag size="small" type="info" effect="plain">
              {{ labelOf(WORK_ORDER_CATEGORY, order.category) }}
            </el-tag>
            <el-tag v-if="order.is_overdue" size="small" type="danger">已超时</el-tag>
            <el-tag v-if="order.transfer_status" size="small" :type="tagOf(TRANSFER_STATUS, order.transfer_status).type">
              转交{{ tagOf(TRANSFER_STATUS, order.transfer_status).label }}
            </el-tag>
          </div>
        </div>
        <div class="order-actions">
          <el-button v-if="can.supplement" type="primary" @click="openDialog('supplement')">补充信息</el-button>
          <el-button v-if="can.revise" type="primary" @click="openDialog('revise')">编辑并重新提交</el-button>
          <el-button v-if="can.assign" type="primary" @click="openDialog('assign')">分配处理人</el-button>
          <el-button v-if="can.start" type="primary" @click="startOrder">开始处理</el-button>
          <el-button v-if="can.submit" type="primary" @click="openDialog('submit')">提交结果</el-button>
          <el-button v-if="can.review" type="primary" @click="openDialog('review')">审核</el-button>
          <el-button v-if="can.transfer" @click="openDialog('transfer')">申请转交</el-button>
          <el-button v-if="can.transferDecision" type="warning" @click="openDialog('transferDecision')">
            转交审批
          </el-button>
          <el-button v-if="can.recall" type="danger" plain @click="openDialog('recall')">撤回</el-button>
          <el-button @click="router.back()">返回</el-button>
        </div>
      </div>

      <el-descriptions :column="3" border class="mt-16">
        <el-descriptions-item label="创建人">{{ order.creator_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="处理人">{{ order.assignee_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="审核人">{{ order.reviewer_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="部门">{{ order.department_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatDateTime(order.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="处理期限">{{ formatDateTime(order.due_at) }}</el-descriptions-item>
        <el-descriptions-item label="开始处理">{{ formatDateTime(order.started_at) }}</el-descriptions-item>
        <el-descriptions-item label="提交时间">{{ formatDateTime(order.submitted_at) }}</el-descriptions-item>
        <el-descriptions-item label="完成时间">{{ formatDateTime(order.completed_at) }}</el-descriptions-item>
        <el-descriptions-item label="来源">
          {{ order.source_type ? `${order.source_type} / ${order.source_name || order.source_id || '-'}` : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="版本">{{ order.version }}</el-descriptions-item>
        <el-descriptions-item label="撤回原因">{{ order.recall_reason || '-' }}</el-descriptions-item>
      </el-descriptions>

      <div class="section-title">描述</div>
      <div class="description-text">{{ order.description || '无' }}</div>

      <div class="section-title">类别信息</div>
      <el-descriptions v-if="order.detail" :column="2" border>
        <el-descriptions-item
          v-for="(value, key) in order.detail"
          :key="key"
          :label="DETAIL_LABELS[key] || key"
        >
          {{ detailText(key, value) }}
        </el-descriptions-item>
      </el-descriptions>
      <div v-else class="muted">暂无类别明细</div>

      <el-tabs class="mt-16">
        <el-tab-pane :label="`流转记录（${order.records?.length || 0}）`">
          <el-timeline v-if="order.records?.length">
            <el-timeline-item
              v-for="record in order.records"
              :key="record.id"
              :timestamp="`${formatDateTime(record.created_at)} · ${record.operator_name || record.operator_id || '系统'}`"
              :type="record.action.startsWith('review_reject') || record.action === 'recall' ? 'danger' : 'primary'"
            >
              <div>{{ labelOf(RECORD_ACTION, record.action) }}</div>
              <div v-if="record.content" class="muted">{{ record.content }}</div>
              <div v-if="record.comment" class="muted">意见：{{ record.comment }}</div>
            </el-timeline-item>
          </el-timeline>
          <div v-else class="muted">暂无流转记录</div>
        </el-tab-pane>

        <el-tab-pane :label="`审核记录（${order.approvals?.length || 0}）`">
          <el-table v-if="order.approvals?.length" :data="order.approvals" size="small">
            <el-table-column prop="review_round" label="轮次" width="70" />
            <el-table-column prop="reviewer_name" label="审核人" width="120" />
            <el-table-column label="结果" width="90">
              <template #default="{ row }">
                <el-tag :type="row.result === 'approved' ? 'success' : 'danger'" size="small">
                  {{ row.result === 'approved' ? '通过' : '驳回' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="comment" label="意见" min-width="200" show-overflow-tooltip />
            <el-table-column label="时间" width="150">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>
          <div v-else class="muted">暂无审核记录</div>
        </el-tab-pane>

        <el-tab-pane :label="`附件（${order.attachments?.length || 0}）`">
          <div class="toolbar">
            <el-upload :show-file-list="false" :http-request="uploadAttachment">
              <el-button type="primary" plain :loading="uploading">上传附件</el-button>
            </el-upload>
            <span class="muted">支持图片、文档等，单个文件不超过 20MB</span>
          </div>
          <el-table :data="order.attachments || []" size="small">
            <el-table-column prop="file_name" label="文件名" min-width="200" show-overflow-tooltip />
            <el-table-column label="大小" width="100">
              <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
            </el-table-column>
            <el-table-column label="上传时间" width="150">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="90">
              <template #default="{ row }">
                <el-button link type="primary" @click="downloadAttachment(row)">下载</el-button>
              </template>
            </el-table-column>
            <template #empty>暂无附件</template>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-dialog v-model="dialog.visible" :title="dialogTitle" width="520px" destroy-on-close>
      <el-form label-width="96px">
        <template v-if="dialog.type === 'assign'">
          <el-form-item label="处理人 ID">
            <el-input-number v-model="form.assignee_id" :min="1" :controls="false" />
            <div class="muted">需为该类别对应的处理岗位人员</div>
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="form.comment" type="textarea" :rows="2" />
          </el-form-item>
        </template>

        <template v-if="dialog.type === 'supplement' || dialog.type === 'revise'">
          <el-alert
            v-if="dialog.type === 'revise'"
            type="warning"
            :closable="false"
            show-icon
            title="工单已被驳回，修改后重新提交将再次进入审核"
            style="margin-bottom: 12px"
          />
          <el-form-item label="标题">
            <el-input v-model="form.title" maxlength="128" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="form.description" type="textarea" :rows="3" />
          </el-form-item>
          <el-form-item label="优先级">
            <el-radio-group v-model="form.priority">
              <el-radio-button v-for="(item, key) in PRIORITY" :key="key" :value="key">
                {{ item.label }}
              </el-radio-button>
            </el-radio-group>
          </el-form-item>
          <template v-if="order?.category === 'device_repair'">
            <el-form-item label="设备 ID">
              <el-input-number v-model="form.device_id" :min="1" :controls="false" />
            </el-form-item>
            <el-form-item label="故障描述">
              <el-input v-model="form.fault_description" type="textarea" :rows="2" />
            </el-form-item>
          </template>
          <template v-if="order?.category === 'expense_reimbursement'">
            <el-form-item label="费用类型">
              <el-select v-model="form.expense_type" style="width: 100%">
                <el-option v-for="(label, key) in EXPENSE_TYPE" :key="key" :label="label" :value="key" />
              </el-select>
            </el-form-item>
            <el-form-item label="金额">
              <el-input-number v-model="form.amount" :min="0" :precision="2" />
            </el-form-item>
          </template>
          <template v-if="order?.category === 'security_patrol'">
            <el-form-item label="巡查区域">
              <el-input v-model="form.patrol_area" />
            </el-form-item>
            <el-form-item label="隐患描述">
              <el-input v-model="form.hazard_description" type="textarea" :rows="2" />
            </el-form-item>
          </template>
          <template v-if="order?.category === 'transport_exception'">
            <el-form-item label="车次号">
              <el-input v-model="form.trip_no" />
            </el-form-item>
            <el-form-item label="异常类型">
              <el-input v-model="form.exception_type" />
            </el-form-item>
          </template>
        </template>

        <template v-if="dialog.type === 'submit'">
          <el-form-item label="处理说明" required>
            <el-input v-model="form.content" type="textarea" :rows="3" placeholder="说明处理过程" />
          </el-form-item>
          <el-form-item v-if="resultField" :label="resultField.label">
            <el-input v-model="form[resultField.key]" type="textarea" :rows="2" />
          </el-form-item>
        </template>

        <template v-if="dialog.type === 'review'">
          <el-form-item label="审核结果">
            <el-radio-group v-model="form.result">
              <el-radio value="approve">通过</el-radio>
              <el-radio value="reject">驳回</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item :label="form.result === 'reject' ? '驳回意见' : '审核意见'" :required="form.result === 'reject'">
            <el-input v-model="form.comment" type="textarea" :rows="3" />
          </el-form-item>
        </template>

        <template v-if="dialog.type === 'transfer'">
          <el-form-item label="转交给">
            <el-input-number v-model="form.transfer_to_id" :min="1" :controls="false" />
          </el-form-item>
          <el-form-item label="转交说明">
            <el-input v-model="form.comment" type="textarea" :rows="2" />
          </el-form-item>
        </template>

        <template v-if="dialog.type === 'transferDecision'">
          <el-form-item label="审批结果">
            <el-radio-group v-model="form.approve">
              <el-radio :value="true">同意转交</el-radio>
              <el-radio :value="false">驳回转交</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="意见">
            <el-input v-model="form.comment" type="textarea" :rows="2" />
          </el-form-item>
        </template>

        <template v-if="dialog.type === 'recall'">
          <el-form-item label="撤回原因" required>
            <el-input v-model="form.reason" type="textarea" :rows="3" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitDialog">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import { workOrderApi } from '@/api'
import { useUserStore } from '@/stores/user'
import {
  EXPENSE_TYPE,
  PRIORITY,
  RECORD_ACTION,
  TRANSFER_STATUS,
  WORK_ORDER_CATEGORY,
  WORK_ORDER_STATUS,
  formatDateTime,
  formatMoney,
  labelOf,
  tagOf,
} from '@/utils/dict'
import { hasPermission } from '@/utils/permission'

const route = useRoute()
const router = useRouter()
const store = useUserStore()

const loading = ref(false)
const submitting = ref(false)
const uploading = ref(false)
const order = ref(null)

const DETAIL_LABELS = {
  device_id: '设备 ID',
  device_no_snapshot: '设备编号',
  device_name_snapshot: '设备名称',
  fault_description: '故障描述',
  repair_result: '维修结果',
  expense_type: '费用类型',
  amount: '金额',
  patrol_area: '巡查区域',
  hazard_description: '隐患描述',
  rectification_result: '整改结果',
  trip_no: '车次号',
  exception_type: '异常类型',
  handling_result: '处理结果',
}

const RESULT_FIELDS = {
  device_repair: { key: 'repair_result', label: '维修结果' },
  security_patrol: { key: 'rectification_result', label: '整改结果' },
  transport_exception: { key: 'handling_result', label: '处理结果' },
}

const resultField = computed(() => (order.value ? RESULT_FIELDS[order.value.category] : null))

const meId = computed(() => store.me?.id)

const ASSIGNER_POSITIONS = {
  device_repair: 'production_head',
  security_patrol: 'security_head',
  transport_exception: 'logistics_head',
}

const can = computed(() => {
  const item = order.value
  if (!item) return {}
  return {
    supplement: item.status === 'supplementing' && item.creator_id === meId.value,
    revise: item.status === 'rejected' && item.creator_id === meId.value,
    assign:
      item.status === 'pending_assignment' &&
      hasPermission(store.me?.permissions, 'work_order_assign:assign') &&
      !!ASSIGNER_POSITIONS[item.category] &&
      store.positionCodes.includes(ASSIGNER_POSITIONS[item.category]),
    start: item.status === 'pending_process' && item.assignee_id === meId.value,
    submit: item.status === 'processing' && item.assignee_id === meId.value,
    review: item.status === 'pending_review' && item.reviewer_id === meId.value,
    transfer:
      ['pending_process', 'processing'].includes(item.status) && item.assignee_id === meId.value,
    transferDecision: item.transfer_status === 'pending' && item.reviewer_id === meId.value,
    recall:
      ['pending_assignment', 'pending_process'].includes(item.status) &&
      item.creator_id === meId.value,
  }
})

const dialog = reactive({ visible: false, type: '' })
const form = reactive({
  assignee_id: undefined,
  comment: '',
  content: '',
  result: 'approve',
  reason: '',
  transfer_to_id: undefined,
  approve: true,
  title: '',
  description: '',
  priority: 'normal',
  device_id: undefined,
  fault_description: '',
  expense_type: '',
  amount: undefined,
  patrol_area: '',
  hazard_description: '',
  rectification_result: '',
  trip_no: '',
  exception_type: '',
  handling_result: '',
  repair_result: '',
})

const DIALOG_TITLES = {
  assign: '分配处理人',
  supplement: '补充工单信息',
  revise: '编辑工单并重新提交',
  submit: '提交处理结果',
  review: '工单审核',
  transfer: '申请转交',
  transferDecision: '转交审批',
  recall: '撤回工单',
}

const dialogTitle = computed(() => DIALOG_TITLES[dialog.type] || '')

function detailText(key, value) {
  if (value === null || value === undefined || value === '') return '-'
  if (key === 'expense_type') return labelOf(EXPENSE_TYPE, value)
  if (key === 'amount') return `¥${formatMoney(value)}`
  return String(value)
}

function formatSize(size) {
  if (!size) return '-'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

async function load() {
  loading.value = true
  try {
    order.value = await workOrderApi.detail(route.params.id)
  } catch {
    order.value = null
  } finally {
    loading.value = false
  }
}

function openDialog(type) {
  dialog.type = type
  dialog.visible = true
  Object.assign(form, {
    assignee_id: order.value?.assignee_id || undefined,
    comment: '',
    content: '',
    result: 'approve',
    reason: '',
    transfer_to_id: order.value?.transfer_to_id || undefined,
    approve: true,
    title: order.value?.title || '',
    description: order.value?.description || '',
    priority: order.value?.priority || 'normal',
    device_id: order.value?.detail?.device_id || undefined,
    fault_description: order.value?.detail?.fault_description || '',
    expense_type: order.value?.detail?.expense_type || '',
    amount: order.value?.detail?.amount ? Number(order.value.detail.amount) : undefined,
    patrol_area: order.value?.detail?.patrol_area || '',
    hazard_description: order.value?.detail?.hazard_description || '',
    rectification_result: order.value?.detail?.rectification_result || '',
    trip_no: order.value?.detail?.trip_no || '',
    exception_type: order.value?.detail?.exception_type || '',
    handling_result: order.value?.detail?.handling_result || '',
    repair_result: order.value?.detail?.repair_result || '',
  })
}

function supplementDetail() {
  const category = order.value.category
  if (category === 'device_repair') {
    return { device_id: form.device_id || null, fault_description: form.fault_description || null }
  }
  if (category === 'expense_reimbursement') {
    return { expense_type: form.expense_type || null, amount: form.amount ?? null }
  }
  if (category === 'security_patrol') {
    return {
      patrol_area: form.patrol_area || null,
      hazard_description: form.hazard_description || null,
    }
  }
  if (category === 'transport_exception') {
    return { trip_no: form.trip_no || null, exception_type: form.exception_type || null }
  }
  return null
}

async function submitDialog() {
  const id = order.value.id
  const version = order.value.version
  const type = dialog.type
  if (type === 'review' && form.result === 'reject' && !form.comment.trim()) {
    ElMessage.warning('驳回必须填写意见')
    return
  }
  submitting.value = true
  try {
    if (type === 'assign') {
      if (!form.assignee_id) {
        ElMessage.warning('请填写处理人 ID')
        return
      }
      await workOrderApi.assign(id, {
        version,
        assignee_id: form.assignee_id,
        comment: form.comment || null,
      })
    } else if (type === 'supplement' || type === 'revise') {
      const payload = {
        version,
        title: form.title || null,
        description: form.description || null,
        priority: form.priority,
      }
      const detail = supplementDetail()
      if (order.value.category === 'device_repair') payload.device = detail
      if (order.value.category === 'expense_reimbursement') payload.expense = detail
      if (order.value.category === 'security_patrol') payload.patrol = detail
      if (order.value.category === 'transport_exception') payload.transport = detail
      if (type === 'supplement') await workOrderApi.supplement(id, payload)
      else await workOrderApi.revise(id, payload)
    } else if (type === 'submit') {
      if (!form.content.trim()) {
        ElMessage.warning('请填写处理说明')
        return
      }
      const payload = { version, content: form.content }
      if (resultField.value) payload[resultField.value.key] = form[resultField.value.key] || null
      await workOrderApi.submit(id, payload)
    } else if (type === 'review') {
      await workOrderApi.review(id, {
        version,
        result: form.result,
        comment: form.comment || null,
      })
    } else if (type === 'transfer') {
      if (!form.transfer_to_id) {
        ElMessage.warning('请填写转交对象 ID')
        return
      }
      await workOrderApi.transfer(id, {
        version,
        transfer_to_id: form.transfer_to_id,
        comment: form.comment || null,
      })
    } else if (type === 'transferDecision') {
      await workOrderApi.transferDecision(id, {
        version,
        approve: form.approve,
        comment: form.comment || null,
      })
    } else if (type === 'recall') {
      if (!form.reason.trim()) {
        ElMessage.warning('请填写撤回原因')
        return
      }
      await workOrderApi.recall(id, { version, reason: form.reason })
    }
    ElMessage.success('操作成功')
    dialog.visible = false
    await load()
  } catch {
    // 拦截器已提示
  } finally {
    submitting.value = false
  }
}

async function startOrder() {
  try {
    await ElMessageBox.confirm('确认开始处理该工单？', '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await workOrderApi.start(order.value.id, order.value.version)
    ElMessage.success('已开始处理')
    await load()
  } catch {
    // 拦截器已提示
  }
}

async function uploadAttachment({ file }) {
  uploading.value = true
  try {
    await workOrderApi.upload(order.value.id, file)
    ElMessage.success('上传成功')
    await load()
  } catch {
    // 拦截器已提示
  } finally {
    uploading.value = false
  }
}

function downloadAttachment(row) {
  workOrderApi.downloadAttachment(order.value.id, row.id, row.file_name)
}

onMounted(load)
</script>

<style scoped>
.order-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.order-no {
  font-size: 13px;
  color: #8a919f;
}

.order-title {
  font-size: 20px;
  font-weight: 600;
  margin: 4px 0 10px;
}

.order-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.order-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: flex-start;
}

.section-title {
  margin: 18px 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.description-text {
  white-space: pre-wrap;
  line-height: 1.7;
  color: #4a5160;
}
</style>

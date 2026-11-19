<template>
  <div class="page">
    <div class="page-card">
      <div class="toolbar">
        <el-select v-model="query.direction" placeholder="方向" clearable style="width: 120px">
          <el-option label="收入" value="in" />
          <el-option label="支出" value="out" />
        </el-select>
        <el-select v-model="query.status" placeholder="状态" clearable style="width: 130px">
          <el-option v-for="(item, key) in DOC_STATUS" :key="key" :label="item.label" :value="key" />
        </el-select>
        <el-button type="primary" @click="reload">查询</el-button>
        <div class="toolbar-spacer"></div>
        <el-button v-if="canCreate" type="primary" plain @click="openCreate">
          录入资金流水
        </el-button>
      </div>

      <el-table v-loading="loading" :data="rows" size="small">
        <el-table-column prop="flow_no" label="流水号" width="170" />
        <el-table-column label="方向" width="80">
          <template #default="{ row }">
            <el-tag :type="row.direction === 'in' ? 'success' : 'warning'" size="small" effect="plain">
              {{ row.direction === 'in' ? '收入' : '支出' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="140" align="right">
          <template #default="{ row }">¥{{ formatMoney(row.amount) }}</template>
        </el-table-column>
        <el-table-column label="日期" width="110">
          <template #default="{ row }">{{ formatDate(row.flow_date) }}</template>
        </el-table-column>
        <el-table-column prop="payment_method" label="支付方式" width="120" />
        <el-table-column label="关联单据" width="180">
          <template #default="{ row }">
            {{ row.related_order_type ? `${row.related_order_type} / ${row.related_order_id || '-'}` : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="tagOf(DOC_STATUS, row.status).type" size="small">
              {{ tagOf(DOC_STATUS, row.status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button
              v-if="canReview && row.status === 'pending_review' && !isMine(row)"
              link
              type="warning"
              @click="openReview(row)"
            >
              审核
            </el-button>
            <el-button
              v-if="canReview && ['pending_review', 'approved'].includes(row.status)"
              link
              type="danger"
              @click="voidFlow(row)"
            >
              作废
            </el-button>
          </template>
        </el-table-column>
        <template #empty>暂无资金流水</template>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="load"
          @size-change="reload"
        />
      </div>
    </div>

    <el-dialog v-model="createVisible" title="录入资金流水" width="560px" destroy-on-close>
      <el-form label-width="96px">
        <el-form-item label="方向">
          <el-radio-group v-model="createForm.direction">
            <el-radio value="in">收入</el-radio>
            <el-radio value="out">支出</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="金额" required>
          <el-input-number v-model="createForm.amount" :min="0.01" :precision="2" :step="100" />
        </el-form-item>
        <el-form-item label="流水日期">
          <el-date-picker v-model="createForm.flow_date" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="支付方式">
          <el-input v-model="createForm.payment_method" maxlength="32" placeholder="如：银行转账" />
        </el-form-item>
        <el-form-item label="关联单据">
          <el-select v-model="createForm.related_order_type" clearable style="width: 150px">
            <el-option label="采购单" value="purchase_order" />
            <el-option label="销售单" value="sales_order" />
          </el-select>
          <el-input-number
            v-if="createForm.related_order_type"
            v-model="createForm.related_order_id"
            :min="1"
            :controls="false"
            style="margin-left: 12px"
            placeholder="单据 ID"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="createForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">提交</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="reviewVisible" title="审核资金流水" width="460px">
      <el-form label-width="88px">
        <el-form-item label="审核结果">
          <el-radio-group v-model="reviewForm.decision">
            <el-radio value="approve">通过</el-radio>
            <el-radio value="reject">驳回</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="意见">
          <el-input v-model="reviewForm.comment" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitReview">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { financeApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { DOC_STATUS, formatDate, formatMoney, tagOf } from '@/utils/dict'
import { hasPermission } from '@/utils/permission'

const userStore = useUserStore()
const canCreate = computed(() =>
  hasPermission(userStore.me?.permissions, 'finance_record:create'),
)
const canReview = computed(() =>
  hasPermission(userStore.me?.permissions, 'finance_record:review'),
)
const isMine = (row) => row.created_by === userStore.me?.id

const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const total = ref(0)

const query = reactive({ direction: '', status: '', page: 1, page_size: 20 })

const createVisible = ref(false)
const createForm = reactive({
  direction: 'in',
  amount: 0,
  flow_date: '',
  payment_method: '',
  related_order_type: '',
  related_order_id: undefined,
  remark: '',
})

const reviewVisible = ref(false)
const reviewTarget = ref(null)
const reviewForm = reactive({ decision: 'approve', comment: '' })

async function load() {
  loading.value = true
  try {
    const data = await financeApi.flows({ ...query })
    rows.value = data?.items || []
    total.value = data?.total || 0
  } catch {
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function reload() {
  query.page = 1
  load()
}

function openCreate() {
  createForm.direction = 'in'
  createForm.amount = 0
  createForm.flow_date = new Date().toISOString().slice(0, 10)
  createForm.payment_method = ''
  createForm.related_order_type = ''
  createForm.related_order_id = undefined
  createForm.remark = ''
  createVisible.value = true
}

async function save() {
  if (!createForm.amount) {
    ElMessage.warning('请输入金额')
    return
  }
  saving.value = true
  try {
    const created = await financeApi.createFlow({
      direction: createForm.direction,
      amount: createForm.amount,
      flow_date: createForm.flow_date || null,
      payment_method: createForm.payment_method || null,
      related_order_type: createForm.related_order_type || null,
      related_order_id: createForm.related_order_id || null,
      remark: createForm.remark || null,
    })
    ElMessage.success(
      created?.status === 'approved' ? '已完成，财务负责人录入自动审核通过' : '已提交，等待财务负责人审核',
    )
    createVisible.value = false
    await load()
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

function openReview(row) {
  reviewTarget.value = row
  reviewForm.decision = 'approve'
  reviewForm.comment = ''
  reviewVisible.value = true
}

async function submitReview() {
  if (reviewForm.decision === 'reject' && !reviewForm.comment.trim()) {
    ElMessage.warning('驳回必须填写意见')
    return
  }
  const action = reviewForm.decision === 'approve' ? '审核通过' : '驳回'
  try {
    await ElMessageBox.confirm(
      `确认${action}资金流水 ${reviewTarget.value.flow_no}？`,
      '提示',
      { type: 'warning' },
    )
  } catch {
    return
  }
  saving.value = true
  try {
    await financeApi.reviewFlow(reviewTarget.value.id, {
      version: reviewTarget.value.version,
      decision: reviewForm.decision,
      comment: reviewForm.comment || null,
    })
    ElMessage.success(reviewForm.decision === 'approve' ? '审核通过' : '已驳回')
    reviewVisible.value = false
    await load()
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

async function voidFlow(row) {
  let reason = ''
  try {
    const result = await ElMessageBox.prompt('请输入作废原因', '作废流水', {
      inputValidator: (value) => (value && value.trim() ? true : '作废原因必填'),
    })
    reason = result.value
  } catch {
    return
  }
  try {
    await financeApi.voidFlow(row.id, { version: row.version, reason })
    ElMessage.success('已作废')
    await load()
  } catch {
    // 拦截器已提示
  }
}

onMounted(load)
</script>

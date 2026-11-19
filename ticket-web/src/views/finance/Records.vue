<template>
  <div class="page">
    <div class="page-card">
      <div class="toolbar">
        <el-input
          v-model="query.keyword"
          placeholder="单号"
          clearable
          style="width: 190px"
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-select v-model="query.record_type" placeholder="类型" clearable style="width: 120px">
          <el-option
            v-for="(label, key) in FINANCE_RECORD_TYPE"
            :key="key"
            :label="label"
            :value="key"
          />
        </el-select>
        <el-select v-model="query.status" placeholder="状态" clearable style="width: 130px">
          <el-option v-for="(item, key) in DOC_STATUS" :key="key" :label="item.label" :value="key" />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          style="width: 260px"
        />
        <el-button type="primary" @click="reload">查询</el-button>
        <div class="toolbar-spacer"></div>
        <el-button v-if="canCreate" type="primary" plain @click="openCreate">
          录入财务记录
        </el-button>
      </div>

      <el-table v-loading="loading" :data="rows" size="small">
        <el-table-column prop="record_no" label="单号" width="170" />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">{{ labelOf(FINANCE_RECORD_TYPE, row.record_type) }}</template>
        </el-table-column>
        <el-table-column label="金额" width="130" align="right">
          <template #default="{ row }">¥{{ formatMoney(row.amount) }}</template>
        </el-table-column>
        <el-table-column label="日期" width="110">
          <template #default="{ row }">{{ formatDate(row.record_date) }}</template>
        </el-table-column>
        <el-table-column prop="accounting_period" label="会计期间" width="100" />
        <el-table-column prop="account_subject" label="会计科目" width="130" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="tagOf(DOC_STATUS, row.status).type" size="small">
              {{ tagOf(DOC_STATUS, row.status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="140" show-overflow-tooltip />
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
              @click="voidRecord(row)"
            >
              作废
            </el-button>
          </template>
        </el-table-column>
        <template #empty>暂无财务记录</template>
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

    <el-dialog v-model="createVisible" title="录入财务记录" width="560px" destroy-on-close>
      <el-form label-width="96px">
        <el-form-item label="记录类型">
          <el-select v-model="createForm.record_type" style="width: 220px">
            <el-option
              v-for="(label, key) in createRecordTypes"
              :key="key"
              :label="label"
              :value="key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="金额" required>
          <el-input-number v-model="createForm.amount" :min="0.01" :precision="2" :step="100" />
        </el-form-item>
        <el-form-item label="记录日期">
          <el-date-picker v-model="createForm.record_date" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="往来单位">
          <el-select v-model="createForm.counterparty_type" style="width: 140px">
            <el-option label="无" value="none" />
            <el-option label="客户" value="customer" />
            <el-option label="供应商" value="supplier" />
          </el-select>
          <el-select
            v-if="createForm.counterparty_type !== 'none'"
            v-model="createForm.counterparty_id"
            filterable
            clearable
            :loading="partnerLoading"
            :placeholder="createForm.counterparty_type === 'supplier' ? '选择供应商' : '选择客户'"
            style="margin-left: 12px; width: 260px"
          >
            <el-option
              v-for="item in partnerOptions"
              :key="item.id"
              :label="`${item.code} ${item.name}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="会计科目">
          <el-input v-model="createForm.account_subject" maxlength="64" />
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

    <el-dialog v-model="reviewVisible" title="审核财务记录" width="460px">
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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { financeApi, masterApi } from '@/api'
import { useUserStore } from '@/stores/user'
import {
  DOC_STATUS,
  FINANCE_RECORD_TYPE,
  formatDate,
  formatMoney,
  labelOf,
  tagOf,
} from '@/utils/dict'
import { hasPermission } from '@/utils/permission'

const userStore = useUserStore()
const canCreate = computed(
  () =>
    hasPermission(userStore.me?.permissions, 'finance_record:create') &&
    !userStore.positionCodes.includes('cashier'),
)
const canReview = computed(() =>
  hasPermission(userStore.me?.permissions, 'finance_record:review'),
)
const isMine = (row) => row.created_by === userStore.me?.id

const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const total = ref(0)
const dateRange = ref([])

const query = reactive({ keyword: '', record_type: '', status: '', page: 1, page_size: 20 })

const createRecordTypes = computed(() =>
  Object.fromEntries(
    Object.entries(FINANCE_RECORD_TYPE).filter(
      ([key]) => key !== 'income_reversal' && key !== 'cost_reversal',
    ),
  ),
)

const createVisible = ref(false)
const partnerOptions = ref([])
const partnerLoading = ref(false)
const createForm = reactive({
  record_type: 'expense',
  amount: 0,
  record_date: '',
  counterparty_type: 'none',
  counterparty_id: undefined,
  account_subject: '',
  remark: '',
})

async function loadPartners(type) {
  createForm.counterparty_id = undefined
  if (type === 'none') {
    partnerOptions.value = []
    return
  }
  partnerLoading.value = true
  try {
    const api = type === 'supplier' ? masterApi.suppliers : masterApi.customers
    const data = await api.list({ status: 'active', page: 1, page_size: 100 })
    partnerOptions.value = Array.isArray(data) ? data : data?.items || []
  } catch {
    partnerOptions.value = []
  } finally {
    partnerLoading.value = false
  }
}

watch(() => createForm.counterparty_type, loadPartners)

const reviewVisible = ref(false)
const reviewTarget = ref(null)
const reviewForm = reactive({ decision: 'approve', comment: '' })

async function load() {
  loading.value = true
  try {
    const data = await financeApi.records({
      ...query,
      start_date: dateRange.value?.[0] || undefined,
      end_date: dateRange.value?.[1] || undefined,
    })
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
  createForm.record_type = 'expense'
  createForm.amount = 0
  createForm.record_date = new Date().toISOString().slice(0, 10)
  createForm.counterparty_type = 'none'
  createForm.counterparty_id = undefined
  partnerOptions.value = []
  createForm.account_subject = ''
  createForm.remark = ''
  createVisible.value = true
}

async function save() {
  if (!createForm.amount) {
    ElMessage.warning('请输入金额')
    return
  }
  if (createForm.counterparty_type !== 'none' && !createForm.counterparty_id) {
    ElMessage.warning(
      createForm.counterparty_type === 'supplier' ? '请选择供应商' : '请选择客户',
    )
    return
  }
  saving.value = true
  try {
    const created = await financeApi.createRecord({
      record_type: createForm.record_type,
      amount: createForm.amount,
      record_date: createForm.record_date || null,
      counterparty_type: createForm.counterparty_type,
      counterparty_id: createForm.counterparty_id || null,
      account_subject: createForm.account_subject || null,
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
      `确认${action}财务记录 ${reviewTarget.value.record_no}？`,
      '提示',
      { type: 'warning' },
    )
  } catch {
    return
  }
  saving.value = true
  try {
    await financeApi.reviewRecord(reviewTarget.value.id, {
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

async function voidRecord(row) {
  let reason = ''
  try {
    const result = await ElMessageBox.prompt('请输入作废原因', '作废记录', {
      inputValidator: (value) => (value && value.trim() ? true : '作废原因必填'),
    })
    reason = result.value
  } catch {
    return
  }
  try {
    await financeApi.voidRecord(row.id, { version: row.version, reason })
    ElMessage.success('已作废')
    await load()
  } catch {
    // 拦截器已提示
  }
}

onMounted(load)
</script>

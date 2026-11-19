<template>
  <div class="page">
    <div class="page-card">
      <div class="toolbar">
        <el-select v-model="query.status" placeholder="状态" clearable style="width: 130px">
          <el-option v-for="(item, key) in DOC_STATUS" :key="key" :label="item.label" :value="key" />
        </el-select>
        <el-input
          v-model="query.keyword"
          placeholder="单据号搜索"
          clearable
          style="width: 200px"
          @keyup.enter="reload"
        />
        <el-button type="primary" @click="reload">查询</el-button>
        <div class="toolbar-spacer"></div>
        <el-button v-if="canCreate" type="primary" plain @click="openCreate">
          新建{{ title }}
        </el-button>
      </div>

      <el-table v-loading="loading" :data="rows" size="small">
        <el-table-column prop="order_no" label="单据号" width="170" />
        <el-table-column :label="partyLabel" min-width="160">
          <template #default="{ row }">
            {{ isPurchase ? row.supplier_name : row.customer_name }}
          </template>
        </el-table-column>
        <el-table-column label="单据日期" width="110">
          <template #default="{ row }">{{ formatDate(row.order_date) }}</template>
        </el-table-column>
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row }">¥{{ formatMoney(row.total_amount) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="tagOf(DOC_STATUS, row.status).type" size="small">
              {{ tagOf(DOC_STATUS, row.status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="履约" width="100">
          <template #default="{ row }">
            <el-tag :type="tagOf(FULFILLMENT_STATUS, row.fulfillment_status).type" size="small">
              {{ tagOf(FULFILLMENT_STATUS, row.fulfillment_status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="300">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button
              v-if="canCreate && isMine(row) && ['draft', 'rejected'].includes(row.status)"
              link
              type="primary"
              @click="submitOrder(row)"
            >
              提交
            </el-button>
            <el-button
              v-if="canReview && row.status === 'pending_review' && !isMine(row)"
              link
              type="warning"
              @click="openReview(row)"
            >
              审核
            </el-button>
            <el-button
              v-if="canCreateMovement && row.status === 'approved' && row.fulfillment_status !== 'completed'"
              link
              type="success"
              @click="createMovement(row)"
            >
              {{ isPurchase ? '生成入库单' : '生成出库单' }}
            </el-button>
            <el-button
              v-if="canReview && ['draft', 'pending_review', 'approved'].includes(row.status)"
              link
              type="danger"
              @click="voidOrder(row)"
            >
              作废
            </el-button>
          </template>
        </el-table-column>
        <template #empty>暂无单据</template>
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

    <el-dialog v-model="createVisible" :title="`新建${title}`" width="760px" destroy-on-close>
      <el-form label-width="96px">
        <el-form-item :label="partyLabel">
          <el-select v-model="createForm.partyId" filterable placeholder="请选择" style="width: 100%">
            <el-option
              v-for="item in parties"
              :key="item.id"
              :label="`${item.code} ${item.name}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="单据日期">
          <el-date-picker v-model="createForm.order_date" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item v-if="isPurchase" label="预计到货">
          <el-date-picker
            v-model="createForm.expected_date"
            type="date"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="createForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>

      <div class="toolbar">
        <strong>明细</strong>
        <div class="toolbar-spacer"></div>
        <el-button size="small" @click="addItem">添加一行</el-button>
      </div>
      <el-table :data="createForm.items" size="small">
        <el-table-column label="产品" min-width="220">
          <template #default="{ row }">
            <el-select
              v-model="row.product_id"
              filterable
              placeholder="选择产品"
              style="width: 100%"
              @change="(id) => onProductChange(row, id)"
            >
              <el-option
                v-for="product in products"
                :key="product.id"
                :label="`${product.code} ${product.name}`"
                :value="product.id"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="140">
          <template #default="{ row }">
            <el-input-number v-model="row.quantity" :min="0.001" :precision="3" :controls="false" />
          </template>
        </el-table-column>
        <el-table-column label="单价" width="140">
          <template #default="{ row }">
            <el-input-number v-model="row.unit_price" :min="0" :precision="2" :controls="false" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70">
          <template #default="{ $index }">
            <el-button link type="danger" @click="createForm.items.splice($index, 1)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存草稿</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" :title="`${title}详情`" width="720px">
      <el-descriptions v-if="detail" :column="2" border>
        <el-descriptions-item label="单据号">{{ detail.order_no }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          {{ tagOf(DOC_STATUS, detail.status).label }}
        </el-descriptions-item>
        <el-descriptions-item label="履约状态">
          {{ tagOf(FULFILLMENT_STATUS, detail.fulfillment_status).label }}
        </el-descriptions-item>
        <el-descriptions-item :label="partyLabel">
          {{ isPurchase ? detail.supplier_name : detail.customer_name }}
        </el-descriptions-item>
        <el-descriptions-item label="金额">¥{{ formatMoney(detail.total_amount) }}</el-descriptions-item>
        <el-descriptions-item label="单据日期">{{ formatDate(detail.order_date) }}</el-descriptions-item>
        <el-descriptions-item v-if="isPurchase" label="预计到货">
          {{ formatDate(detail.expected_date) }}
        </el-descriptions-item>
        <el-descriptions-item label="备注">{{ detail.remark || '-' }}</el-descriptions-item>
        <el-descriptions-item label="作废原因">{{ detail.void_reason || '-' }}</el-descriptions-item>
      </el-descriptions>
      <el-table :data="detail?.items || []" size="small" class="mt-12">
        <el-table-column prop="product_name" label="产品" min-width="160" />
        <el-table-column prop="line_no" label="行号" width="70" />
        <el-table-column prop="quantity" label="数量" width="90" />
        <el-table-column prop="executed_quantity" label="已执行" width="90" />
        <el-table-column prop="remaining_quantity" label="剩余" width="90" />
        <el-table-column prop="unit_price" label="单价" width="100" />
        <el-table-column prop="amount" label="金额" width="120" />
        <template #empty>暂无明细</template>
      </el-table>
    </el-dialog>

    <el-dialog v-model="reviewVisible" :title="`审核${title}`" width="460px">
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
import { useRoute, useRouter } from 'vue-router'

import { masterApi, purchaseApi, salesApi } from '@/api'
import { useUserStore } from '@/stores/user'
import {
  DOC_STATUS,
  FULFILLMENT_STATUS,
  formatDate,
  formatDateTime,
  formatMoney,
  tagOf,
} from '@/utils/dict'
import { hasPermission } from '@/utils/permission'

const props = defineProps({
  mode: { type: String, default: 'purchase' },
})

const isPurchase = computed(() => props.mode === 'purchase')
const title = computed(() => (isPurchase.value ? '采购单' : '销售单'))
const partyLabel = computed(() => (isPurchase.value ? '供应商' : '客户'))
const api = computed(() => (isPurchase.value ? purchaseApi : salesApi))

const userStore = useUserStore()
const route = useRoute()
const router = useRouter()
const permissionResource = computed(() =>
  isPurchase.value ? 'purchase_order' : 'sales_order',
)
const canCreate = computed(() =>
  hasPermission(userStore.me?.permissions, `${permissionResource.value}:create`),
)
const canReview = computed(() =>
  hasPermission(userStore.me?.permissions, `${permissionResource.value}:review`),
)
const canCreateMovement = computed(() =>
  hasPermission(userStore.me?.permissions, 'inventory:create'),
)
const isMine = (row) => row.created_by === userStore.me?.id

const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const total = ref(0)
const parties = ref([])
const products = ref([])

const query = reactive({ status: '', keyword: '', page: 1, page_size: 20 })

const createVisible = ref(false)
const createForm = reactive({
  partyId: null,
  order_date: '',
  expected_date: '',
  remark: '',
  items: [],
})

const detailVisible = ref(false)
const detail = ref(null)

const reviewVisible = ref(false)
const reviewForm = reactive({ decision: 'approve', comment: '' })
const reviewTarget = ref(null)

async function load() {
  loading.value = true
  try {
    const data = await api.value.list({ ...query })
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

async function loadOptions() {
  try {
    const [partyData, productData] = await Promise.all([
      isPurchase.value ? masterApi.suppliers.list({ page: 1, page_size: 100 }) : masterApi.customers.list({ page: 1, page_size: 100 }),
      masterApi.products.list({ page: 1, page_size: 100 }),
    ])
    parties.value = partyData?.items || []
    products.value = productData?.items || []
  } catch {
    parties.value = []
    products.value = []
  }
}

function openCreate() {
  createForm.partyId = null
  createForm.order_date = new Date().toISOString().slice(0, 10)
  createForm.expected_date = ''
  createForm.remark = ''
  createForm.items = [{ product_id: null, quantity: 1, unit_price: 0 }]
  createVisible.value = true
}

function addItem() {
  createForm.items.push({ product_id: null, quantity: 1, unit_price: 0 })
}

function onProductChange(row, productId) {
  const product = products.value.find((item) => item.id === productId)
  if (!product) return
  row.unit_price = Number(isPurchase.value ? product.purchase_price : product.sale_price) || 0
}

async function save() {
  if (!createForm.partyId) {
    ElMessage.warning(`请选择${partyLabel.value}`)
    return
  }
  if (!createForm.items.length || createForm.items.some((item) => !item.product_id)) {
    ElMessage.warning('请完善单据明细')
    return
  }
  const payload = {
    order_date: createForm.order_date || null,
    remark: createForm.remark || null,
    items: createForm.items.map((item) => ({
      product_id: item.product_id,
      quantity: item.quantity,
      unit_price: item.unit_price,
    })),
  }
  if (isPurchase.value) {
    payload.supplier_id = createForm.partyId
    payload.expected_date = createForm.expected_date || null
  } else {
    payload.customer_id = createForm.partyId
  }
  saving.value = true
  try {
    await api.value.create(payload)
    ElMessage.success('草稿已保存')
    createVisible.value = false
    await load()
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

function createMovement(row) {
  router.push({
    path: '/stock-movements',
    query: {
      movement_type: isPurchase.value ? 'inbound' : 'outbound',
      source_type: isPurchase.value ? 'purchase_order' : 'sales_order',
      source_id: row.id,
    },
  })
}

async function openDetail(row) {
  detailVisible.value = true
  detail.value = null
  try {
    detail.value = await api.value.detail(row.id)
  } catch {
    detailVisible.value = false
  }
}

async function submitOrder(row) {
  try {
    await ElMessageBox.confirm(`确认提交单据 ${row.order_no}？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.value.submit(row.id, row.version)
    ElMessage.success('已提交，等待审核')
    await load()
  } catch {
    // 拦截器已提示
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
      `确认${action}单据 ${reviewTarget.value.order_no}？`,
      '提示',
      { type: 'warning' },
    )
  } catch {
    return
  }
  saving.value = true
  try {
    await api.value.review(reviewTarget.value.id, {
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

async function voidOrder(row) {
  let reason = ''
  try {
    const result = await ElMessageBox.prompt('请输入作废原因', '作废单据', {
      inputType: 'textarea',
      inputValidator: (value) => (value && value.trim() ? true : '作废原因必填'),
    })
    reason = result.value
  } catch {
    return
  }
  try {
    await api.value.void(row.id, { version: row.version, reason })
    ElMessage.success('已作废')
    await load()
  } catch {
    // 拦截器已提示
  }
}

onMounted(async () => {
  await Promise.all([load(), loadOptions()])
  const id = Number(route.query.id)
  if (id) openDetail({ id })
})
</script>

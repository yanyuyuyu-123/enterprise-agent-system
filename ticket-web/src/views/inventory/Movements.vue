<template>
  <div class="page">
    <div class="page-card">
      <div class="toolbar">
        <el-select v-model="query.status" placeholder="状态" clearable style="width: 140px">
          <el-option v-for="(item, key) in DOC_STATUS" :key="key" :label="item.label" :value="key" />
        </el-select>
        <el-select v-model="query.warehouse_id" placeholder="仓库" clearable style="width: 170px">
          <el-option v-for="item in warehouses" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
        <el-button type="primary" @click="reload">查询</el-button>
        <div class="toolbar-spacer"></div>
        <el-button v-if="canCreate" type="primary" plain @click="openCreate">新建出入库单</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" size="small">
        <el-table-column prop="movement_no" label="单据号" width="170" />
        <el-table-column label="类型" width="80">
          <template #default="{ row }">{{ labelOf(MOVEMENT_TYPE, row.movement_type) }}</template>
        </el-table-column>
        <el-table-column prop="warehouse_name" label="仓库" width="140" />
        <el-table-column label="来源" width="140">
          <template #default="{ row }">
            {{ SOURCE_TYPE[row.source_type] || row.source_type }}{{ row.source_id ? ` / ${row.source_id}` : '' }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="150">
          <template #default="{ row }">
            <el-tag :type="tagOf(DOC_STATUS, row.status).type" size="small">
              {{ tagOf(DOC_STATUS, row.status).label }}
            </el-tag>
            <el-tag v-if="row.is_reversed" type="danger" size="small" style="margin-left: 6px">已冲销</el-tag>
            <el-tag v-else-if="row.reversal_of_id" type="warning" size="small" style="margin-left: 6px">红字单</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="290">
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
            <span
              v-if="canCreate && !isMine(row) && ['draft', 'rejected'].includes(row.status)"
              style="margin-left: 8px; color: #909399; font-size: 12px"
            >
              仅制单人可提交
            </span>
            <el-button
              v-if="canUpdate && row.status === 'pending_execute'"
              link
              type="warning"
              @click="openExecute(row)"
            >
              执行
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
              v-if="canReverse(row)"
              link
              type="danger"
              @click="reverseMovement(row)"
            >
              冲销
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

    <el-dialog v-model="createVisible" title="新建出入库单" width="720px" destroy-on-close>
      <el-form label-width="96px">
        <el-form-item label="类型">
          <el-radio-group v-model="createForm.movement_type">
            <el-radio value="inbound">入库</el-radio>
            <el-radio value="outbound">出库</el-radio>
            <el-radio value="purchase_return">采购退货</el-radio>
            <el-radio value="sales_return">销售退货</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="仓库">
          <el-select v-model="createForm.warehouse_id" placeholder="选择仓库" style="width: 240px">
            <el-option v-for="item in warehouses" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源类型">
          <el-select v-model="createForm.source_type" style="width: 240px">
            <el-option
              v-for="item in sourceOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="createForm.source_type !== 'manual'" label="来源单据">
          <el-select
            v-model="createForm.source_id"
            filterable
            clearable
            :loading="sourceLoading"
            :placeholder="`选择已审核${createForm.source_type === 'sales_order' ? '销售单' : '采购单'}`"
            style="width: 240px"
          >
            <el-option
              v-for="item in sourceOrders"
              :key="item.id"
              :label="item.order_no"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="createForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>

      <div class="toolbar">
        <strong>明细</strong>
        <div class="toolbar-spacer"></div>
        <el-button size="small" @click="createForm.items.push({ product_id: null, quantity: 1 })">
          添加一行
        </el-button>
      </div>
      <el-table :data="createForm.items" size="small">
        <el-table-column label="产品" min-width="240">
          <template #default="{ row }">
            <el-select v-model="row.product_id" filterable placeholder="选择产品" style="width: 100%">
              <el-option
                v-for="product in products"
                :key="product.id"
                :label="`${product.code} ${product.name}`"
                :value="product.id"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="150">
          <template #default="{ row }">
            <el-input-number v-model="row.quantity" :min="0.001" :precision="3" :controls="false" />
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

    <el-dialog v-model="executeVisible" title="执行出入库" width="560px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="执行时填写实际数量，审核通过后才会变更库存。"
      />
      <el-table :data="executeForm.items" size="small" class="mt-12">
        <el-table-column label="产品" min-width="180">
          <template #default="{ row }">{{ row.product_name || row.product_id }}</template>
        </el-table-column>
        <el-table-column label="计划数量" width="110">
          <template #default="{ row }">{{ row.plan_quantity }}</template>
        </el-table-column>
        <el-table-column label="实际数量" width="150">
          <template #default="{ row }">
            <el-input-number v-model="row.quantity" :min="0" :precision="3" :controls="false" />
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="executeVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitExecute">提交执行</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" title="出入库单详情" width="680px">
      <el-descriptions v-if="detail" :column="2" border>
        <el-descriptions-item label="单据号">{{ detail.movement_no }}</el-descriptions-item>
        <el-descriptions-item label="类型">
          {{ labelOf(MOVEMENT_TYPE, detail.movement_type) }}
        </el-descriptions-item>
        <el-descriptions-item label="仓库">{{ detail.warehouse_name }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          {{ tagOf(DOC_STATUS, detail.status).label }}
        </el-descriptions-item>
        <el-descriptions-item label="来源">
          {{ SOURCE_TYPE[detail.source_type] || detail.source_type
          }}{{ detail.source_id ? ` / ${detail.source_id}` : '' }}
        </el-descriptions-item>
        <el-descriptions-item label="冲销状态">
          <template v-if="detail.is_reversed">已冲销（{{ formatDateTime(detail.reversed_at) }}）</template>
          <template v-else-if="detail.reversal_of_id">红字单，冲销原单 #{{ detail.reversal_of_id }}</template>
          <template v-else>正常</template>
        </el-descriptions-item>
        <el-descriptions-item label="备注">{{ detail.remark || '-' }}</el-descriptions-item>
        <el-descriptions-item label="作废原因">{{ detail.void_reason || '-' }}</el-descriptions-item>
      </el-descriptions>
      <el-table :data="detail?.items || []" size="small" class="mt-12">
        <el-table-column label="产品" min-width="160">
          <template #default="{ row }">{{ row.product_name || row.product_id }}</template>
        </el-table-column>
        <el-table-column prop="quantity" label="数量" width="100" />
        <el-table-column prop="before_quantity" label="执行前" width="100" />
        <el-table-column prop="after_quantity" label="执行后" width="100" />
        <template #empty>暂无明细</template>
      </el-table>
    </el-dialog>

    <el-dialog v-model="reviewVisible" title="审核出入库单" width="460px">
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
import { useRoute } from 'vue-router'

import { inventoryApi, masterApi, purchaseApi, salesApi } from '@/api'
import { useUserStore } from '@/stores/user'
import {
  DOC_STATUS,
  MOVEMENT_TYPE,
  formatDateTime,
  labelOf,
  tagOf,
} from '@/utils/dict'
import { hasPermission } from '@/utils/permission'

const userStore = useUserStore()
const route = useRoute()
const canCreate = computed(() =>
  hasPermission(userStore.me?.permissions, 'inventory:create'),
)
const canReview = computed(() =>
  hasPermission(userStore.me?.permissions, 'inventory:review'),
)
const canUpdate = computed(() =>
  hasPermission(userStore.me?.permissions, 'inventory:update'),
)
const isMine = (row) => row.created_by === userStore.me?.id
const canReadSalesOrder = computed(() =>
  hasPermission(userStore.me?.permissions, 'sales_order:read'),
)
const canReadPurchaseOrder = computed(() =>
  hasPermission(userStore.me?.permissions, 'purchase_order:read'),
)
const SOURCE_TYPE = {
  manual: '手工录入',
  purchase_order: '采购单',
  sales_order: '销售单',
  stock_check: '盘点单',
}

const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const total = ref(0)
const warehouses = ref([])
const products = ref([])

const query = reactive({ status: '', warehouse_id: undefined, page: 1, page_size: 20 })

const createVisible = ref(false)
const sourceOrders = ref([])
const sourceLoading = ref(false)
const createForm = reactive({
  movement_type: 'inbound',
  warehouse_id: undefined,
  source_type: 'manual',
  source_id: undefined,
  remark: '',
  items: [],
})

async function loadSourceOrders() {
  createForm.source_id = undefined
  if (createForm.source_type === 'manual') {
    sourceOrders.value = []
    return
  }
  sourceLoading.value = true
  try {
    const api = createForm.source_type === 'sales_order' ? salesApi : purchaseApi
    const data = await api.list({ status: 'approved', page: 1, page_size: 100 })
    sourceOrders.value = data?.items || []
  } catch {
    sourceOrders.value = []
  } finally {
    sourceLoading.value = false
  }
}

const sourceOptions = computed(() => {
  if (createForm.movement_type === 'purchase_return') {
    return [{ label: '采购单', value: 'purchase_order' }]
  }
  if (createForm.movement_type === 'sales_return') {
    return [{ label: '销售单', value: 'sales_order' }]
  }
  const options = [{ label: '手工录入', value: 'manual' }]
  if (createForm.movement_type === 'inbound' && canReadPurchaseOrder.value) {
    options.push({ label: '采购单', value: 'purchase_order' })
  }
  if (createForm.movement_type === 'outbound' && canReadSalesOrder.value) {
    options.push({ label: '销售单', value: 'sales_order' })
  }
  return options
})

watch(
  () => createForm.movement_type,
  () => {
    if (!sourceOptions.value.some((item) => item.value === createForm.source_type)) {
      createForm.source_type = sourceOptions.value[0].value
    }
    loadSourceOrders()
  },
)

watch(() => createForm.source_type, loadSourceOrders)

const executeVisible = ref(false)
const executeTarget = ref(null)
const executeForm = reactive({ items: [] })

const detailVisible = ref(false)
const detail = ref(null)

const reviewVisible = ref(false)
const reviewTarget = ref(null)
const reviewForm = reactive({ decision: 'approve', comment: '' })

async function load() {
  loading.value = true
  try {
    const data = await inventoryApi.movements({ ...query })
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
    const warehouseData = await masterApi.warehouses()
    warehouses.value = Array.isArray(warehouseData) ? warehouseData : warehouseData?.items || []
    if (canCreate.value) {
      const productData = await masterApi.products.list({ page: 1, page_size: 100 })
      products.value = productData?.items || []
    }
  } catch {
    warehouses.value = []
    products.value = []
  }
}

function openCreate() {
  createForm.movement_type = 'inbound'
  createForm.warehouse_id = undefined
  createForm.source_type = 'manual'
  createForm.source_id = undefined
  createForm.remark = ''
  createForm.items = [{ product_id: null, quantity: 1 }]
  sourceOrders.value = []
  createVisible.value = true
}

async function save() {
  if (!createForm.warehouse_id) {
    ElMessage.warning('请选择仓库')
    return
  }
  if (!createForm.items.length || createForm.items.some((item) => !item.product_id)) {
    ElMessage.warning('请完善明细')
    return
  }
  if (createForm.source_type !== 'manual' && !createForm.source_id) {
    ElMessage.warning('请选择来源单据')
    return
  }
  saving.value = true
  try {
    await inventoryApi.createMovement({
      movement_type: createForm.movement_type,
      warehouse_id: createForm.warehouse_id,
      source_type: createForm.source_type,
      source_id: createForm.source_type === 'manual' ? null : createForm.source_id,
      remark: createForm.remark || null,
      items: createForm.items,
    })
    ElMessage.success('草稿已保存，请在列表中点击「提交」')
    createVisible.value = false
    await load()
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

async function submitOrder(row) {
  try {
    await ElMessageBox.confirm(`确认提交单据 ${row.movement_no}？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    const updated = await inventoryApi.submitMovement(row.id, row.version)
    ElMessage.success(
      updated?.status === 'approved' ? '已完成，库存已更新' : '已提交，等待理货员执行',
    )
    await load()
  } catch {
    // 拦截器已提示
  }
}

async function openDetail(row) {
  detailVisible.value = true
  detail.value = null
  try {
    detail.value = await inventoryApi.movement(row.id)
  } catch {
    detailVisible.value = false
  }
}

async function openExecute(row) {
  executeTarget.value = row
  executeVisible.value = true
  executeForm.items = []
  try {
    const data = await inventoryApi.movement(row.id)
    executeForm.items = (data.items || []).map((item) => ({
      product_id: item.product_id,
      product_name: item.product_name,
      plan_quantity: item.quantity,
      quantity: Number(item.quantity),
    }))
  } catch {
    executeVisible.value = false
  }
}

async function submitExecute() {
  try {
    await ElMessageBox.confirm(
      `确认提交执行单据 ${executeTarget.value.movement_no}？提交后等待仓库负责人审核。`,
      '提示',
      { type: 'warning' },
    )
  } catch {
    return
  }
  saving.value = true
  try {
    await inventoryApi.executeMovement(executeTarget.value.id, {
      version: executeTarget.value.version,
      items: executeForm.items.map((item) => ({
        product_id: item.product_id,
        quantity: item.quantity,
      })),
    })
    ElMessage.success('已提交执行，等待仓库负责人审核')
    executeVisible.value = false
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
      `确认${action}单据 ${reviewTarget.value.movement_no}？${
        reviewForm.decision === 'approve' ? '通过后将立即变更库存。' : ''
      }`,
      '提示',
      { type: 'warning' },
    )
  } catch {
    return
  }
  saving.value = true
  try {
    await inventoryApi.reviewMovement(reviewTarget.value.id, {
      version: reviewTarget.value.version,
      decision: reviewForm.decision,
      comment: reviewForm.comment || null,
    })
    ElMessage.success(reviewForm.decision === 'approve' ? '审核通过，库存已更新' : '已驳回')
    reviewVisible.value = false
    await load()
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

function canReverse(row) {
  return (
    canReview.value &&
    row.status === 'approved' &&
    !row.is_reversed &&
    !row.reversal_of_id &&
    row.source_type !== 'stock_check'
  )
}

async function reverseMovement(row) {
  let reason
  try {
    const { value } = await ElMessageBox.prompt(
      `冲销后将生成红字单并回滚库存与财务记录：${row.movement_no}`,
      '填写冲销原因',
      {
        inputPlaceholder: '例如：数量录错',
        inputValidator: (value) => (value && value.trim() ? true : '冲销原因必填'),
        type: 'warning',
      },
    )
    reason = value.trim()
  } catch {
    return
  }
  saving.value = true
  try {
    const data = await inventoryApi.reverseMovement(row.id, {
      version: row.version,
      reason,
    })
    ElMessage.success(`已冲销，红字单 ${data.reversal_no}，库存与财务已回滚`)
    await load()
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await Promise.all([load(), loadOptions()])
  const id = Number(route.query.id)
  if (id) {
    openDetail({ id })
    return
  }
  const movementType = route.query.movement_type
  const sourceType = route.query.source_type
  if (movementType && sourceType) {
    openCreate()
    createForm.movement_type = movementType
    createForm.source_type = sourceType
    await loadSourceOrders()
    createForm.source_id = Number(route.query.source_id) || undefined
    createVisible.value = true
  }
})
</script>

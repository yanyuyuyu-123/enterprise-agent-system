<template>
  <div class="page">
    <div class="page-card">
      <div class="toolbar">
        <el-select v-model="query.status" placeholder="状态" clearable style="width: 140px">
          <el-option v-for="(item, key) in DOC_STATUS" :key="key" :label="item.label" :value="key" />
        </el-select>
        <el-button type="primary" @click="reload">查询</el-button>
        <div class="toolbar-spacer"></div>
        <el-button v-if="canCreate" type="primary" plain @click="openCreate">新建盘点单</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" size="small">
        <el-table-column prop="check_no" label="盘点单号" width="170" />
        <el-table-column prop="warehouse_name" label="仓库" width="160" />
        <el-table-column label="盘点日期" width="120">
          <template #default="{ row }">{{ formatDate(row.check_date) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="tagOf(DOC_STATUS, row.status).type" size="small">
              {{ tagOf(DOC_STATUS, row.status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button
              v-if="canCreate && isMine(row) && ['draft', 'rejected'].includes(row.status)"
              link
              type="primary"
              @click="submitCheck(row)"
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
              v-if="canReview && row.status === 'pending_review' && !isMine(row)"
              link
              type="warning"
              @click="openReview(row)"
            >
              审核
            </el-button>
          </template>
        </el-table-column>
        <template #empty>暂无盘点单</template>
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

    <el-dialog v-model="createVisible" title="新建盘点单" width="720px" destroy-on-close>
      <el-form label-width="96px">
        <el-form-item label="仓库">
          <el-select v-model="createForm.warehouse_id" placeholder="选择仓库" style="width: 240px">
            <el-option v-for="item in warehouses" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="盘点日期">
          <el-date-picker v-model="createForm.check_date" type="date" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="createForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>

      <div class="toolbar">
        <strong>盘点明细（实盘数量）</strong>
        <div class="toolbar-spacer"></div>
        <el-button size="small" @click="createForm.items.push({ product_id: null, actual_quantity: 0 })">
          添加一行
        </el-button>
      </div>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="账面数量为创建盘点单时的库存快照，差异 = 实盘 - 账面。"
      />
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
        <el-table-column label="账面数量" width="110">
          <template #default="{ row }">{{ bookMap[row.product_id] ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="实盘数量" width="150">
          <template #default="{ row }">
            <el-input-number v-model="row.actual_quantity" :min="0" :precision="3" :controls="false" />
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

    <el-dialog v-model="detailVisible" title="盘点单详情" width="680px">
      <el-descriptions v-if="detail" :column="2" border>
        <el-descriptions-item label="盘点单号">{{ detail.check_no }}</el-descriptions-item>
        <el-descriptions-item label="仓库">
          {{ detail.warehouse_name || detail.warehouse_id }}
        </el-descriptions-item>
        <el-descriptions-item label="盘点日期">{{ formatDate(detail.check_date) }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          {{ tagOf(DOC_STATUS, detail.status).label }}
        </el-descriptions-item>
        <el-descriptions-item label="备注">{{ detail.remark || '-' }}</el-descriptions-item>
      </el-descriptions>
      <el-table :data="detail?.items || []" size="small" class="mt-12">
        <el-table-column label="产品" min-width="160">
          <template #default="{ row }">{{ row.product_name || row.product_id }}</template>
        </el-table-column>
        <el-table-column prop="book_quantity" label="账面数量" width="100" />
        <el-table-column prop="actual_quantity" label="实盘数量" width="100" />
        <el-table-column label="差异" width="100">
          <template #default="{ row }">
            <span :style="{ color: Number(row.diff_quantity) === 0 ? '#909399' : Number(row.diff_quantity) > 0 ? '#67c23a' : '#f56c6c' }">
              {{ row.diff_quantity }}
            </span>
          </template>
        </el-table-column>
        <template #empty>暂无明细</template>
      </el-table>
    </el-dialog>

    <el-dialog v-model="reviewVisible" title="审核盘点单" width="460px">
      <el-form label-width="88px">
        <el-form-item label="审核结果">
          <el-radio-group v-model="reviewForm.decision">
            <el-radio value="approve">通过并生成调整单</el-radio>
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

import { inventoryApi, masterApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { DOC_STATUS, formatDate, formatDateTime, tagOf } from '@/utils/dict'
import { hasPermission } from '@/utils/permission'

const userStore = useUserStore()
const route = useRoute()
const canCreate = computed(() =>
  hasPermission(userStore.me?.permissions, 'inventory:create'),
)
const canReview = computed(() =>
  hasPermission(userStore.me?.permissions, 'inventory:review'),
)
const isMine = (row) => row.created_by === userStore.me?.id

const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const total = ref(0)
const warehouses = ref([])
const products = ref([])

const query = reactive({ status: '', page: 1, page_size: 20 })

const createVisible = ref(false)
const bookMap = ref({})
const createForm = reactive({
  warehouse_id: undefined,
  check_date: '',
  remark: '',
  items: [],
})

async function loadBook() {
  if (!createForm.warehouse_id) {
    bookMap.value = {}
    return
  }
  try {
    const rows = await inventoryApi.stock({ warehouse_id: createForm.warehouse_id })
    bookMap.value = Object.fromEntries(
      (rows || []).map((row) => [row.product_id, row.quantity]),
    )
  } catch {
    bookMap.value = {}
  }
}

watch(() => createForm.warehouse_id, loadBook)

const detailVisible = ref(false)
const detail = ref(null)

const reviewVisible = ref(false)
const reviewTarget = ref(null)
const reviewForm = reactive({ decision: 'approve', comment: '' })

async function load() {
  loading.value = true
  try {
    const data = await inventoryApi.checks({ ...query })
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
  bookMap.value = {}
  createForm.warehouse_id = undefined
  createForm.check_date = new Date().toISOString().slice(0, 10)
  createForm.remark = ''
  createForm.items = [{ product_id: null, actual_quantity: 0 }]
  createVisible.value = true
}

async function save() {
  if (!createForm.warehouse_id) {
    ElMessage.warning('请选择仓库')
    return
  }
  if (!createForm.items.length || createForm.items.some((item) => !item.product_id)) {
    ElMessage.warning('请完善盘点明细')
    return
  }
  saving.value = true
  try {
    await inventoryApi.createCheck({
      warehouse_id: createForm.warehouse_id,
      check_date: createForm.check_date || null,
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

async function submitCheck(row) {
  try {
    await ElMessageBox.confirm(`确认提交盘点单 ${row.check_no}？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    const updated = await inventoryApi.submitCheck(row.id, row.version)
    ElMessage.success(
      updated?.status === 'approved' ? '已完成，库存调整已生成' : '已提交，等待仓库负责人审核',
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
    detail.value = await inventoryApi.check(row.id)
  } catch {
    detailVisible.value = false
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
      `确认${action}盘点单 ${reviewTarget.value.check_no}？${
        reviewForm.decision === 'approve' ? '通过后将生成库存调整。' : ''
      }`,
      '提示',
      { type: 'warning' },
    )
  } catch {
    return
  }
  saving.value = true
  try {
    await inventoryApi.reviewCheck(reviewTarget.value.id, {
      version: reviewTarget.value.version,
      decision: reviewForm.decision,
      comment: reviewForm.comment || null,
    })
    ElMessage.success(
      reviewForm.decision === 'approve' ? '审核通过，库存调整已生成' : '已驳回',
    )
    reviewVisible.value = false
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
  if (id) openDetail({ id })
})
</script>

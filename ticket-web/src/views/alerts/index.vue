<template>
  <div class="page">
    <div class="page-card">
      <el-tabs v-model="tab">
        <el-tab-pane label="异常预警" name="alerts">
          <div class="toolbar">
            <el-select v-model="query.status" placeholder="处理状态" clearable style="width: 130px">
              <el-option
                v-for="(item, key) in ALERT_STATUS"
                :key="key"
                :label="item.label"
                :value="key"
              />
            </el-select>
            <el-select v-model="query.alert_type" placeholder="预警类型" clearable style="width: 180px">
              <el-option
                v-for="(label, key) in ALERT_TYPES"
                :key="key"
                :label="label"
                :value="key"
              />
            </el-select>
            <el-button type="primary" @click="reload">查询</el-button>
          </div>

          <el-table v-loading="loading" :data="rows" size="small">
            <el-table-column prop="alert_no" label="编号" width="150" />
            <el-table-column label="类型" width="140">
              <template #default="{ row }">{{ ALERT_TYPES[row.alert_type] || row.alert_type }}</template>
            </el-table-column>
            <el-table-column label="级别" width="80">
              <template #default="{ row }">
                <el-tag :type="levelTag(row.level)" size="small">
                  {{ ALERT_LEVEL[row.level] || row.level || '-' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
            <el-table-column prop="content" label="内容" min-width="240" show-overflow-tooltip />
            <el-table-column label="触发时间" width="160">
              <template #default="{ row }">{{ formatDateTime(row.triggered_at) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="tagOf(ALERT_STATUS, row.status).type" size="small">
                  {{ tagOf(ALERT_STATUS, row.status).label }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="处理说明" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">{{ row.handle_note || '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="140" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="row.status === 'open'"
                  link
                  type="warning"
                  @click="acknowledge(row)"
                >
                  认领
                </el-button>
                <el-button
                  v-if="row.status !== 'closed'"
                  link
                  type="primary"
                  @click="closeAlert(row)"
                >
                  关闭
                </el-button>
              </template>
            </el-table-column>
            <template #empty>暂无预警</template>
          </el-table>

          <div class="pager">
            <el-pagination
              v-model:current-page="query.page"
              v-model:page-size="query.page_size"
              :total="total"
              layout="total, prev, pager, next"
              @current-change="load"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane v-if="canReadSafeStock" label="安全库存" name="safe-stock">
          <div class="toolbar">
            <el-button v-if="canUpdateSafeStock" type="primary" @click="openSafeStock(null)">
              新增配置
            </el-button>
            <div class="toolbar-spacer" />
            <el-button @click="loadSafeStock">刷新</el-button>
          </div>

          <el-table v-loading="safeLoading" :data="safeRows" size="small">
            <el-table-column prop="product_code" label="产品编码" width="140" />
            <el-table-column prop="product_name" label="产品名称" min-width="180" show-overflow-tooltip />
            <el-table-column prop="warehouse_name" label="仓库" width="140" />
            <el-table-column prop="safe_quantity" label="安全库存" width="120" />
            <el-table-column label="更新时间" width="170">
              <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
            </el-table-column>
            <el-table-column v-if="canUpdateSafeStock" label="操作" width="90">
              <template #default="{ row }">
                <el-button link type="primary" @click="openSafeStock(row)">编辑</el-button>
              </template>
            </el-table-column>
            <template #empty>暂无安全库存配置，低于安全线的预警不会触发</template>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-dialog v-model="safeVisible" :title="safeForm.id ? '编辑安全库存' : '新增安全库存'" width="460px">
      <el-form label-width="90px">
        <el-form-item label="产品">
          <el-select
            v-model="safeForm.product_id"
            filterable
            :disabled="Boolean(safeForm.id)"
            placeholder="选择产品"
            style="width: 100%"
          >
            <el-option
              v-for="item in products"
              :key="item.id"
              :label="`${item.code} ${item.name}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="仓库">
          <el-select
            v-model="safeForm.warehouse_id"
            :disabled="Boolean(safeForm.id)"
            placeholder="选择仓库"
            style="width: 100%"
          >
            <el-option v-for="item in warehouses" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="安全库存">
          <el-input-number v-model="safeForm.safe_quantity" :min="0" :precision="2" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="safeVisible = false">取消</el-button>
        <el-button type="primary" :loading="safeSaving" @click="saveSafeStock">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { alertApi, masterApi } from '@/api'
import { useUserStore } from '@/stores/user'
import {
  ALERT_LEVEL,
  ALERT_STATUS,
  ALERT_TYPES,
  formatDateTime,
  tagOf,
} from '@/utils/dict'
import { hasAnyPermission } from '@/utils/permission'

const store = useUserStore()
const canReadSafeStock = computed(() =>
  hasAnyPermission(store.me?.permissions, ['safe_stock:read']),
)
const canUpdateSafeStock = computed(() =>
  hasAnyPermission(store.me?.permissions, ['safe_stock:update']),
)

const tab = ref('alerts')
const loading = ref(false)
const rows = ref([])
const total = ref(0)
const query = reactive({ status: '', alert_type: '', page: 1, page_size: 20 })

const safeLoading = ref(false)
const safeRows = ref([])
const safeVisible = ref(false)
const safeSaving = ref(false)
const products = ref([])
const warehouses = ref([])
const safeForm = reactive({ id: null, product_id: null, warehouse_id: null, safe_quantity: 0 })

function levelTag(level) {
  if (level === 'high') return 'danger'
  if (level === 'medium') return 'warning'
  return 'info'
}

async function load() {
  loading.value = true
  try {
    const data = await alertApi.list({
      ...query,
      status: query.status || undefined,
      alert_type: query.alert_type || undefined,
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

async function acknowledge(row) {
  try {
    await alertApi.acknowledge(row.id)
    ElMessage.success('已认领')
    await load()
  } catch {
    // 拦截器已提示
  }
}

async function closeAlert(row) {
  let note = ''
  try {
    const result = await ElMessageBox.prompt('请填写处理说明（500 字以内）', '关闭预警', {
      inputType: 'textarea',
      inputValidator: (value) => {
        const text = (value || '').trim()
        if (!text) return '处理说明必填'
        if (text.length > 500) return '处理说明不能超过 500 字'
        return true
      },
    })
    note = result.value.trim()
  } catch {
    return
  }
  try {
    await alertApi.close(row.id, { handle_note: note })
    ElMessage.success('已关闭')
    await load()
  } catch {
    // 拦截器已提示
  }
}

async function loadSafeStock() {
  if (!canReadSafeStock.value) return
  safeLoading.value = true
  try {
    const data = await alertApi.safeStock()
    safeRows.value = data?.items || []
  } catch {
    safeRows.value = []
  } finally {
    safeLoading.value = false
  }
}

async function loadOptions() {
  try {
    const [productData, warehouseData] = await Promise.all([
      masterApi.products.list({ page: 1, page_size: 100 }),
      masterApi.warehouses(),
    ])
    products.value = productData?.items || []
    warehouses.value = Array.isArray(warehouseData) ? warehouseData : warehouseData?.items || []
  } catch {
    products.value = []
    warehouses.value = []
  }
}

async function openSafeStock(row) {
  await loadOptions()
  safeForm.id = row?.id || null
  safeForm.product_id = row?.product_id || null
  safeForm.warehouse_id = row?.warehouse_id || null
  safeForm.safe_quantity = row ? Number(row.safe_quantity) : 0
  safeVisible.value = true
}

async function saveSafeStock() {
  if (!safeForm.product_id || !safeForm.warehouse_id) {
    ElMessage.warning('请选择产品和仓库')
    return
  }
  safeSaving.value = true
  try {
    await alertApi.saveSafeStock({
      product_id: safeForm.product_id,
      warehouse_id: safeForm.warehouse_id,
      safe_quantity: safeForm.safe_quantity,
    })
    ElMessage.success('已保存')
    safeVisible.value = false
    await loadSafeStock()
  } catch {
    // 拦截器已提示
  } finally {
    safeSaving.value = false
  }
}

watch(tab, (value) => {
  if (value === 'safe-stock' && !safeRows.value.length) loadSafeStock()
})

onMounted(() => {
  load()
  if (canReadSafeStock.value) loadSafeStock()
})
</script>

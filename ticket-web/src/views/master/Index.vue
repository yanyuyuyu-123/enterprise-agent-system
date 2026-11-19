<template>
  <div class="page">
    <div class="page-card">
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <el-tab-pane v-for="tab in visibleTabs" :key="tab.key" :label="tab.label" :name="tab.key">
          <div class="toolbar">
            <el-input
              v-model="keyword"
              placeholder="按编码 / 名称搜索"
              clearable
              style="width: 220px"
              @keyup.enter="reload"
            />
            <el-button type="primary" @click="reload">查询</el-button>
            <div class="toolbar-spacer"></div>
            <el-button v-if="canCreate(tab)" type="primary" plain @click="openCreate">
              新建{{ tab.label }}
            </el-button>
          </div>

          <el-table v-loading="loading" :data="rows" size="small">
            <el-table-column
              v-for="column in tab.columns"
              :key="column.prop"
              :prop="column.prop"
              :label="column.label"
              :width="column.width"
              :min-width="column.minWidth"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                {{ column.format ? column.format(row[column.prop]) : (row[column.prop] ?? '-') }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button v-if="canUpdate(tab)" link type="primary" @click="openEdit(row)">
                  编辑
                </el-button>
              </template>
            </el-table-column>
            <template #empty>暂无数据</template>
          </el-table>

          <div class="pager">
            <el-pagination
              v-model:current-page="page"
              :page-size="pageSize"
              :total="total"
              layout="total, prev, pager, next"
              @current-change="load"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="520px" destroy-on-close>
      <el-form label-width="96px">
        <el-form-item
          v-for="field in currentTab.fields"
          :key="field.prop"
          :label="field.label"
          :required="field.required"
        >
          <el-select
            v-if="field.type === 'select'"
            v-model="form[field.prop]"
            style="width: 100%"
            :disabled="field.createOnly && isEdit"
          >
            <el-option
              v-for="option in field.options"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-input-number
            v-else-if="field.type === 'number'"
            v-model="form[field.prop]"
            :min="0"
            :precision="2"
            :controls="false"
            style="width: 100%"
            :disabled="field.createOnly && isEdit"
          />
          <el-switch
            v-else-if="field.type === 'switch'"
            v-model="form[field.prop]"
            :disabled="field.createOnly && isEdit"
          />
          <el-input
            v-else
            v-model="form[field.prop]"
            :disabled="field.createOnly && isEdit"
            maxlength="128"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { masterApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { formatMoney } from '@/utils/dict'
import { hasPermission } from '@/utils/permission'

const userStore = useUserStore()

const PARTNER_STATUS = [
  { label: '启用', value: 'active' },
  { label: '停用', value: 'inactive' },
]
const PAYMENT_TYPE = [
  { label: '现结', value: 'cash' },
  { label: '账期', value: 'credit' },
]

const tabs = [
  {
    key: 'suppliers',
    label: '供应商',
    permission: 'supplier',
    api: masterApi.suppliers,
    columns: [
      { prop: 'code', label: '编码', width: 130 },
      { prop: 'name', label: '名称', minWidth: 180 },
      { prop: 'contact_name', label: '联系人', width: 100 },
      { prop: 'phone', label: '电话', width: 130 },
      {
        prop: 'payment_type',
        label: '结算方式',
        width: 100,
        format: (value) => (value === 'credit' ? '账期' : '现结'),
      },
      {
        prop: 'status',
        label: '状态',
        width: 90,
        format: (value) => (value === 'active' ? '启用' : '停用'),
      },
    ],
    fields: [
      { prop: 'code', label: '编码', required: true, createOnly: true },
      { prop: 'name', label: '名称', required: true },
      { prop: 'contact_name', label: '联系人' },
      { prop: 'phone', label: '电话' },
      { prop: 'address', label: '地址' },
      { prop: 'payment_type', label: '结算方式', type: 'select', options: PAYMENT_TYPE },
      { prop: 'status', label: '状态', type: 'select', options: PARTNER_STATUS },
    ],
  },
  {
    key: 'customers',
    label: '客户',
    permission: 'customer',
    api: masterApi.customers,
    columns: [
      { prop: 'code', label: '编码', width: 130 },
      { prop: 'name', label: '名称', minWidth: 180 },
      { prop: 'contact_name', label: '联系人', width: 100 },
      { prop: 'phone', label: '电话', width: 130 },
      {
        prop: 'credit_limit',
        label: '信用额度',
        width: 120,
        format: (value) => formatMoney(value),
      },
      {
        prop: 'status',
        label: '状态',
        width: 90,
        format: (value) => (value === 'active' ? '启用' : '停用'),
      },
    ],
    fields: [
      { prop: 'code', label: '编码', required: true, createOnly: true },
      { prop: 'name', label: '名称', required: true },
      { prop: 'contact_name', label: '联系人' },
      { prop: 'phone', label: '电话' },
      { prop: 'address', label: '地址' },
      { prop: 'credit_limit', label: '信用额度', type: 'number' },
      { prop: 'status', label: '状态', type: 'select', options: PARTNER_STATUS },
    ],
  },
  {
    key: 'products',
    label: '产品',
    permission: 'product',
    api: masterApi.products,
    columns: [
      { prop: 'code', label: '编码', width: 130 },
      { prop: 'name', label: '名称', minWidth: 160 },
      { prop: 'spec', label: '规格', width: 120 },
      { prop: 'unit', label: '单位', width: 80 },
      { prop: 'category', label: '分类', width: 110 },
      {
        prop: 'purchase_price',
        label: '采购价',
        width: 100,
        format: (value) => formatMoney(value),
      },
      { prop: 'sale_price', label: '销售价', width: 100, format: (value) => formatMoney(value) },
      {
        prop: 'is_active',
        label: '是否启用',
        width: 90,
        format: (value) => (value ? '启用' : '停用'),
      },
    ],
    fields: [
      { prop: 'code', label: '编码', required: true, createOnly: true },
      { prop: 'name', label: '名称', required: true },
      { prop: 'spec', label: '规格' },
      { prop: 'unit', label: '单位' },
      { prop: 'category', label: '分类' },
      { prop: 'purchase_price', label: '采购价', type: 'number' },
      { prop: 'sale_price', label: '销售价', type: 'number' },
      { prop: 'is_active', label: '是否启用', type: 'switch' },
    ],
  },
]

const visibleTabs = computed(() =>
  tabs.filter((tab) => hasPermission(userStore.me?.permissions, `${tab.permission}:read`)),
)
const canCreate = (tab) =>
  hasPermission(userStore.me?.permissions, `${tab.permission}:create`)
const canUpdate = (tab) =>
  hasPermission(userStore.me?.permissions, `${tab.permission}:update`)

const activeTab = ref(visibleTabs.value[0]?.key || '')
const keyword = ref('')
const page = ref(1)
const pageSize = 20
const total = ref(0)
const rows = ref([])
const loading = ref(false)

const dialogVisible = ref(false)
const isEdit = ref(false)
const saving = ref(false)
const editingId = ref(null)
const form = reactive({})

const currentTab = computed(() => tabs.find((tab) => tab.key === activeTab.value) || tabs[0])
const dialogTitle = computed(
  () => `${isEdit.value ? '编辑' : '新建'}${currentTab.value.label}`,
)

async function load() {
  loading.value = true
  try {
    const data = await currentTab.value.api.list({
      keyword: keyword.value || undefined,
      page: page.value,
      page_size: pageSize,
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
  page.value = 1
  load()
}

function onTabChange() {
  keyword.value = ''
  reload()
}

function resetForm() {
  for (const field of currentTab.value.fields) {
    form[field.prop] = field.type === 'number' ? 0 : field.type === 'switch' ? true : ''
  }
  form.status = 'active'
  form.payment_type = 'cash'
}

function openCreate() {
  isEdit.value = false
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  editingId.value = row.id
  resetForm()
  for (const field of currentTab.value.fields) {
    form[field.prop] = row[field.prop] ?? form[field.prop]
  }
  dialogVisible.value = true
}

async function save() {
  const config = currentTab.value
  for (const field of config.fields) {
    if (field.required && !form[field.prop]) {
      ElMessage.warning(`请填写${field.label}`)
      return
    }
  }
  const payload = {}
  for (const field of config.fields) {
    if (field.createOnly && isEdit.value) continue
    payload[field.prop] = form[field.prop]
  }
  saving.value = true
  try {
    if (isEdit.value) {
      await config.api.update(editingId.value, payload)
    } else {
      await config.api.create(payload)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await load()
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  if (activeTab.value) load()
})
</script>

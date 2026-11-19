<template>
  <div class="page">
    <div class="page-card">
      <div class="toolbar">
        <el-select v-model="query.status" placeholder="状态" clearable style="width: 130px">
          <el-option
            v-for="(item, key) in WORK_ORDER_STATUS"
            :key="key"
            :label="item.label"
            :value="key"
          />
        </el-select>
        <el-select v-model="query.category" placeholder="类别" clearable style="width: 130px">
          <el-option
            v-for="(label, key) in WORK_ORDER_CATEGORY"
            :key="key"
            :label="label"
            :value="key"
          />
        </el-select>
        <el-select v-model="query.priority" placeholder="优先级" clearable style="width: 120px">
          <el-option
            v-for="(item, key) in PRIORITY"
            :key="key"
            :label="item.label"
            :value="key"
          />
        </el-select>
        <el-input
          v-model="query.keyword"
          placeholder="工单号 / 标题"
          clearable
          style="width: 200px"
          @keyup.enter="reload"
        />
        <el-button type="primary" @click="reload">查询</el-button>
        <el-button @click="reset">重置</el-button>
        <div class="toolbar-spacer"></div>
        <el-button type="primary" plain @click="router.push('/work-orders/create')">
          新建工单
        </el-button>
      </div>

      <el-table v-loading="loading" :data="rows" @row-click="openDetail">
        <el-table-column prop="order_no" label="工单号" width="170" />
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="类别" width="110">
          <template #default="{ row }">{{ labelOf(WORK_ORDER_CATEGORY, row.category) }}</template>
        </el-table-column>
        <el-table-column label="优先级" width="90">
          <template #default="{ row }">
            <el-tag :type="tagOf(PRIORITY, row.priority).type" size="small" effect="plain">
              {{ tagOf(PRIORITY, row.priority).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="tagOf(WORK_ORDER_STATUS, row.status).type" size="small">
              {{ tagOf(WORK_ORDER_STATUS, row.status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="处理人" width="90">
          <template #default="{ row }">{{ row.assignee_id || '-' }}</template>
        </el-table-column>
        <el-table-column label="期限" width="150">
          <template #default="{ row }">
            <span :class="{ overdue: row.is_overdue }">{{ formatDateTime(row.due_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <template #empty>暂无工单</template>
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
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { workOrderApi } from '@/api'
import {
  PRIORITY,
  WORK_ORDER_CATEGORY,
  WORK_ORDER_STATUS,
  formatDateTime,
  labelOf,
  tagOf,
} from '@/utils/dict'

const router = useRouter()
const loading = ref(false)
const rows = ref([])
const total = ref(0)

const query = reactive({
  status: '',
  category: '',
  priority: '',
  keyword: '',
  page: 1,
  page_size: 20,
})

async function load() {
  loading.value = true
  try {
    const data = await workOrderApi.list({ ...query })
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

function reset() {
  query.status = ''
  query.category = ''
  query.priority = ''
  query.keyword = ''
  reload()
}

function openDetail(row) {
  router.push(`/work-orders/${row.id}`)
}

onMounted(load)
</script>

<style scoped>
.overdue {
  color: #d64545;
  font-weight: 600;
}

:deep(.el-table__row) {
  cursor: pointer;
}
</style>

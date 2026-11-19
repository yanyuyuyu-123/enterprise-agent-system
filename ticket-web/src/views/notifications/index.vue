<template>
  <div class="page">
    <div class="page-card">
      <div class="toolbar">
        <el-radio-group v-model="filter" @change="reload">
          <el-radio-button value="unread">未读</el-radio-button>
          <el-radio-button value="all">全部</el-radio-button>
        </el-radio-group>
        <div class="toolbar-spacer"></div>
        <span class="muted">未读 {{ unread }} 条</span>
        <el-button size="small" :disabled="!unread" @click="markAllRead">全部已读</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" size="small">
        <el-table-column label="类型" width="120">
          <template #default="{ row }">{{ labelOf(NOTIFICATION_TYPE, row.type) }}</template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column prop="content" label="内容" min-width="240" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_read ? 'info' : 'warning'" size="small">
              {{ row.is_read ? '已读' : '未读' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="150">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button
              v-if="!row.is_read"
              link
              type="primary"
              @click="markRead(row)"
            >
              标记已读
            </el-button>
            <el-button
              v-if="row.related_type === 'work_order' && row.related_id"
              link
              type="primary"
              @click="openOrder(row)"
            >
              查看工单
            </el-button>
            <el-button
              v-if="row.related_type === 'report' && row.related_id"
              link
              type="primary"
              @click="openReport(row)"
            >
              查看报告
            </el-button>
            <el-button
              v-if="row.related_type === 'stock_movement' && row.related_id"
              link
              type="primary"
              @click="openRelated(row, '/stock-movements')"
            >
              查看单据
            </el-button>
            <el-button
              v-if="row.related_type === 'stock_check' && row.related_id"
              link
              type="primary"
              @click="openRelated(row, '/stock-checks')"
            >
              查看盘点单
            </el-button>
          </template>
        </el-table-column>
        <template #empty>暂无通知</template>
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
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import { notificationApi } from '@/api'
import { NOTIFICATION_TYPE, formatDateTime, labelOf } from '@/utils/dict'

const router = useRouter()
const loading = ref(false)
const rows = ref([])
const total = ref(0)
const unread = ref(0)
const filter = ref('unread')
const page = ref(1)
const pageSize = 20

async function load() {
  loading.value = true
  try {
    const data = await notificationApi.list({
      is_read: filter.value === 'unread' ? false : undefined,
      page: page.value,
      page_size: pageSize,
    })
    rows.value = data?.items || []
    total.value = data?.total || 0
    unread.value = data?.unread ?? 0
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

async function markRead(row) {
  try {
    await notificationApi.read(row.id)
    ElMessage.success('已标记已读')
    await load()
  } catch {
    // 拦截器已提示
  }
}

async function markAllRead() {
  try {
    const data = await notificationApi.readAll()
    ElMessage.success(`已将 ${data?.updated ?? 0} 条通知标记为已读`)
    await load()
  } catch {
    // 拦截器已提示
  }
}

async function openOrder(row) {
  if (!row.is_read) {
    try {
      await notificationApi.read(row.id)
      row.is_read = true
    } catch {
      // 标记失败不阻止查看工单
    }
  }
  router.push(`/work-orders/${row.related_id}`)
}

async function openReport(row) {
  if (!row.is_read) {
    try {
      await notificationApi.read(row.id)
      row.is_read = true
    } catch {
      // 标记失败不阻止查看报告
    }
  }
  router.push({ path: '/reports', query: { report_id: row.related_id } })
}

async function openRelated(row, path) {
  if (!row.is_read) {
    try {
      await notificationApi.read(row.id)
      row.is_read = true
    } catch {
      // 标记失败不阻止查看单据
    }
  }
  router.push({ path, query: { id: row.related_id } })
}

onMounted(load)
</script>

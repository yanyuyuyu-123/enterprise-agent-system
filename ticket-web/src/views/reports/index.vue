<template>
  <div class="page">
    <div class="page-card">
      <div class="toolbar">
        <el-select v-model="query.report_type" placeholder="报告类型" clearable style="width: 130px">
          <el-option
            v-for="(label, key) in REPORT_TYPES"
            :key="key"
            :label="label"
            :value="key"
          />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          style="width: 250px"
        />
        <el-button type="primary" @click="reload">查询</el-button>
        <div class="toolbar-spacer" />
        <el-button v-if="isGeneralManager" @click="openViewers">查看名单</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" size="small">
        <el-table-column label="序号" width="70">
          <template #default="{ $index }">
            {{ (query.page - 1) * query.page_size + $index + 1 }}
          </template>
        </el-table-column>
        <el-table-column label="标题" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ reportTitle(row) }}</template>
        </el-table-column>
        <el-table-column label="类型" width="80">
          <template #default="{ row }">{{ REPORT_TYPES[row.report_type] || row.report_type }}</template>
        </el-table-column>
        <el-table-column label="统计周期" width="210">
          <template #default="{ row }">
            {{ formatDate(row.period_start) }} ~ {{ formatDate(row.period_end) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="tagOf(REPORT_STATUS, row.status).type" size="small">
              {{ tagOf(REPORT_STATUS, row.status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="生成时间" width="160">
          <template #default="{ row }">{{ formatDateTime(row.generated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">查看</el-button>
            <el-button link type="primary" @click="downloadReport(row)">下载</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无报告，报告会在每天 08:00 自动生成</template>
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
    </div>

    <el-dialog v-model="detailVisible" :title="detailTitle" width="960px" top="6vh">
      <iframe
        v-if="detail?.content"
        class="report-frame"
        :srcdoc="detail.content"
        sandbox="allow-same-origin"
      ></iframe>
      <div v-else class="muted">该报告没有可预览内容，请下载查看。</div>
    </el-dialog>

    <el-drawer v-model="viewerVisible" title="报告查看名单" size="420px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="名单内的用户可以查看全部报告，未在名单内的人需要 report:read 权限。"
        class="mb-12"
      />
      <el-select
        v-model="viewerIds"
        multiple
        filterable
        placeholder="选择可以查看报告的人"
        style="width: 100%"
      >
        <el-option
          v-for="item in candidates"
          :key="item.user_id"
          :label="`${item.name}（${item.employee_no}）`"
          :value="item.user_id"
        />
      </el-select>
      <div class="drawer-footer">
        <el-button @click="viewerVisible = false">取消</el-button>
        <el-button type="primary" :loading="viewerSaving" @click="saveViewers">保存</el-button>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute } from 'vue-router'

import { reportApi } from '@/api'
import { useUserStore } from '@/stores/user'
import {
  REPORT_STATUS,
  REPORT_TYPES,
  formatDate,
  formatDateTime,
  tagOf,
} from '@/utils/dict'

const store = useUserStore()
const route = useRoute()
const isGeneralManager = computed(() => store.positionCodes.includes('general_manager'))

const loading = ref(false)
const rows = ref([])
const total = ref(0)
const dateRange = ref([])
const query = reactive({ report_type: '', page: 1, page_size: 20 })

const detailVisible = ref(false)
const detail = ref(null)
const detailRow = ref(null)

const viewerVisible = ref(false)
const viewerSaving = ref(false)
const viewerIds = ref([])
const candidates = ref([])

const detailTitle = computed(() => (detailRow.value ? reportTitle(detailRow.value) : '报告详情'))

function reportTitle(row) {
  const type = REPORT_TYPES[row.report_type] || row.report_type
  return `${type} ${formatDate(row.period_start)} ~ ${formatDate(row.period_end)}`
}

async function load() {
  loading.value = true
  try {
    const data = await reportApi.list({
      ...query,
      report_type: query.report_type || undefined,
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

async function openDetail(row) {
  detailRow.value = row
  detailVisible.value = true
  detail.value = null
  try {
    detail.value = await reportApi.detail(row.id)
  } catch {
    detail.value = null
  }
}

function downloadReport(row) {
  reportApi.download(row.id, `${row.report_no}.html`)
}

async function openViewers() {
  viewerVisible.value = true
  try {
    const [current, all] = await Promise.all([
      reportApi.viewers(),
      reportApi.viewerCandidates(),
    ])
    candidates.value = all?.items || []
    viewerIds.value = (current?.items || []).map((item) => item.user_id)
  } catch {
    candidates.value = []
    viewerIds.value = []
  }
}

async function saveViewers() {
  viewerSaving.value = true
  try {
    await reportApi.saveViewers({ user_ids: viewerIds.value })
    ElMessage.success('名单已保存')
    viewerVisible.value = false
  } catch {
    // 拦截器已提示
  } finally {
    viewerSaving.value = false
  }
}

onMounted(async () => {
  await load()
  const reportId = Number(route.query.report_id)
  if (!reportId) return
  const row = rows.value.find((item) => item.id === reportId)
  if (row) openDetail(row)
})
</script>

<style scoped>
.mb-12 {
  margin-bottom: 12px;
}

.report-frame {
  width: 100%;
  height: 70vh;
  border: 1px solid #eef0f4;
  border-radius: 4px;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
</style>

<template>
  <div class="page">
    <div class="page-card">
      <div class="toolbar">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          style="width: 260px"
        />
        <el-select v-model="category" placeholder="工单类别" clearable style="width: 140px">
          <el-option
            v-for="(label, key) in WORK_ORDER_CATEGORY"
            :key="key"
            :label="label"
            :value="key"
          />
        </el-select>
        <el-button type="primary" :loading="loading" @click="load">统计</el-button>
      </div>

      <el-row :gutter="12">
        <el-col v-for="card in cards" :key="card.label" :span="24 / cards.length">
          <div class="stat-card">
            <div class="stat-label">{{ card.label }}</div>
            <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
          </div>
        </el-col>
      </el-row>
    </div>

    <el-row :gutter="12" class="mt-12">
      <el-col :span="10">
        <div class="page-card">
          <div class="card-title">状态分布</div>
          <div ref="pieRef" class="chart"></div>
        </div>
      </el-col>
      <el-col :span="14">
        <div class="page-card">
          <div class="card-title">类别工单量</div>
          <div ref="barRef" class="chart"></div>
        </div>
      </el-col>
    </el-row>

    <div class="page-card mt-12">
      <div class="card-title">
        重复问题（统计周期 {{ stats?.repeat?.period_days ?? '-' }} 天，共
        {{ stats?.repeat?.order_count ?? 0 }} 单）
      </div>
      <el-table :data="stats?.repeat?.groups || []" size="small">
        <el-table-column label="类别" width="140">
          <template #default="{ row }">{{ labelOf(WORK_ORDER_CATEGORY, row.category) }}</template>
        </el-table-column>
        <el-table-column prop="key" label="问题特征" min-width="240" show-overflow-tooltip />
        <el-table-column prop="count" label="出现次数" width="110" />
        <template #empty>暂无重复问题</template>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import * as echarts from 'echarts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { statsApi } from '@/api'
import { WORK_ORDER_CATEGORY, WORK_ORDER_STATUS, labelOf } from '@/utils/dict'

const loading = ref(false)
const stats = ref(null)
const dateRange = ref([])
const category = ref('')
const pieRef = ref()
const barRef = ref()

let pieChart = null
let barChart = null

const cards = computed(() => [
  { label: '工单总数', value: stats.value?.total ?? 0, color: '#1f4fc4' },
  { label: '已完成', value: stats.value?.completed ?? 0, color: '#16a34a' },
  {
    label: '完成率',
    value: `${Math.round((stats.value?.completion_rate ?? 0) * 100)}%`,
    color: '#2f6feb',
  },
  {
    label: '平均处理时长',
    value: `${stats.value?.avg_process_hours ?? 0} h`,
    color: '#d98a0b',
  },
  { label: '超时工单', value: stats.value?.overdue ?? 0, color: '#e0443e' },
])

const STATUS_LABEL = Object.fromEntries(
  Object.entries(WORK_ORDER_STATUS).map(([key, item]) => [key, item.label]),
)

function renderCharts() {
  if (!stats.value) return
  pieChart?.dispose()
  barChart?.dispose()
  pieChart = echarts.init(pieRef.value)
  barChart = echarts.init(barRef.value)

  pieChart.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [
      {
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '45%'],
        data: Object.entries(stats.value.by_status || {}).map(([key, value]) => ({
          name: labelOf(STATUS_LABEL, key),
          value,
        })),
      },
    ],
  })

  const categoryEntries = Object.entries(stats.value.by_category || {})
  barChart.setOption({
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: categoryEntries.map(([key]) => labelOf(WORK_ORDER_CATEGORY, key)),
    },
    yAxis: { type: 'value' },
    series: [
      {
        type: 'bar',
        barWidth: 40,
        itemStyle: { color: '#2f6feb', borderRadius: [6, 6, 0, 0] },
        data: categoryEntries.map(([, value]) => value),
      },
    ],
  })
}

function handleResize() {
  pieChart?.resize()
  barChart?.resize()
}

async function load() {
  loading.value = true
  try {
    stats.value = await statsApi.workOrders({
      start_at: dateRange.value?.[0] ? `${dateRange.value[0]}T00:00:00` : undefined,
      end_at: dateRange.value?.[1] ? `${dateRange.value[1]}T23:59:59` : undefined,
      category: category.value || undefined,
    })
    await nextTick()
    renderCharts()
  } catch {
    stats.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  pieChart?.dispose()
  barChart?.dispose()
})
</script>

<style scoped>
.stat-card {
  padding: 14px 16px;
  background: #fafbfc;
  border: 1px solid #eef0f4;
  border-radius: 6px;
}

.stat-label {
  font-size: 13px;
  color: #8a919f;
}

.stat-value {
  margin-top: 6px;
  font-size: 24px;
  font-weight: 600;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
}

.chart {
  height: 260px;
}
</style>

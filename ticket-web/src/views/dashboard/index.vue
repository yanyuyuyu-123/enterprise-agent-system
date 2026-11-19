<template>
  <div class="page">
    <el-row v-if="canStats" :gutter="12" class="top-row">
      <el-col :span="16">
        <div class="page-card finance-card">
          <div class="finance-head">
            <div>
              <div class="finance-title">财务情况</div>
              <div class="finance-sub">近 6 个月收入、成本与净利走势</div>
            </div>
            <span class="range-pill">近 6 个月</span>
          </div>
          <div ref="financeRef" class="chart-finance"></div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="page-card metric-panel">
          <div class="card-title">工单概览</div>
          <div class="metric-list">
            <div v-for="card in cards" :key="card.label" class="metric-row">
              <span class="metric-label">{{ card.label }}</span>
              <span class="metric-value" :style="{ color: card.color }">{{ card.value }}</span>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <div class="page-card mt-12">
      <div class="toolbar">
        <div class="card-title" style="margin: 0">最近工单</div>
        <div class="toolbar-spacer"></div>
        <el-button text type="primary" @click="router.push('/work-orders')">查看全部</el-button>
      </div>
      <el-table v-loading="loading" :data="orders" size="small">
        <el-table-column prop="order_no" label="工单号" width="170" />
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column label="类别" width="110">
          <template #default="{ row }">{{ labelOf(WORK_ORDER_CATEGORY, row.category) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="tagOf(WORK_ORDER_STATUS, row.status).type" size="small">
              {{ tagOf(WORK_ORDER_STATUS, row.status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button link type="primary" @click="router.push(`/work-orders/${row.id}`)">详情</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无工单</template>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import * as echarts from 'echarts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { statsApi, workOrderApi } from '@/api'
import { useUserStore } from '@/stores/user'
import {
  WORK_ORDER_CATEGORY,
  WORK_ORDER_STATUS,
  formatDateTime,
  labelOf,
  tagOf,
} from '@/utils/dict'
import { hasPermission } from '@/utils/permission'

const router = useRouter()
const store = useUserStore()
const loading = ref(false)
const stats = ref(null)
const finance = ref(null)
const orders = ref([])
const financeRef = ref()

const canStats = computed(() => hasPermission(store.me?.permissions, 'report:read'))

let financeChart = null
let chartObserver = null

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

function renderCharts() {
  financeChart?.dispose()
  financeChart = echarts.init(financeRef.value)

  const items = finance.value?.items || []
  const months = items.map((item) => `${item.period.slice(5)} 月`)
  const cost = items.map((item) => Number(item.cost))
  const profit = items.map((item) => Number(item.net_profit))
  const revenue = items.map((item) => Number(item.revenue))
  financeChart.setOption({
    grid: { left: 48, right: 16, top: 34, bottom: 26 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line', lineStyle: { color: '#f97316', type: 'dashed' } },
      backgroundColor: '#fff',
      borderColor: '#eef0f4',
      borderWidth: 1,
      padding: [10, 14],
      textStyle: { color: '#344054', fontSize: 12 },
      extraCssText: 'box-shadow: 0 8px 24px rgba(16, 24, 40, 0.12); border-radius: 10px;',
      formatter: (params) => {
        const index = params[0].dataIndex
        const total = revenue[index]
        const rate = total ? ((profit[index] / total) * 100).toFixed(1) : '0.0'
        return [
          `<div style="font-weight:600;margin-bottom:6px">${months[index]}</div>`,
          `收入 <b>${(total / 10000).toFixed(1)} 万</b>`,
          `成本 <b>${(cost[index] / 10000).toFixed(1)} 万</b>`,
          `净利 <b>${(profit[index] / 10000).toFixed(1)} 万</b>`,
          `<span style="color:#98a2b3">毛利率 ${rate}%</span>`,
        ].join('<br/>')
      },
    },
    legend: {
      top: 0,
      right: 0,
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      itemGap: 16,
      textStyle: { color: '#667085', fontSize: 12 },
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: months,
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: '#98a2b3', fontSize: 11, margin: 14 },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: '#98a2b3',
        fontSize: 11,
        formatter: (value) => (value >= 10000 ? `${value / 10000}万` : value),
      },
      splitLine: { lineStyle: { type: 'dotted', color: '#e8ecf3' } },
    },
    series: [
      {
        name: '收入',
        type: 'line',
        smooth: true,
        showSymbol: false,
        symbol: 'circle',
        symbolSize: 7,
        lineStyle: { width: 2, color: '#f97316' },
        itemStyle: { color: '#f97316' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(249, 115, 22, 0.28)' },
            { offset: 1, color: 'rgba(249, 115, 22, 0)' },
          ]),
        },
        data: revenue,
      },
      {
        name: '成本',
        type: 'line',
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.5, color: '#c7ccd6', type: 'dashed' },
        itemStyle: { color: '#c7ccd6' },
        data: cost,
      },
      {
        name: '净利',
        type: 'line',
        smooth: true,
        showSymbol: false,
        symbol: 'circle',
        symbolSize: 7,
        lineStyle: { width: 2, color: '#344054' },
        itemStyle: { color: '#344054', borderColor: '#fff', borderWidth: 2 },
        data: profit,
      },
    ],
  })
}

function handleResize() {
  financeChart?.resize()
}

onMounted(async () => {
  loading.value = true
  try {
    const [statsData, listData, financeData] = await Promise.all([
      canStats.value ? statsApi.workOrders({}) : Promise.resolve(null),
      workOrderApi.list({ page: 1, page_size: 5 }),
      canStats.value
        ? statsApi.financeTrend({ months: 6 }).catch(() => null)
        : Promise.resolve(null),
    ])
    stats.value = statsData
    finance.value = financeData
    orders.value = listData?.items || []
    await nextTick()
    if (canStats.value) {
      renderCharts()
      chartObserver = new ResizeObserver(() => financeChart?.resize())
      chartObserver.observe(financeRef.value)
    }
    window.addEventListener('resize', handleResize)
  } catch {
    // 请求拦截器已提示
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chartObserver?.disconnect()
  financeChart?.dispose()
})
</script>

<style scoped>
.page {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 56px);
}

.top-row {
  flex: 1;
}

.top-row :deep(.el-col) {
  display: flex;
}

.finance-card {
  display: flex;
  flex: 1;
  flex-direction: column;
  height: 100%;
  border-radius: 16px;
}

.metric-panel {
  display: flex;
  flex: 1;
  flex-direction: column;
  height: 100%;
  min-width: 0;
}

.metric-list {
  display: flex;
  flex: 1;
  flex-direction: column;
  justify-content: center;
  gap: 18px;
}

.metric-row {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  column-gap: 16px;
  padding: 6px 2px;
  border-bottom: 1px solid #eef0f4;
}

.metric-row:last-child {
  border-bottom: none;
}

.metric-label {
  font-size: 13px;
  line-height: 1;
  color: #8a919f;
}

.metric-value {
  font-size: 20px;
  font-weight: 600;
  line-height: 1;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
}

.finance-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.range-pill {
  padding: 4px 10px;
  font-size: 12px;
  color: #667085;
  background: #f4f6f9;
  border-radius: 999px;
}

.finance-title {
  font-size: 16px;
  font-weight: 600;
  color: #1d2939;
}

.finance-sub {
  margin-top: 4px;
  font-size: 12px;
  color: #98a2b3;
}

.chart-finance {
  flex: 1;
  min-height: 220px;
  margin-top: 8px;
}
</style>

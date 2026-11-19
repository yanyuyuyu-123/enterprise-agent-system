<template>
  <div class="page">
    <div class="page-card">
      <el-tabs v-model="activeTab" @tab-change="reload">
        <el-tab-pane label="业务操作日志" name="operation" />
        <el-tab-pane label="Agent 调用日志" name="agent" />
        <el-tab-pane label="系统日志" name="system" />
      </el-tabs>

      <div class="toolbar">
        <template v-if="activeTab !== 'agent'">
          <el-select v-model="query.log_level" placeholder="级别" clearable style="width: 120px">
            <el-option label="普通" value="normal" />
            <el-option label="重要" value="important" />
            <el-option label="关键" value="critical" />
          </el-select>
          <el-input v-model="query.resource" placeholder="资源" clearable style="width: 150px" />
          <el-input v-model="query.action" placeholder="动作" clearable style="width: 130px" />
        </template>
        <template v-else>
          <el-input v-model="query.tool_name" placeholder="工具名称" clearable style="width: 180px" />
          <el-select v-model="query.success" placeholder="结果" clearable style="width: 120px">
            <el-option label="成功" :value="true" />
            <el-option label="失败" :value="false" />
          </el-select>
        </template>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          style="width: 250px"
        />
        <el-button type="primary" @click="reload">查询</el-button>
      </div>

      <el-table v-if="activeTab !== 'agent'" v-loading="loading" :data="rows" size="small">
        <el-table-column type="expand">
          <template #default="{ row }">
            <pre class="detail-json">{{ JSON.stringify(row.detail, null, 2) }}</pre>
          </template>
        </el-table-column>
        <el-table-column label="级别" width="80">
          <template #default="{ row }">
            <el-tag
              :type="row.log_level === 'critical' ? 'danger' : row.log_level === 'important' ? 'warning' : 'info'"
              size="small"
            >
              {{ LEVEL_LABEL[row.log_level] || row.log_level || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="user_name" label="操作人" width="110" />
        <el-table-column prop="resource" label="资源" width="150" />
        <el-table-column prop="action" label="动作" width="110" />
        <el-table-column label="对象" width="140">
          <template #default="{ row }">
            {{ row.target_type ? `${row.target_type} / ${row.target_id || '-'}` : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="result" label="结果" width="80" />
        <el-table-column prop="request_id" label="Request ID" width="180" show-overflow-tooltip />
        <el-table-column label="时间" width="150">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <template #empty>暂无日志</template>
      </el-table>

      <el-table v-else v-loading="loading" :data="rows" size="small">
        <el-table-column prop="session_id" label="会话" width="170" show-overflow-tooltip />
        <el-table-column prop="agent_name" label="Agent" width="130" />
        <el-table-column prop="intent" label="意图" width="140" />
        <el-table-column prop="tool_name" label="工具" width="170" />
        <el-table-column prop="input_summary" label="入参摘要" min-width="200" show-overflow-tooltip />
        <el-table-column prop="output_summary" label="输出摘要" min-width="200" show-overflow-tooltip />
        <el-table-column label="结果" width="80">
          <template #default="{ row }">
            <el-tag :type="row.success ? 'success' : 'danger'" size="small">
              {{ row.success ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="latency_ms" label="耗时(ms)" width="100" />
        <el-table-column label="时间" width="150">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <template #empty>暂无日志</template>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :total="total"
          :page-sizes="[20, 50, 100]"
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

import { logApi } from '@/api'
import { formatDateTime } from '@/utils/dict'

const LEVEL_LABEL = { normal: '普通', important: '重要', critical: '关键' }

const activeTab = ref('operation')
const loading = ref(false)
const rows = ref([])
const total = ref(0)
const dateRange = ref([])

const query = reactive({
  log_level: '',
  resource: '',
  action: '',
  tool_name: '',
  success: undefined,
  page: 1,
  page_size: 20,
})

async function load() {
  loading.value = true
  try {
    const params = {
      ...query,
      log_level: query.log_level || undefined,
      resource: query.resource || undefined,
      action: query.action || undefined,
      tool_name: query.tool_name || undefined,
      success: query.success,
      start_at: dateRange.value?.[0] ? `${dateRange.value[0]}T00:00:00` : undefined,
      end_at: dateRange.value?.[1] ? `${dateRange.value[1]}T23:59:59` : undefined,
    }
    const data = await logApi[activeTab.value](params)
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

onMounted(load)
</script>

<style scoped>
.detail-json {
  margin: 0;
  padding: 8px 16px;
  background: #fafbfc;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>

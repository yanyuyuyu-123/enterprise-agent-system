<template>
  <div class="page">
    <div class="page-card">
      <div class="toolbar">
        <el-select v-model="warehouseId" placeholder="仓库" clearable style="width: 180px">
          <el-option v-for="item in warehouses" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
        <el-input
          v-model="keyword"
          placeholder="产品编码 / 名称"
          clearable
          style="width: 220px"
          @keyup.enter="load"
        />
        <el-button type="primary" @click="load">查询</el-button>
        <el-button @click="reset">重置</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" size="small">
        <el-table-column prop="product_code" label="产品编码" width="140" />
        <el-table-column prop="product_name" label="产品名称" min-width="180" />
        <el-table-column prop="unit" label="单位" width="80" />
        <el-table-column prop="warehouse_name" label="仓库" width="140" />
        <el-table-column prop="quantity" label="结存数量" width="130" align="right" />
        <el-table-column label="更新时间" width="160">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <template #empty>暂无库存数据</template>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'

import { inventoryApi, masterApi } from '@/api'
import { formatDateTime } from '@/utils/dict'

const loading = ref(false)
const rows = ref([])
const warehouses = ref([])
const warehouseId = ref()
const keyword = ref('')

async function loadWarehouses() {
  try {
    const data = await masterApi.warehouses()
    warehouses.value = Array.isArray(data) ? data : data?.items || []
  } catch {
    warehouses.value = []
  }
}

async function load() {
  loading.value = true
  try {
    const data = await inventoryApi.stock({
      warehouse_id: warehouseId.value || undefined,
      keyword: keyword.value || undefined,
    })
    rows.value = Array.isArray(data) ? data : data?.items || []
  } catch {
    rows.value = []
  } finally {
    loading.value = false
  }
}

function reset() {
  warehouseId.value = undefined
  keyword.value = ''
  load()
}

onMounted(() => {
  loadWarehouses()
  load()
})
</script>

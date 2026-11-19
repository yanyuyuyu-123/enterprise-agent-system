<template>
  <div class="page">
    <div class="page-card">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="后端暂未提供组织接口（/org/departments、/org/positions），页面已按规范预留，接口上线后可直接对接。"
        class="mb-12"
      />

      <el-tabs v-model="tab">
        <el-tab-pane label="部门" name="department">
          <div class="toolbar">
            <el-input placeholder="部门名称" style="width: 200px" disabled />
            <el-button type="primary" disabled>新建部门</el-button>
          </div>
          <el-table :data="[]" size="small">
            <el-table-column prop="code" label="编码" width="140" />
            <el-table-column prop="name" label="名称" min-width="180" />
            <el-table-column prop="parent_name" label="上级部门" width="160" />
            <el-table-column prop="manager_name" label="负责人" width="120" />
            <el-table-column prop="status" label="状态" width="90" />
            <el-table-column label="操作" width="120" />
            <template #empty>暂无部门数据</template>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="岗位" name="position">
          <div class="toolbar">
            <el-input placeholder="岗位名称" style="width: 200px" disabled />
            <el-button type="primary" disabled>新建岗位</el-button>
          </div>
          <el-table :data="[]" size="small">
            <el-table-column prop="code" label="岗位编码" width="160" />
            <el-table-column prop="name" label="岗位名称" min-width="180" />
            <el-table-column prop="department_name" label="所属部门" width="160" />
            <el-table-column prop="level" label="层级" width="90" />
            <el-table-column label="权限" width="120" />
            <template #empty>暂无岗位数据</template>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const tab = ref('department')
</script>

<style scoped>
.mb-12 {
  margin-bottom: 12px;
}
</style>

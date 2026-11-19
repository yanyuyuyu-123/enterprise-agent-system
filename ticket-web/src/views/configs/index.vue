<template>
  <div class="page">
    <div class="page-card">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="后端暂未提供配置接口（/configs），页面已预留。配置按分类管理，键前缀受岗位限制，修改会写入关键日志。"
        class="mb-12"
      />

      <div class="toolbar">
        <el-select placeholder="配置分类" style="width: 150px" disabled>
          <el-option label="工单" value="work_order" />
          <el-option label="知识库" value="knowledge" />
          <el-option label="Agent" value="agent" />
          <el-option label="语音" value="voice" />
        </el-select>
        <el-input placeholder="配置键" style="width: 220px" disabled />
        <div class="toolbar-spacer"></div>
        <el-button type="primary" disabled>保存配置</el-button>
      </div>

      <el-table :data="[]" size="small">
        <el-table-column prop="config_key" label="配置键" width="260" />
        <el-table-column prop="config_value" label="配置值" min-width="200" />
        <el-table-column prop="category" label="分类" width="120" />
        <el-table-column prop="description" label="说明" min-width="220" />
        <el-table-column label="更新时间" width="160" />
        <template #empty>暂无配置数据</template>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.mb-12 {
  margin-bottom: 12px;
}
</style>

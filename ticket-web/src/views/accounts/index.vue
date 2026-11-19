<template>
  <div class="page">
    <div class="page-card">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="后端暂未提供账号申请接口（/accounts/requests），页面已预留。账号开通、变更、停用需人事负责人审批。"
        class="mb-12"
      />

      <div class="toolbar">
        <el-select placeholder="申请类型" style="width: 150px" disabled>
          <el-option label="开通账号" value="create" />
          <el-option label="变更账号" value="update" />
          <el-option label="停用账号" value="disable" />
        </el-select>
        <el-select placeholder="审批状态" style="width: 130px" disabled>
          <el-option label="待审批" value="pending" />
          <el-option label="已通过" value="approved" />
          <el-option label="已驳回" value="rejected" />
        </el-select>
        <div class="toolbar-spacer"></div>
        <el-button type="primary" disabled>提交申请</el-button>
      </div>

      <el-table :data="[]" size="small">
        <el-table-column prop="request_no" label="申请单号" width="170" />
        <el-table-column prop="request_type" label="类型" width="110" />
        <el-table-column prop="target_name" label="目标人员" width="140" />
        <el-table-column prop="applicant_name" label="申请人" width="120" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column label="申请时间" width="160" />
        <el-table-column label="操作" width="140" />
        <template #empty>暂无申请单</template>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.mb-12 {
  margin-bottom: 12px;
}
</style>

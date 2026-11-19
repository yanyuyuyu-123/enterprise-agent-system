<template>
  <el-container class="layout">
    <el-aside width="220px" class="layout-aside">
      <div class="brand">
        <el-icon :size="20"><Cpu /></el-icon>
        <span>企业智能 Agent</span>
      </div>
      <el-scrollbar>
        <el-menu
          router
          :default-active="activeMenu"
          background-color="#ffffff"
          text-color="#5a6577"
          active-text-color="#2f6feb"
          class="side-menu"
        >
          <el-menu-item index="/dashboard">
            <el-icon><Odometer /></el-icon>
            <span>工作台</span>
          </el-menu-item>

          <el-sub-menu index="work-order">
            <template #title>
              <el-icon><Tickets /></el-icon>
              <span>工单管理</span>
            </template>
            <el-menu-item index="/work-orders">工单列表</el-menu-item>
            <el-menu-item index="/work-orders/create">新建工单</el-menu-item>
          </el-sub-menu>

          <el-menu-item index="/agent">
            <el-icon><ChatDotRound /></el-icon>
            <span>Agent Chat</span>
          </el-menu-item>

          <el-sub-menu v-if="canBusiness" index="business">
            <template #title>
              <el-icon><Shop /></el-icon>
              <span>经营业务</span>
            </template>
            <el-menu-item v-if="can('purchase_order:read')" index="/purchase-orders">采购单</el-menu-item>
            <el-menu-item v-if="can('sales_order:read')" index="/sales-orders">销售单</el-menu-item>
            <el-menu-item v-if="can('inventory:read')" index="/inventory">库存查询</el-menu-item>
            <el-menu-item v-if="can('inventory:read')" index="/stock-movements">出入库单</el-menu-item>
            <el-menu-item v-if="can('inventory:read')" index="/stock-checks">库存盘点</el-menu-item>
            <el-menu-item v-if="can('finance_record:read')" index="/finance/records">财务记录</el-menu-item>
            <el-menu-item v-if="can('finance_record:read')" index="/finance/cash-flows">资金流水</el-menu-item>
            <el-menu-item v-if="canMasterData" index="/master-data">主数据</el-menu-item>
          </el-sub-menu>

          <el-menu-item index="/knowledge">
            <el-icon><Collection /></el-icon>
            <span>企业知识库</span>
          </el-menu-item>

          <el-sub-menu v-if="canData" index="data">
            <template #title>
              <el-icon><DataAnalysis /></el-icon>
              <span>数据与报告</span>
            </template>
            <el-menu-item v-if="can('report:read')" index="/stats">工单统计</el-menu-item>
            <el-menu-item v-if="can('report:read') || store.me?.report_viewer" index="/reports">报告中心</el-menu-item>
            <el-menu-item v-if="can('alert:read')" index="/alerts">异常预警</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="system">
            <template #title>
              <el-icon><Setting /></el-icon>
              <span>系统管理</span>
            </template>
            <el-menu-item index="/notifications">通知中心</el-menu-item>
            <el-menu-item index="/logs">日志查询</el-menu-item>
            <el-menu-item v-if="can('account:read')" index="/accounts">账号申请</el-menu-item>
            <el-menu-item v-if="can('org:read')" index="/org">部门与岗位</el-menu-item>
            <el-menu-item v-if="can('config:config')" index="/configs">系统配置</el-menu-item>
          </el-sub-menu>
        </el-menu>
      </el-scrollbar>
    </el-aside>

    <el-container>
      <el-header class="layout-header">
        <div class="header-title">{{ route.meta.title }}</div>
        <div class="header-actions">
          <el-badge :value="unread" :hidden="unread === 0" :max="99">
            <el-button circle text @click="router.push('/notifications')">
              <el-icon :size="18"><Bell /></el-icon>
            </el-button>
          </el-badge>
          <el-dropdown @command="onUserCommand">
            <span class="user-entry">
              <el-avatar :size="28">{{ store.displayName.slice(0, 1) }}</el-avatar>
              <span class="user-name">{{ store.displayName }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>{{ store.positionNames }}</el-dropdown-item>
                <el-dropdown-item command="notifications">通知中心</el-dropdown-item>
                <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="layout-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { notificationApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { hasAnyPermission, hasPermission } from '@/utils/permission'

const route = useRoute()
const router = useRouter()
const store = useUserStore()
const unread = ref(0)

const permissions = computed(() => store.me?.permissions || [])
const can = (key) => hasPermission(permissions.value, key)
const canBusiness = computed(() =>
  hasAnyPermission(permissions.value, [
    'purchase_order:read',
    'sales_order:read',
    'inventory:read',
    'finance_record:read',
    'product:read',
    'supplier:read',
    'customer:read',
  ]),
)
const canData = computed(() =>
  hasAnyPermission(permissions.value, ['report:read', 'alert:read']) || store.me?.report_viewer,
)
const canMasterData = computed(() =>
  hasAnyPermission(permissions.value, ['product:read', 'supplier:read', 'customer:read']),
)

const activeMenu = computed(() => route.meta.activeMenu || route.path)

async function loadUnread() {
  try {
    const data = await notificationApi.list({ is_read: false, page_size: 1 }, { silent: true })
    unread.value = data?.unread ?? 0
  } catch {
    unread.value = 0
  }
}

let timer = null

onMounted(() => {
  loadUnread()
  timer = window.setInterval(loadUnread, 60000)
})

watch(() => route.fullPath, loadUnread)

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})

async function onUserCommand(command) {
  if (command === 'notifications') {
    router.push('/notifications')
    return
  }
  if (command === 'logout') {
    try {
      await ElMessageBox.confirm('确认退出登录？', '提示', {
        type: 'warning',
        confirmButtonText: '退出',
        cancelButtonText: '取消',
      })
    } catch {
      return
    }
    await store.logout()
    ElMessage.success('已退出登录')
    router.replace('/login')
  }
}
</script>

<style scoped>
.layout {
  height: 100%;
}

.layout-aside {
  background: #fff;
  border-right: 1px solid #e9edf5;
  display: flex;
  flex-direction: column;
}

.brand {
  height: 56px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 18px;
  color: #1f2a37;
  font-weight: 600;
  font-size: 15px;
  letter-spacing: 0.3px;
  border-bottom: 1px solid #eef1f6;
}

.brand .el-icon {
  color: #2f6feb;
}

.side-menu {
  border-right: none;
  padding: 8px 0 16px;
}

.side-menu :deep(.el-menu-item),
.side-menu :deep(.el-sub-menu__title) {
  height: 40px;
  line-height: 40px;
  margin: 2px 10px;
  border-radius: 8px;
  font-size: 13px;
}

.side-menu :deep(.el-menu-item:hover),
.side-menu :deep(.el-sub-menu__title:hover) {
  background: #f5f7fb;
}

.side-menu :deep(.el-menu-item.is-active) {
  background: #eaf1fd;
  font-weight: 600;
}

.side-menu :deep(.el-sub-menu .el-menu-item) {
  min-width: auto;
  padding-left: 46px !important;
}

.layout-header {
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #e9edf5;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2a37;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-entry {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #38414f;
}

.user-entry .el-avatar {
  background: #eaf1fd;
  color: #2f6feb;
  font-size: 13px;
  font-weight: 600;
}

.user-name {
  font-size: 13px;
}

.layout-main {
  background: #f4f6fa;
  padding: 0;
  overflow: auto;
}
</style>

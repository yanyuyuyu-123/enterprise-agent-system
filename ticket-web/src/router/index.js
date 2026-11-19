import { createRouter, createWebHistory } from 'vue-router'

import { useUserStore } from '@/stores/user'
import { hasAnyPermission } from '@/utils/permission'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    component: () => import('@/layout/index.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        component: () => import('@/views/dashboard/index.vue'),
        meta: { title: '工作台' },
      },
      {
        path: 'work-orders',
        component: () => import('@/views/workorder/List.vue'),
        meta: { title: '工单列表' },
      },
      {
        path: 'work-orders/create',
        component: () => import('@/views/workorder/Create.vue'),
        meta: { title: '新建工单', activeMenu: '/work-orders' },
      },
      {
        path: 'work-orders/:id',
        component: () => import('@/views/workorder/Detail.vue'),
        meta: { title: '工单详情', activeMenu: '/work-orders' },
      },
      {
        path: 'agent',
        component: () => import('@/views/agent/index.vue'),
        meta: { title: 'Agent Chat' },
      },
      {
        path: 'voice',
        component: () => import('@/views/voice/index.vue'),
        meta: { title: '语音助手' },
      },
      {
        path: 'purchase-orders',
        component: () => import('@/views/business/OrderList.vue'),
        props: { mode: 'purchase' },
        meta: { title: '采购单', permissions: ['purchase_order:read'] },
      },
      {
        path: 'sales-orders',
        component: () => import('@/views/business/OrderList.vue'),
        props: { mode: 'sales' },
        meta: { title: '销售单', permissions: ['sales_order:read'] },
      },
      {
        path: 'master-data',
        component: () => import('@/views/master/Index.vue'),
        meta: { title: '主数据', permissions: ['product:read', 'supplier:read', 'customer:read'] },
      },
      {
        path: 'inventory',
        component: () => import('@/views/inventory/Stock.vue'),
        meta: { title: '库存查询', permissions: ['inventory:read'] },
      },
      {
        path: 'stock-movements',
        component: () => import('@/views/inventory/Movements.vue'),
        meta: { title: '出入库单', permissions: ['inventory:read'] },
      },
      {
        path: 'stock-checks',
        component: () => import('@/views/inventory/Checks.vue'),
        meta: { title: '库存盘点', permissions: ['inventory:read'] },
      },
      {
        path: 'finance/records',
        component: () => import('@/views/finance/Records.vue'),
        meta: { title: '财务记录', permissions: ['finance_record:read'] },
      },
      {
        path: 'finance/cash-flows',
        component: () => import('@/views/finance/CashFlows.vue'),
        meta: { title: '资金流水', permissions: ['finance_record:read'] },
      },
      {
        path: 'knowledge',
        component: () => import('@/views/knowledge/index.vue'),
        meta: { title: '企业知识库', permissions: ['knowledge_document:read'] },
      },
      {
        path: 'stats',
        component: () => import('@/views/stats/index.vue'),
        meta: { title: '工单统计', permissions: ['report:read'] },
      },
      {
        path: 'reports',
        component: () => import('@/views/reports/index.vue'),
        meta: { title: '报告中心', permissions: ['report:read'] },
      },
      {
        path: 'alerts',
        component: () => import('@/views/alerts/index.vue'),
        meta: { title: '异常预警', permissions: ['alert:read'] },
      },
      {
        path: 'notifications',
        component: () => import('@/views/notifications/index.vue'),
        meta: { title: '通知中心' },
      },
      {
        path: 'logs',
        component: () => import('@/views/logs/index.vue'),
        meta: { title: '日志查询', permissions: ['operation_log:read'] },
      },
      {
        path: 'accounts',
        component: () => import('@/views/accounts/index.vue'),
        meta: { title: '账号申请', permissions: ['account:read'] },
      },
      {
        path: 'org',
        component: () => import('@/views/org/index.vue'),
        meta: { title: '部门与岗位', permissions: ['org:read'] },
      },
      {
        path: 'configs',
        component: () => import('@/views/configs/index.vue'),
        meta: { title: '系统配置', permissions: ['config:config'] },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  document.title = to.meta.title ? `${to.meta.title} · 企业智能 Agent` : '企业智能 Agent'
  const store = useUserStore()
  if (to.meta.public) return true
  if (!store.accessToken) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (!store.me) {
    try {
      await store.fetchMe()
    } catch {
      store.reset()
      return { path: '/login' }
    }
  }
  const required = to.meta.permissions
  if (required && !hasAnyPermission(store.me?.permissions, required)) {
    return { path: '/dashboard' }
  }
  return true
})

export default router

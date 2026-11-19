import request, { download } from './request'

export const authApi = {
  login: (payload) => request.post('/auth/login', payload),
  logout: (payload) => request.post('/auth/logout', payload),
  me: () => request.get('/users/me'),
}

export const workOrderApi = {
  list: (params) => request.get('/work_orders', { params }),
  detail: (id) => request.get(`/work_orders/${id}`),
  create: (payload) => request.post('/work_orders', payload),
  supplement: (id, payload) => request.post(`/work_orders/${id}/supplement`, payload),
  revise: (id, payload) => request.post(`/work_orders/${id}/revise`, payload),
  assign: (id, payload) => request.post(`/work_orders/${id}/assign`, payload),
  reassign: (id, payload) => request.post(`/work_orders/${id}/reassign`, payload),
  start: (id, version) => request.post(`/work_orders/${id}/start`, { version }),
  submit: (id, payload) => request.post(`/work_orders/${id}/submit`, payload),
  review: (id, payload) => request.post(`/work_orders/${id}/review`, payload),
  recall: (id, payload) => request.post(`/work_orders/${id}/recall`, payload),
  transfer: (id, payload) => request.post(`/work_orders/${id}/transfer`, payload),
  transferDecision: (id, payload) => request.post(`/work_orders/${id}/transfer/decision`, payload),
  upload: (id, file) => {
    const form = new FormData()
    form.append('file', file)
    return request.post(`/work_orders/${id}/attachments`, form)
  },
  downloadAttachment: (orderId, attachmentId, fileName) =>
    download(`/work_orders/${orderId}/attachments/${attachmentId}/download`, fileName),
}

function crud(base) {
  return {
    list: (params) => request.get(base, { params }),
    detail: (id) => request.get(`${base}/${id}`),
    create: (payload) => request.post(base, payload),
    update: (id, payload) => request.put(`${base}/${id}`, payload),
  }
}

export const masterApi = {
  suppliers: crud('/suppliers'),
  customers: crud('/customers'),
  products: crud('/products'),
  warehouses: () => request.get('/warehouses'),
}

function orderApi(base) {
  return {
    list: (params) => request.get(base, { params }),
    detail: (id) => request.get(`${base}/${id}`),
    create: (payload) => request.post(base, payload),
    update: (id, payload) => request.put(`${base}/${id}`, payload),
    submit: (id, version) => request.post(`${base}/${id}/submit`, { version }),
    review: (id, payload) => request.post(`${base}/${id}/review`, payload),
    void: (id, payload) => request.post(`${base}/${id}/void`, payload),
  }
}

export const purchaseApi = orderApi('/purchase-orders')
export const salesApi = orderApi('/sales-orders')

export const inventoryApi = {
  stock: (params) => request.get('/inventory', { params }),
  movements: (params) => request.get('/stock-movements', { params }),
  movement: (id) => request.get(`/stock-movements/${id}`),
  createMovement: (payload) => request.post('/stock-movements', payload),
  submitMovement: (id, version) => request.post(`/stock-movements/${id}/submit`, { version }),
  executeMovement: (id, payload) => request.post(`/stock-movements/${id}/execute`, payload),
  reviewMovement: (id, payload) => request.post(`/stock-movements/${id}/review`, payload),
  reverseMovement: (id, payload) => request.post(`/stock-movements/${id}/reverse`, payload),
  checks: (params) => request.get('/stock-checks', { params }),
  check: (id) => request.get(`/stock-checks/${id}`),
  createCheck: (payload) => request.post('/stock-checks', payload),
  submitCheck: (id, version) => request.post(`/stock-checks/${id}/submit`, { version }),
  reviewCheck: (id, payload) => request.post(`/stock-checks/${id}/review`, payload),
}

export const financeApi = {
  records: (params) => request.get('/finance-records', { params }),
  createRecord: (payload) => request.post('/finance-records', payload),
  reviewRecord: (id, payload) => request.post(`/finance-records/${id}/review`, payload),
  voidRecord: (id, payload) => request.post(`/finance-records/${id}/void`, payload),
  flows: (params) => request.get('/cash-flows', { params }),
  createFlow: (payload) => request.post('/cash-flows', payload),
  reviewFlow: (id, payload) => request.post(`/cash-flows/${id}/review`, payload),
  voidFlow: (id, payload) => request.post(`/cash-flows/${id}/void`, payload),
}

export const knowledgeApi = {
  list: (params) => request.get('/knowledge/documents', { params }),
  upload: (form) => request.post('/knowledge/documents', form),
  detail: (id) => request.get(`/knowledge/documents/${id}`),
  remove: (id) => request.delete(`/knowledge/documents/${id}`),
  reprocess: (id) => request.post(`/knowledge/documents/${id}/reprocess`),
  download: (id, fileName) => download(`/knowledge/documents/${id}/download`, fileName),
  search: (payload) => request.post('/knowledge/search', payload),
}

export const agentApi = {
  sessions: (limit = 20) => request.get('/agent/sessions', { params: { limit } }),
  sessionMessages: (sessionId) =>
    request.get(`/agent/sessions/${encodeURIComponent(sessionId)}/messages`),
}

export const statsApi = {
  workOrders: (params) => request.get('/stats/work_orders', { params }),
  trend: (params) => request.get('/stats/work-orders/trend', { params }),
  overdueDistribution: (params) => request.get('/stats/work-orders/overdue-distribution', { params }),
  financeTrend: (params) => request.get('/stats/finance-trend', { params }),
}

export const logApi = {
  operation: (params) => request.get('/logs/operation', { params }),
  agent: (params) => request.get('/logs/agent', { params }),
  system: (params) => request.get('/logs/system', { params }),
}

export const notificationApi = {
  list: (params, config = {}) => request.get('/notifications', { params, ...config }),
  read: (id) => request.post(`/notifications/${id}/read`),
  readAll: () => request.post('/notifications/read-all'),
}

export const voiceApi = {
  asr: (form) => request.post('/voice/asr', form),
  confirm: (payload) => request.post('/voice/confirm', payload),
  tts: (payload) => request.post('/voice/tts', payload),
  fileBlob: (id) => request.get(`/voice/files/${id}/download`, { responseType: 'blob' }),
  voiceprintStatus: () => request.get('/voice/voiceprint'),
  enrollVoiceprint: (form) => request.post('/voice/voiceprint', form),
  removeVoiceprint: () => request.delete('/voice/voiceprint'),
}

export const reportApi = {
  list: (params) => request.get('/reports', { params }),
  detail: (id) => request.get(`/reports/${id}`),
  download: (id, fileName) => download(`/reports/${id}/download`, fileName),
  viewers: () => request.get('/report-viewers'),
  viewerCandidates: () => request.get('/report-viewers/candidates'),
  saveViewers: (payload) => request.put('/report-viewers', payload),
}

export const alertApi = {
  list: (params) => request.get('/alerts', { params }),
  acknowledge: (id) => request.post(`/alerts/${id}/acknowledge`),
  close: (id, payload) => request.post(`/alerts/${id}/close`, payload),
  safeStock: () => request.get('/safe-stock-configs'),
  saveSafeStock: (payload) => request.put('/safe-stock-configs', payload),
}

import axios from 'axios'
import { ElMessage } from 'element-plus'

export const TOKEN_KEY = 'ticket_access_token'
export const REFRESH_KEY = 'ticket_refresh_token'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

let refreshing = null

function toLogin() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
  if (!window.location.pathname.startsWith('/login')) {
    window.location.replace('/login')
  }
}

async function refreshAccessToken() {
  const refreshToken = localStorage.getItem(REFRESH_KEY)
  if (!refreshToken) return false
  if (!refreshing) {
    refreshing = axios
      .post('/api/v1/auth/refresh', { refresh_token: refreshToken })
      .then((response) => {
        const data = response.data?.data
        if (response.data?.code === 0 && data?.access_token) {
          localStorage.setItem(TOKEN_KEY, data.access_token)
          if (data.refresh_token) localStorage.setItem(REFRESH_KEY, data.refresh_token)
          return true
        }
        return false
      })
      .catch(() => false)
      .finally(() => {
        refreshing = null
      })
  }
  return refreshing
}

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => {
    if (response.config.responseType === 'blob') return response
    const body = response.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 0) return body.data
      if (!response.config.silent) ElMessage.error(body.message || '请求失败')
      return Promise.reject(Object.assign(new Error(body.message || '请求失败'), { code: body.code }))
    }
    return body
  },
  async (error) => {
    const status = error.response?.status
    const config = error.config || {}
    if (status === 401) {
      const renewed = await refreshAccessToken()
      if (renewed) {
        config.__retried = true
        config.headers = config.headers || {}
        config.headers.Authorization = `Bearer ${localStorage.getItem(TOKEN_KEY)}`
        return http.request(config)
      }
      toLogin()
      return Promise.reject(error)
    }
    if (status === 404) {
      if (!config.silent) ElMessage.error('接口暂未实现（404）')
    } else if (!config.silent) {
      ElMessage.error(error.response?.data?.message || error.message || '网络异常，请确认后端已启动')
    }
    return Promise.reject(error)
  },
)

export async function download(url, fileName) {
  const response = await http.get(url, { responseType: 'blob' })
  const objectUrl = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = fileName || 'download'
  link.click()
  URL.revokeObjectURL(objectUrl)
}

export default http

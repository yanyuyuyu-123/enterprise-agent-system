import { defineStore } from 'pinia'

import { authApi } from '@/api'
import { REFRESH_KEY, TOKEN_KEY } from '@/api/request'

export const useUserStore = defineStore('user', {
  state: () => ({
    accessToken: localStorage.getItem(TOKEN_KEY) || '',
    refreshToken: localStorage.getItem(REFRESH_KEY) || '',
    me: null,
  }),
  getters: {
    displayName: (state) => state.me?.name || state.me?.employee_no || '未登录',
    positionNames: (state) =>
      (state.me?.positions || []).map((item) => item.name).join(' / ') || '无岗位',
    positionCodes: (state) => (state.me?.positions || []).map((item) => item.code),
  },
  actions: {
    setTokens(data) {
      this.accessToken = data.access_token
      this.refreshToken = data.refresh_token
      localStorage.setItem(TOKEN_KEY, data.access_token)
      localStorage.setItem(REFRESH_KEY, data.refresh_token)
    },
    async login(payload) {
      const data = await authApi.login(payload)
      this.setTokens(data)
      await this.fetchMe()
    },
    async fetchMe() {
      this.me = await authApi.me()
    },
    async logout() {
      try {
        await authApi.logout({ refresh_token: this.refreshToken })
      } catch {
        // 令牌已失效时也要能退出
      }
      this.reset()
    },
    reset() {
      this.accessToken = ''
      this.refreshToken = ''
      this.me = null
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(REFRESH_KEY)
    },
  },
})

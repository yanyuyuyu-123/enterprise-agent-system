<template>
  <div class="login-page">
    <div class="glow glow-left"></div>
    <div class="glow glow-right"></div>

    <div class="login-panel">
      <section class="brand">
        <div class="brand-mark">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="5" r="2.6" />
            <circle cx="5" cy="18" r="2.6" />
            <circle cx="19" cy="18" r="2.6" />
            <path d="M12 7.6 6.4 15.6M12 7.6l5.6 8M7.6 18h8.8" />
          </svg>
        </div>
        <h1 class="brand-title">企业智能<br />Agent</h1>
        <div class="brand-orbit">
          <span></span>
          <span></span>
          <span></span>
        </div>
      </section>

      <section class="form-side">
        <header class="form-head">
          <h2>登录</h2>
          <p>使用工号与密码登录</p>
        </header>

        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
          <el-form-item label="工号" prop="employee_no">
            <el-input v-model="form.employee_no" placeholder="请输入工号" autocomplete="username" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              show-password
              placeholder="请输入密码"
              autocomplete="current-password"
              @keyup.enter="submit"
            />
          </el-form-item>
          <el-button type="primary" class="login-button" :loading="loading" @click="submit">
            登录
          </el-button>
        </el-form>

        <p class="form-foot">账号由人事专员开通，忘记密码请联系管理员</p>
      </section>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const store = useUserStore()

const formRef = ref()
const loading = ref(false)
const form = reactive({ employee_no: '', password: '' })

const rules = {
  employee_no: [{ required: true, message: '请输入工号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await store.login({ employee_no: form.employee_no.trim(), password: form.password })
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    router.replace(redirect)
  } catch {
    // 错误提示由请求拦截器统一处理
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  position: relative;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: #eef2f9;
}

.glow {
  position: absolute;
  width: 520px;
  height: 520px;
  border-radius: 50%;
  filter: blur(10px);
  pointer-events: none;
}

.glow-left {
  top: -180px;
  left: -140px;
  background: radial-gradient(circle, rgba(60, 120, 240, 0.22), transparent 68%);
}

.glow-right {
  right: -180px;
  bottom: -200px;
  background: radial-gradient(circle, rgba(93, 168, 255, 0.22), transparent 68%);
}

.login-panel {
  position: relative;
  z-index: 1;
  width: 880px;
  min-height: 470px;
  display: grid;
  grid-template-columns: 0.92fr 1fr;
  background: #fff;
  border-radius: 20px;
  overflow: hidden;
  box-shadow:
    0 1px 2px rgba(20, 33, 61, 0.04),
    0 24px 60px rgba(20, 33, 61, 0.12);
}

.brand {
  position: relative;
  padding: 56px 44px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  color: #fff;
  background:
    radial-gradient(circle at 78% 12%, rgba(255, 255, 255, 0.16), transparent 42%),
    linear-gradient(155deg, #2f6bed 0%, #1e46b8 55%, #17358f 100%);
  overflow: hidden;
}

.brand::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.07) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.07) 1px, transparent 1px);
  background-size: 34px 34px;
  -webkit-mask-image: radial-gradient(circle at 32% 26%, #000 10%, transparent 72%);
  mask-image: radial-gradient(circle at 32% 26%, #000 10%, transparent 72%);
}

.brand-mark {
  position: relative;
  width: 46px;
  height: 46px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.28);
  backdrop-filter: blur(4px);
}

.brand-mark svg {
  width: 26px;
  height: 26px;
  stroke: #fff;
  stroke-width: 1.4;
  stroke-linecap: round;
}

.brand-title {
  position: relative;
  margin: 22px 0 0;
  font-size: 30px;
  font-weight: 600;
  line-height: 1.38;
  letter-spacing: 0.5px;
}

.brand-orbit {
  position: relative;
  margin-top: 40px;
  display: flex;
  gap: 8px;
}

.brand-orbit span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.5);
}

.brand-orbit span:first-child {
  width: 34px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.85);
}

.form-side {
  padding: 52px 52px 40px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.form-head {
  margin-bottom: 26px;
}

.form-head h2 {
  margin: 0;
  font-size: 26px;
  font-weight: 600;
  color: #1d2433;
  letter-spacing: 0.5px;
}

.form-head p {
  margin: 8px 0 0;
  font-size: 13px;
  color: #8b94a7;
}

.form-side :deep(.el-form-item) {
  margin-bottom: 20px;
}

.form-side :deep(.el-form-item__label) {
  padding-bottom: 6px;
  font-size: 13px;
  color: #4a5468;
}

.form-side :deep(.el-input__wrapper) {
  height: 44px;
  padding: 0 14px;
  border-radius: 10px;
  background: #f6f8fc;
  box-shadow: inset 0 0 0 1px #e4e9f2;
  transition: box-shadow 0.2s ease, background 0.2s ease;
}

.form-side :deep(.el-input__wrapper:hover) {
  background: #f2f5fb;
}

.form-side :deep(.el-input__wrapper.is-focus) {
  background: #fff;
  box-shadow: inset 0 0 0 1px #2f6bed, 0 0 0 3px rgba(47, 107, 237, 0.12);
}

.login-button {
  width: 100%;
  height: 44px;
  margin-top: 6px;
  border: none;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 500;
  letter-spacing: 2px;
  background: linear-gradient(135deg, #3a7bf5, #2058d8);
  box-shadow: 0 8px 20px rgba(47, 107, 237, 0.25);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.login-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(47, 107, 237, 0.32);
}

.login-button:active {
  transform: translateY(0);
}

.form-foot {
  margin: 26px 0 0;
  text-align: center;
  font-size: 12px;
  color: #a3abbd;
}

@media (max-width: 900px) {
  .login-panel {
    width: calc(100% - 40px);
    grid-template-columns: 1fr;
    min-height: auto;
  }

  .brand {
    display: none;
  }

  .form-side {
    padding: 40px 32px;
  }
}
</style>

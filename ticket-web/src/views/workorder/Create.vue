<template>
  <div class="page">
    <div class="page-card">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="信息不完整时工单会先进入「补充信息」，补全后自动进入分配；报销工单创建后自动分配给自己。"
        class="mt-0"
      />

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="96px"
        class="mt-16"
        style="max-width: 760px"
      >
        <el-form-item label="工单类别" prop="category">
          <el-select v-model="form.category" placeholder="选择类别" style="width: 240px">
            <el-option
              v-for="(label, key) in categoryOptions"
              :key="key"
              :label="label"
              :value="key"
            />
          </el-select>
          <span class="muted" style="margin-left: 12px">{{ categoryHint }}</span>
        </el-form-item>

        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" maxlength="128" show-word-limit placeholder="一句话描述问题" />
        </el-form-item>

        <el-form-item label="详细描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="4"
            placeholder="补充时间、地点、现象等信息"
          />
        </el-form-item>

        <el-form-item label="优先级">
          <el-radio-group v-model="form.priority">
            <el-radio-button v-for="(item, key) in PRIORITY" :key="key" :value="key">
              {{ item.label }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>

        <template v-if="form.category === 'device_repair'">
          <el-form-item label="设备 ID">
            <el-input-number v-model="form.device_id" :min="1" :controls="false" />
            <span class="muted" style="margin-left: 12px">设备主数据接口未开放，暂填设备 ID</span>
          </el-form-item>
          <el-form-item label="故障描述">
            <el-input v-model="form.fault_description" type="textarea" :rows="3" />
          </el-form-item>
        </template>

        <template v-if="form.category === 'expense_reimbursement'">
          <el-form-item label="费用类型">
            <el-select v-model="form.expense_type" placeholder="选择费用类型" style="width: 240px">
              <el-option v-for="(label, key) in EXPENSE_TYPE" :key="key" :label="label" :value="key" />
            </el-select>
          </el-form-item>
          <el-form-item label="报销金额">
            <el-input-number v-model="form.amount" :min="0" :precision="2" :step="100" />
          </el-form-item>
        </template>

        <template v-if="form.category === 'security_patrol'">
          <el-form-item label="巡查区域">
            <el-input v-model="form.patrol_area" maxlength="128" />
          </el-form-item>
          <el-form-item label="隐患描述">
            <el-input v-model="form.hazard_description" type="textarea" :rows="3" />
          </el-form-item>
        </template>

        <template v-if="form.category === 'transport_exception'">
          <el-form-item label="车次号">
            <el-input v-model="form.trip_no" maxlength="64" />
          </el-form-item>
          <el-form-item label="异常类型">
            <el-input v-model="form.exception_type" maxlength="32" placeholder="如：延误、货损" />
          </el-form-item>
        </template>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submit">提交工单</el-button>
          <el-button @click="router.back()">取消</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import { workOrderApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { EXPENSE_TYPE, PRIORITY, WORK_ORDER_CATEGORY, tagOf } from '@/utils/dict'

const router = useRouter()
const userStore = useUserStore()
const formRef = ref()
const submitting = ref(false)

const CATEGORY_POSITIONS = {
  device_repair: ['production_worker', 'repairman'],
  security_patrol: ['guard'],
  transport_exception: ['transporter', 'dispatcher'],
}

const categoryOptions = computed(() => {
  const codes = userStore.positionCodes
  return Object.fromEntries(
    Object.entries(WORK_ORDER_CATEGORY).filter(([key]) => {
      const allowed = CATEGORY_POSITIONS[key]
      return !allowed || allowed.some((code) => codes.includes(code))
    }),
  )
})

const form = reactive({
  category: Object.keys(categoryOptions.value)[0] || 'expense_reimbursement',
  title: '',
  description: '',
  priority: 'normal',
  device_id: undefined,
  fault_description: '',
  expense_type: '',
  amount: undefined,
  patrol_area: '',
  hazard_description: '',
  trip_no: '',
  exception_type: '',
})

const rules = {
  category: [{ required: true, message: '请选择类别', trigger: 'change' }],
  title: [{ required: true, message: '请填写标题', trigger: 'blur' }],
}

const CATEGORY_HINT = {
  device_repair: '处理人：维修工；审核人：生产主任',
  expense_reimbursement: '处理人：本人；审核人：财务负责人',
  security_patrol: '处理人：保安；审核人：保安队长',
  transport_exception: '处理人：运输人员；审核人：物流负责人',
}

const categoryHint = computed(() => CATEGORY_HINT[form.category] || '')

function buildPayload() {
  const payload = {
    category: form.category,
    title: form.title.trim(),
    description: form.description || null,
    priority: form.priority,
  }
  if (form.category === 'device_repair') {
    payload.device = {
      device_id: form.device_id || null,
      fault_description: form.fault_description || null,
    }
  }
  if (form.category === 'expense_reimbursement') {
    payload.expense = {
      expense_type: form.expense_type || null,
      amount: form.amount ?? null,
    }
  }
  if (form.category === 'security_patrol') {
    payload.patrol = {
      patrol_area: form.patrol_area || null,
      hazard_description: form.hazard_description || null,
    }
  }
  if (form.category === 'transport_exception') {
    payload.transport = {
      trip_no: form.trip_no || null,
      exception_type: form.exception_type || null,
    }
  }
  return payload
}

async function submit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const data = await workOrderApi.create(buildPayload())
    const status = tagOf(
      { supplementing: { label: '补充信息' }, pending_assignment: { label: '待分配' }, pending_process: { label: '待处理' } },
      data.status,
    ).label
    ElMessage.success(`工单 ${data.order_no} 已创建，当前状态：${status}`)
    router.replace(`/work-orders/${data.id}`)
  } catch {
    // 拦截器已提示
  } finally {
    submitting.value = false
  }
}
</script>

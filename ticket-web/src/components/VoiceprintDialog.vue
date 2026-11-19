<template>
  <el-dialog
    :model-value="modelValue"
    title="我的声纹"
    width="540px"
    :close-on-click-modal="false"
    @update:model-value="(value) => emit('update:modelValue', value)"
    @open="loadStatus"
    @closed="reset"
  >
    <div v-loading="loading">
      <template v-if="status.enrolled">
        <div class="vp-enrolled">
          <el-tag type="success" size="small">已录入（{{ status.samples }} 段样本）</el-tag>
          <span v-if="status.updated_at" class="muted">
            最近录入：{{ formatDateTime(status.updated_at) }}
          </span>
        </div>
        <div class="muted mt-8">声纹已与当前账号绑定，语音输入会校验是否为本人。如需更换，请先删除后重新录入。</div>
      </template>

      <template v-else>
        <el-alert
          v-if="!status.available"
          type="warning"
          :closable="false"
          show-icon
          title="声纹模型未配置，暂不支持录入"
        />
        <template v-else>
          <el-steps :active="samples.length" simple>
            <el-step v-for="i in 3" :key="i" :title="`第 ${i} 段`" />
          </el-steps>

          <div class="record-area">
            <el-button
              :type="recording ? 'danger' : 'primary'"
              size="large"
              circle
              :disabled="!recording && samples.length >= 3"
              @click="recording ? stopRecord() : startRecord()"
            >
              <el-icon :size="22">
                <VideoPause v-if="recording" />
                <Microphone v-else />
              </el-icon>
            </el-button>
            <div class="record-tip">
              {{
                recording
                  ? `录音中 ${seconds}s / ${MAX_SECONDS}s，点击停止`
                  : `点击录制第 ${Math.min(samples.length + 1, 3)} 段，每段 ${MIN_SECONDS}~${MAX_SECONDS} 秒`
              }}
            </div>
          </div>

          <el-table :data="samples" size="small" class="mt-12">
            <el-table-column label="录音" width="120">
              <template #default="{ $index }">第 {{ $index + 1 }} 段</template>
            </el-table-column>
            <el-table-column label="时长" width="100">
              <template #default="{ row }">{{ row.seconds.toFixed(1) }} 秒</template>
            </el-table-column>
            <el-table-column label="操作" width="90">
              <template #default="{ $index }">
                <el-button link type="danger" @click="retake($index)">重录</el-button>
              </template>
            </el-table-column>
            <template #empty>还没有录音，请至少录入 3 段</template>
          </el-table>

          <div class="muted mt-8">请用本人声音朗读任意文字，三段内容可以不同，环境尽量安静。</div>
        </template>
      </template>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
      <el-button
        v-if="status.enrolled"
        type="danger"
        plain
        :loading="removing"
        @click="removeVoiceprint"
      >
        删除声纹
      </el-button>
      <el-button
        v-else
        type="primary"
        :loading="saving"
        :disabled="!status.available || samples.length < 3"
        @click="submit"
      >
        提交录入
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { voiceApi } from '@/api'
import { encodeWav, mergeAndResample } from '@/utils/audio'
import { formatDateTime } from '@/utils/dict'

defineProps({ modelValue: { type: Boolean, default: false } })
const emit = defineEmits(['update:modelValue'])

const TARGET_RATE = 16000
const MIN_SECONDS = 2
const MAX_SECONDS = 10

const loading = ref(false)
const saving = ref(false)
const removing = ref(false)
const status = ref({ enrolled: false, available: true, samples: 0, updated_at: null })
const samples = ref([])
const recording = ref(false)
const seconds = ref(0)

let context = null
let source = null
let processor = null
let stream = null
let chunks = []
let timer = null
let rate = TARGET_RATE

async function loadStatus() {
  loading.value = true
  try {
    const data = await voiceApi.voiceprintStatus()
    if (data) status.value = data
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function cleanup() {
  if (timer) window.clearInterval(timer)
  timer = null
  processor?.disconnect()
  source?.disconnect()
  stream?.getTracks().forEach((track) => track.stop())
  context?.close()
  context = null
  processor = null
  source = null
  stream = null
}

function reset() {
  if (recording.value) stopRecord()
  samples.value = []
  seconds.value = 0
}

async function startRecord() {
  if (samples.value.length >= 3) return
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch {
    ElMessage.error('无法访问麦克风，请检查浏览器权限')
    return
  }
  context = new AudioContext({ sampleRate: TARGET_RATE })
  rate = context.sampleRate
  source = context.createMediaStreamSource(stream)
  processor = context.createScriptProcessor(4096, 1, 1)
  chunks = []
  processor.onaudioprocess = (event) => {
    if (!recording.value) return
    chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)))
  }
  source.connect(processor)
  processor.connect(context.destination)
  recording.value = true
  seconds.value = 0
  timer = window.setInterval(() => {
    seconds.value += 1
    if (seconds.value >= MAX_SECONDS) stopRecord()
  }, 1000)
}

function stopRecord() {
  if (!recording.value) return
  recording.value = false
  cleanup()
  if (!chunks.length) {
    ElMessage.warning('没有录到声音')
    return
  }
  const merged = mergeAndResample(chunks, rate, TARGET_RATE)
  const duration = merged.length / TARGET_RATE
  chunks = []
  if (duration < MIN_SECONDS) {
    ElMessage.warning(`每段至少 ${MIN_SECONDS} 秒，请重录`)
    return
  }
  if (samples.value.length >= 3) return
  samples.value.push({ blob: encodeWav(merged, TARGET_RATE), seconds: duration })
}

function retake(index) {
  samples.value.splice(index, 1)
}

async function submit() {
  if (samples.value.length < 3) return
  saving.value = true
  try {
    const form = new FormData()
    samples.value.slice(0, 3).forEach((item, index) => {
      form.append('files', item.blob, `voiceprint_${index + 1}.wav`)
    })
    const data = await voiceApi.enrollVoiceprint(form)
    if (data) status.value = data
    samples.value = []
    ElMessage.success('声纹已绑定当前账号')
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

async function removeVoiceprint() {
  try {
    await ElMessageBox.confirm('删除后语音输入将不再校验声纹，确定删除吗？', '删除声纹', {
      type: 'warning',
    })
  } catch {
    return
  }
  removing.value = true
  try {
    const data = await voiceApi.removeVoiceprint()
    if (data) status.value = data
    ElMessage.success('声纹已删除')
  } catch {
    // 拦截器已提示
  } finally {
    removing.value = false
  }
}
</script>

<style scoped>
.muted {
  font-size: 12px;
  color: #6b7280;
}

.mt-8 {
  margin-top: 8px;
}

.mt-12 {
  margin-top: 12px;
}

.vp-enrolled {
  display: flex;
  align-items: center;
  gap: 10px;
}

.record-area {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.record-tip {
  font-size: 13px;
  color: #6b7280;
}
</style>

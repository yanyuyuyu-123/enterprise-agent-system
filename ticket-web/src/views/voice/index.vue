<template>
  <div class="page">
    <el-row :gutter="12">
      <el-col :span="12">
        <div class="page-card">
          <div class="card-title">语音转文字</div>

          <div class="record-area">
            <el-button
              :type="recording ? 'danger' : 'primary'"
              size="large"
              circle
              @click="recording ? stopRecord() : startRecord()"
            >
              <el-icon :size="22">
                <VideoPause v-if="recording" />
                <Microphone v-else />
              </el-icon>
            </el-button>
            <div class="record-tip">
              {{ recording ? `录音中 ${seconds}s / ${MAX_SECONDS}s，点击停止` : `点击开始录音，最长 ${MAX_SECONDS} 秒` }}
            </div>
          </div>

          <audio v-if="audioUrl" :src="audioUrl" controls class="audio mt-12"></audio>

          <div class="toolbar mt-12">
            <el-button type="primary" plain :loading="asrLoading" :disabled="!audioBlob" @click="uploadAsr">
              上传识别
            </el-button>
            <div class="toolbar-spacer"></div>
            <span v-if="confidence !== null" class="muted">语义可信度 {{ Math.round(confidence * 100) }}%</span>
          </div>

          <el-alert
            v-if="result?.needs_confirmation"
            type="warning"
            :closable="false"
            show-icon
            class="mt-12"
            :title="result.confirmation_question || '识别结果可能不准确，请确认后使用'"
          />

          <div v-if="result?.original_text && result.original_text !== asrText" class="mt-12">
            <div class="label">原始识别</div>
            <div class="raw-text">{{ result.original_text }}</div>
          </div>

          <div v-if="suspected.length" class="mt-8">
            <div class="label">可疑内容</div>
            <div class="suspected">
              <el-tag v-for="item in suspected" :key="item" type="warning" size="small">
                {{ item }}
              </el-tag>
            </div>
          </div>

          <div class="mt-8">
            <div class="label">确认文本（可直接修改）</div>
            <el-input
              v-model="asrText"
              type="textarea"
              :rows="4"
              placeholder="识别结果会显示在这里"
            />
          </div>

          <div class="toolbar mt-8">
            <span v-if="transcriptId" class="muted">转写编号：{{ transcriptId }}</span>
            <div class="toolbar-spacer"></div>
            <el-button :disabled="!asrText || !transcriptId" @click="confirmText">确认文本</el-button>
            <el-button type="primary" :disabled="!asrText" @click="askAgent">在 Agent 中提问</el-button>
          </div>
        </div>

        <div class="page-card mt-12">
          <div class="card-title">我的声纹</div>
          <div class="vp-row">
            <div>
              <div class="muted">账号：{{ me?.name }}{{ me?.employee_no ? `（${me.employee_no}）` : '' }}</div>
              <div class="muted mt-8">
                状态：
                <el-tag :type="voiceprint.enrolled ? 'success' : 'info'" size="small">
                  {{ voiceprint.enrolled ? `已录入（${voiceprint.samples} 段样本）` : '未录入' }}
                </el-tag>
              </div>
              <div v-if="voiceprint.enrolled && voiceprint.updated_at" class="muted mt-8">
                最近录入：{{ formatDateTime(voiceprint.updated_at) }}
              </div>
            </div>
            <div class="vp-actions">
              <el-button
                v-if="!voiceprint.enrolled"
                type="primary"
                plain
                :disabled="!voiceprint.available"
                @click="openVoiceprint"
              >
                录入声纹
              </el-button>
              <el-button
                v-else
                link
                type="danger"
                :loading="vpRemoving"
                @click="removeVoiceprint"
              >
                删除声纹
              </el-button>
            </div>
          </div>
          <el-alert
            v-if="!voiceprint.available"
            type="warning"
            :closable="false"
            show-icon
            class="mt-8"
            title="声纹模型未配置，暂不支持录入"
          />
          <div class="muted mt-8">一个账号只能绑定一个声纹，录入后语音输入会校验是否为本人。</div>
        </div>
      </el-col>

      <el-col :span="12">
        <div class="page-card">
          <div class="card-title">文字转语音</div>
          <el-input
            v-model="ttsText"
            type="textarea"
            :rows="6"
            placeholder="输入要播报的文本，超过 500 字会自动截断"
          />
          <div class="toolbar mt-8">
            <span class="muted">单次不超过 500 字</span>
            <div class="toolbar-spacer"></div>
            <el-button type="primary" :loading="ttsLoading" :disabled="!ttsText.trim()" @click="synthesize">
              生成语音
            </el-button>
          </div>
          <el-alert
            v-if="ttsTruncated"
            type="info"
            :closable="false"
            show-icon
            class="mt-8"
            title="内容较长，已截断"
          />
          <audio v-if="ttsUrl" :src="ttsUrl" controls class="audio mt-12" autoplay></audio>
          <div v-if="ttsFileId" class="muted mt-8">语音文件编号：{{ ttsFileId }}（7 天后自动清理）</div>
        </div>
      </el-col>
    </el-row>

    <el-dialog v-model="vpDialog" title="录入声纹" width="540px" :close-on-click-modal="false">
      <el-steps :active="vpSamples.length" simple>
        <el-step v-for="i in 3" :key="i" :title="`第 ${i} 段`" />
      </el-steps>

      <div class="record-area mt-12">
        <el-button
          :type="vpRecording ? 'danger' : 'primary'"
          size="large"
          circle
          :disabled="!vpRecording && vpSamples.length >= 3"
          @click="vpRecording ? vpStopRecord() : vpStartRecord()"
        >
          <el-icon :size="22">
            <VideoPause v-if="vpRecording" />
            <Microphone v-else />
          </el-icon>
        </el-button>
        <div class="record-tip">
          {{
            vpRecording
              ? `录音中 ${vpSeconds}s / ${VP_MAX_SECONDS}s，点击停止`
              : `点击录制第 ${Math.min(vpSamples.length + 1, 3)} 段，每段 ${VP_MIN_SECONDS}~${VP_MAX_SECONDS} 秒`
          }}
        </div>
      </div>

      <el-table :data="vpSamples" size="small" class="mt-12">
        <el-table-column label="录音" width="120">
          <template #default="{ $index }">第 {{ $index + 1 }} 段</template>
        </el-table-column>
        <el-table-column label="时长" width="100">
          <template #default="{ row }">{{ row.seconds.toFixed(1) }} 秒</template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ $index }">
            <el-button link type="danger" @click="vpRetake($index)">重录</el-button>
          </template>
        </el-table-column>
        <template #empty>还没有录音，请至少录入 3 段</template>
      </el-table>

      <div class="muted mt-8">请用本人声音朗读任意文字，三段内容可以不同，环境尽量安静。</div>

      <template #footer>
        <el-button @click="closeVoiceprint">取消</el-button>
        <el-button type="primary" :loading="vpSaving" :disabled="vpSamples.length < 3" @click="submitVoiceprint">
          提交录入
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'

import { voiceApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { encodeWav, mergeAndResample } from '@/utils/audio'
import { formatDateTime } from '@/utils/dict'

const TARGET_RATE = 16000
const MAX_SECONDS = 60
const VP_MIN_SECONDS = 2
const VP_MAX_SECONDS = 10

const router = useRouter()
const userStore = useUserStore()
const me = computed(() => userStore.me)

const recording = ref(false)
const seconds = ref(0)
const audioBlob = ref(null)
const audioUrl = ref('')
const asrText = ref('')
const result = ref(null)
const transcriptId = ref('')
const asrLoading = ref(false)

const ttsText = ref('')
const ttsLoading = ref(false)
const ttsUrl = ref('')
const ttsFileId = ref('')
const ttsTruncated = ref(false)

const voiceprint = ref({ enrolled: false, available: true, samples: 0, updated_at: null })
const vpDialog = ref(false)
const vpSamples = ref([])
const vpRecording = ref(false)
const vpSeconds = ref(0)
const vpSaving = ref(false)
const vpRemoving = ref(false)

let vpContext = null
let vpSource = null
let vpProcessor = null
let vpStream = null
let vpChunks = []
let vpTimer = null
let vpRate = TARGET_RATE

async function loadVoiceprint() {
  try {
    const data = await voiceApi.voiceprintStatus()
    if (data) voiceprint.value = data
  } catch {
    // 拦截器已提示
  }
}

function openVoiceprint() {
  vpSamples.value = []
  vpDialog.value = true
}

function closeVoiceprint() {
  if (vpRecording.value) vpStopRecord()
  vpDialog.value = false
}

function vpCleanup() {
  if (vpTimer) window.clearInterval(vpTimer)
  vpTimer = null
  vpProcessor?.disconnect()
  vpSource?.disconnect()
  vpStream?.getTracks().forEach((track) => track.stop())
  vpContext?.close()
  vpContext = null
  vpProcessor = null
  vpSource = null
  vpStream = null
}

async function vpStartRecord() {
  if (vpSamples.value.length >= 3) return
  try {
    vpStream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch {
    ElMessage.error('无法访问麦克风，请检查浏览器权限')
    return
  }
  vpContext = new AudioContext({ sampleRate: TARGET_RATE })
  vpRate = vpContext.sampleRate
  vpSource = vpContext.createMediaStreamSource(vpStream)
  vpProcessor = vpContext.createScriptProcessor(4096, 1, 1)
  vpChunks = []
  vpProcessor.onaudioprocess = (event) => {
    if (!vpRecording.value) return
    vpChunks.push(new Float32Array(event.inputBuffer.getChannelData(0)))
  }
  vpSource.connect(vpProcessor)
  vpProcessor.connect(vpContext.destination)
  vpRecording.value = true
  vpSeconds.value = 0
  vpTimer = window.setInterval(() => {
    vpSeconds.value += 1
    if (vpSeconds.value >= VP_MAX_SECONDS) vpStopRecord()
  }, 1000)
}

function vpStopRecord() {
  if (!vpRecording.value) return
  vpRecording.value = false
  vpCleanup()
  if (!vpChunks.length) {
    ElMessage.warning('没有录到声音')
    return
  }
  const samples = mergeAndResample(vpChunks, vpRate, TARGET_RATE)
  const seconds = samples.length / TARGET_RATE
  vpChunks = []
  if (seconds < VP_MIN_SECONDS) {
    ElMessage.warning(`每段至少 ${VP_MIN_SECONDS} 秒，请重录`)
    return
  }
  if (vpSamples.value.length >= 3) return
  vpSamples.value.push({ blob: encodeWav(samples, TARGET_RATE), seconds })
}

function vpRetake(index) {
  vpSamples.value.splice(index, 1)
}

async function submitVoiceprint() {
  if (vpSamples.value.length < 3) return
  vpSaving.value = true
  try {
    const form = new FormData()
    vpSamples.value.slice(0, 3).forEach((item, index) => {
      form.append('files', item.blob, `voiceprint_${index + 1}.wav`)
    })
    const data = await voiceApi.enrollVoiceprint(form)
    if (data) voiceprint.value = data
    vpDialog.value = false
    vpSamples.value = []
    ElMessage.success('声纹已绑定当前账号')
  } catch {
    // 拦截器已提示
  } finally {
    vpSaving.value = false
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
  vpRemoving.value = true
  try {
    const data = await voiceApi.removeVoiceprint()
    if (data) voiceprint.value = data
    ElMessage.success('声纹已删除')
  } catch {
    // 拦截器已提示
  } finally {
    vpRemoving.value = false
  }
}

const confidence = computed(() => {
  const value = result.value?.semantic_confidence
  return value === null || value === undefined ? null : Number(value)
})
const suspected = computed(() => result.value?.suspected_errors || [])

let audioContext = null
let sourceNode = null
let processor = null
let mediaStream = null
let chunks = []
let timer = null
let actualRate = TARGET_RATE

async function startRecord() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch {
    ElMessage.error('无法访问麦克风，请检查浏览器权限')
    return
  }
  audioContext = new AudioContext({ sampleRate: TARGET_RATE })
  actualRate = audioContext.sampleRate
  sourceNode = audioContext.createMediaStreamSource(mediaStream)
  processor = audioContext.createScriptProcessor(4096, 1, 1)
  chunks = []
  processor.onaudioprocess = (event) => {
    if (!recording.value) return
    chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)))
  }
  sourceNode.connect(processor)
  processor.connect(audioContext.destination)
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
  if (timer) window.clearInterval(timer)
  processor?.disconnect()
  sourceNode?.disconnect()
  mediaStream?.getTracks().forEach((track) => track.stop())
  audioContext?.close()
  audioContext = null
  if (!chunks.length) {
    ElMessage.warning('没有录到声音')
    return
  }
  const samples = mergeAndResample(chunks, actualRate, TARGET_RATE)
  audioBlob.value = encodeWav(samples, TARGET_RATE)
  if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
  audioUrl.value = URL.createObjectURL(audioBlob.value)
}

async function uploadAsr() {
  if (!audioBlob.value) return
  asrLoading.value = true
  try {
    const form = new FormData()
    form.append('file', new File([audioBlob.value], 'record.wav', { type: 'audio/wav' }))
    const data = await voiceApi.asr(form)
    result.value = data
    transcriptId.value = String(data?.transcript_id || '')
    asrText.value = data?.final_text || data?.corrected_text || data?.original_text || ''
    // 文本清晰时不再手动点确认，直接带着问题进 Agent
    if (!data?.needs_confirmation && asrText.value) {
      askAgent(true)
    }
  } catch {
    // 拦截器已提示
  } finally {
    asrLoading.value = false
  }
}

async function confirmText() {
  try {
    const data = await voiceApi.confirm({
      transcript_id: Number(transcriptId.value),
      final_text: asrText.value,
    })
    if (data?.final_text) asrText.value = data.final_text
    ElMessage.success('文本已确认')
  } catch {
    // 拦截器已提示
  }
}

function askAgent(autoSend = false) {
  if (!asrText.value.trim()) return
  router.push({ path: '/agent', query: { q: asrText.value, ...(autoSend ? { send: '1' } : {}) } })
}

async function synthesize() {
  ttsLoading.value = true
  try {
    const data = await voiceApi.tts({ text: ttsText.value })
    ttsFileId.value = String(data?.voice_file_id || '')
    ttsTruncated.value = Boolean(data?.truncated)
    if (!ttsFileId.value) {
      ElMessage.error('语音合成未返回文件')
      return
    }
    const response = await voiceApi.fileBlob(ttsFileId.value)
    if (ttsUrl.value) URL.revokeObjectURL(ttsUrl.value)
    ttsUrl.value = URL.createObjectURL(response.data)
  } catch {
    // 拦截器已提示
  } finally {
    ttsLoading.value = false
  }
}

onMounted(loadVoiceprint)

onBeforeUnmount(() => {
  if (recording.value) stopRecord()
  if (vpRecording.value) vpStopRecord()
  if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
  if (ttsUrl.value) URL.revokeObjectURL(ttsUrl.value)
})
</script>

<style scoped>
.card-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
}

.record-area {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.record-tip {
  font-size: 13px;
  color: #6b7280;
}

.audio {
  width: 100%;
}

.label {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
}

.raw-text {
  font-size: 13px;
  color: #4b5563;
  background: #f9fafb;
  border-radius: 4px;
  padding: 8px 10px;
  line-height: 1.6;
}

.suspected {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.vp-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.vp-actions {
  flex: none;
}
</style>

<template>
  <div class="page">
    <div class="page-card chat-card">
      <div class="chat-head">
        <div>
          <div class="chat-title">Agent</div>
          <div class="muted">自动判断问题类型，分派给工单、知识库、运营、财务 Agent；写操作需二次确认</div>
        </div>
        <div class="chat-actions">
          <el-button size="small" @click="voiceprintVisible = true">声纹录入</el-button>
          <el-button size="small" @click="openHistory">历史会话</el-button>
          <el-button size="small" @click="resetSession">新会话</el-button>
        </div>
      </div>

      <div ref="chatRef" class="chat-body">
        <div v-if="!messages.length" class="chat-empty">
          <div class="empty-title">我是企业智能助手</div>
          <div class="empty-sub">
            工单、制度流程、经营数据、财务数据都可以直接问我；涉及写操作会先请你确认。
          </div>
          <div class="capability-list">
            <div v-for="item in capabilities" :key="item.title" class="capability-item">
              <div class="capability-title">{{ item.title }}</div>
              <div class="capability-desc">{{ item.desc }}</div>
            </div>
          </div>
          <div class="empty-sub">创建工单：</div>
          <div class="quick-list">
            <el-button
              v-for="item in createPrompts"
              :key="item.label"
              size="small"
              round
              @click="useQuick(item.text)"
            >
              {{ item.label }}
            </el-button>
          </div>
          <div class="empty-sub">试着这样问：</div>
          <div class="quick-list">
            <el-button
              v-for="item in quickPrompts"
              :key="item"
              size="small"
              round
              @click="useQuick(item)"
            >
              {{ item }}
            </el-button>
          </div>
        </div>

        <div
          v-for="(message, index) in messages"
          :key="index"
          class="message"
          :class="message.role"
        >
          <div class="bubble">
            <div class="bubble-content">{{ message.content || (streamingIndex === index ? '思考中…' : '') }}</div>

            <div v-if="message.sources?.length" class="sources">
              <template v-if="metricSources(message.sources).length">
                <div class="sources-title">数据来源（数据库实时统计）</div>
                <div
                  v-for="source in metricSources(message.sources)"
                  :key="`m-${source.id || source.title}`"
                  class="source-item"
                >
                  {{ source.title }} {{ source.locator }}
                </div>
              </template>
              <template v-if="calculatorSources(message.sources).length">
                <div class="sources-title">计算工具</div>
                <div
                  v-for="source in calculatorSources(message.sources)"
                  :key="`c-${source.id || source.title}`"
                  class="source-item"
                >
                  {{ source.title }} {{ source.locator }}
                </div>
              </template>
              <template v-if="knowledgeSources(message.sources).length">
                <div class="sources-title">参考知识</div>
                <div
                  v-for="source in knowledgeSources(message.sources)"
                  :key="`k-${source.chunk_id || source.id || source.title}`"
                  class="source-item"
                >
                  《{{ source.title }}》 {{ source.locator }}
                </div>
              </template>
            </div>

            <div v-if="message.confirmation" class="confirm-box">
              <div class="confirm-title">该操作需要确认</div>
              <div v-if="message.confirmation.summary" class="confirm-summary">
                {{ message.confirmation.summary }}
              </div>
              <div class="muted">确认后会按业务规则执行，成功后可在对应页面查看结果。</div>
              <div class="confirm-actions">
                <el-button type="primary" size="small" @click="confirmAction(index, false)">
                  确认执行
                </el-button>
                <el-button size="small" @click="confirmAction(index, true)">取消</el-button>
              </div>
            </div>

            <div v-if="resultLink(message)" class="result-link">
              <el-link type="primary" @click="router.push(resultLink(message).path)">
                {{ resultLink(message).label }}
              </el-link>
            </div>
          </div>
        </div>
      </div>

      <div v-if="voiceState === 'confirm'" class="voice-confirm">
        <div class="voice-confirm-head">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ voiceQuestion }}</span>
        </div>
        <el-input
          v-model="voiceText"
          type="textarea"
          :rows="2"
          resize="none"
          @keydown.enter.exact.prevent="confirmVoice"
        />
        <div v-if="voiceSuspected.length" class="voice-tags">
          <el-tag v-for="item in voiceSuspected" :key="item" size="small" type="warning">
            {{ item }}
          </el-tag>
        </div>
        <div class="voice-confirm-actions">
          <span class="muted">可直接修改文字，确认后发给 Agent</span>
          <div>
            <el-button size="small" @click="retryVoice">重说</el-button>
            <el-button
              type="primary"
              size="small"
              :disabled="!voiceText.trim()"
              @click="confirmVoice"
            >
              发送
            </el-button>
          </div>
        </div>
      </div>

      <div v-if="voiceState === 'recording'" class="chat-input recording">
        <div class="voice-live">
          <span class="voice-dot"></span>
          <div class="voice-wave">
            <span
              v-for="(level, index) in voiceLevels"
              :key="index"
              :style="{ height: `${level}px` }"
            ></span>
          </div>
          <span class="voice-timer">{{ voiceSeconds }}s</span>
          <span class="voice-hint">说完停顿一下会自动发送</span>
        </div>
        <el-button class="voice-stop" type="danger" circle @click="stopVoice">
          <el-icon :size="18"><VideoPause /></el-icon>
        </el-button>
      </div>

      <div v-else-if="voiceState === 'transcribing'" class="chat-input transcribing">
        <el-icon class="is-loading" :size="18"><Loading /></el-icon>
        <span>正在识别语音…</span>
      </div>

      <div v-else class="chat-input">
        <el-input
          v-model="input"
          type="textarea"
          :rows="2"
          resize="none"
          placeholder="输入问题，Enter 发送，Shift + Enter 换行"
          @keydown.enter.exact.prevent="send"
        />
        <el-button v-if="canVoice" class="mic-btn" circle title="语音输入" @click="startVoice">
          <el-icon :size="18"><Microphone /></el-icon>
        </el-button>
        <el-button type="primary" :loading="sending" :disabled="!input.trim()" @click="send">
          发送
        </el-button>
      </div>
    </div>

    <el-drawer v-model="historyVisible" title="历史会话" size="380px">
      <div v-if="historyLoading" class="muted">加载中…</div>
      <div v-else-if="!historySessions.length" class="muted">暂无历史会话</div>
      <div v-else class="history-list">
        <div
          v-for="item in historySessions"
          :key="item.session_id"
          class="history-item"
          :class="{ active: item.session_id === sessionId }"
          @click="loadSession(item)"
        >
          <div class="history-title">{{ item.title }}</div>
          <div class="history-preview">{{ item.preview }}</div>
          <div class="history-time">{{ formatTime(item.last_at) }}</div>
        </div>
      </div>
    </el-drawer>

    <VoiceprintDialog v-model="voiceprintVisible" />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import { TOKEN_KEY } from '@/api/request'
import { agentApi, voiceApi } from '@/api'
import VoiceprintDialog from '@/components/VoiceprintDialog.vue'
import { useUserStore } from '@/stores/user'
import { encodeWav, mergeAndResample } from '@/utils/audio'
import { hasPermission } from '@/utils/permission'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const CHAT_STORAGE_PREFIX = 'ticket-agent-chat'

const createPrompts = [
  { label: '设备维修', text: '帮我创建一个设备维修工单，产煤机 A 出现故障' },
  { label: '报销', text: '帮我创建一个报销工单，采购杂费 1000 元' },
  { label: '安全巡查', text: '帮我创建一个安全巡查工单' },
  { label: '运输异常', text: '帮我创建一个运输异常工单' },
]

const quickPrompts = [
  '我负责的待处理工单有哪些？',
  '报销流程是什么？',
  '本月库存和销售情况',
  '本月收入、成本和利润',
]

const capabilities = [
  { title: '工单办理', desc: '创建报修、报销、巡查、运输异常工单，查询、查看详情、分配、提交结果' },
  { title: '制度流程', desc: '查询企业知识库里的制度、流程、手册、合同、报价' },
  { title: '经营数据', desc: '采购、销售、库存、客户、供应商汇总' },
  { title: '财务数据', desc: '收入、成本、利润、资金、应收应付汇总' },
]

const messages = ref([])
const input = ref('')
const sending = ref(false)
const streamingIndex = ref(-1)
const sessionId = ref('')
const chatRef = ref()
const historyVisible = ref(false)
const historyLoading = ref(false)
const voiceprintVisible = ref(false)
const historySessions = ref([])

// 语音输入：点一下麦克风就开口说，停顿自动结束；听不清才要确认
const VOICE_RATE = 16000
const MAX_VOICE_SECONDS = 60
const SILENCE_MS = 1400
const SILENCE_RMS = 0.015

const canVoice = computed(() => hasPermission(userStore.me?.permissions, 'voice:create'))
const voiceState = ref('idle') // idle | recording | transcribing | confirm
const voiceSeconds = ref(0)
const voiceText = ref('')
const voiceQuestion = ref('')
const voiceResult = ref(null)
const voiceLevels = ref(Array.from({ length: 24 }, () => 3))
const voiceSuspected = computed(() => voiceResult.value?.suspected_errors || [])

let audioContext = null
let sourceNode = null
let processor = null
let mediaStream = null
let voiceTimer = null
let voiceChunks = []
let voiceRate = VOICE_RATE
let voiceStartedAt = 0
let lastSpeechAt = 0
let hasSpeech = false

function scrollToBottom() {
  nextTick(() => {
    if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight
  })
}

function metricSources(sources = []) {
  return sources.filter((source) => source.type === 'metric')
}

function calculatorSources(sources = []) {
  return sources.filter((source) => source.type === 'calculator')
}

function knowledgeSources(sources = []) {
  // 只展示带标题的知识片段；业务/车辆工具的结果没有标题，不放进“参考知识”
  return sources.filter(
    (source) => source.title && source.type !== 'metric' && source.type !== 'calculator',
  )
}

function storageKey() {
  const me = userStore.me
  const identity = me?.id || me?.employee_no || me?.username || 'default'
  return `${CHAT_STORAGE_PREFIX}:${identity}`
}

function persistChat() {
  try {
    localStorage.setItem(
      storageKey(),
      JSON.stringify({
        sessionId: sessionId.value,
        messages: messages.value,
        draft: input.value,
      }),
    )
  } catch {
    // 存储空间不足时忽略
  }
}

function restoreChat() {
  try {
    const raw = localStorage.getItem(storageKey())
    if (!raw) return
    const data = JSON.parse(raw)
    if (Array.isArray(data?.messages)) messages.value = data.messages
    if (typeof data?.sessionId === 'string') sessionId.value = data.sessionId
    // 恢复未发送的草稿，避免切到其他页面后输入内容丢失
    if (typeof data?.draft === 'string') input.value = data.draft
  } catch {
    // 本地数据损坏时忽略
  }
}

function useQuick(text) {
  input.value = text
  send()
}

function resetSession() {
  messages.value = []
  sessionId.value = ''
  input.value = ''
  try {
    localStorage.removeItem(storageKey())
  } catch {
    // 忽略
  }
}

async function openHistory() {
  historyVisible.value = true
  historyLoading.value = true
  try {
    historySessions.value = (await agentApi.sessions()) || []
  } catch {
    historySessions.value = []
  } finally {
    historyLoading.value = false
  }
}

async function loadSession(item) {
  try {
    const data = await agentApi.sessionMessages(item.session_id)
    messages.value = (data.messages || []).map((message) => ({
      role: message.role,
      content: message.content,
      sources: message.sources || [],
    }))
    sessionId.value = data.session_id
    historyVisible.value = false
    persistChat()
    scrollToBottom()
  } catch {
    // 错误提示由请求拦截器统一处理
  }
}

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (num) => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function handleEvent(event, message) {
  if (event.type === 'start') {
    if (event.session_id) sessionId.value = event.session_id
  } else if (event.type === 'token') {
    message.content += event.content || ''
    scrollToBottom()
  } else if (event.type === 'result') {
    if (event.session_id) sessionId.value = event.session_id
    if (event.answer) message.content = event.answer
    message.confirmation = event.confirmation || null
    message.sources = event.sources || []
    message.tool_result = event.tool_result || null
  } else if (event.type === 'error') {
    message.content = event.message || '处理失败'
    ElMessage.error(event.message || '处理失败')
  }
  persistChat()
}

function resultLink(message) {
  const data = message.tool_result?.data
  if (!data) return null
  if (data.movement_no) {
    return { label: `查看出入库单 ${data.movement_no}`, path: `/stock-movements?id=${data.id}` }
  }
  const orderNo = data.order_no
  if (!orderNo) return null
  if (orderNo.startsWith('PO')) {
    return { label: `查看采购单 ${orderNo}`, path: `/purchase-orders?id=${data.id}` }
  }
  if (orderNo.startsWith('SO')) {
    return { label: `查看销售单 ${orderNo}`, path: `/sales-orders?id=${data.id}` }
  }
  return null
}

async function streamChat(payload, message) {
  const response = await fetch('/api/v1/agent/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${localStorage.getItem(TOKEN_KEY) || ''}`,
    },
    body: JSON.stringify(payload),
  })
  if (!response.ok || !response.body) {
    throw new Error(`请求失败（${response.status}）`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const chunk = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      for (const line of chunk.split('\n')) {
        if (line.startsWith('data: ')) {
          try {
            handleEvent(JSON.parse(line.slice(6)), message)
          } catch {
            // 忽略无法解析的片段
          }
        }
      }
      boundary = buffer.indexOf('\n\n')
    }
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  input.value = ''
  messages.value.push({ role: 'user', content: text })
  messages.value.push({ role: 'assistant', content: '', sources: [] })
  const message = messages.value[messages.value.length - 1]
  streamingIndex.value = messages.value.length - 1
  sending.value = true
  persistChat()
  scrollToBottom()
  try {
    await streamChat({ session_id: sessionId.value || null, message: text }, message)
  } catch (error) {
    message.content = error.message || '网络异常，请稍后重试'
    ElMessage.error(message.content)
  } finally {
    sending.value = false
    streamingIndex.value = -1
    persistChat()
    scrollToBottom()
  }
}

async function confirmAction(index, cancel) {
  const message = messages.value[index]
  const token = message.confirmation?.confirm_token
  if (!token) return
  message.confirmation = null
  messages.value.push({
    role: 'user',
    content: cancel ? '取消该操作' : '确认执行',
  })
  messages.value.push({ role: 'assistant', content: '', sources: [] })
  const next = messages.value[messages.value.length - 1]
  streamingIndex.value = messages.value.length - 1
  sending.value = true
  persistChat()
  scrollToBottom()
  try {
    await streamChat(
      { session_id: sessionId.value || null, confirm_token: token, cancel },
      next,
    )
  } catch (error) {
    next.content = error.message || '网络异常，请稍后重试'
  } finally {
    sending.value = false
    streamingIndex.value = -1
    persistChat()
    scrollToBottom()
  }
}

function releaseRecorder() {
  const captured = voiceChunks
  voiceChunks = []
  if (voiceTimer) window.clearInterval(voiceTimer)
  voiceTimer = null
  processor?.disconnect()
  sourceNode?.disconnect()
  mediaStream?.getTracks().forEach((track) => track.stop())
  audioContext?.close()
  processor = null
  sourceNode = null
  mediaStream = null
  audioContext = null
  return captured
}

async function startVoice() {
  if (voiceState.value === 'recording' || voiceState.value === 'transcribing') return
  if (voiceState.value === 'confirm') resetVoice()
  if (!canVoice.value) {
    ElMessage.warning('当前账号没有语音输入权限')
    return
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch {
    ElMessage.error('无法访问麦克风，请检查浏览器权限')
    return
  }

  audioContext = new AudioContext({ sampleRate: VOICE_RATE })
  voiceRate = audioContext.sampleRate
  sourceNode = audioContext.createMediaStreamSource(mediaStream)
  processor = audioContext.createScriptProcessor(2048, 1, 1)
  voiceChunks = []
  hasSpeech = false
  lastSpeechAt = 0
  voiceStartedAt = Date.now()
  voiceSeconds.value = 0
  voiceLevels.value = Array.from({ length: 24 }, () => 3)

  processor.onaudioprocess = (event) => {
    if (voiceState.value !== 'recording') return
    const data = new Float32Array(event.inputBuffer.getChannelData(0))
    voiceChunks.push(data)
    let sum = 0
    for (let i = 0; i < data.length; i += 1) sum += data[i] * data[i]
    const rms = Math.sqrt(sum / data.length)
    voiceLevels.value = [...voiceLevels.value.slice(1), Math.min(30, 3 + rms * 260)]
    if (rms > SILENCE_RMS) {
      hasSpeech = true
      lastSpeechAt = Date.now()
    } else if (hasSpeech && Date.now() - lastSpeechAt > SILENCE_MS) {
      stopVoice()
    }
  }

  sourceNode.connect(processor)
  processor.connect(audioContext.destination)
  voiceState.value = 'recording'
  voiceTimer = window.setInterval(() => {
    voiceSeconds.value = Math.floor((Date.now() - voiceStartedAt) / 1000)
    if (voiceSeconds.value >= MAX_VOICE_SECONDS) stopVoice()
  }, 500)
}

async function stopVoice() {
  if (voiceState.value !== 'recording') return
  const captured = releaseRecorder()
  voiceState.value = 'idle'
  if (!hasSpeech || !captured.length) {
    ElMessage.warning('没有听到声音，请再说一次')
    return
  }
  const samples = mergeAndResample(captured, voiceRate, VOICE_RATE)
  if (samples.length < VOICE_RATE * 0.4) {
    ElMessage.warning('说话时间太短，请再说一次')
    return
  }
  await recognizeVoice(encodeWav(samples, VOICE_RATE))
}

async function recognizeVoice(blob) {
  voiceState.value = 'transcribing'
  try {
    const form = new FormData()
    form.append('file', new File([blob], 'voice.wav', { type: 'audio/wav' }))
    const data = await voiceApi.asr(form)
    const text = (data?.final_text || data?.corrected_text || data?.original_text || '').trim()
    if (!text) {
      ElMessage.warning('没有识别到内容，请再说一次')
      voiceState.value = 'idle'
      return
    }
    if (data.needs_confirmation) {
      voiceResult.value = { ...data }
      voiceText.value = text
      voiceQuestion.value = data.confirmation_question || '识别结果需要确认'
      voiceState.value = 'confirm'
      return
    }
    // 文本清晰：直接发给 Agent，和手打字完全同一条链路
    voiceState.value = 'idle'
    input.value = text
    await send()
  } catch {
    voiceState.value = 'idle'
  }
}

async function confirmVoice() {
  const text = voiceText.value.trim()
  if (!text) return
  const transcriptId = voiceResult.value?.transcript_id
  if (transcriptId) {
    try {
      await voiceApi.confirm({ transcript_id: Number(transcriptId), final_text: text })
    } catch {
      // 确认记录失败不影响发送
    }
  }
  resetVoice()
  input.value = text
  await send()
}

function resetVoice() {
  voiceResult.value = null
  voiceText.value = ''
  voiceQuestion.value = ''
  voiceState.value = 'idle'
}

async function retryVoice() {
  resetVoice()
  await startVoice()
}

onMounted(() => {
  restoreChat()
  const question = typeof route.query.q === 'string' ? route.query.q : ''
  if (question) {
    input.value = question
    if (route.query.send === '1') {
      // 语音转写已确认清晰：直接发送，并清掉地址栏参数避免刷新重复发送
      router.replace({ path: '/agent' })
      send()
    }
  }
  scrollToBottom()
})

onBeforeUnmount(() => {
  // 离开页面前保存输入框草稿，回来时还能接着写
  persistChat()
  releaseRecorder()
})
</script>

<style scoped>
.chat-card {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 88px);
  padding: 0;
}

.chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #eef0f4;
}

.chat-title {
  font-size: 15px;
  font-weight: 600;
}

.chat-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.chat-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.history-item {
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s;
}

.history-item:hover {
  border-color: #c6e2ff;
  background: #f5f9ff;
}

.history-item.active {
  border-color: #409eff;
  background: #ecf5ff;
}

.history-title {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-preview {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-time {
  margin-top: 6px;
  font-size: 12px;
  color: #c0c4cc;
}

.chat-body {
  flex: 1;
  overflow: auto;
  padding: 16px;
  background: #fafbfc;
}

.chat-empty {
  max-width: 620px;
  margin: 24px auto 0;
}

.empty-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.empty-sub {
  margin-top: 6px;
  font-size: 13px;
  color: #909399;
  line-height: 1.6;
}

.capability-list {
  margin: 16px 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.capability-item {
  padding: 10px 12px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
}

.capability-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.capability-desc {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.quick-list {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.message {
  display: flex;
  flex-direction: column;
  margin-bottom: 14px;
}

.message.user {
  align-items: flex-end;
}

.message.assistant {
  align-items: flex-start;
}

.bubble {
  max-width: 78%;
  background: #fff;
  border: 1px solid #eef0f4;
  border-radius: 8px;
  padding: 10px 12px;
}

.message.user .bubble {
  background: #2f6feb;
  border-color: #2f6feb;
  color: #fff;
}

.bubble-content {
  white-space: pre-wrap;
  line-height: 1.7;
  font-size: 13px;
}

.sources {
  margin-top: 10px;
  border-top: 1px dashed #e5e8ef;
  padding-top: 8px;
  font-size: 12px;
  color: #6b7280;
}

.sources-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.source-item {
  line-height: 1.7;
}

.confirm-box {
  margin-top: 10px;
  border: 1px solid #f0d08a;
  background: #fff9ec;
  border-radius: 6px;
  padding: 10px;
  color: #1f2329;
}

.confirm-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.confirm-summary {
  font-size: 13px;
  color: #b26a00;
  margin-bottom: 4px;
  word-break: break-all;
}

.result-link {
  margin-top: 8px;
}

.confirm-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}

.chat-input {
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  border-top: 1px solid #eef0f4;
  align-items: flex-end;
}

.chat-input :deep(.el-textarea) {
  flex: 1;
}

.mic-btn {
  flex: none;
  width: 40px;
  height: 40px;
  border: 1px solid #dfe4ee;
  color: #38414f;
  background: #fff;
}

.mic-btn:hover {
  color: #2f6feb;
  border-color: #b9d1fb;
  background: #f2f7ff;
}

.chat-input.recording {
  align-items: center;
  background: #f7f9ff;
}

.voice-live {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 40px;
  padding: 0 4px;
}

.voice-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #ef4444;
  animation: voice-pulse 1.2s ease-in-out infinite;
}

@keyframes voice-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.35;
    transform: scale(0.8);
  }
}

.voice-wave {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 3px;
  height: 34px;
  overflow: hidden;
}

.voice-wave span {
  width: 3px;
  border-radius: 2px;
  background: #2f6feb;
  transition: height 0.12s linear;
}

.voice-timer {
  font-size: 13px;
  color: #38414f;
  font-variant-numeric: tabular-nums;
}

.voice-hint {
  font-size: 12px;
  color: #98a2b3;
}

.voice-stop {
  flex: none;
  width: 40px;
  height: 40px;
}

.chat-input.transcribing {
  align-items: center;
  gap: 8px;
  color: #6b7280;
  font-size: 13px;
}

.voice-confirm {
  margin: 0 16px;
  padding: 12px;
  border: 1px solid #f0d08a;
  background: #fff9ec;
  border-radius: 10px 10px 0 0;
  border-bottom: none;
}

.voice-confirm-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #8a5b00;
  margin-bottom: 8px;
}

.voice-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.voice-confirm-actions {
  margin-top: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
}
</style>

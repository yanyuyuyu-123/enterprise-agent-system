<template>
  <div class="page">
    <el-row :gutter="12">
      <el-col :span="24">
        <div class="page-card">
          <div class="toolbar">
            <el-select v-model="query.status" placeholder="状态" clearable style="width: 130px">
              <el-option
                v-for="(item, key) in KNOWLEDGE_STATUS"
                :key="key"
                :label="item.label"
                :value="key"
              />
            </el-select>
            <el-select v-model="query.category" placeholder="分类" clearable style="width: 120px">
              <el-option
                v-for="(label, key) in KNOWLEDGE_CATEGORY"
                :key="key"
                :label="label"
                :value="key"
              />
            </el-select>
            <el-button type="primary" @click="reload">查询</el-button>
            <div class="toolbar-spacer"></div>
            <el-button v-if="canCreate" type="primary" plain @click="openUpload">上传文档</el-button>
          </div>

          <el-table v-loading="loading" :data="rows" size="small">
            <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
            <el-table-column label="分类" width="90">
              <template #default="{ row }">{{ labelOf(KNOWLEDGE_CATEGORY, row.category) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="tagOf(KNOWLEDGE_STATUS, row.status).type" size="small">
                  {{ tagOf(KNOWLEDGE_STATUS, row.status).label }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="chunk_count" label="切片" width="70" />
            <el-table-column prop="version" label="版本" width="70" />
            <el-table-column label="更新时间" width="150">
              <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="200">
              <template #default="{ row }">
                <el-button link type="primary" @click="openDetail(row)">详情</el-button>
                <el-button link type="primary" @click="downloadDoc(row)">下载</el-button>
                <el-button v-if="canUpdate" link type="warning" @click="reprocess(row)">重解析</el-button>
                <el-button v-if="canDelete" link type="danger" @click="removeDoc(row)">删除</el-button>
              </template>
            </el-table-column>
            <template #empty>暂无知识文档</template>
          </el-table>

          <div class="pager">
            <el-pagination
              v-model:current-page="query.page"
              v-model:page-size="query.page_size"
              :total="total"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next"
              @current-change="load"
              @size-change="reload"
            />
          </div>
        </div>
      </el-col>
    </el-row>

    <el-dialog v-model="uploadVisible" title="上传知识文档" width="640px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="分类">
          <el-select v-model="uploadForm.category" style="width: 100%">
            <el-option
              v-for="(label, key) in KNOWLEDGE_CATEGORY"
              :key="key"
              :label="label"
              :value="key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="可见范围">
          <el-radio-group v-model="uploadForm.visibility_scope">
            <el-radio value="company">全公司</el-radio>
            <el-radio value="department">本部门</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="文件" required>
          <input type="file" multiple @change="onFilesChange" />
          <div class="muted">支持 pdf/docx/xlsx/csv/md/txt，可一次选择多个文件</div>
        </el-form-item>
      </el-form>

      <div v-if="uploadFiles.length" class="file-list">
        <div v-for="(item, index) in uploadFiles" :key="item.key" class="file-row">
          <span class="file-name" :title="item.file.name">{{ item.file.name }}</span>
          <el-input v-model="item.title" size="small" placeholder="标题" />
          <el-button link type="danger" @click="removeFile(index)">移除</el-button>
        </div>
      </div>

      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="submitUpload">
          {{ uploading ? uploadProgress : `上传${uploadFiles.length ? `（${uploadFiles.length}）` : ''}` }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" title="文档详情" width="620px">
      <el-descriptions v-if="detail" :column="2" border>
        <el-descriptions-item label="文档编号">{{ detail.doc_no }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          {{ tagOf(KNOWLEDGE_STATUS, detail.status).label }}
        </el-descriptions-item>
        <el-descriptions-item label="标题" :span="2">{{ detail.title }}</el-descriptions-item>
        <el-descriptions-item label="文件名">{{ detail.file_name }}</el-descriptions-item>
        <el-descriptions-item label="分类">
          {{ labelOf(KNOWLEDGE_CATEGORY, detail.category) }}
        </el-descriptions-item>
        <el-descriptions-item label="可见范围">
          {{ detail.visibility_scope === 'company' ? '全公司' : '本部门' }}
        </el-descriptions-item>
        <el-descriptions-item label="切片数">{{ detail.chunk_count }}</el-descriptions-item>
        <el-descriptions-item label="版本">{{ detail.version }}</el-descriptions-item>
        <el-descriptions-item label="解析时间">
          {{ formatDateTime(detail.parsed_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="错误信息" :span="2">
          {{ detail.error_message || '-' }}
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { knowledgeApi } from '@/api'
import { useUserStore } from '@/stores/user'
import {
  KNOWLEDGE_CATEGORY,
  KNOWLEDGE_STATUS,
  formatDateTime,
  labelOf,
  tagOf,
} from '@/utils/dict'
import { hasPermission } from '@/utils/permission'

const store = useUserStore()
const canCreate = computed(() =>
  hasPermission(store.me?.permissions, 'knowledge_document:create'),
)
const canDelete = computed(() =>
  hasPermission(store.me?.permissions, 'knowledge_document:delete'),
)
const canUpdate = computed(() =>
  hasPermission(store.me?.permissions, 'knowledge_document:update'),
)

const loading = ref(false)
const uploading = ref(false)
const uploadProgress = ref('')
const rows = ref([])
const total = ref(0)

const query = reactive({ status: '', category: '', page: 1, page_size: 20 })

const uploadVisible = ref(false)
const uploadForm = reactive({
  category: 'policy',
  visibility_scope: 'company',
})
const uploadFiles = ref([])

const detailVisible = ref(false)
const detail = ref(null)

async function load() {
  loading.value = true
  try {
    const data = await knowledgeApi.list({ ...query })
    rows.value = data?.items || []
    total.value = data?.total || 0
  } catch {
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function reload() {
  query.page = 1
  load()
}

function openUpload() {
  uploadForm.category = 'policy'
  uploadForm.visibility_scope = 'company'
  uploadFiles.value = []
  uploadVisible.value = true
}

function onFilesChange(event) {
  const selected = Array.from(event.target.files || [])
  for (const file of selected) {
    uploadFiles.value.push({
      key: `${file.name}-${file.lastModified}-${Math.random().toString(36).slice(2)}`,
      file,
      title: file.name.replace(/\.[^.]+$/, ''),
    })
  }
  event.target.value = ''
}

function removeFile(index) {
  uploadFiles.value.splice(index, 1)
}

async function submitUpload() {
  const pending = uploadFiles.value
  if (!pending.length) {
    ElMessage.warning('请选择文件')
    return
  }
  if (pending.some((item) => !item.title.trim())) {
    ElMessage.warning('请填写每个文件的标题')
    return
  }
  uploading.value = true
  let done = 0
  let failed = 0
  for (const [index, item] of pending.entries()) {
    uploadProgress.value = `上传中 ${index + 1}/${pending.length}`
    const form = new FormData()
    form.append('title', item.title.trim())
    form.append('category', uploadForm.category)
    form.append('visibility_scope', uploadForm.visibility_scope)
    form.append('file', item.file)
    try {
      await knowledgeApi.upload(form)
      done += 1
    } catch {
      // 拦截器已提示
      failed += 1
    }
  }
  uploading.value = false
  uploadProgress.value = ''
  if (done) ElMessage.success(`已上传 ${done} 个文件，后台解析完成后可被 Agent 检索`)
  if (failed) {
    ElMessage.warning(`${failed} 个文件上传失败，请重试`)
  } else {
    uploadVisible.value = false
  }
  await load()
}

async function openDetail(row) {
  detailVisible.value = true
  detail.value = null
  try {
    detail.value = await knowledgeApi.detail(row.id)
  } catch {
    detailVisible.value = false
  }
}

function downloadDoc(row) {
  knowledgeApi.download(row.id, row.file_name)
}

async function reprocess(row) {
  try {
    await ElMessageBox.confirm(`确认重新解析《${row.title}》？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await knowledgeApi.reprocess(row.id)
    ElMessage.success('已提交解析任务')
    await load()
  } catch {
    // 拦截器已提示
  }
}

async function removeDoc(row) {
  try {
    await ElMessageBox.confirm(`确认删除《${row.title}》？删除后不可检索。`, '删除文档', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await knowledgeApi.remove(row.id)
    ElMessage.success('已删除')
    await load()
  } catch {
    // 拦截器已提示
  }
}

onMounted(load)
</script>

<style scoped>
.file-list {
  margin-top: 4px;
  max-height: 320px;
  overflow: auto;
  border-top: 1px solid #eef0f4;
}

.file-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid #f4f6f9;
}

.file-name {
  width: 200px;
  flex-shrink: 0;
  font-size: 12px;
  color: #4a5160;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-row .el-input {
  flex: 1;
}
</style>

<template>
  <Card title="📚 知识库管理" variant="primary">
    <div class="knowledge-upload">
      <!-- 文件上传区域 -->
      <div class="upload-section">
        <h4>上传文档</h4>
        <div
          class="upload-zone"
          :class="{ 'drag-over': isDragOver }"
          @drop.prevent="handleDrop"
          @dragover.prevent="isDragOver = true"
          @dragleave.prevent="isDragOver = false"
          @click="triggerFileInput"
        >
          <input
            ref="fileInput"
            type="file"
            @change="handleFileSelect"
            accept=".pdf,.docx,.pptx,.md,.txt,.png,.jpg,.jpeg,.mp3,.mp4"
            style="display: none"
            multiple
          />
          <div class="upload-content">
            <div class="upload-icon">📄</div>
            <p class="upload-text">点击或拖拽文件到这里上传</p>
            <p class="upload-hint">
              支持 PDF、Word、PowerPoint、Markdown、文本、图片、音频、视频
            </p>
          </div>
        </div>

        <!-- 上传列表 -->
        <div v-if="uploadQueue.length > 0" class="upload-queue">
          <h5>上传队列</h5>
          <div
            v-for="item in uploadQueue"
            :key="item.id"
            class="upload-item"
          >
            <span class="file-name">{{ item.file.name }}</span>
            <span class="file-size">{{ formatFileSize(item.file.size) }}</span>
            <span :class="['status', item.status]">{{ item.statusText }}</span>
          </div>
        </div>

        <button
          v-if="uploadQueue.length > 0"
          @click="startUpload"
          :disabled="isUploading"
          class="upload-button"
        >
          {{ isUploading ? '上传中...' : '开始上传' }}
        </button>
      </div>

      <!-- 文档列表 -->
      <div class="documents-section">
        <div class="section-header">
          <h4>我的文档</h4>
          <button @click="refreshDocuments" class="refresh-button">
            🔄 刷新
          </button>
        </div>

        <div v-if="loading" class="loading">加载中...</div>

        <div v-else-if="documents.length === 0" class="empty-state">
          暂无文档，请上传文档到知识库
        </div>

        <div v-else class="documents-list">
          <div
            v-for="doc in documents"
            :key="doc.document_id"
            class="document-item"
          >
            <div class="doc-icon">📄</div>
            <div class="doc-info">
              <div class="doc-name">{{ doc.filename }}</div>
              <div class="doc-meta">
                <span class="doc-date">{{ formatDate(doc.created_at) }}</span>
                <span :class="['doc-status', doc.status]">
                  {{ getStatusText(doc.status) }}
                </span>
              </div>
            </div>
            <button
              @click="deleteDocument(doc.document_id)"
              class="delete-button"
            >
              🗑️
            </button>
          </div>
        </div>

        <!-- 统计信息 -->
        <div v-if="stats" class="stats-section">
          <div class="stat-item">
            <div class="stat-label">总文档数</div>
            <div class="stat-value">{{ stats.total_documents }}</div>
          </div>
          <div class="stat-item">
            <div class="stat-label">就绪文档</div>
            <div class="stat-value">{{ stats.ready_documents }}</div>
          </div>
          <div class="stat-item">
            <div class="stat-label">处理中</div>
            <div class="stat-value">{{ stats.processing_documents }}</div>
          </div>
        </div>
      </div>
    </div>
  </Card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useKnowledgeStore } from '@/stores/knowledge'
import Card from './Card.vue'

const knowledgeStore = useKnowledgeStore()

const fileInput = ref(null)
const isDragOver = ref(false)
const uploadQueue = ref([])
const isUploading = ref(false)
const documents = ref([])
const loading = ref(false)
const stats = ref(null)

const props = defineProps({
  userId: {
    type: String,
    required: true
  }
})

onMounted(() => {
  loadDocuments()
  loadStats()
})

function triggerFileInput() {
  fileInput.value?.click()
}

function handleFileSelect(event) {
  const files = Array.from(event.target.files)
  addFilesToQueue(files)
}

function handleDrop(event) {
  isDragOver.value = false
  const files = Array.from(event.dataTransfer.files)
  addFilesToQueue(files)
}

function addFilesToQueue(files) {
  const newItems = files.map(file => ({
    id: Date.now() + Math.random(),
    file,
    status: 'pending',
    statusText: '等待上传'
  }))
  uploadQueue.value.push(...newItems)
}

async function startUpload() {
  if (isUploading.value) return

  isUploading.value = true

  for (const item of uploadQueue.value) {
    if (item.status !== 'pending') continue

    item.status = 'uploading'
    item.statusText = '上传中...'

    try {
      await knowledgeStore.uploadDocument(props.userId, item.file)
      item.status = 'success'
      item.statusText = '✅ 完成'
    } catch (error) {
      console.error('上传失败:', error)
      item.status = 'error'
      item.statusText = '❌ 失败'
    }
  }

  isUploading.value = false

  // 刷新文档列表
  await loadDocuments()
  await loadStats()

  // 清理已完成的项目
  setTimeout(() => {
    uploadQueue.value = uploadQueue.value.filter(
      item => item.status === 'error'
    )
  }, 2000)
}

async function loadDocuments() {
  loading.value = true
  try {
    documents.value = await knowledgeStore.listDocuments(props.userId)
  } catch (error) {
    console.error('加载文档失败:', error)
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    stats.value = await knowledgeStore.getStats(props.userId)
  } catch (error) {
    console.error('加载统计失败:', error)
  }
}

async function refreshDocuments() {
  await loadDocuments()
  await loadStats()
}

async function deleteDocument(documentId) {
  if (!confirm('确定要删除这个文档吗？')) return

  try {
    await knowledgeStore.deleteDocument(props.userId, documentId)
    await loadDocuments()
    await loadStats()
  } catch (error) {
    console.error('删除文档失败:', error)
    alert('删除失败: ' + error.message)
  }
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function formatDate(dateString) {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleString('zh-CN')
}

function getStatusText(status) {
  const statusMap = {
    pending: '等待中',
    partitioning: '分割中',
    partitioned: '已分割',
    refined: '已优化',
    chunked: '已分块',
    indexed: '已索引',
    ready: '就绪',
    failed: '失败'
  }
  return statusMap[status] || status
}
</script>

<style scoped>
.knowledge-upload {
  display: flex;
  flex-direction: column;
  gap: 30px;
}

.upload-section h4,
.documents-section h4 {
  margin: 0 0 15px 0;
  font-size: 16px;
  font-weight: 600;
  color: #2c3e50;
}

/* 上传区域 */
.upload-zone {
  border: 2px dashed #cbd5e0;
  border-radius: 12px;
  padding: 40px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  background: #f9fafb;
}

.upload-zone:hover,
.upload-zone.drag-over {
  border-color: #667eea;
  background: #eef2ff;
}

.upload-icon {
  font-size: 48px;
  margin-bottom: 10px;
}

.upload-text {
  font-size: 16px;
  font-weight: 500;
  color: #2c3e50;
  margin: 0 0 5px 0;
}

.upload-hint {
  font-size: 12px;
  color: #718096;
  margin: 0;
}

/* 上传队列 */
.upload-queue {
  margin-top: 20px;
}

.upload-queue h5 {
  font-size: 14px;
  margin: 0 0 10px 0;
  color: #4a5568;
}

.upload-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  background: #f7fafc;
  border-radius: 8px;
  margin-bottom: 8px;
}

.file-name {
  flex: 1;
  font-size: 14px;
  color: #2c3e50;
}

.file-size {
  font-size: 12px;
  color: #718096;
}

.status {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.status.pending {
  background: #edf2f7;
  color: #4a5568;
}

.status.uploading {
  background: #bee3f8;
  color: #2c5282;
}

.status.success {
  background: #c6f6d5;
  color: #22543d;
}

.status.error {
  background: #fed7d7;
  color: #742a2a;
}

.upload-button {
  width: 100%;
  padding: 12px;
  margin-top: 15px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.upload-button:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.upload-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 文档列表 */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.refresh-button {
  padding: 6px 12px;
  background: #edf2f7;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-button:hover {
  background: #e2e8f0;
}

.loading,
.empty-state {
  padding: 40px;
  text-align: center;
  color: #718096;
  font-size: 14px;
}

.documents-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 400px;
  overflow-y: auto;
}

.document-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #f7fafc;
  border-radius: 8px;
  transition: all 0.2s;
}

.document-item:hover {
  background: #edf2f7;
}

.doc-icon {
  font-size: 24px;
}

.doc-info {
  flex: 1;
}

.doc-name {
  font-size: 14px;
  font-weight: 500;
  color: #2c3e50;
  margin-bottom: 4px;
}

.doc-meta {
  display: flex;
  gap: 10px;
  font-size: 12px;
}

.doc-date {
  color: #718096;
}

.doc-status {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.doc-status.ready {
  background: #c6f6d5;
  color: #22543d;
}

.doc-status.pending,
.doc-status.partitioning,
.doc-status.partitioned,
.doc-status.refined,
.doc-status.chunked,
.doc-status.indexed {
  background: #bee3f8;
  color: #2c5282;
}

.doc-status.failed {
  background: #fed7d7;
  color: #742a2a;
}

.delete-button {
  padding: 6px 10px;
  background: transparent;
  border: none;
  font-size: 18px;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.delete-button:hover {
  opacity: 1;
}

/* 统计信息 */
.stats-section {
  display: flex;
  gap: 15px;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e5e7eb;
}

.stat-item {
  flex: 1;
  text-align: center;
}

.stat-label {
  font-size: 12px;
  color: #718096;
  margin-bottom: 5px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #667eea;
}
</style>


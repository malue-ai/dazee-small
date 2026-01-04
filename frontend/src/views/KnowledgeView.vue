<template>
  <div class="knowledge-view">
    <!-- 顶部导航 -->
    <div class="top-bar">
      <div class="left-section">
        <h1 class="page-title">📚 知识库</h1>
        <div class="stats-bar">
          <div class="stat-badge">
            <span class="stat-label">总文件</span>
            <span class="stat-value">{{ stats?.total_files || 0 }}</span>
          </div>
          <div class="stat-badge">
            <span class="stat-label">已就绪</span>
            <span class="stat-value success">{{ stats?.by_status?.ready || 0 }}</span>
          </div>
          <div class="stat-badge">
            <span class="stat-label">处理中</span>
            <span class="stat-value warning">{{ stats?.by_status?.processing || 0 }}</span>
          </div>
          <div class="stat-badge">
            <span class="stat-label">总大小</span>
            <span class="stat-value">{{ formatFileSize(stats?.total_size || 0) }}</span>
          </div>
        </div>
      </div>
      <div class="right-section">
        <button @click="$router.push('/')" class="back-button">
          ← 返回聊天
        </button>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="main-content">
      <!-- 左侧：上传和过滤 -->
      <div class="sidebar">
        <!-- 上传区域 -->
        <div class="upload-card">
          <h3 class="card-title">上传文件</h3>
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
            <div class="upload-icon">📤</div>
            <p class="upload-text">点击或拖拽上传</p>
            <p class="upload-hint">支持 PDF, Word, PPT, 图片等</p>
          </div>

          <!-- 上传队列 -->
          <div v-if="uploadQueue.length > 0" class="upload-queue">
            <div class="queue-header">
              <span>上传队列 ({{ uploadQueue.length }})</span>
              <button @click="clearQueue" class="clear-btn">清空</button>
            </div>
            <div
              v-for="item in uploadQueue"
              :key="item.id"
              class="queue-item"
            >
              <div class="item-info">
                <span class="item-name">{{ item.file.name }}</span>
                <span class="item-size">{{ formatFileSize(item.file.size) }}</span>
              </div>
              <div :class="['item-status', item.status]">
                {{ item.statusText }}
              </div>
            </div>
            <button
              @click="startUpload"
              :disabled="isUploading"
              class="start-upload-btn"
            >
              {{ isUploading ? '上传中...' : '开始上传' }}
            </button>
          </div>
        </div>

        <!-- 从文件库导入 -->
        <div class="import-card">
          <button @click="showImportDialog = true" class="import-btn">
            📥 从文件库导入
          </button>
        </div>

        <!-- 分类过滤 -->
        <div class="filter-card">
          <h3 class="card-title">分类</h3>
          <div class="filter-list">
            <button
              v-for="cat in categories"
              :key="cat.value"
              :class="['filter-item', { active: selectedCategory === cat.value }]"
              @click="selectedCategory = cat.value"
            >
              <span class="filter-icon">{{ cat.icon }}</span>
              <span class="filter-label">{{ cat.label }}</span>
              <span class="filter-count">{{ getCategoryCount(cat.value) }}</span>
            </button>
          </div>
        </div>

        <!-- 状态过滤 -->
        <div class="filter-card">
          <h3 class="card-title">状态</h3>
          <div class="filter-list">
            <button
              v-for="stat in statuses"
              :key="stat.value"
              :class="['filter-item', { active: selectedStatus === stat.value }]"
              @click="selectedStatus = stat.value"
            >
              <span :class="['status-dot', stat.value]"></span>
              <span class="filter-label">{{ stat.label }}</span>
              <span class="filter-count">{{ getStatusCount(stat.value) }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 右侧：文件列表 -->
      <div class="content-area">
        <!-- 搜索和排序 -->
        <div class="toolbar">
          <div class="search-box">
            <span class="search-icon">🔍</span>
            <input
              v-model="searchQuery"
              type="text"
              placeholder="搜索文件名..."
              class="search-input"
            />
          </div>
          <div class="toolbar-actions">
            <select v-model="sortBy" class="sort-select">
              <option value="created_at">最新上传</option>
              <option value="filename">文件名</option>
              <option value="file_size">文件大小</option>
            </select>
            <button @click="toggleViewMode" class="view-mode-btn">
              {{ viewMode === 'grid' ? '📋 列表' : '🔲 网格' }}
            </button>
            <button @click="refreshFiles" class="refresh-btn">
              🔄 刷新
            </button>
          </div>
        </div>

        <!-- 文件列表 -->
        <div v-if="loading" class="loading-state">
          <div class="spinner"></div>
          <p>加载中...</p>
        </div>

        <div v-else-if="filteredFiles.length === 0" class="empty-state">
          <div class="empty-icon">📭</div>
          <p class="empty-text">暂无文件</p>
          <p class="empty-hint">点击左侧上传区域添加文件</p>
        </div>

        <div v-else :class="['files-container', viewMode]">
          <div
            v-for="file in filteredFiles"
            :key="file.document_id"
            :class="['file-card', { selected: selectedFile?.document_id === file.document_id }]"
            @click="selectFile(file)"
          >
            <!-- 文件图标 -->
            <div class="file-icon">{{ getFileIcon(file.filename) }}</div>

            <!-- 文件信息 -->
            <div class="file-info">
              <div class="file-name" :title="file.filename">
                {{ file.filename }}
              </div>
              <div class="file-meta">
                <span class="meta-item">
                  {{ formatDate(file.created_at) }}
                </span>
                <span class="meta-item">
                  {{ getStatusText(file.status) }}
                </span>
              </div>
              <div class="file-tags" v-if="file.tags && file.tags.length > 0">
                <span
                  v-for="tag in file.tags.slice(0, 3)"
                  :key="tag"
                  class="tag"
                >
                  {{ tag }}
                </span>
              </div>
            </div>

            <!-- 状态标识 -->
            <div :class="['file-status', file.status]">
              {{ getStatusText(file.status) }}
            </div>

            <!-- 操作按钮 -->
            <div class="file-actions">
              <button
                @click.stop="downloadFile(file)"
                class="action-btn"
                title="下载"
              >
                ⬇️
              </button>
              <button
                @click.stop="deleteFile(file)"
                class="action-btn danger"
                title="删除"
              >
                🗑️
              </button>
            </div>
          </div>
        </div>

        <!-- 分页 -->
        <div v-if="totalPages > 1" class="pagination">
          <button
            @click="currentPage--"
            :disabled="currentPage === 1"
            class="page-btn"
          >
            ← 上一页
          </button>
          <span class="page-info">
            第 {{ currentPage }} / {{ totalPages }} 页
          </span>
          <button
            @click="currentPage++"
            :disabled="currentPage === totalPages"
            class="page-btn"
          >
            下一页 →
          </button>
        </div>
      </div>
    </div>

    <!-- 文件详情侧边栏 -->
    <transition name="slide">
      <div v-if="selectedFile" class="detail-panel">
        <div class="detail-header">
          <h3>文件详情</h3>
          <button @click="selectedFile = null" class="close-btn">✕</button>
        </div>

        <div class="detail-content">
          <!-- 文件预览 -->
          <div class="preview-section">
            <div class="preview-icon">{{ getFileIcon(selectedFile.filename) }}</div>
            <div class="preview-name">{{ selectedFile.filename }}</div>
          </div>

          <!-- 基本信息 -->
          <div class="info-section">
            <h4 class="section-title">基本信息</h4>
            <div class="info-row">
              <span class="info-label">文档 ID</span>
              <span class="info-value">{{ selectedFile.document_id }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">上传时间</span>
              <span class="info-value">{{ formatDate(selectedFile.created_at) }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">更新时间</span>
              <span class="info-value">{{ formatDate(selectedFile.updated_at) }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">状态</span>
              <span :class="['info-value', 'status', selectedFile.status]">
                {{ getStatusText(selectedFile.status) }}
              </span>
            </div>
            <div class="info-row" v-if="selectedFile.category">
              <span class="info-label">分类</span>
              <span class="info-value">{{ getCategoryLabel(selectedFile.category) }}</span>
            </div>
          </div>

          <!-- 元数据 -->
          <div class="info-section" v-if="selectedFile.metadata">
            <h4 class="section-title">元数据</h4>
            <div
              v-for="(value, key) in selectedFile.metadata"
              :key="key"
              class="info-row"
            >
              <span class="info-label">{{ key }}</span>
              <span class="info-value">{{ value }}</span>
            </div>
          </div>

          <!-- 标签 -->
          <div class="info-section" v-if="selectedFile.tags && selectedFile.tags.length > 0">
            <h4 class="section-title">标签</h4>
            <div class="tags-container">
              <span
                v-for="tag in selectedFile.tags"
                :key="tag"
                class="tag-pill"
              >
                {{ tag }}
              </span>
            </div>
          </div>

          <!-- 操作 -->
          <div class="actions-section">
            <button @click="viewContent(selectedFile)" class="detail-action-btn">
              📄 查看原文
            </button>
            <button @click="viewChunks(selectedFile)" class="detail-action-btn">
              🧩 查看分块
            </button>
            <button @click="downloadFile(selectedFile)" class="detail-action-btn primary">
              ⬇️ 下载文件
            </button>
            <button @click="deleteFile(selectedFile)" class="detail-action-btn danger">
              🗑️ 删除文件
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- 查看原文对话框 -->
    <div v-if="showContentDialog" class="dialog-overlay" @click.self="showContentDialog = false">
      <div class="dialog content-dialog">
        <div class="dialog-header">
          <h3>📄 文档原文</h3>
          <button @click="showContentDialog = false" class="close-btn">✕</button>
        </div>
        
        <div class="dialog-body">
          <div v-if="loadingContent" class="loading-message">
            加载中...
          </div>
          <div v-else-if="documentContent" class="content-text">
            <pre>{{ documentContent }}</pre>
          </div>
          <div v-else class="empty-message">
            无内容
          </div>
        </div>
      </div>
    </div>

    <!-- 查看分块对话框 -->
    <div v-if="showChunksDialog" class="dialog-overlay" @click.self="showChunksDialog = false">
      <div class="dialog chunks-dialog">
        <div class="dialog-header">
          <h3>🧩 文档分块 ({{ documentChunks.length }} 块)</h3>
          <button @click="showChunksDialog = false" class="close-btn">✕</button>
        </div>
        
        <div class="dialog-body">
          <div v-if="loadingChunks" class="loading-message">
            加载中...
          </div>
          <div v-else-if="documentChunks.length > 0" class="chunks-list">
            <div v-for="(chunk, index) in documentChunks" :key="chunk.id" class="chunk-item">
              <div class="chunk-header">
                <span class="chunk-number">分块 #{{ index + 1 }}</span>
                <span class="chunk-id">ID: {{ chunk.id }}</span>
              </div>
              <div class="chunk-text">{{ chunk.text }}</div>
            </div>
          </div>
          <div v-else class="empty-message">
            无分块数据
          </div>
        </div>
      </div>
    </div>

    <!-- 从文件库导入对话框 -->
    <div v-if="showImportDialog" class="dialog-overlay" @click.self="showImportDialog = false">
      <div class="dialog">
        <div class="dialog-header">
          <h3>从文件库导入</h3>
          <button @click="showImportDialog = false" class="close-btn">✕</button>
        </div>
        
        <div class="dialog-body">
          <div v-if="loadingFileLibrary" class="loading-message">
            加载文件列表中...
          </div>
          
          <div v-else-if="fileLibraryFiles.length === 0" class="empty-message">
            文件库暂无文件
          </div>
          
          <div v-else class="file-library-list">
            <div
              v-for="file in fileLibraryFiles"
              :key="file.id"
              :class="['library-file-item', { selected: selectedImportFiles.includes(file.id) }]"
              @click="toggleSelectFile(file.id)"
            >
              <input
                type="checkbox"
                :checked="selectedImportFiles.includes(file.id)"
                @click.stop="toggleSelectFile(file.id)"
              />
              <div class="file-info">
                <div class="file-name">{{ file.filename }}</div>
                <div class="file-meta">
                  <span>{{ formatFileSize(file.file_size) }}</span>
                  <span>{{ formatDate(file.created_at) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <div class="dialog-footer">
          <button @click="showImportDialog = false" class="cancel-btn">取消</button>
          <button
            @click="startImport"
            :disabled="selectedImportFiles.length === 0 || isImporting"
            class="import-btn-dialog"
          >
            {{ isImporting ? '导入中...' : `导入 (${selectedImportFiles.length})` }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useKnowledgeStore } from '@/stores/knowledge'
import { useChatStore } from '@/stores/chat'
import axios from '@/api/axios'

const router = useRouter()
const knowledgeStore = useKnowledgeStore()
const chatStore = useChatStore()

// 用户 ID
const userId = computed(() => chatStore.initUserId())

// 状态
const files = ref([])
const stats = ref(null)
const loading = ref(false)
const isDragOver = ref(false)
const fileInput = ref(null)
const uploadQueue = ref([])
const isUploading = ref(false)
const selectedFile = ref(null)

// 导入文件库对话框相关
const showImportDialog = ref(false)
const fileLibraryFiles = ref([])  // 文件库中的文件
const selectedImportFiles = ref([])  // 选中要导入的文件
const loadingFileLibrary = ref(false)
const isImporting = ref(false)

// 查看原文和分块对话框相关
const showContentDialog = ref(false)
const documentContent = ref('')
const loadingContent = ref(false)
const showChunksDialog = ref(false)
const documentChunks = ref([])
const loadingChunks = ref(false)

// 轮询相关（用于刷新处理中文档的状态）
const pollingTimer = ref(null)
const POLLING_INTERVAL = 5000  // 5秒轮询一次

// 过滤和排序
const selectedCategory = ref('all')
const selectedStatus = ref('all')
const searchQuery = ref('')
const sortBy = ref('created_at')
const viewMode = ref('grid') // grid | list
const currentPage = ref(1)
const pageSize = 20

// 分类和状态定义
const categories = [
  { value: 'all', label: '全部', icon: '📁' },
  { value: 'knowledge', label: '知识库', icon: '📚' },
  { value: 'attachment', label: '附件', icon: '📎' },
  { value: 'avatar', label: '头像', icon: '👤' },
  { value: 'media', label: '媒体', icon: '🎬' },
  { value: 'export', label: '导出', icon: '📤' },
  { value: 'temp', label: '临时', icon: '⏱️' }
]

const statuses = [
  { value: 'all', label: '全部' },
  { value: 'ready', label: '已就绪' },
  { value: 'processing', label: '处理中' },
  { value: 'uploaded', label: '已上传' },
  { value: 'failed', label: '失败' }
]

// 计算属性
const filteredFiles = computed(() => {
  let result = files.value

  // 分类过滤
  if (selectedCategory.value !== 'all') {
    result = result.filter(f => f.category === selectedCategory.value)
  }

  // 状态过滤
  if (selectedStatus.value !== 'all') {
    result = result.filter(f => f.status === selectedStatus.value)
  }

  // 搜索过滤
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(f =>
      f.filename.toLowerCase().includes(query)
    )
  }

  // 排序
  result.sort((a, b) => {
    if (sortBy.value === 'created_at') {
      return new Date(b.created_at) - new Date(a.created_at)
    } else if (sortBy.value === 'filename') {
      return a.filename.localeCompare(b.filename)
    } else if (sortBy.value === 'file_size') {
      return b.file_size - a.file_size
    }
    return 0
  })

  // 分页
  const start = (currentPage.value - 1) * pageSize
  const end = start + pageSize
  return result.slice(start, end)
})

const totalPages = computed(() => {
  const total = files.value.length
  return Math.ceil(total / pageSize)
})

// 生命周期
onMounted(async () => {
  await loadFiles(true)  // 首次加载时刷新状态
  await loadStats()
})

// 组件卸载时停止轮询
onUnmounted(() => {
  stopPolling()
})

// 监听过滤变化，重置到第一页
watch([selectedCategory, selectedStatus, searchQuery], () => {
  currentPage.value = 1
})

// 方法
async function loadFiles(refresh = false) {
  loading.value = true
  try {
    const response = await axios.get(`/v1/knowledge/documents/${userId.value}`, {
      params: {
        limit: 1000,
        offset: 0,
        refresh: refresh  // 是否从 Ragie 刷新状态
      }
    })
    files.value = response.data.data?.documents || []
    
    // 检查是否有处理中的文档
    const hasProcessing = response.data.data?.has_processing || false
    
    // 如果有处理中的文档，启动轮询
    if (hasProcessing && !pollingTimer.value) {
      startPolling()
    } else if (!hasProcessing && pollingTimer.value) {
      stopPolling()
    }
  } catch (error) {
    console.error('加载文档列表失败:', error)
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    const response = await axios.get(`/v1/knowledge/stats/${userId.value}`)
    stats.value = response.data.data
  } catch (error) {
    console.error('加载统计失败:', error)
  }
}

async function refreshFiles() {
  await loadFiles(true)  // 带 refresh=true 刷新状态
  await loadStats()
}

// ========== 轮询机制（用于刷新处理中文档状态）==========

function startPolling() {
  if (pollingTimer.value) return  // 已在轮询中
  
  console.log('🔄 开始轮询文档状态（每 5 秒）')
  pollingTimer.value = setInterval(async () => {
    console.log('🔄 轮询刷新文档状态...')
    await loadFiles(true)  // 从 Ragie 刷新状态
    await loadStats()
  }, POLLING_INTERVAL)
}

function stopPolling() {
  if (pollingTimer.value) {
    console.log('✅ 停止轮询（所有文档处理完成）')
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

function triggerFileInput() {
  fileInput.value?.click()
}

function handleFileSelect(event) {
  const newFiles = Array.from(event.target.files)
  addFilesToQueue(newFiles)
  event.target.value = '' // 清空 input
}

function handleDrop(event) {
  isDragOver.value = false
  const newFiles = Array.from(event.dataTransfer.files)
  addFilesToQueue(newFiles)
}

function addFilesToQueue(newFiles) {
  const items = newFiles.map(file => ({
    id: Date.now() + Math.random(),
    file,
    status: 'pending',
    statusText: '等待上传'
  }))
  uploadQueue.value.push(...items)
}

function clearQueue() {
  uploadQueue.value = []
}

async function startUpload() {
  if (isUploading.value) return

  const pendingItems = uploadQueue.value.filter(item => item.status === 'pending')
  if (pendingItems.length === 0) return

  isUploading.value = true

  // 批量上传所有待上传的文件
  try {
    // 标记所有文件为上传中
    pendingItems.forEach(item => {
      item.status = 'uploading'
      item.statusText = '上传中...'
    })

    // 构建 FormData（支持单个或多个文件）
    const formData = new FormData()
    pendingItems.forEach(item => {
      formData.append('files', item.file)  // 注意：后端参数名是 files
    })
    formData.append('user_id', userId.value)

    // 批量上传
    const response = await axios.post('/v1/knowledge/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    // 处理响应
    if (response.data.code === 200) {
      const result = response.data.data
      
      // 单个文件上传返回 DocumentUploadResponse
      if (result.document_id) {
        pendingItems[0].status = 'success'
        pendingItems[0].statusText = '✅ 完成'
      }
      // 批量上传返回 DocumentBatchUploadResponse
      else if (result.total !== undefined) {
        // 根据上传结果更新每个文件的状态
        const documents = result.documents || []
        pendingItems.forEach((item, index) => {
          const doc = documents[index]
          if (doc && doc.document_id) {
            item.status = 'success'
            item.statusText = '✅ 完成'
          } else {
            item.status = 'error'
            item.statusText = doc?.message || '❌ 失败'
          }
        })
        
        console.log(`批量上传完成：成功 ${result.succeeded}/${result.total}`)
      }
    }
  } catch (error) {
    console.error('上传失败:', error)
    // 标记所有文件为失败
    pendingItems.forEach(item => {
      item.status = 'error'
      item.statusText = '❌ 失败: ' + (error.response?.data?.detail || error.message)
    })
  }

  isUploading.value = false

  // 刷新列表
  await refreshFiles()

  // 2秒后清空成功的项目
  setTimeout(() => {
    uploadQueue.value = uploadQueue.value.filter(item => item.status === 'error')
  }, 2000)
}

function selectFile(file) {
  selectedFile.value = file
}

async function viewContent(file) {
  try {
    showContentDialog.value = true
    loadingContent.value = true
    documentContent.value = ''
    
    const response = await axios.get(`/v1/knowledge/documents/${userId.value}/${file.document_id}/content`)
    documentContent.value = response.data.data.content || '(无内容)'
  } catch (error) {
    console.error('获取文档内容失败:', error)
    documentContent.value = '获取失败: ' + (error.response?.data?.detail || error.message)
  } finally {
    loadingContent.value = false
  }
}

async function viewChunks(file) {
  try {
    showChunksDialog.value = true
    loadingChunks.value = true
    documentChunks.value = []
    
    const response = await axios.get(`/v1/knowledge/documents/${userId.value}/${file.document_id}/chunks`)
    documentChunks.value = response.data.data.chunks || []
  } catch (error) {
    console.error('获取文档分块失败:', error)
    alert('获取分块失败: ' + (error.response?.data?.detail || error.message))
    showChunksDialog.value = false
  } finally {
    loadingChunks.value = false
  }
}

async function downloadFile(file) {
  try {
    // 优先级 1: 使用 S3 预签名 URL（如果有）
    if (file.metadata?.s3_presigned_url) {
      console.log('📥 使用 S3 预签名 URL 下载:', file.filename)
      window.open(file.metadata.s3_presigned_url, '_blank')
      return
    }
    
    // 优先级 2: 通过后端 API 下载（会自动选择 S3 或 Ragie）
    console.log('📥 通过后端 API 下载:', file.filename)
    const response = await axios.get(
      `/v1/knowledge/documents/${userId.value}/${file.document_id}/download?source=auto`,
      { responseType: 'blob' }
    )
    
    // 创建下载链接
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', file.filename)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (error) {
    console.error('下载失败:', error)
    alert('下载失败: ' + (error.response?.data?.detail || error.message))
  }
}

async function deleteFile(file) {
  if (!confirm(`确定要删除 "${file.filename}" 吗？`)) return

  try {
    await axios.delete(`/v1/knowledge/documents/${userId.value}/${file.document_id}`)
    await refreshFiles()
    if (selectedFile.value?.document_id === file.document_id) {
      selectedFile.value = null
    }
  } catch (error) {
    console.error('删除失败:', error)
    alert('删除失败: ' + error.message)
  }
}

// ========== 从文件库导入 ==========

async function loadFileLibrary() {
  loadingFileLibrary.value = true
  try {
    const response = await axios.get(`/v1/files`, {
      params: {
        user_id: userId.value,
        limit: 100,
        offset: 0
      }
    })
    fileLibraryFiles.value = response.data.data?.files || []
  } catch (error) {
    console.error('加载文件库失败:', error)
    alert('加载文件库失败: ' + error.message)
  } finally {
    loadingFileLibrary.value = false
  }
}

function toggleSelectFile(fileId) {
  const index = selectedImportFiles.value.indexOf(fileId)
  if (index > -1) {
    selectedImportFiles.value.splice(index, 1)
  } else {
    selectedImportFiles.value.push(fileId)
  }
}

async function startImport() {
  if (selectedImportFiles.value.length === 0 || isImporting.value) return

  isImporting.value = true

  try {
    const formData = new FormData()
    formData.append('user_id', userId.value)
    formData.append('file_ids', JSON.stringify(selectedImportFiles.value))

    const response = await axios.post('/v1/knowledge/import-from-files', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    if (response.data.code === 200) {
      const result = response.data.data
      console.log(`导入完成：成功 ${result.succeeded}/${result.total}`)
      alert(`导入完成：成功 ${result.succeeded}，失败 ${result.failed}`)
      
      // 关闭对话框并刷新列表
      showImportDialog.value = false
      selectedImportFiles.value = []
      await refreshFiles()
    }
  } catch (error) {
    console.error('导入失败:', error)
    alert('导入失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    isImporting.value = false
  }
}

// Watch：打开对话框时加载文件库
watch(showImportDialog, (newVal) => {
  if (newVal) {
    selectedImportFiles.value = []
    loadFileLibrary()
  }
})

function toggleViewMode() {
  viewMode.value = viewMode.value === 'grid' ? 'list' : 'grid'
}

function getCategoryCount(category) {
  if (category === 'all') return files.value.length
  return files.value.filter(f => f.category === category).length
}

function getStatusCount(status) {
  if (status === 'all') return files.value.length
  return files.value.filter(f => f.status === status).length
}

function getCategoryLabel(category) {
  return categories.find(c => c.value === category)?.label || category
}

function getFileIcon(filename) {
  if (!filename) return '📄'
  const ext = filename.toLowerCase().split('.').pop()
  
  // 根据文件扩展名返回图标
  const iconMap = {
    pdf: '📕',
    doc: '📘', docx: '📘',
    xls: '📗', xlsx: '📗', csv: '📗',
    ppt: '📙', pptx: '📙',
    jpg: '🖼️', jpeg: '🖼️', png: '🖼️', gif: '🖼️', svg: '🖼️',
    mp4: '🎬', avi: '🎬', mov: '🎬',
    mp3: '🎵', wav: '🎵',
    txt: '📝', md: '📝', log: '📝',
    zip: '📦', rar: '📦', '7z': '📦',
    json: '⚙️', xml: '⚙️', yaml: '⚙️', yml: '⚙️'
  }
  
  return iconMap[ext] || '📄'
}

function getStatusText(status) {
  // Ragie 文档处理状态流程：
  // pending → partitioning → partitioned → refined → chunked → indexed → summary_indexed → keyword_indexed → ready
  const map = {
    uploading: '⏫ 上传中',
    uploaded: '✅ 已上传',
    pending: '⏳ 等待处理',
    partitioning: '🔄 分析中...',
    partitioned: '🔄 分区完成',
    refined: '🔄 优化中...',
    chunked: '🔄 切分中...',
    indexed: '🔄 索引中...',
    summary_indexed: '🔄 生成摘要...',
    keyword_indexed: '🔄 关键词索引...',
    processing: '🔄 处理中',
    ready: '✅ 已就绪',
    failed: '❌ 失败',
    deleted: '🗑️ 已删除'
  }
  return map[status] || status
}

function formatFileSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB'
}

function formatDate(dateString) {
  if (!dateString) return '-'
  const date = new Date(dateString)
  const now = new Date()
  const diff = now - date

  // 小于1分钟
  if (diff < 60000) return '刚刚'
  // 小于1小时
  if (diff < 3600000) return Math.floor(diff / 60000) + ' 分钟前'
  // 小于1天
  if (diff < 86400000) return Math.floor(diff / 3600000) + ' 小时前'
  // 小于7天
  if (diff < 604800000) return Math.floor(diff / 86400000) + ' 天前'

  // 否则显示日期
  return date.toLocaleDateString('zh-CN')
}
</script>

<style scoped>
.knowledge-view {
  width: 100%;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f7fa;
  overflow: hidden;
}

/* 顶部栏 */
.top-bar {
  background: white;
  padding: 20px 30px;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.left-section {
  display: flex;
  align-items: center;
  gap: 30px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: #1a202c;
  margin: 0;
}

.stats-bar {
  display: flex;
  gap: 15px;
}

.stat-badge {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 16px;
  background: #f7fafc;
  border-radius: 8px;
}

.stat-label {
  font-size: 11px;
  color: #718096;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 16px;
  font-weight: 700;
  color: #2d3748;
}

.stat-value.success {
  color: #38a169;
}

.stat-value.warning {
  color: #d69e2e;
}

.back-button {
  padding: 10px 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.back-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

/* 主内容区 */
.main-content {
  flex: 1;
  display: flex;
  gap: 20px;
  padding: 20px 30px;
  overflow: hidden;
}

/* 侧边栏 */
.sidebar {
  width: 280px;
  display: flex;
  flex-direction: column;
  gap: 15px;
  overflow-y: auto;
}

.upload-card,
.filter-card {
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #2d3748;
  margin: 0 0 15px 0;
}

/* 上传区域 */
.upload-zone {
  border: 2px dashed #cbd5e0;
  border-radius: 8px;
  padding: 30px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s;
  background: #f9fafb;
}

.upload-zone:hover,
.upload-zone.drag-over {
  border-color: #667eea;
  background: #eef2ff;
}

.upload-icon {
  font-size: 36px;
  margin-bottom: 10px;
}

.upload-text {
  font-size: 14px;
  font-weight: 500;
  color: #2d3748;
  margin: 0 0 5px 0;
}

.upload-hint {
  font-size: 11px;
  color: #718096;
  margin: 0;
}

/* 上传队列 */
.upload-queue {
  margin-top: 15px;
}

.queue-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  font-size: 12px;
  color: #4a5568;
}

.clear-btn {
  padding: 2px 8px;
  background: transparent;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}

.clear-btn:hover {
  background: #f7fafc;
}

.queue-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px;
  background: #f7fafc;
  border-radius: 6px;
  margin-bottom: 6px;
  font-size: 12px;
}

.item-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow: hidden;
}

.item-name {
  font-weight: 500;
  color: #2d3748;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-size {
  color: #718096;
  font-size: 11px;
}

.item-status {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 500;
  white-space: nowrap;
}

.item-status.pending {
  background: #edf2f7;
  color: #4a5568;
}

.item-status.uploading {
  background: #bee3f8;
  color: #2c5282;
}

.item-status.success {
  background: #c6f6d5;
  color: #22543d;
}

.item-status.error {
  background: #fed7d7;
  color: #742a2a;
}

.start-upload-btn {
  width: 100%;
  padding: 10px;
  margin-top: 10px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.start-upload-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.start-upload-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 过滤列表 */
.filter-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}

.filter-item:hover {
  background: #f7fafc;
}

.filter-item.active {
  background: #eef2ff;
  color: #667eea;
  font-weight: 600;
}

.filter-icon {
  font-size: 16px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #cbd5e0;
}

.status-dot.ready {
  background: #48bb78;
}

.status-dot.processing {
  background: #ed8936;
}

.status-dot.uploaded {
  background: #4299e1;
}

.status-dot.failed {
  background: #f56565;
}

.filter-label {
  flex: 1;
  font-size: 13px;
}

.filter-count {
  font-size: 12px;
  color: #718096;
  background: #edf2f7;
  padding: 2px 8px;
  border-radius: 4px;
}

.filter-item.active .filter-count {
  background: #667eea;
  color: white;
}

/* 内容区域 */
.content-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 15px;
  overflow: hidden;
}

/* 工具栏 */
.toolbar {
  display: flex;
  gap: 15px;
  background: white;
  padding: 15px 20px;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.search-box {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 15px;
  background: #f7fafc;
  border-radius: 8px;
}

.search-icon {
  font-size: 16px;
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 14px;
  outline: none;
}

.toolbar-actions {
  display: flex;
  gap: 10px;
}

.sort-select {
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 13px;
  outline: none;
  cursor: pointer;
}

.view-mode-btn,
.refresh-btn {
  padding: 8px 16px;
  background: #f7fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.view-mode-btn:hover,
.refresh-btn:hover {
  background: #edf2f7;
}

/* 文件容器 */
.files-container {
  flex: 1;
  overflow-y: auto;
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.files-container.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 15px;
  align-content: start;
}

.files-container.list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 加载和空状态 */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #718096;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #e2e8f0;
  border-top-color: #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 15px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 15px;
}

.empty-text {
  font-size: 16px;
  font-weight: 600;
  color: #4a5568;
  margin: 0 0 8px 0;
}

.empty-hint {
  font-size: 13px;
  color: #a0aec0;
  margin: 0;
}

/* 文件卡片 */
.file-card {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 15px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.file-card:hover {
  background: #f3f4f6;
  border-color: #d1d5db;
  transform: translateY(-2px);
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
}

.file-card.selected {
  border-color: #667eea;
  background: #eef2ff;
}

.grid .file-card {
  flex-direction: column;
  text-align: center;
}

.file-icon {
  font-size: 48px;
}

.list .file-icon {
  font-size: 32px;
}

.file-info {
  flex: 1;
  min-width: 0;
}

.grid .file-info {
  width: 100%;
}

.file-name {
  font-size: 14px;
  font-weight: 600;
  color: #2d3748;
  margin-bottom: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.grid .file-name {
  white-space: normal;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.file-meta {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: #718096;
}

.grid .file-meta {
  justify-content: center;
}

.file-tags {
  display: flex;
  gap: 5px;
  margin-top: 6px;
  flex-wrap: wrap;
}

.grid .file-tags {
  justify-content: center;
}

.tag {
  padding: 2px 6px;
  background: #e2e8f0;
  color: #4a5568;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 500;
}

.file-status {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.file-status.ready {
  background: #c6f6d5;
  color: #22543d;
}

.file-status.processing {
  background: #feebc8;
  color: #7c2d12;
}

.file-status.uploaded {
  background: #bee3f8;
  color: #2c5282;
}

.file-status.failed {
  background: #fed7d7;
  color: #742a2a;
}

.file-actions {
  display: flex;
  gap: 5px;
}

.action-btn {
  padding: 6px 10px;
  background: transparent;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 16px;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #f7fafc;
  border-color: #cbd5e0;
}

.action-btn.danger:hover {
  background: #fed7d7;
  border-color: #fc8181;
}

/* 分页 */
.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 20px;
  padding: 15px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.page-btn {
  padding: 8px 16px;
  background: #f7fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.page-btn:hover:not(:disabled) {
  background: #edf2f7;
}

.page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  font-size: 14px;
  color: #4a5568;
}

/* 详情面板 */
.detail-panel {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 0;
  width: 400px;
  background: white;
  box-shadow: -4px 0 12px rgba(0, 0, 0, 0.1);
  z-index: 100;
  display: flex;
  flex-direction: column;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e5e7eb;
}

.detail-header h3 {
  font-size: 18px;
  font-weight: 700;
  color: #1a202c;
  margin: 0;
}

.close-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  font-size: 20px;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.2s;
}

.close-btn:hover {
  background: #f7fafc;
}

.detail-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.preview-section {
  text-align: center;
  padding: 30px 20px;
  background: #f9fafb;
  border-radius: 8px;
  margin-bottom: 20px;
}

.preview-icon {
  font-size: 72px;
  margin-bottom: 15px;
}

.preview-name {
  font-size: 16px;
  font-weight: 600;
  color: #2d3748;
  word-break: break-word;
}

.info-section {
  margin-bottom: 25px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #2d3748;
  margin: 0 0 12px 0;
}

.info-row {
  display: flex;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid #f0f0f0;
}

.info-row:last-child {
  border-bottom: none;
}

.info-label {
  font-size: 13px;
  color: #718096;
}

.info-value {
  font-size: 13px;
  font-weight: 500;
  color: #2d3748;
  text-align: right;
}

.info-value.status {
  padding: 2px 8px;
  border-radius: 4px;
}

.tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-pill {
  padding: 6px 12px;
  background: #eef2ff;
  color: #667eea;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
}

.actions-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 30px;
}

.detail-action-btn {
  padding: 12px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.detail-action-btn.primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.detail-action-btn.primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.detail-action-btn.danger {
  background: #fed7d7;
  color: #742a2a;
}

.detail-action-btn.danger:hover {
  background: #fc8181;
  color: white;
}

/* 滑动动画 */
.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}

/* 响应式 */
@media (max-width: 1200px) {
  .sidebar {
    width: 240px;
  }

  .detail-panel {
    width: 350px;
  }
}

@media (max-width: 768px) {
  .main-content {
    flex-direction: column;
  }

  .sidebar {
    width: 100%;
    flex-direction: row;
    overflow-x: auto;
  }

  .detail-panel {
    width: 100%;
  }
}

/* ========== 从文件库导入 ========== */

.import-card {
  margin-bottom: 20px;
}

.import-btn {
  width: 100%;
  padding: 12px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.3s;
}

.import-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

/* 对话框 */

.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog {
  background: white;
  border-radius: 12px;
  width: 90%;
  max-width: 600px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e0e0e0;
}

.dialog-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: #999;
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.close-btn:hover {
  background: #f0f0f0;
  color: #333;
}

.dialog-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.loading-message,
.empty-message {
  text-align: center;
  padding: 40px 20px;
  color: #999;
}

.file-library-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.library-file-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.library-file-item:hover {
  border-color: #667eea;
  background: #f8f9ff;
}

.library-file-item.selected {
  border-color: #667eea;
  background: #f0f3ff;
}

.library-file-item input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.library-file-item .file-info {
  flex: 1;
}

.library-file-item .file-name {
  font-weight: 500;
  color: #333;
  margin-bottom: 4px;
}

.library-file-item .file-meta {
  font-size: 12px;
  color: #999;
  display: flex;
  gap: 12px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px;
  border-top: 1px solid #e0e0e0;
}

.cancel-btn,
.import-btn-dialog {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}

.cancel-btn {
  background: #f0f0f0;
  color: #666;
}

.cancel-btn:hover {
  background: #e0e0e0;
}

.import-btn-dialog {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.import-btn-dialog:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.import-btn-dialog:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 查看原文对话框 */
.content-dialog {
  max-width: 800px;
}

.content-text {
  padding: 20px;
  overflow: auto;
  max-height: 60vh;
  background: #f8f9fa;
  border-radius: 8px;
  margin: 0;
}

.content-text pre {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: #333;
}

/* 查看分块对话框 */
.chunks-dialog {
  max-width: 900px;
}

.chunks-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  overflow: auto;
  max-height: 60vh;
}

.chunk-item {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 16px;
  border-left: 4px solid #667eea;
}

.chunk-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e0e0e0;
}

.chunk-number {
  font-weight: 600;
  color: #667eea;
  font-size: 14px;
}

.chunk-id {
  font-size: 11px;
  color: #999;
  font-family: 'Monaco', 'Menlo', monospace;
}

.chunk-text {
  color: #333;
  line-height: 1.6;
  font-size: 13px;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.loading-message,
.empty-message {
  text-align: center;
  padding: 40px;
  color: #999;
  font-size: 14px;
}
</style>


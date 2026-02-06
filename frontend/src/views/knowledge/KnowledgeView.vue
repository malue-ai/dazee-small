<template>
  <div class="h-full flex flex-col overflow-hidden bg-white">
    <!-- 顶部工具栏 (统一布局) -->
    <div class="h-16 flex items-center justify-between px-6 border-b border-border bg-white sticky top-0 z-10 flex-shrink-0">
      <div class="flex items-center gap-4">
        <h1 class="text-lg font-bold flex items-center gap-2 text-foreground">
          <Database class="w-6 h-6 text-primary" />
          知识库管理
        </h1>
        <div class="text-sm text-muted-foreground bg-muted px-2.5 py-1 rounded-md border border-border">
          共 {{ stats?.total_documents || files.length }} 个文件
        </div>
      </div>
      
      <!-- 顶部操作区 -->
      <div class="flex items-center gap-3">
         <button 
           @click="triggerFileInput"
           class="flex items-center gap-2 px-4 py-2 bg-primary text-white text-sm font-medium rounded-xl hover:bg-primary-hover transition-all shadow-lg shadow-primary/20 active:scale-95"
         >
           <UploadCloud class="w-4 h-4" />
           上传文件
         </button>
      </div>
    </div>

    <!-- 主体区域 -->
    <div class="flex-1 flex overflow-hidden">
      <!-- 左侧侧边栏：上传和筛选 -->
      <div class="w-72 border-r border-border bg-muted overflow-y-auto p-4 flex flex-col gap-6 flex-shrink-0">
        <!-- 上传区域 -->
        <div class="bg-white border border-border rounded-xl p-4 shadow-sm">
          <h3 class="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
            <UploadCloud class="w-4 h-4 text-primary" />
            上传文件
          </h3>
          <div
            class="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all duration-200"
            :class="isDragOver ? 'border-primary bg-accent' : 'border-border hover:border-primary hover:bg-muted'"
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
            <div class="flex justify-center mb-2">
              <Upload class="w-8 h-8 text-muted-foreground/30 group-hover:text-primary transition-colors" />
            </div>
            <p class="text-sm font-medium text-foreground mb-1">点击或拖拽上传</p>
            <p class="text-xs text-muted-foreground/50">支持 PDF, Word, 图片等</p>
          </div>

          <!-- 上传队列 -->
          <div v-if="uploadQueue.length > 0" class="mt-4 space-y-2">
            <div class="flex items-center justify-between text-xs">
              <span class="font-medium text-muted-foreground">队列 ({{ uploadQueue.length }})</span>
              <button @click="clearQueue" class="text-destructive hover:text-destructive">清空</button>
            </div>
            <div class="space-y-2 max-h-32 overflow-y-auto pr-1 scrollbar-thin">
              <div
                v-for="item in uploadQueue"
                :key="item.id"
                class="flex items-center justify-between p-2 bg-muted rounded border border-border text-xs"
              >
                <div class="flex-1 truncate mr-2">
                  <div class="font-medium text-foreground truncate">{{ item.file.name }}</div>
                  <div class="text-muted-foreground/50 text-[10px]">{{ formatFileSize(item.file.size) }}</div>
                </div>
                <span :class="['px-1.5 py-0.5 rounded text-[10px] font-medium', item.status === 'success' ? 'bg-success/10 text-success' : item.status === 'error' ? 'bg-destructive/10 text-destructive' : 'bg-muted-foreground/20 text-muted-foreground']">
                  {{ item.statusText }}
                </span>
              </div>
            </div>
            <button
              @click="startUpload"
              :disabled="isUploading"
              class="w-full py-2 bg-primary text-white text-xs font-medium rounded-lg hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {{ isUploading ? '上传中...' : '开始上传' }}
            </button>
          </div>
        </div>

        <!-- 分类过滤 -->
        <div class="space-y-1">
          <h3 class="text-xs font-bold text-muted-foreground/50 uppercase tracking-wider px-2 mb-2">分类</h3>
          <div class="space-y-0.5">
            <button
              v-for="cat in categories"
              :key="cat.value"
              class="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors"
              :class="selectedCategory === cat.value ? 'bg-white shadow-sm text-foreground font-medium' : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'"
              @click="selectedCategory = cat.value"
            >
              <div class="flex items-center gap-2">
                <component :is="cat.icon" class="w-4 h-4" :class="selectedCategory === cat.value ? 'text-foreground' : 'text-muted-foreground/50'" />
                <span>{{ cat.label }}</span>
              </div>
              <span class="text-xs text-muted-foreground/50">{{ getCategoryCount(cat.value) }}</span>
            </button>
          </div>
        </div>

        <!-- 状态过滤 -->
        <div class="space-y-1">
          <h3 class="text-xs font-bold text-muted-foreground/50 uppercase tracking-wider px-2 mb-2">状态</h3>
          <div class="space-y-0.5">
            <button
              v-for="stat in statuses"
              :key="stat.value"
              class="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors"
              :class="selectedStatus === stat.value ? 'bg-white shadow-sm text-foreground font-medium' : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'"
              @click="selectedStatus = stat.value"
            >
              <div class="flex items-center gap-2">
                <span :class="['w-1.5 h-1.5 rounded-full', stat.value === 'ready' ? 'bg-success' : stat.value === 'processing' ? 'bg-primary' : 'bg-muted-foreground/30']"></span>
                <span>{{ stat.label }}</span>
              </div>
              <span class="text-xs text-muted-foreground/50">{{ getStatusCount(stat.value) }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 右侧主区域：文件列表 -->
      <div class="flex-1 flex flex-col overflow-hidden bg-white">
        <!-- 工具栏 -->
        <div class="h-14 flex items-center justify-between gap-4 px-6 border-b border-border bg-white sticky top-0 z-10">
          <div class="flex-1 max-w-md relative group">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/50 group-focus-within:text-muted-foreground transition-colors" />
            <input
              v-model="searchQuery"
              type="text"
              placeholder="搜索文件名..."
              class="w-full pl-9 pr-4 py-2 bg-muted border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all placeholder-gray-400 text-foreground"
            />
          </div>
          <div class="flex items-center gap-2">
            <div class="relative">
              <select 
                v-model="sortBy" 
                class="appearance-none pl-3 pr-8 py-2 bg-muted border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 cursor-pointer text-muted-foreground font-medium hover:bg-muted transition-colors"
              >
                <option value="created_at">最新上传</option>
                <option value="filename">文件名</option>
                <option value="file_size">文件大小</option>
              </select>
              <ChevronDown class="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/50 pointer-events-none" />
            </div>
            
            <div class="flex bg-muted rounded-lg p-0.5 border border-border">
              <button 
                @click="viewMode = 'grid'" 
                class="p-1.5 rounded-md transition-all"
                :class="viewMode === 'grid' ? 'bg-white shadow-sm text-foreground' : 'text-muted-foreground/50 hover:text-muted-foreground'"
              >
                <LayoutGrid class="w-4 h-4" />
              </button>
              <button 
                @click="viewMode = 'list'" 
                class="p-1.5 rounded-md transition-all"
                :class="viewMode === 'list' ? 'bg-white shadow-sm text-foreground' : 'text-muted-foreground/50 hover:text-muted-foreground'"
              >
                <List class="w-4 h-4" />
              </button>
            </div>

            <button 
              @click="refreshFiles" 
              class="p-2 bg-muted border border-border rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition-all"
            >
              <RefreshCw class="w-4 h-4 transition-transform group-hover:rotate-180" />
            </button>
          </div>
        </div>

        <!-- 文件列表 -->
        <div class="flex-1 overflow-y-auto p-6 scrollbar-thin">
          <div v-if="loading" class="flex flex-col items-center justify-center h-64 text-muted-foreground/50">
            <Loader2 class="w-8 h-8 animate-spin mb-2" />
            <p class="text-xs">加载文件中...</p>
          </div>

          <div v-else-if="filteredFiles.length === 0" class="flex flex-col items-center justify-center h-64 text-muted-foreground/50">
            <div class="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mb-4 border border-border">
              <FolderOpen class="w-8 h-8 opacity-30" />
            </div>
            <p class="text-sm font-medium text-muted-foreground mb-1">暂无文件</p>
            <p class="text-xs">点击左侧上传区域添加文件</p>
          </div>

          <div v-else>
            <!-- 网格视图 -->
            <div v-if="viewMode === 'grid'" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4">
              <div
                v-for="file in filteredFiles"
                :key="file.document_id"
                class="group relative bg-white border border-border rounded-xl p-4 cursor-pointer transition-all duration-200 hover:shadow-md hover:border-border"
                :class="selectedFile?.document_id === file.document_id ? 'ring-2 ring-primary/50 border-primary' : ''"
                @click="selectFile(file)"
              >
                <div class="flex justify-center py-4 mb-2">
                  <FileText class="w-12 h-12 text-muted-foreground/30 group-hover:text-primary transition-colors" />
                </div>
                
                <div class="space-y-1.5">
                  <div class="font-medium text-foreground text-sm truncate" :title="file.filename">{{ file.filename }}</div>
                  
                  <div class="flex items-center justify-between text-[10px] text-muted-foreground/50">
                    <span>{{ formatDate(file.created_at) }}</span>
                    <span :class="['px-1.5 py-0.5 rounded font-medium', file.status === 'ready' ? 'bg-success/10 text-success' : 'bg-accent text-accent-foreground']">
                      {{ getStatusText(file.status) }}
                    </span>
                  </div>
                </div>

                <!-- 悬浮操作栏 -->
                <div class="absolute inset-x-2 bottom-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-all duration-200 translate-y-1 group-hover:translate-y-0 bg-white p-1 rounded-lg border border-border shadow-sm">
                  <button
                    @click.stop="downloadFile(file)"
                    class="flex-1 py-1.5 bg-muted rounded text-[10px] font-medium text-muted-foreground hover:bg-muted transition-colors"
                  >
                    下载
                  </button>
                  <button
                    @click.stop="deleteFile(file)"
                    class="flex-1 py-1.5 bg-destructive/10 text-destructive rounded text-[10px] font-medium hover:bg-destructive/20 transition-colors"
                  >
                    删除
                  </button>
                </div>
              </div>
            </div>

            <!-- 列表视图 -->
            <div v-else class="space-y-2">
              <div
                v-for="file in filteredFiles"
                :key="file.document_id"
                class="group flex items-center gap-4 p-3 bg-white border border-border rounded-lg cursor-pointer transition-colors hover:bg-muted hover:border-border"
                :class="selectedFile?.document_id === file.document_id ? 'bg-accent/30 border-primary/30' : ''"
                @click="selectFile(file)"
              >
                <FileText class="w-8 h-8 text-muted-foreground/50" />
                
                <div class="flex-1 min-w-0 grid grid-cols-12 gap-4 items-center">
                  <div class="col-span-5 font-medium text-foreground text-sm truncate" :title="file.filename">{{ file.filename }}</div>
                  <div class="col-span-3 text-xs text-muted-foreground">{{ formatDate(file.created_at) }}</div>
                  <div class="col-span-2 text-xs text-muted-foreground font-mono">{{ formatFileSize(file.metadata?.file_size || 0) }}</div>
                  <div class="col-span-2 text-right">
                    <span :class="['px-2 py-0.5 rounded text-[10px] font-medium', file.status === 'ready' ? 'bg-success/10 text-success' : 'bg-accent text-accent-foreground']">
                      {{ getStatusText(file.status) }}
                    </span>
                  </div>
                </div>

                <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    @click.stop="downloadFile(file)"
                    class="p-1.5 text-muted-foreground/50 hover:text-foreground hover:bg-muted rounded transition-colors"
                    title="下载"
                  >
                    <Download class="w-4 h-4" />
                  </button>
                  <button
                    @click.stop="deleteFile(file)"
                    class="p-1.5 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 rounded transition-colors"
                    title="删除"
                  >
                    <Trash2 class="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

            <!-- 分页 -->
            <div v-if="totalPages > 1" class="flex items-center justify-center gap-3 mt-8">
              <button
                @click="currentPage--"
                :disabled="currentPage === 1"
                class="px-3 py-1.5 bg-white border border-border rounded-lg text-xs font-medium text-muted-foreground hover:bg-muted transition-colors disabled:opacity-50"
              >
                上一页
              </button>
              <span class="text-xs font-medium text-muted-foreground">
                {{ currentPage }} / {{ totalPages }}
              </span>
              <button
                @click="currentPage++"
                :disabled="currentPage === totalPages"
                class="px-3 py-1.5 bg-white border border-border rounded-lg text-xs font-medium text-muted-foreground hover:bg-muted transition-colors disabled:opacity-50"
              >
                下一页
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 文件详情侧边栏 -->
      <transition
        enter-active-class="transition-transform duration-300 ease-out"
        leave-active-class="transition-transform duration-300 ease-in"
        enter-from-class="translate-x-full"
        leave-to-class="translate-x-full"
      >
        <div v-if="selectedFile" class="w-[360px] border-l border-border bg-white flex flex-col shadow-xl z-20">
          <div class="h-14 flex items-center justify-between px-5 border-b border-border">
            <h3 class="font-semibold text-foreground text-sm">文件详情</h3>
            <button @click="selectedFile = null" class="p-1.5 rounded-md text-muted-foreground/50 hover:bg-muted hover:text-foreground transition-colors">
              <X class="w-4 h-4" />
            </button>
          </div>

          <div class="flex-1 overflow-y-auto p-5 space-y-6">
            <!-- 文件预览 -->
            <div class="flex flex-col items-center py-6 bg-muted rounded-xl border border-border">
              <FileText class="w-16 h-16 text-gray-300 mb-3" />
              <div class="text-center font-semibold text-foreground px-4 break-words leading-snug text-sm">{{ selectedFile.filename }}</div>
            </div>

            <!-- 基本信息 -->
            <div class="space-y-3">
              <h4 class="font-semibold text-foreground text-xs uppercase tracking-wide mb-2">基本信息</h4>
              <div class="flex justify-between items-center text-xs">
                <span class="text-muted-foreground">文档 ID</span>
                <span class="font-mono bg-muted px-1.5 py-0.5 rounded text-muted-foreground">{{ selectedFile.document_id.substring(0, 8) }}...</span>
              </div>
              <div class="flex justify-between items-center text-xs">
                <span class="text-muted-foreground">上传时间</span>
                <span class="text-foreground">{{ formatDate(selectedFile.created_at) }}</span>
              </div>
              <div class="flex justify-between items-center text-xs">
                <span class="text-muted-foreground">状态</span>
                <span :class="['px-1.5 py-0.5 rounded font-medium', selectedFile.status === 'ready' ? 'bg-success/10 text-success' : 'bg-accent text-accent-foreground']">
                  {{ getStatusText(selectedFile.status) }}
                </span>
              </div>
              <div v-if="selectedFile.category" class="flex justify-between items-center text-xs">
                <span class="text-muted-foreground">分类</span>
                <span class="bg-muted text-muted-foreground px-1.5 py-0.5 rounded font-medium">{{ getCategoryLabel(selectedFile.category) }}</span>
              </div>
            </div>

            <!-- 元数据 -->
            <div v-if="selectedFile.metadata" class="space-y-3 pt-4 border-t border-border">
              <h4 class="font-semibold text-foreground text-xs uppercase tracking-wide mb-2">元数据</h4>
              <div v-for="(value, key) in selectedFile.metadata" :key="key" class="flex justify-between items-center text-xs">
                <span class="text-muted-foreground">{{ key }}</span>
                <span class="font-mono text-foreground truncate max-w-[150px]" :title="value">{{ value }}</span>
              </div>
            </div>

            <!-- 操作按钮 -->
            <div class="flex flex-col gap-2 pt-6 mt-auto">
              <button
                @click="downloadFile(selectedFile)"
                class="w-full py-2 bg-primary text-white rounded-lg text-xs font-medium hover:bg-primary-hover transition-all shadow-sm"
              >
                下载文件
              </button>
              <button
                @click="deleteFile(selectedFile)"
                class="w-full py-2 bg-white border border-destructive/30 text-destructive rounded-lg text-xs font-medium hover:bg-destructive/10 transition-all"
              >
                删除文件
              </button>
            </div>
          </div>
        </div>
      </transition>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useKnowledgeStore } from '@/stores/knowledge'
import axios from '@/api/index'
import { 
  UploadCloud, 
  Upload, 
  Search, 
  ChevronDown, 
  LayoutGrid, 
  List, 
  RefreshCw, 
  Loader2, 
  FolderOpen, 
  FileText, 
  Download, 
  Trash2, 
  X,
  File,
  Image,
  Music,
  Video,
  FileBox,
  Database
} from 'lucide-vue-next'

const router = useRouter()
const knowledgeStore = useKnowledgeStore()

const getCurrentUserId = () => 'local'

// 数据状态
const files = ref([])
const stats = ref(null)
const loading = ref(true)
const selectedFile = ref(null)

// 上传状态
const fileInput = ref(null)
const uploadQueue = ref([])
const isUploading = ref(false)
const isDragOver = ref(false)

// 筛选和搜索
const searchQuery = ref('')
const selectedCategory = ref('all')
const selectedStatus = ref('all')
const sortBy = ref('created_at')
const viewMode = ref('grid')

// 分页
const currentPage = ref(1)
const pageSize = 20

// 分类选项
const categories = [
  { value: 'all', label: '全部', icon: FileBox },
  { value: 'document', label: '文档', icon: FileText },
  { value: 'image', label: '图片', icon: Image },
  { value: 'audio', label: '音频', icon: Music },
  { value: 'video', label: '视频', icon: Video },
]

// 状态选项
const statuses = [
  { value: 'all', label: '全部' },
  { value: 'ready', label: '就绪' },
  { value: 'processing', label: '处理中' },
  { value: 'failed', label: '失败' },
]

// 筛选后的文件
const filteredFiles = computed(() => {
  let result = files.value

  // 搜索
  if (searchQuery.value) {
    result = result.filter(f => f.filename.toLowerCase().includes(searchQuery.value.toLowerCase()))
  }

  // 分类筛选
  if (selectedCategory.value !== 'all') {
    result = result.filter(f => f.category === selectedCategory.value)
  }

  // 状态筛选
  if (selectedStatus.value !== 'all') {
    result = result.filter(f => f.status === selectedStatus.value)
  }

  // 排序
  result = result.sort((a, b) => {
    if (sortBy.value === 'created_at') {
      return new Date(b.created_at) - new Date(a.created_at)
    } else if (sortBy.value === 'filename') {
      return a.filename.localeCompare(b.filename)
    } else if (sortBy.value === 'file_size') {
      return (b.metadata?.file_size || 0) - (a.metadata?.file_size || 0)
    }
    return 0
  })

  // 分页
  const start = (currentPage.value - 1) * pageSize
  return result.slice(start, start + pageSize)
})

const totalPages = computed(() => {
  let result = files.value

  if (searchQuery.value) {
    result = result.filter(f => f.filename.toLowerCase().includes(searchQuery.value.toLowerCase()))
  }

  if (selectedCategory.value !== 'all') {
    result = result.filter(f => f.category === selectedCategory.value)
  }

  if (selectedStatus.value !== 'all') {
    result = result.filter(f => f.status === selectedStatus.value)
  }

  return Math.ceil(result.length / pageSize)
})

// 工具函数
const getStatusText = (status) => {
  const map = { ready: '就绪', processing: '处理中', failed: '失败' }
  return map[status] || status
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const formatFileSize = (bytes) => {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i]
}

const getCategoryCount = (category) => {
  if (category === 'all') return files.value.length
  return files.value.filter(f => f.category === category).length
}

const getStatusCount = (status) => {
  if (status === 'all') return files.value.length
  return files.value.filter(f => f.status === status).length
}

const getCategoryLabel = (category) => {
  return categories.find(c => c.value === category)?.label || category
}

// 文件操作
const triggerFileInput = () => {
  fileInput.value?.click()
}

const handleFileSelect = (e) => {
  const selectedFiles = Array.from(e.target.files)
  selectedFiles.forEach(file => {
    uploadQueue.value.push({
      id: Date.now() + Math.random(),
      file,
      status: 'pending',
      statusText: '等待上传'
    })
  })
  e.target.value = ''
}

const handleDrop = (e) => {
  isDragOver.value = false
  const droppedFiles = Array.from(e.dataTransfer.files)
  droppedFiles.forEach(file => {
    uploadQueue.value.push({
      id: Date.now() + Math.random(),
      file,
      status: 'pending',
      statusText: '等待上传'
    })
  })
}

const clearQueue = () => {
  uploadQueue.value = []
}

const startUpload = async () => {
  isUploading.value = true

  for (const item of uploadQueue.value) {
    if (item.status !== 'pending') continue

    try {
      item.status = 'uploading'
      item.statusText = '上传中'

      const formData = new FormData()
      // 后端期望 files（复数）
      formData.append('files', item.file)
      formData.append('user_id', getCurrentUserId())

      await axios.post('/v1/knowledge/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })

      item.status = 'success'
      item.statusText = '成功'
    } catch (error) {
      console.error('上传失败:', error)
      item.status = 'error'
      item.statusText = '失败'
      item.statusText = '失败'
    }
  }

  isUploading.value = false
  // 上传后强制刷新，从 Ragie API 获取最新状态
  await refreshFiles(true)
}

// 轮询定时器
let pollingTimer = null

const refreshFiles = async (forceRefresh = false) => {
  try {
    loading.value = true
    const userId = getCurrentUserId()
    // 正确的后端路由: /api/v1/knowledge/documents/{user_id}
    // forceRefresh=true 时传递 refresh=true 参数，从 Ragie API 刷新处理中文档的状态
    const response = await axios.get(`/v1/knowledge/documents/${userId}`, {
      params: { refresh: forceRefresh }
    })
    files.value = response.data.data?.documents || []
    
    // 检查是否有处理中的文档，用于控制轮询
    const hasProcessing = files.value.some(f => 
      ['pending', 'partitioning', 'partitioned', 'refined', 'chunked', 'indexed', 'summary_indexed', 'keyword_indexed'].includes(f.status)
    )
    
    // 如果有处理中的文档，启动轮询（每 5 秒刷新一次）
    if (hasProcessing && !pollingTimer) {
      pollingTimer = setInterval(() => {
        refreshFiles(true)  // 轮询时强制刷新
      }, 5000)
    }
    // 如果没有处理中的文档，停止轮询
    else if (!hasProcessing && pollingTimer) {
      clearInterval(pollingTimer)
      pollingTimer = null
    }
    
    // 统计信息从单独接口获取
    try {
      const statsResponse = await axios.get(`/v1/knowledge/stats/${userId}`)
      stats.value = statsResponse.data.data || null
    } catch {
      // 统计接口失败不影响主流程
      stats.value = null
    }
  } catch (error) {
    console.error('加载文件列表失败:', error)
  } finally {
    loading.value = false
  }
}

const selectFile = (file) => {
  selectedFile.value = file
}

const downloadFile = async (file) => {
  try {
    const userId = getCurrentUserId()
    // 正确的后端路由: /api/v1/knowledge/documents/{user_id}/{document_id}/download
    const response = await axios.get(`/v1/knowledge/documents/${userId}/${file.document_id}/download`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', file.filename)
    document.body.appendChild(link)
    link.click()
    link.remove()
  } catch (error) {
    console.error('下载失败:', error)
    alert('下载失败')
  }
}

const deleteFile = async (file) => {
  if (!confirm(`确定要删除 "${file.filename}" 吗？`)) return

  try {
    const userId = getCurrentUserId()
    // 正确的后端路由: /api/v1/knowledge/documents/{user_id}/{document_id}
    await axios.delete(`/v1/knowledge/documents/${userId}/${file.document_id}`)
    if (selectedFile.value?.document_id === file.document_id) {
      selectedFile.value = null
    }
    await refreshFiles()
  } catch (error) {
    console.error('删除失败:', error)
    alert('删除失败')
  }
}

const toggleViewMode = () => {
  viewMode.value = viewMode.value === 'grid' ? 'list' : 'grid'
}

// 生命周期
onMounted(() => {
  refreshFiles()
})

onUnmounted(() => {
  // 组件卸载时清理轮询定时器
  if (pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
})

// 筛选变化时重置分页
watch([searchQuery, selectedCategory, selectedStatus], () => {
  currentPage.value = 1
})
</script>

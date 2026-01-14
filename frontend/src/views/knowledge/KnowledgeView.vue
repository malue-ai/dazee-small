<template>
  <div class="h-screen w-full flex flex-col bg-gray-50 relative overflow-hidden text-gray-900 font-sans">
    <!-- 背景装饰 -->
    <div class="absolute inset-0 z-0 opacity-20 pointer-events-none">
      <div class="absolute top-0 left-0 w-[500px] h-[500px] bg-blue-200 rounded-full mix-blend-multiply filter blur-3xl animate-blob"></div>
      <div class="absolute top-0 right-0 w-[500px] h-[500px] bg-purple-200 rounded-full mix-blend-multiply filter blur-3xl animate-blob animation-delay-2000"></div>
      <div class="absolute -bottom-8 left-20 w-[500px] h-[500px] bg-pink-200 rounded-full mix-blend-multiply filter blur-3xl animate-blob animation-delay-4000"></div>
    </div>

    <!-- 顶部导航 -->
    <div class="h-16 flex items-center justify-between px-8 border-b border-white/20 bg-white/40 backdrop-blur-md sticky top-0 z-20">
      <div class="flex items-center gap-6">
        <h1 class="text-lg font-bold flex items-center gap-2 text-gray-800">
          <span class="text-2xl">📚</span> 知识库
        </h1>
        <div class="flex items-center gap-3 text-xs font-medium">
          <div class="px-3 py-1.5 bg-white/60 rounded-lg shadow-sm border border-white/40">
            <span class="text-gray-500">总文件</span>
            <span class="ml-2 font-bold text-gray-900">{{ stats?.total_files || 0 }}</span>
          </div>
          <div class="px-3 py-1.5 bg-green-50/80 text-green-700 rounded-lg shadow-sm border border-green-100">
            <span class="opacity-80">就绪</span>
            <span class="ml-2 font-bold">{{ stats?.by_status?.ready || 0 }}</span>
          </div>
          <div class="px-3 py-1.5 bg-white/60 rounded-lg shadow-sm border border-white/40 text-gray-500 font-mono">
            {{ formatFileSize(stats?.total_size || 0) }}
          </div>
        </div>
      </div>
      <button 
        @click="$router.push('/')" 
        class="px-5 py-2.5 bg-white/60 border border-white/40 text-gray-600 text-sm font-medium rounded-xl hover:bg-white hover:text-gray-900 transition-all shadow-sm"
      >
        ← 返回聊天
      </button>
    </div>

    <!-- 主内容区 -->
    <div class="flex-1 flex overflow-hidden relative z-10">
      <!-- 左侧侧边栏：上传和筛选 -->
      <div class="w-80 border-r border-white/20 bg-white/60 backdrop-blur-xl overflow-y-auto p-6 flex flex-col gap-6">
        <!-- 上传区域 -->
        <div class="bg-white/50 border border-white/40 rounded-2xl p-5 shadow-sm">
          <h3 class="text-sm font-bold text-gray-800 mb-4">上传文件</h3>
          <div
            class="border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200"
            :class="isDragOver ? 'border-blue-400 bg-blue-50/50' : 'border-gray-300 hover:border-blue-400 hover:bg-white/50'"
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
            <div class="text-4xl mb-3 transform transition-transform group-hover:scale-110">📤</div>
            <p class="text-sm font-medium text-gray-700 mb-1">点击或拖拽上传</p>
            <p class="text-xs text-gray-400">PDF, Word, PPT, 图片等</p>
          </div>

          <!-- 上传队列 -->
          <div v-if="uploadQueue.length > 0" class="mt-5 space-y-3">
            <div class="flex items-center justify-between text-xs">
              <span class="font-bold text-gray-500">队列 ({{ uploadQueue.length }})</span>
              <button @click="clearQueue" class="text-red-500 hover:text-red-600 hover:underline">清空</button>
            </div>
            <div class="space-y-2 max-h-40 overflow-y-auto pr-1 scrollbar-thin">
              <div
                v-for="item in uploadQueue"
                :key="item.id"
                class="flex items-center justify-between p-3 bg-white/60 rounded-lg text-xs border border-white/40 shadow-sm"
              >
                <div class="flex-1 truncate mr-2">
                  <div class="font-medium text-gray-800 truncate">{{ item.file.name }}</div>
                  <div class="text-gray-400 text-[10px]">{{ formatFileSize(item.file.size) }}</div>
                </div>
                <span :class="['px-2 py-1 rounded-md text-[10px] font-bold', item.status === 'success' ? 'bg-green-100 text-green-700' : item.status === 'error' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600']">
                  {{ item.statusText }}
                </span>
              </div>
            </div>
            <button
              @click="startUpload"
              :disabled="isUploading"
              class="w-full py-2.5 bg-gray-900 text-white text-sm font-medium rounded-xl hover:bg-gray-800 transition-all shadow-lg shadow-gray-900/10 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {{ isUploading ? '上传中...' : '开始上传' }}
            </button>
          </div>
        </div>

        <!-- 分类过滤 -->
        <div class="space-y-2">
          <h3 class="text-xs font-bold text-gray-400 uppercase tracking-wider px-2">分类</h3>
          <div class="space-y-1">
            <button
              v-for="cat in categories"
              :key="cat.value"
              class="w-full flex items-center justify-between px-4 py-2.5 rounded-xl text-sm transition-all"
              :class="selectedCategory === cat.value ? 'bg-white shadow-md text-blue-600 font-medium' : 'text-gray-600 hover:bg-white/50 hover:text-gray-900'"
              @click="selectedCategory = cat.value"
            >
              <div class="flex items-center gap-3">
                <span class="text-lg">{{ cat.icon }}</span>
                <span>{{ cat.label }}</span>
              </div>
              <span class="text-xs bg-gray-100 px-2 py-0.5 rounded-md text-gray-500">{{ getCategoryCount(cat.value) }}</span>
            </button>
          </div>
        </div>

        <!-- 状态过滤 -->
        <div class="space-y-2">
          <h3 class="text-xs font-bold text-gray-400 uppercase tracking-wider px-2">状态</h3>
          <div class="space-y-1">
            <button
              v-for="stat in statuses"
              :key="stat.value"
              class="w-full flex items-center justify-between px-4 py-2.5 rounded-xl text-sm transition-all"
              :class="selectedStatus === stat.value ? 'bg-white shadow-md text-blue-600 font-medium' : 'text-gray-600 hover:bg-white/50 hover:text-gray-900'"
              @click="selectedStatus = stat.value"
            >
              <div class="flex items-center gap-3">
                <span :class="['w-2 h-2 rounded-full ring-2 ring-opacity-30', stat.value === 'ready' ? 'bg-green-500 ring-green-500' : stat.value === 'processing' ? 'bg-yellow-500 ring-yellow-500' : 'bg-gray-300 ring-gray-300']"></span>
                <span>{{ stat.label }}</span>
              </div>
              <span class="text-xs bg-gray-100 px-2 py-0.5 rounded-md text-gray-500">{{ getStatusCount(stat.value) }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 右侧主区域：文件列表 -->
      <div class="flex-1 flex flex-col overflow-hidden">
        <!-- 工具栏 -->
        <div class="flex items-center justify-between gap-4 px-8 py-4 border-b border-white/20 bg-white/30 backdrop-blur-sm">
          <div class="flex-1 max-w-lg relative group">
            <span class="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-blue-500 transition-colors">🔍</span>
            <input
              v-model="searchQuery"
              type="text"
              placeholder="搜索文件名..."
              class="w-full pl-10 pr-4 py-2.5 bg-white/60 border border-white/40 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm placeholder-gray-400 text-gray-800"
            />
          </div>
          <div class="flex items-center gap-3">
            <div class="relative">
              <select 
                v-model="sortBy" 
                class="appearance-none pl-4 pr-10 py-2.5 bg-white/60 border border-white/40 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 cursor-pointer shadow-sm text-gray-700 font-medium hover:bg-white transition-colors"
              >
                <option value="created_at">最新上传</option>
                <option value="filename">文件名</option>
                <option value="file_size">文件大小</option>
              </select>
              <div class="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-gray-400 text-xs">▼</div>
            </div>
            
            <div class="flex bg-white/60 rounded-xl p-1 border border-white/40 shadow-sm">
              <button 
                @click="viewMode = 'grid'" 
                class="p-2 rounded-lg transition-all"
                :class="viewMode === 'grid' ? 'bg-white shadow text-blue-600' : 'text-gray-400 hover:text-gray-600'"
              >
                <span class="text-lg">🔲</span>
              </button>
              <button 
                @click="viewMode = 'list'" 
                class="p-2 rounded-lg transition-all"
                :class="viewMode === 'list' ? 'bg-white shadow text-blue-600' : 'text-gray-400 hover:text-gray-600'"
              >
                <span class="text-lg">📋</span>
              </button>
            </div>

            <button 
              @click="refreshFiles" 
              class="p-2.5 bg-white/60 border border-white/40 rounded-xl text-gray-600 hover:bg-white hover:text-blue-600 transition-all shadow-sm group"
            >
              <span class="block transition-transform group-hover:rotate-180">🔄</span>
            </button>
          </div>
        </div>

        <!-- 文件列表 -->
        <div class="flex-1 overflow-y-auto p-8 scrollbar-thin">
          <div v-if="loading" class="flex flex-col items-center justify-center h-[60vh] text-gray-400">
            <div class="w-10 h-10 border-3 border-gray-200 border-t-blue-500 rounded-full animate-spin mb-4"></div>
            <p class="text-sm font-medium">加载文件中...</p>
          </div>

          <div v-else-if="filteredFiles.length === 0" class="flex flex-col items-center justify-center h-[60vh] text-gray-400">
            <div class="w-24 h-24 bg-white/50 rounded-3xl flex items-center justify-center mb-6 border border-white/40 shadow-sm">
              <span class="text-5xl opacity-30">📭</span>
            </div>
            <p class="text-lg font-bold text-gray-700 mb-2">暂无文件</p>
            <p class="text-sm">点击左侧上传区域添加文件</p>
          </div>

          <div v-else>
            <!-- 网格视图 -->
            <div v-if="viewMode === 'grid'" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-5">
              <div
                v-for="file in filteredFiles"
                :key="file.document_id"
                class="group relative bg-white/70 backdrop-blur-sm border border-white/50 rounded-2xl p-5 cursor-pointer transition-all duration-300 hover:bg-white hover:shadow-xl hover:shadow-blue-900/5 hover:-translate-y-1"
                :class="selectedFile?.document_id === file.document_id ? 'ring-2 ring-blue-500 shadow-lg bg-white' : ''"
                @click="selectFile(file)"
              >
                <div class="flex justify-center py-6 mb-2">
                  <span class="text-5xl drop-shadow-sm transform transition-transform group-hover:scale-110">{{ getFileIcon(file.filename) }}</span>
                </div>
                
                <div class="space-y-2">
                  <div class="font-bold text-gray-800 text-sm truncate" :title="file.filename">{{ file.filename }}</div>
                  
                  <div class="flex items-center justify-between text-xs">
                    <span class="text-gray-400">{{ formatDate(file.created_at) }}</span>
                    <span :class="['px-2 py-0.5 rounded-md font-medium', file.status === 'ready' ? 'bg-green-50 text-green-600' : 'bg-yellow-50 text-yellow-600']">
                      {{ getStatusText(file.status) }}
                    </span>
                  </div>
                </div>

                <!-- 悬浮操作栏 -->
                <div class="absolute inset-x-4 bottom-4 flex gap-2 opacity-0 group-hover:opacity-100 transition-all duration-200 translate-y-2 group-hover:translate-y-0">
                  <button
                    @click.stop="downloadFile(file)"
                    class="flex-1 py-2 bg-gray-100 rounded-lg text-xs font-medium text-gray-600 hover:bg-gray-200 transition-colors shadow-sm"
                  >
                    ⬇️ 下载
                  </button>
                  <button
                    @click.stop="deleteFile(file)"
                    class="flex-1 py-2 bg-red-50 text-red-500 rounded-lg text-xs font-medium hover:bg-red-100 transition-colors shadow-sm"
                  >
                    🗑️ 删除
                  </button>
                </div>
              </div>
            </div>

            <!-- 列表视图 -->
            <div v-else class="space-y-3">
              <div
                v-for="file in filteredFiles"
                :key="file.document_id"
                class="group flex items-center gap-5 p-4 bg-white/60 backdrop-blur-sm border border-white/50 rounded-xl cursor-pointer transition-all hover:bg-white hover:shadow-md"
                :class="selectedFile?.document_id === file.document_id ? 'ring-2 ring-blue-500 bg-white' : ''"
                @click="selectFile(file)"
              >
                <div class="text-3xl flex-shrink-0">{{ getFileIcon(file.filename) }}</div>
                
                <div class="flex-1 min-w-0 grid grid-cols-12 gap-4 items-center">
                  <div class="col-span-5 font-bold text-gray-800 text-sm truncate" :title="file.filename">{{ file.filename }}</div>
                  <div class="col-span-3 text-xs text-gray-500">{{ formatDate(file.created_at) }}</div>
                  <div class="col-span-2 text-xs text-gray-500 font-mono">{{ formatFileSize(file.metadata?.file_size || 0) }}</div>
                  <div class="col-span-2 text-right">
                    <span :class="['px-2.5 py-1 rounded-md text-xs font-medium', file.status === 'ready' ? 'bg-green-50 text-green-600' : 'bg-yellow-50 text-yellow-600']">
                      {{ getStatusText(file.status) }}
                    </span>
                  </div>
                </div>

                <div class="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    @click.stop="downloadFile(file)"
                    class="p-2 bg-gray-100 rounded-lg hover:bg-gray-200 text-gray-600 transition-colors"
                    title="下载"
                  >
                    ⬇️
                  </button>
                  <button
                    @click.stop="deleteFile(file)"
                    class="p-2 bg-red-50 text-red-500 rounded-lg hover:bg-red-100 transition-colors"
                    title="删除"
                  >
                    🗑️
                  </button>
                </div>
              </div>
            </div>

            <!-- 分页 -->
            <div v-if="totalPages > 1" class="flex items-center justify-center gap-4 mt-10">
              <button
                @click="currentPage--"
                :disabled="currentPage === 1"
                class="px-5 py-2.5 bg-white/60 border border-white/40 rounded-xl text-sm font-medium text-gray-600 hover:bg-white hover:text-gray-900 transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                ← 上一页
              </button>
              <span class="text-sm font-medium text-gray-500 bg-white/40 px-4 py-2 rounded-lg border border-white/20">
                {{ currentPage }} / {{ totalPages }}
              </span>
              <button
                @click="currentPage++"
                :disabled="currentPage === totalPages"
                class="px-5 py-2.5 bg-white/60 border border-white/40 rounded-xl text-sm font-medium text-gray-600 hover:bg-white hover:text-gray-900 transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                下一页 →
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
        <div v-if="selectedFile" class="w-[400px] border-l border-white/20 bg-white/80 backdrop-blur-2xl flex flex-col shadow-2xl z-20">
          <div class="h-16 flex items-center justify-between px-6 border-b border-white/20">
            <h3 class="font-bold text-gray-800">文件详情</h3>
            <button @click="selectedFile = null" class="p-2 rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-900 transition-colors">✕</button>
          </div>

          <div class="flex-1 overflow-y-auto p-6 space-y-6">
            <!-- 文件预览 -->
            <div class="flex flex-col items-center py-8 bg-white/50 rounded-2xl border border-white/40">
              <div class="text-7xl mb-4 drop-shadow-md">{{ getFileIcon(selectedFile.filename) }}</div>
              <div class="text-center font-bold text-gray-800 px-4 break-words leading-tight">{{ selectedFile.filename }}</div>
            </div>

            <!-- 基本信息 -->
            <div class="bg-white/50 rounded-2xl border border-white/40 p-5 space-y-4">
              <h4 class="font-bold text-gray-700 text-sm uppercase tracking-wide mb-2">基本信息</h4>
              <div class="flex justify-between items-center text-sm">
                <span class="text-gray-500">文档 ID</span>
                <span class="font-mono text-xs bg-gray-100 px-2 py-1 rounded text-gray-600">{{ selectedFile.document_id.substring(0, 8) }}...</span>
              </div>
              <div class="flex justify-between items-center text-sm">
                <span class="text-gray-500">上传时间</span>
                <span class="text-gray-800 font-medium">{{ formatDate(selectedFile.created_at) }}</span>
              </div>
              <div class="flex justify-between items-center text-sm">
                <span class="text-gray-500">状态</span>
                <span :class="['px-2.5 py-1 rounded-md text-xs font-bold', selectedFile.status === 'ready' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700']">
                  {{ getStatusText(selectedFile.status) }}
                </span>
              </div>
              <div v-if="selectedFile.category" class="flex justify-between items-center text-sm">
                <span class="text-gray-500">分类</span>
                <span class="bg-blue-50 text-blue-600 px-2.5 py-1 rounded-md text-xs font-medium">{{ getCategoryLabel(selectedFile.category) }}</span>
              </div>
            </div>

            <!-- 元数据 -->
            <div v-if="selectedFile.metadata" class="bg-white/50 rounded-2xl border border-white/40 p-5 space-y-3">
              <h4 class="font-bold text-gray-700 text-sm uppercase tracking-wide mb-2">元数据</h4>
              <div v-for="(value, key) in selectedFile.metadata" :key="key" class="flex justify-between items-center text-sm border-b border-gray-100/50 last:border-0 pb-2 last:pb-0">
                <span class="text-gray-500">{{ key }}</span>
                <span class="font-mono text-xs text-gray-700 truncate max-w-[150px]" :title="value">{{ value }}</span>
              </div>
            </div>

            <!-- 操作按钮 -->
            <div class="flex flex-col gap-3 pt-4 mt-auto">
              <button
                @click="downloadFile(selectedFile)"
                class="w-full py-3 bg-gray-900 text-white rounded-xl text-sm font-bold hover:bg-gray-800 transition-all shadow-lg shadow-gray-900/10 active:scale-95"
              >
                ⬇️ 下载文件
              </button>
              <button
                @click="deleteFile(selectedFile)"
                class="w-full py-3 bg-red-50 text-red-500 rounded-xl text-sm font-bold hover:bg-red-100 transition-all active:scale-95"
              >
                🗑️ 删除文件
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
import { useAuthStore } from '@/stores/auth'
import axios from '@/api/index'

const router = useRouter()
const knowledgeStore = useKnowledgeStore()
const authStore = useAuthStore()

// 获取当前用户 ID（优先使用登录用户 ID）
const getCurrentUserId = () => {
  return authStore.user?.id || authStore.initUserId()
}

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
  { value: 'all', label: '全部', icon: '📁' },
  { value: 'document', label: '文档', icon: '📄' },
  { value: 'image', label: '图片', icon: '🖼️' },
  { value: 'audio', label: '音频', icon: '🎵' },
  { value: 'video', label: '视频', icon: '🎬' },
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
const getFileIcon = (filename) => {
  const ext = filename.split('.').pop().toLowerCase()
  const iconMap = {
    pdf: '📕', docx: '📘', pptx: '📙', xlsx: '📗',
    png: '🖼️', jpg: '🖼️', jpeg: '🖼️',
    mp3: '🎵', mp4: '🎬', txt: '📄', md: '📝',
  }
  return iconMap[ext] || '📄'
}

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
      console.log('📡 启动状态轮询（有处理中的文档）')
      pollingTimer = setInterval(() => {
        refreshFiles(true)  // 轮询时强制刷新
      }, 5000)
    }
    // 如果没有处理中的文档，停止轮询
    else if (!hasProcessing && pollingTimer) {
      console.log('✅ 停止状态轮询（所有文档已就绪）')
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

<style scoped>
@keyframes blob {
  0% { transform: translate(0px, 0px) scale(1); }
  33% { transform: translate(30px, -50px) scale(1.1); }
  66% { transform: translate(-20px, 20px) scale(0.9); }
  100% { transform: translate(0px, 0px) scale(1); }
}
.animate-blob {
  animation: blob 15s infinite;
}
.animation-delay-2000 {
  animation-delay: 2s;
}
.animation-delay-4000 {
  animation-delay: 4s;
}

/* 滚动条优化 */
.scrollbar-thin::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-thin::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.3);
  border-radius: 3px;
}
.scrollbar-thin::-webkit-scrollbar-thumb:hover {
  background-color: rgba(156, 163, 175, 0.5);
}
</style>
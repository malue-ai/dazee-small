<template>
  <div class="flex flex-col h-full bg-white overflow-hidden">
    <!-- 头部 -->
    <div class="flex items-center justify-between px-4 py-2.5 border-b border-border bg-white">
      <div class="flex items-center gap-2 min-w-0 flex-1">
        <component :is="getFileIcon()" class="w-4 h-4 flex-shrink-0" :class="getIconClass()" />
        <span class="text-xs font-semibold text-gray-700 truncate">{{ fileName }}</span>
      </div>
      <div class="flex gap-1.5 items-center flex-shrink-0">
        <button 
          v-if="canPreviewInBrowser" 
          @click="openInNewTab" 
          class="flex items-center gap-1 px-2.5 py-1.5 text-[10px] font-medium text-gray-500 bg-white border border-gray-200 rounded-md hover:bg-gray-50 hover:text-gray-700 transition-colors"
          title="在新标签页打开"
        >
          <ExternalLink class="w-3 h-3" />
          新窗口
        </button>
        <button 
          @click="downloadFile" 
          class="flex items-center gap-1 px-2.5 py-1.5 text-[10px] font-medium text-gray-500 bg-white border border-gray-200 rounded-md hover:bg-gray-50 hover:text-gray-700 transition-colors" 
          title="下载"
        >
          <Download class="w-3 h-3" />
          下载
        </button>
        <button 
          @click="$emit('close')" 
          class="w-7 h-7 flex items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors" 
          title="关闭"
        >
          <X class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- 预览区域 -->
    <div class="flex-1 overflow-hidden relative bg-gray-50">
      <!-- 加载状态 -->
      <div v-if="isLoading" class="flex flex-col items-center justify-center h-full text-gray-400 gap-2">
        <Loader2 class="w-6 h-6 animate-spin" />
        <span class="text-xs">加载中...</span>
      </div>

      <!-- HTML 预览（iframe） -->
      <iframe 
        v-else-if="isHtml"
        :srcdoc="htmlContent"
        class="w-full h-full border-none bg-white"
        sandbox="allow-scripts allow-same-origin"
        @load="onIframeLoad"
      ></iframe>

      <!-- 代码预览 -->
      <div v-else-if="isCode" class="h-full overflow-auto p-4 bg-gray-900">
        <pre class="m-0 font-mono text-xs leading-relaxed"><code class="text-gray-300 whitespace-pre-wrap break-all">{{ fileContent }}</code></pre>
      </div>

      <!-- 图片预览 -->
      <div v-else-if="isImage" class="flex items-center justify-center h-full p-6 bg-gray-100">
        <img :src="imageUrl" :alt="fileName" class="max-w-full max-h-full object-contain rounded-lg shadow-lg" />
      </div>

      <!-- 不支持预览 -->
      <div v-else class="flex flex-col items-center justify-center h-full text-gray-400 text-center p-8">
        <File class="w-12 h-12 mb-3 opacity-40" />
        <p class="text-sm font-medium">此文件类型暂不支持预览</p>
        <p class="text-xs text-gray-400 mt-1 mb-4">{{ fileExtension.toUpperCase() }} 文件</p>
        <button 
          @click="downloadFile" 
          class="flex items-center gap-2 px-5 py-2.5 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800 transition-colors shadow-sm"
        >
          <Download class="w-4 h-4" />
          下载文件
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { 
  FileText, 
  FileCode, 
  FileJson, 
  Image, 
  File, 
  Globe,
  Download, 
  ExternalLink, 
  X, 
  Loader2 
} from 'lucide-vue-next'

// Props
const props = defineProps({
  conversationId: {
    type: String,
    required: true
  },
  filePath: {
    type: String,
    required: true
  }
})

// Emits
const emit = defineEmits(['close'])

// Store
const workspaceStore = useWorkspaceStore()

// 状态
const isLoading = ref(true)
const fileContent = ref('')
const htmlContent = ref('')
const imageUrl = ref('')

// 计算属性
const fileName = computed(() => {
  const parts = props.filePath.split('/')
  return parts[parts.length - 1]
})

const fileExtension = computed(() => {
  const parts = fileName.value.split('.')
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : ''
})

const isHtml = computed(() => {
  return ['html', 'htm'].includes(fileExtension.value)
})

const isCode = computed(() => {
  const codeExtensions = [
    'js', 'ts', 'jsx', 'tsx', 'vue', 'py', 'css', 'scss', 'less',
    'json', 'yaml', 'yml', 'xml', 'md', 'txt', 'sh', 'bash',
    'java', 'c', 'cpp', 'h', 'go', 'rs', 'rb', 'php', 'sql'
  ]
  return codeExtensions.includes(fileExtension.value)
})

const isImage = computed(() => {
  const imageExtensions = ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'ico']
  return imageExtensions.includes(fileExtension.value)
})

const canPreviewInBrowser = computed(() => {
  return isHtml.value
})

// 获取文件图标组件
function getFileIcon() {
  const ext = fileExtension.value
  const iconMap: Record<string, any> = {
    'html': Globe,
    'htm': Globe,
    'js': FileCode,
    'ts': FileCode,
    'jsx': FileCode,
    'tsx': FileCode,
    'vue': FileCode,
    'py': FileCode,
    'css': FileCode,
    'scss': FileCode,
    'json': FileJson,
    'yaml': FileJson,
    'yml': FileJson,
    'md': FileText,
    'png': Image,
    'jpg': Image,
    'jpeg': Image,
    'gif': Image,
    'svg': Image
  }
  return iconMap[ext] || File
}

// 获取图标颜色类
function getIconClass() {
  const ext = fileExtension.value
  const colorMap: Record<string, string> = {
    'html': 'text-orange-500',
    'htm': 'text-orange-500',
    'js': 'text-yellow-500',
    'ts': 'text-blue-600',
    'jsx': 'text-cyan-500',
    'tsx': 'text-cyan-600',
    'vue': 'text-green-500',
    'py': 'text-blue-500',
    'css': 'text-pink-500',
    'scss': 'text-pink-600',
    'json': 'text-gray-500',
    'md': 'text-gray-600',
    'png': 'text-purple-500',
    'jpg': 'text-purple-500',
    'jpeg': 'text-purple-500',
    'gif': 'text-purple-500',
    'svg': 'text-orange-400'
  }
  return colorMap[ext] || 'text-gray-400'
}

/**
 * 规范化文件路径用于 URL
 */
function normalizePathForUrl(path: string): string {
  const cleanPath = path.startsWith('/') ? path.slice(1) : path
  return cleanPath.split('/').map(encodeURIComponent).join('/')
}

// 加载文件内容
async function loadFile() {
  isLoading.value = true
  
  try {
    if (isImage.value) {
      // 图片使用 URL
      imageUrl.value = `/api/v1/workspace/${props.conversationId}/files/${normalizePathForUrl(props.filePath)}?download=true`
    } else {
      // 文本文件获取内容
      const content = await workspaceStore.getFileContent(props.conversationId, props.filePath)
      
      if (isHtml.value) {
        htmlContent.value = content
      } else {
        fileContent.value = content
      }
    }
  } catch (error: any) {
    console.error('加载文件失败:', error)
    fileContent.value = `加载失败: ${error.message}`
  } finally {
    isLoading.value = false
  }
}

// 在新标签页打开
function openInNewTab() {
  if (isHtml.value && htmlContent.value) {
    const blob = new Blob([htmlContent.value], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
    // 延迟清理 URL
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
}

// 下载文件
function downloadFile() {
  workspaceStore.downloadFile(props.conversationId, props.filePath)
}

// iframe 加载完成
function onIframeLoad() {
  // HTML 预览加载完成
}

// 监听文件路径变化
watch(() => props.filePath, () => {
  loadFile()
}, { immediate: true })

// 初始化
onMounted(() => {
  loadFile()
})
</script>


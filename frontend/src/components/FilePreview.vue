<template>
  <div class="file-preview">
    <!-- 头部 -->
    <div class="preview-header">
      <div class="file-info">
        <span class="file-icon">{{ getFileIcon() }}</span>
        <span class="file-name">{{ fileName }}</span>
      </div>
      <div class="preview-actions">
        <button 
          v-if="canPreviewInBrowser" 
          @click="openInNewTab" 
          class="action-btn"
          title="在新标签页打开"
        >
          🔗 新窗口
        </button>
        <button @click="downloadFile" class="action-btn" title="下载">
          ⬇️ 下载
        </button>
        <button @click="$emit('close')" class="close-btn" title="关闭">
          ✕
        </button>
      </div>
    </div>

    <!-- 预览区域 -->
    <div class="preview-content">
      <!-- 加载状态 -->
      <div v-if="isLoading" class="loading-state">
        <div class="loading-spinner"></div>
        <span>加载中...</span>
      </div>

      <!-- HTML 预览（iframe） -->
      <iframe 
        v-else-if="isHtml"
        :srcdoc="htmlContent"
        class="html-preview"
        sandbox="allow-scripts allow-same-origin"
        @load="onIframeLoad"
      ></iframe>

      <!-- 代码预览 -->
      <div v-else-if="isCode" class="code-preview">
        <pre><code>{{ fileContent }}</code></pre>
      </div>

      <!-- 图片预览 -->
      <div v-else-if="isImage" class="image-preview">
        <img :src="imageUrl" :alt="fileName" />
      </div>

      <!-- 不支持预览 -->
      <div v-else class="unsupported-preview">
        <div class="unsupported-icon">📄</div>
        <p>此文件类型暂不支持预览</p>
        <p class="file-type">{{ fileExtension.toUpperCase() }} 文件</p>
        <button @click="downloadFile" class="download-btn">
          ⬇️ 下载文件
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'

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

// 获取文件图标
function getFileIcon() {
  const ext = fileExtension.value
  const iconMap = {
    'html': '🌐',
    'htm': '🌐',
    'js': '📜',
    'ts': '📘',
    'jsx': '⚛️',
    'tsx': '⚛️',
    'vue': '💚',
    'py': '🐍',
    'css': '🎨',
    'scss': '🎨',
    'json': '📋',
    'md': '📝',
    'png': '🖼️',
    'jpg': '🖼️',
    'jpeg': '🖼️',
    'gif': '🖼️',
    'svg': '🎭'
  }
  return iconMap[ext] || '📄'
}

// 加载文件内容
async function loadFile() {
  isLoading.value = true
  
  try {
    if (isImage.value) {
      // 图片使用 URL
      imageUrl.value = `/api/v1/workspace/${props.conversationId}/files/${props.filePath}?download=true`
    } else {
      // 文本文件获取内容
      const content = await workspaceStore.getFileContent(props.conversationId, props.filePath)
      
      if (isHtml.value) {
        htmlContent.value = content
      } else {
        fileContent.value = content
      }
    }
  } catch (error) {
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
  console.log('HTML 预览加载完成')
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

<style scoped>
.file-preview {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: transparent;
  overflow: hidden;
}

/* 头部 */
.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.02);
  border-bottom: 1px solid #2d2d44;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.file-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.file-name {
  font-size: 13px;
  font-weight: 600;
  color: #e5e5e5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-actions {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-shrink: 0;
}

.action-btn {
  padding: 5px 10px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  color: #a0a0b0;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.15);
  color: #e5e5e5;
}

.close-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.15);
  border-radius: 6px;
  color: #ef4444;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.close-btn:hover {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.3);
}

/* 预览区域 */
.preview-content {
  flex: 1;
  overflow: hidden;
  position: relative;
  background: #0a0a12;
}

/* 加载状态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #666;
  gap: 10px;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid rgba(102, 126, 234, 0.2);
  border-top-color: #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* HTML 预览 */
.html-preview {
  width: 100%;
  height: 100%;
  border: none;
  background: white;
}

/* 代码预览 */
.code-preview {
  height: 100%;
  overflow: auto;
  padding: 14px 16px;
  background: #0a0a12;
}

.code-preview pre {
  margin: 0;
  font-family: 'JetBrains Mono', 'SF Mono', 'Fira Code', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.7;
}

.code-preview code {
  color: #c9d1d9;
  white-space: pre-wrap;
  word-break: break-all;
}

/* 图片预览 */
.image-preview {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 20px;
  background: #0a0a12;
}

.image-preview img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
}

/* 不支持预览 */
.unsupported-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #666;
  text-align: center;
  padding: 32px;
}

.unsupported-icon {
  font-size: 48px;
  margin-bottom: 12px;
  opacity: 0.4;
}

.unsupported-preview p {
  margin: 6px 0;
  font-size: 13px;
}

.file-type {
  font-size: 11px;
  opacity: 0.5;
  margin-bottom: 16px !important;
}

.download-btn {
  padding: 10px 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  border-radius: 6px;
  color: white;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.download-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.35);
}

/* 滚动条样式 */
.code-preview::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.code-preview::-webkit-scrollbar-track {
  background: transparent;
}

.code-preview::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
  border-radius: 3px;
}

.code-preview::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}
</style>


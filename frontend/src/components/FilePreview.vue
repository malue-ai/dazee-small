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
  background: #1a1a2e;
  border-radius: 12px;
  overflow: hidden;
}

/* 头部 */
.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: linear-gradient(135deg, #2d2d44 0%, #1e1e2e 100%);
  border-bottom: 1px solid #3d3d5c;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-icon {
  font-size: 18px;
}

.file-name {
  font-size: 14px;
  font-weight: 500;
  color: #e5e5e5;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.action-btn {
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.1);
  border: none;
  border-radius: 6px;
  color: #e5e5e5;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}

.close-btn {
  padding: 6px 10px;
  background: rgba(255, 100, 100, 0.2);
  border: none;
  border-radius: 6px;
  color: #ff6b6b;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.close-btn:hover {
  background: rgba(255, 100, 100, 0.4);
}

/* 预览区域 */
.preview-content {
  flex: 1;
  overflow: hidden;
  position: relative;
}

/* 加载状态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #a0a0b0;
  gap: 12px;
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(102, 126, 234, 0.3);
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
  padding: 16px;
  background: #0d1117;
}

.code-preview pre {
  margin: 0;
  font-family: 'SF Mono', 'Fira Code', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.6;
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
  background: #0d0d15;
}

.image-preview img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

/* 不支持预览 */
.unsupported-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #a0a0b0;
  text-align: center;
  padding: 40px;
}

.unsupported-icon {
  font-size: 64px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.unsupported-preview p {
  margin: 8px 0;
}

.file-type {
  font-size: 12px;
  opacity: 0.6;
  margin-bottom: 20px !important;
}

.download-btn {
  padding: 12px 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.download-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

/* 滚动条样式 */
.code-preview::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.code-preview::-webkit-scrollbar-track {
  background: transparent;
}

.code-preview::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 4px;
}

.code-preview::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}
</style>


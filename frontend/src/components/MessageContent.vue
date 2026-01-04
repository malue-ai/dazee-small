<template>
  <div class="message-content">
    <!-- 渲染所有内容块 -->
    <template v-for="(block, index) in contentBlocks" :key="index">
      <!-- 思考过程 -->
      <div v-if="block.type === 'thinking'" class="content-block thinking-block">
        <div class="block-header">
          <span class="block-icon">💭</span>
          <span class="block-title">思考过程</span>
          <button @click="toggleBlock(index)" class="toggle-btn">
            {{ expandedBlocks[index] ? '收起' : '展开' }}
          </button>
        </div>
        <div v-show="expandedBlocks[index]" class="block-content thinking-content">
          {{ block.thinking }}
        </div>
      </div>

      <!-- 文本内容 -->
      <div v-else-if="block.type === 'text'" class="content-block text-block">
        <MarkdownRenderer :content="block.text" />
      </div>

      <!-- 工具调用 -->
      <div v-else-if="block.type === 'tool_use'" class="content-block tool-use-block">
        <div class="block-header">
          <span class="block-icon">🔧</span>
          <span class="block-title">{{ formatToolName(block.name) }}</span>
          <span class="tool-status" :class="getToolStatus(block.id)">
            {{ getToolStatusText(block.id) }}
          </span>
        </div>
        <div class="block-content tool-input">
          <pre>{{ formatToolInput(block.input) }}</pre>
        </div>
      </div>

      <!-- 工具结果 -->
      <div v-else-if="block.type === 'tool_result'" class="content-block tool-result-block" :class="{ 'is-error': block.is_error }">
        <div class="block-header">
          <span class="block-icon">{{ block.is_error ? '❌' : '✅' }}</span>
          <span class="block-title">{{ block.is_error ? '执行失败' : '执行结果' }}</span>
        </div>
        <div class="block-content tool-output">
          <pre>{{ formatToolResult(block.content) }}</pre>
        </div>
      </div>

      <!-- 图片 -->
      <div v-else-if="block.type === 'image'" class="content-block image-block">
        <img :src="getImageSrc(block)" :alt="block.alt || '图片'" />
      </div>

      <!-- 文件 -->
      <div v-else-if="block.type === 'file'" class="content-block file-block">
        <div class="file-card">
          <span class="file-icon">📄</span>
          <div class="file-info">
            <span class="file-name">{{ block.name || '文件' }}</span>
            <span class="file-size" v-if="block.size">{{ formatFileSize(block.size) }}</span>
          </div>
          <a v-if="block.url" :href="block.url" target="_blank" class="download-btn">下载</a>
        </div>
      </div>

      <!-- 未知类型 -->
      <div v-else class="content-block unknown-block">
        <div class="block-header">
          <span class="block-icon">📦</span>
          <span class="block-title">{{ block.type || '未知内容' }}</span>
        </div>
        <div class="block-content">
          <pre>{{ JSON.stringify(block, null, 2) }}</pre>
        </div>
      </div>
    </template>

    <!-- 如果没有内容块，显示纯文本 -->
    <div v-if="contentBlocks.length === 0 && content" class="content-block text-block">
      <MarkdownRenderer :content="content" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'

const props = defineProps({
  // 原始内容（可能是字符串或数组）
  content: {
    type: [String, Array, Object],
    default: ''
  },
  // 工具调用状态映射
  toolStatuses: {
    type: Object,
    default: () => ({})
  }
})

// 展开/收起状态
const expandedBlocks = reactive({})

// 解析内容块
const contentBlocks = computed(() => {
  const content = props.content
  
  // 如果是数组，直接使用
  if (Array.isArray(content)) {
    return content
  }
  
  // 如果是字符串，尝试解析 JSON
  if (typeof content === 'string') {
    // 尝试解析为 JSON
    try {
      const parsed = JSON.parse(content)
      if (Array.isArray(parsed)) {
        return parsed
      }
      // 如果是对象，包装成数组
      if (typeof parsed === 'object' && parsed !== null) {
        return [parsed]
      }
    } catch {
      // 解析失败，返回空数组（会显示原始文本）
    }
  }
  
  return []
})

// 切换块的展开/收起
function toggleBlock(index) {
  expandedBlocks[index] = !expandedBlocks[index]
}

// 格式化工具名称
function formatToolName(name) {
  if (!name) return '工具调用'
  
  // 将下划线转为空格，首字母大写
  return name
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
}

// 格式化工具输入
function formatToolInput(input) {
  if (!input) return '{}'
  
  if (typeof input === 'string') {
    try {
      return JSON.stringify(JSON.parse(input), null, 2)
    } catch {
      return input
    }
  }
  
  return JSON.stringify(input, null, 2)
}

// 格式化工具结果
function formatToolResult(content) {
  if (!content) return ''
  
  // 如果是字符串，尝试解析 JSON 美化
  if (typeof content === 'string') {
    try {
      const parsed = JSON.parse(content)
      return JSON.stringify(parsed, null, 2)
    } catch {
      return content
    }
  }
  
  return JSON.stringify(content, null, 2)
}

// 获取工具状态
function getToolStatus(toolId) {
  const status = props.toolStatuses[toolId]
  if (!status) return 'pending'
  return status.success ? 'success' : 'error'
}

// 获取工具状态文本
function getToolStatusText(toolId) {
  const status = props.toolStatuses[toolId]
  if (!status) return '执行中...'
  return status.success ? '成功' : '失败'
}

// 获取图片 src
function getImageSrc(block) {
  if (block.source?.type === 'base64') {
    return `data:${block.source.media_type};base64,${block.source.data}`
  }
  if (block.source?.type === 'url') {
    return block.source.url
  }
  return block.url || ''
}

// 格式化文件大小
function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}
</script>

<style scoped>
.message-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.content-block {
  border-radius: 8px;
}

/* 思考过程 */
.thinking-block {
  background: rgba(102, 126, 234, 0.08);
  border-left: 3px solid #667eea;
  padding: 12px;
}

.thinking-content {
  font-size: 13px;
  color: #4a5568;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-style: italic;
  margin-top: 8px;
}

/* 文本内容 */
.text-block {
  /* 文本块无额外样式，由 MarkdownRenderer 处理 */
}

/* 工具调用 */
.tool-use-block {
  background: #f7fafc;
  border: 1px solid #e2e8f0;
  padding: 12px;
}

.tool-input {
  background: #1a202c;
  color: #e2e8f0;
  border-radius: 6px;
  padding: 12px;
  margin-top: 8px;
  overflow-x: auto;
}

.tool-input pre {
  margin: 0;
  font-size: 12px;
  font-family: 'Consolas', 'Monaco', monospace;
  white-space: pre-wrap;
  word-break: break-all;
}

/* 工具结果 */
.tool-result-block {
  background: #f0fff4;
  border: 1px solid #9ae6b4;
  padding: 12px;
}

.tool-result-block.is-error {
  background: #fff5f5;
  border-color: #feb2b2;
}

.tool-output {
  background: #f7fafc;
  border-radius: 6px;
  padding: 12px;
  margin-top: 8px;
  overflow-x: auto;
}

.tool-output pre {
  margin: 0;
  font-size: 12px;
  font-family: 'Consolas', 'Monaco', monospace;
  white-space: pre-wrap;
  word-break: break-all;
  color: #2d3748;
}

/* 图片 */
.image-block img {
  max-width: 100%;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* 文件 */
.file-block {
  padding: 0;
}

.file-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #f7fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.file-icon {
  font-size: 24px;
}

.file-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.file-name {
  font-weight: 500;
  color: #2d3748;
}

.file-size {
  font-size: 12px;
  color: #718096;
}

.download-btn {
  padding: 6px 12px;
  background: #667eea;
  color: white;
  border-radius: 6px;
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
}

.download-btn:hover {
  background: #5a67d8;
}

/* 未知内容 */
.unknown-block {
  background: #fffbeb;
  border: 1px solid #fcd34d;
  padding: 12px;
}

.unknown-block pre {
  margin: 0;
  font-size: 11px;
  color: #78350f;
  overflow-x: auto;
}

/* 通用块头部 */
.block-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.block-icon {
  font-size: 16px;
}

.block-title {
  font-weight: 600;
  color: #4a5568;
}

.toggle-btn {
  margin-left: auto;
  padding: 2px 8px;
  background: transparent;
  border: 1px solid #cbd5e0;
  border-radius: 4px;
  font-size: 11px;
  color: #718096;
  cursor: pointer;
}

.toggle-btn:hover {
  background: #edf2f7;
}

/* 工具状态 */
.tool-status {
  margin-left: auto;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.tool-status.pending {
  background: #fef3c7;
  color: #92400e;
}

.tool-status.success {
  background: #d1fae5;
  color: #065f46;
}

.tool-status.error {
  background: #fee2e2;
  color: #991b1b;
}
</style>


<template>
  <div class="message-content">
    <!-- 渲染所有内容块 -->
    <template v-for="(block, index) in contentBlocks" :key="index">
      <!-- 思考过程 -->
      <div v-if="block.type === 'thinking'" class="thinking-block">
        <div class="thinking-header" @click="toggleBlock(index)">
          <div class="thinking-left">
            <svg class="thinking-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 16v-4M12 8h.01"/>
            </svg>
            <span class="thinking-title">思考过程</span>
          </div>
          <svg 
            class="thinking-chevron" 
            :class="{ 'is-expanded': expandedBlocks[index] }"
            viewBox="0 0 24 24" 
            fill="none" 
            stroke="currentColor" 
            stroke-width="2"
          >
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
        <Transition name="collapse">
          <div v-show="expandedBlocks[index]" class="thinking-content">
            <p>{{ block.thinking }}</p>
          </div>
        </Transition>
      </div>

      <!-- 文本内容 -->
      <div v-else-if="block.type === 'text'" class="content-block text-block">
        <MarkdownRenderer :content="block.text" @mermaid-detected="handleMermaidDetected" />
      </div>

      <!-- 工具调用 (合并 Tool Use 和 Tool Result) -->
      <template v-else-if="block.type === 'tool_use'">
        <ToolMessage 
          :name="block.name"
          :input="block.input"
          :partial-input="block.partialInput"
          :result="getToolResultContent(block.id)"
          :status="getToolStatus(block.id)"
        />
      </template>

      <!-- 单独的工具结果 (如果未被合并，例如历史记录中没有配对的 use) -->
      <template v-else-if="block.type === 'tool_result' && !hasPairedToolUse(block.tool_use_id)">
         <div class="content-block tool-result-block" :class="{ 'is-error': block.is_error }">
          <div class="block-header">
            <span class="block-icon">{{ block.is_error ? '❌' : '✅' }}</span>
            <span class="block-title">{{ block.is_error ? '执行失败' : '执行结果' }}</span>
          </div>
          <div class="block-content tool-output">
            <pre>{{ formatToolResult(block.content) }}</pre>
          </div>
        </div>
      </template>

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
      <div v-else-if="!['tool_result'].includes(block.type)" class="content-block unknown-block">
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
      <MarkdownRenderer :content="content" @mermaid-detected="handleMermaidDetected" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import ToolMessage from './ToolMessage.vue'

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

// 事件冒泡
const emit = defineEmits(['mermaid-detected'])

// 处理 mermaid 检测事件，冒泡给父组件
function handleMermaidDetected(charts) {
  emit('mermaid-detected', charts)
}

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
  // 检查 pending 标志（工具正在执行中）
  if (status.pending) return 'pending'
  return status.success ? 'success' : 'error'
}

// 获取工具结果内容
function getToolResultContent(toolId) {
  const status = props.toolStatuses[toolId]
  if (!status || !status.result) return null
  return status.result
}

// 检查是否有配对的 Tool Use
function hasPairedToolUse(toolUseId) {
  if (!toolUseId) return false
  return contentBlocks.value.some(b => b.type === 'tool_use' && b.id === toolUseId)
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

/* 思考过程 - Apple 风格 */
.thinking-block {
  background: #f9fafb;
  border-radius: 12px;
  overflow: hidden;
}

.thinking-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.thinking-header:hover {
  background: #f3f4f6;
}

.thinking-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.thinking-icon {
  width: 16px;
  height: 16px;
  color: #9ca3af;
}

.thinking-title {
  font-size: 13px;
  font-weight: 500;
  color: #6b7280;
}

.thinking-chevron {
  width: 16px;
  height: 16px;
  color: #9ca3af;
  transition: transform 0.2s ease;
}

.thinking-chevron.is-expanded {
  transform: rotate(180deg);
}

.thinking-content {
  padding: 0 14px 14px;
}

.thinking-content p {
  margin: 0;
  font-size: 13px;
  color: #6b7280;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
}

/* 折叠动画 */
.collapse-enter-active,
.collapse-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}

.collapse-enter-from,
.collapse-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}

.collapse-enter-to,
.collapse-leave-from {
  opacity: 1;
  max-height: 500px;
}

/* 文本内容 */
.text-block {
  /* 文本块无额外样式，由 MarkdownRenderer 处理 */
}

/* 工具结果（未合并） */
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
</style>

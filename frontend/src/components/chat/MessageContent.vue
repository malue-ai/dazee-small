<template>
  <div class="message-content">
    <!-- 渲染所有内容块 -->
    <template v-for="(block, index) in contentBlocks" :key="index">
      <!-- 跳过 null/undefined 块 -->
      <template v-if="block">
      <!-- 思考过程 -->
      <div v-if="block.type === 'thinking'" class="thinking-card" :class="{ 'is-streaming': isStreaming }">
        <div class="thinking-header" @click="toggleBlock(index)">
          <div class="thinking-label">
            <span class="thinking-dot" :class="{ 'is-active': isStreaming }"></span>
            <span>{{ isStreaming ? '正在思考...' : '思考过程' }}</span>
          </div>
          <span class="thinking-toggle">{{ isThinkingExpanded(index) ? '收起' : '展开' }}</span>
        </div>
        <div v-show="isThinkingExpanded(index)" class="thinking-body">
          <MarkdownRenderer :content="block.thinking || ''" />
          <span v-if="isStreaming" class="typing-cursor"></span>
        </div>
      </div>

      <!-- 文本内容 -->
      <div v-else-if="block.type === 'text'" class="content-block text-block">
        <MarkdownRenderer :content="block.text" @mermaid-detected="handleMermaidDetected" />
      </div>

      <!-- 工具调用 (合并 Tool Use 和 Tool Result) -->
      <template v-else-if="block.type === 'tool_use' || block.type === 'server_tool_use'">
        <ToolMessage 
          :name="block.name"
          :input="block.input"
          :partial-input="block.partialInput"
          :result="getToolResultContent(block.id)"
          :partial-result="getToolPartialResult(block.id)"
          :status="getToolStatus(block.id)"
          :intermediate-content="getToolIntermediateContent(block.id)"
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
    </template>

    <!-- 如果没有内容块，显示纯文本 -->
    <div v-if="contentBlocks.length === 0 && content" class="content-block text-block">
      <MarkdownRenderer :content="content" @mermaid-detected="handleMermaidDetected" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, watch } from 'vue'
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
  },
  // 是否正在流式输出
  isStreaming: {
    type: Boolean,
    default: false
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

// 用户手动操作过的块（记录用户是否手动展开/收起过）
const userToggledBlocks = reactive({})

// 监听 isStreaming 变化，流式输出时自动展开 thinking，结束后自动折叠
watch(
  () => props.isStreaming,
  (streaming, wasStreaming) => {
    // 流式结束时，自动折叠所有用户没有手动操作过的 thinking 块
    if (wasStreaming && !streaming) {
      contentBlocks.value.forEach((block, index) => {
        if (block.type === 'thinking' && !userToggledBlocks[index]) {
          expandedBlocks[index] = false
        }
      })
    }
  }
)

// 计算属性：判断某个 thinking 块是否应该展开
const isThinkingExpanded = (index) => {
  // 如果用户手动操作过，使用用户的选择
  if (userToggledBlocks[index] !== undefined) {
    return expandedBlocks[index] ?? false
  }
  // 流式输出时自动展开
  if (props.isStreaming) {
    return true
  }
  // 默认折叠
  return expandedBlocks[index] ?? false
}

// 解析内容块
// 注意：使用 getter 函数让 Vue 能够追踪数组元素内部属性的变化
const contentBlocks = computed(() => {
  const content = props.content
  
  // 如果是数组，映射每个元素以建立响应式依赖
  if (Array.isArray(content)) {
    return content.map(block => {
      if (!block) return block
      // 返回新对象，包含所有原始属性（这会让 Vue 追踪每个属性）
      return { ...block }
    })
  }
  
  // 如果是字符串，尝试解析 JSON
  if (typeof content === 'string') {
    // 尝试解析为 JSON
    try {
      const parsed = JSON.parse(content)
      if (Array.isArray(parsed)) {
        return [...parsed]
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

// 切换块的展开/收起（用户手动操作）
function toggleBlock(index) {
  // 记录用户手动操作过
  userToggledBlocks[index] = true
  // 切换展开/收起状态
  const currentState = isThinkingExpanded(index)
  expandedBlocks[index] = !currentState
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

// 获取工具结果内容（完整）
function getToolResultContent(toolId) {
  const status = props.toolStatuses[toolId]
  if (!status || !status.result) return null
  // 只有当不再 pending 时才返回完整结果
  if (status.pending) return null
  return status.result
}

// 获取工具流式结果（部分）
function getToolPartialResult(toolId) {
  // 从 contentBlocks 中查找对应的 tool_result 块
  for (const block of contentBlocks.value) {
    if (block && block.type === 'tool_result' && block.tool_use_id === toolId) {
      return block.content || null
    }
  }
  return null
}

// 获取工具中间内容 (从不完整的 JSON 中提取)
function getToolIntermediateContent(toolId) {
  // 尝试从流式结果中提取
  const partialResult = getToolPartialResult(toolId)
  if (partialResult) {
    // 尝试正则匹配 "preview": "..."
    const previewMatch = partialResult.match(/"preview"\s*:\s*"([^"]+)"/)
    if (previewMatch && previewMatch[1]) {
      return {
        type: 'image',
        data: previewMatch[1]
      }
    }
  }
  
  return null
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
  max-width: 100%;
  overflow-wrap: break-word;
  word-break: break-word;
}

.content-block {
  border-radius: 8px;
}

/* 思考过程 - 简洁风格 */
.thinking-card {
  background: #f8f9fa;
  border-radius: 10px;
  overflow: hidden;
}

.thinking-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s;
}

.thinking-header:hover {
  background: #f1f3f4;
}

.thinking-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #5f6368;
}

.thinking-dot {
  width: 6px;
  height: 6px;
  background: #9aa0a6;
  border-radius: 50%;
  transition: all 0.3s ease;
}

/* 流式输出时的脉冲动画 */
.thinking-dot.is-active {
  background: #4285f4;
  animation: pulse 1.5s infinite ease-in-out;
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.3);
    opacity: 0.7;
  }
}

.thinking-toggle {
  font-size: 12px;
  color: #9aa0a6;
}

.thinking-body {
  padding: 0 14px 12px;
  font-size: 13px;
  color: #5f6368;
  line-height: 1.6;
}

.thinking-body :deep(.markdown-body) {
  font-size: 13px;
  color: #5f6368;
}

.thinking-body :deep(.markdown-body p) {
  margin-bottom: 8px;
}

.thinking-body :deep(.markdown-body pre) {
  background: #f1f3f4;
  border: 1px solid #e8eaed;
}

/* 打字机光标效果 */
.typing-cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  background-color: #4285f4;
  margin-left: 2px;
  vertical-align: text-bottom;
  animation: blink-cursor 0.8s infinite;
}

@keyframes blink-cursor {
  0%, 50% {
    opacity: 1;
  }
  51%, 100% {
    opacity: 0;
  }
}

/* 流式输出时的卡片边框效果 */
.thinking-card.is-streaming {
  border-left: 2px solid #4285f4;
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

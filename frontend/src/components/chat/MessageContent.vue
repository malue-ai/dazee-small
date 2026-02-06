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
          <div class="thinking-toggle">
            <ChevronUp v-if="isThinkingExpanded(index)" class="w-4 h-4" />
            <ChevronDown v-else class="w-4 h-4" />
          </div>
        </div>
        <div v-show="isThinkingExpanded(index)" class="thinking-body">
          <MarkdownRenderer :content="block.thinking || ''" :final="!isStreaming" />
          <span v-if="isStreaming" class="typing-cursor"></span>
        </div>
      </div>

      <!-- 文本内容 -->
      <div v-else-if="block.type === 'text'" class="content-block text-block">
        <MarkdownRenderer :content="block.text" :final="!isStreaming" />
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
            <span class="block-icon">
              <XCircle v-if="block.is_error" class="w-4 h-4 text-destructive" />
              <CheckCircle2 v-else class="w-4 h-4 text-success" />
            </span>
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
          <FileText class="w-6 h-6 text-muted-foreground" />
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
          <span class="block-icon">
            <Package class="w-4 h-4 text-muted-foreground" />
          </span>
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
      <MarkdownRenderer :content="content" :final="!isStreaming" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, watch } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import ToolMessage from './ToolMessage.vue'
import { 
  CheckCircle2, 
  XCircle, 
  FileText, 
  Package, 
  Image as ImageIcon,
  Download,
  ChevronDown,
  ChevronUp
} from 'lucide-vue-next'

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

/* 思考过程 */
.thinking-card {
  background: var(--color-muted);
  border-radius: 12px;
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
  background: rgba(0, 0, 0, 0.03);
}

.thinking-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-muted-foreground);
}

.thinking-dot {
  width: 6px;
  height: 6px;
  background: var(--color-muted-foreground);
  border-radius: 50%;
  transition: all 0.3s ease;
}

.thinking-dot.is-active {
  background: var(--color-primary);
  animation: pulse 1.5s infinite ease-in-out;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.3); opacity: 0.7; }
}

.thinking-toggle {
  font-size: 12px;
  color: var(--color-muted-foreground);
}

.thinking-body {
  padding: 0 14px 12px;
  font-size: 13px;
  color: var(--color-muted-foreground);
  line-height: 1.6;
}

.thinking-body :deep(.markdown-body) {
  font-size: 13px;
  color: var(--color-muted-foreground);
}

.thinking-body :deep(.markdown-body p) {
  margin-bottom: 8px;
}

.thinking-body :deep(.markdown-body pre) {
  background: rgba(0, 0, 0, 0.03);
  border: 1px solid var(--color-border);
}

.typing-cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  background-color: var(--color-primary);
  margin-left: 2px;
  vertical-align: text-bottom;
  animation: blink-cursor 0.8s infinite;
}

@keyframes blink-cursor {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.thinking-card.is-streaming {
  border-left: 2px solid var(--color-primary);
}

/* 工具结果（未合并） */
.tool-result-block {
  background: var(--color-accent);
  border: 1px solid var(--color-primary);
  padding: 12px;
  border-radius: 12px;
}

.tool-result-block.is-error {
  background: rgba(239, 68, 68, 0.05);
  border-color: var(--color-destructive);
}

.tool-output {
  background: var(--color-muted);
  border-radius: 8px;
  padding: 12px;
  margin-top: 8px;
  overflow-x: auto;
}

.tool-output pre {
  margin: 0;
  font-size: 12px;
  font-family: 'SF Mono', Consolas, Monaco, monospace;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--color-foreground);
}

/* 图片 */
.image-block img {
  max-width: 100%;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

/* 文件 */
.file-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--color-muted);
  border: 1px solid var(--color-border);
  border-radius: 12px;
}

.file-name {
  font-weight: 500;
  color: var(--color-foreground);
}

.file-size {
  font-size: 12px;
  color: var(--color-muted-foreground);
}

.download-btn {
  padding: 6px 12px;
  background: var(--color-primary);
  color: white;
  border-radius: 8px;
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
}

.download-btn:hover {
  background: var(--color-primary-hover);
}

/* 未知内容 */
.unknown-block {
  background: var(--color-accent);
  border: 1px solid var(--color-primary);
  padding: 12px;
  border-radius: 12px;
}

.unknown-block pre {
  margin: 0;
  font-size: 11px;
  color: var(--color-accent-foreground);
  overflow-x: auto;
}

/* 通用块头部 */
.block-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.block-title {
  font-weight: 600;
  color: var(--color-foreground);
}

.toggle-btn {
  margin-left: auto;
  padding: 2px 8px;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 11px;
  color: var(--color-muted-foreground);
  cursor: pointer;
}

.toggle-btn:hover {
  background: var(--color-muted);
}
</style>

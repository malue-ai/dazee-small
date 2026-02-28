<template>
  <div class="message-content">
    <!-- 渲染所有内容块 -->
    <template v-for="(block, index) in contentBlocks" :key="index">
      <!-- 跳过 null/undefined 块 -->
      <template v-if="block">
      <!-- 思考过程 -->
      <div v-if="block.type === 'thinking'" class="thinking-block mb-1" :class="{ 'is-streaming': isStreaming }">
        <div class="flex items-center gap-2 py-1 cursor-pointer select-none opacity-70 hover:opacity-100 transition-opacity" @click="toggleBlock(index)">
          <div class="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <span v-if="!isThinkingExpanded(index)" class="w-1.5 h-1.5 rounded-full bg-muted-foreground transition-all" :class="{ 'bg-primary animate-pulse': isStreaming }"></span>
            <ChevronUp v-if="isThinkingExpanded(index)" class="w-3 h-3" />
            <ChevronDown v-else class="w-3 h-3" />
            <span v-if="isStreaming">思考中...</span>
            <span v-else>已思考 {{ formattedDuration || '' }}</span>
          </div>
        </div>
        <div v-show="isThinkingExpanded(index)" class="pl-3 border-l-2 border-muted-foreground/15 ml-1.5 mt-0.5 mb-2 text-[13px] text-muted-foreground leading-relaxed">
          <MarkdownRenderer :content="block.thinking || ''" :final="!isStreaming" />
          <span v-if="isStreaming" class="inline-block w-0.5 h-3 ml-0.5 bg-primary align-middle animate-pulse"></span>
        </div>
      </div>

      <!-- 文本内容 -->
      <div v-else-if="block.type === 'text'" class="content-block text-block">
        <MarkdownRenderer :content="block.text" :final="!isStreaming" />
      </div>

      <!-- 工具调用 -->
      <template v-else-if="block.type === 'tool_use' || block.type === 'server_tool_use'">
        <ToolBlock
          :block="block"
          :tool-statuses="toolStatuses"
          :content-blocks="contentBlocks"
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
            <!-- 多模态 tool_result：content 为 content blocks 数组（如 observe_screen 返回 text + image）-->
            <template v-if="Array.isArray(block.content)">
              <template v-for="(sub, i) in block.content" :key="i">
                <div v-if="sub?.type === 'text'" class="text-block mb-2"><MarkdownRenderer :content="sub.text || ''" :final="true" /></div>
                <div v-else-if="sub?.type === 'image'" class="image-block mt-2">
                  <img :src="getImageSrc(sub)" alt="截图" class="max-w-full rounded-lg border border-border" />
                </div>
              </template>
            </template>
            <pre v-else>{{ formatToolResult(block.content) }}</pre>
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
    <div v-if="contentBlocks.length === 0 && content" class="content-block text-block !mt-0">
      <MarkdownRenderer :content="content" :final="!isStreaming" />
    </div>

    <!-- 云端任务进度卡片 -->
    <CloudProgressCard
      v-if="cloudProgress && cloudProgress.length > 0"
      :cloud-progress="cloudProgress"
    />
  </div>
</template>

<script setup>
import { ref, computed, reactive, watch, onMounted, onUnmounted } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import ToolBlock from './ToolBlock.vue'
import CloudProgressCard from './CloudProgressCard.vue'
import { resolveResourceUrl } from '@/api'
import { 
  CheckCircle2, 
  XCircle, 
  FileText, 
  Package, 
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
  },
  // 云端任务进度数组
  cloudProgress: {
    type: Array,
    default: () => []
  }
})

// 思考时间计时器
const thinkingDuration = ref(0)
const startTime = ref(null)
let timer = null

// 展开/收起状态
const expandedBlocks = reactive({})

// 用户手动操作过的块（记录用户是否手动展开/收起过）
const userToggledBlocks = reactive({})

// 切换块的展开/收起（用户手动操作）
function toggleBlock(index) {
  // 记录用户手动操作过
  userToggledBlocks[index] = true
  // 切换展开/收起状态
  const currentState = isThinkingExpanded(index)
  // 强制更新
  expandedBlocks[index] = !currentState
}

// 格式化时间
const formattedDuration = computed(() => {
  if (thinkingDuration.value < 1) return ''
  return `${thinkingDuration.value.toFixed(1)}s`
})

// 开始计时
function startTimer() {
  if (timer) return
  startTime.value = Date.now()
  timer = setInterval(() => {
    thinkingDuration.value = (Date.now() - startTime.value) / 1000
  }, 100)
}

// 停止计时
function stopTimer() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

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

// 监听流式状态来控制计时器
watch(() => props.isStreaming, (streaming) => {
  // 检查是否有正在生成的 thinking 块
  // 确保 contentBlocks 不为空且有有效值
  const hasThinking = contentBlocks.value && contentBlocks.value.some(b => b && b.type === 'thinking')
  
  if (streaming && hasThinking) {
    startTimer()
  } else {
    stopTimer()
  }
}, { immediate: true })

onUnmounted(() => {
  stopTimer()
})

// 监听 isStreaming 变化，流式输出时自动展开 thinking，结束后自动折叠
watch(
  () => props.isStreaming,
  (streaming, wasStreaming) => {
    // 流式结束时，自动折叠所有用户没有手动操作过的 thinking 块
    if (wasStreaming && !streaming) {
      contentBlocks.value.forEach((block, index) => {
        if (block && block.type === 'thinking' && !userToggledBlocks[index]) {
          expandedBlocks[index] = false
        }
      })
    }
  }
)

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

// 检查是否有配对的 Tool Use
function hasPairedToolUse(toolUseId) {
  if (!toolUseId) return false
  return contentBlocks.value.some(b => b.type === 'tool_use' && b.id === toolUseId)
}

// 获取图片 src（resolveResourceUrl 确保 Tauri 打包后相对路径也能访问后端）
function getImageSrc(block) {
  if (block.source?.type === 'base64') {
    return `data:${block.source.media_type};base64,${block.source.data}`
  }
  if (block.source?.type === 'url') {
    return resolveResourceUrl(block.source.url)
  }
  return resolveResourceUrl(block.url || '')
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
  gap: 2px; /* 极小间距 */
  max-width: 100%;
  overflow-wrap: break-word;
  word-break: break-word;
}

.content-block {
  border-radius: 8px;
}

/* 文本块不需要顶部 margin，因为它已经在 flex gap 中了 */
.text-block {
  margin-top: 0;
}


.tool-result-block {
  background: var(--color-muted);
  border: 1px solid var(--color-border);
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

<template>
  <div 
    class="flex-1 min-h-0 overflow-y-auto overflow-x-hidden scroll-smooth p-6 md:p-8 scrollbar-overlay" 
    ref="containerRef"
    @scroll="handleScroll"
  >
    <!-- 加载更多历史消息 -->
    <div v-if="hasMore || loadingMore" class="flex justify-center py-4">
      <button 
        v-if="hasMore && !loadingMore"
        @click="emit('load-more')"
        class="px-4 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
      >
        加载更早的消息
      </button>
      <div v-if="loadingMore" class="flex items-center gap-2 text-sm text-muted-foreground/50">
        <Loader2 class="w-4 h-4 animate-spin" />
        加载中...
      </div>
    </div>

    <!-- 欢迎页 -->
    <div v-if="messages.length === 0 && !loadingMore" class="h-full flex flex-col items-center justify-center text-center -mt-10">
      <!-- Agent 模式：显示项目图标、名称、描述 -->
      <template v-if="agentInfo">
        <div class="w-20 h-20 bg-card rounded-3xl shadow-lg border border-border flex items-center justify-center mb-8 transform hover:scale-105 transition-transform duration-300">
          <span class="text-3xl font-bold text-foreground">{{ agentIcon }}</span>
        </div>
        <h1 class="text-3xl font-bold mb-4 text-foreground">{{ agentInfo.name }}</h1>
        <p class="text-muted-foreground mb-10 max-w-md">{{ agentInfo.description || '开始和这个项目对话吧' }}</p>
      </template>

      <!-- 默认模式：通用欢迎语 -->
      <template v-else>
        <div class="w-20 h-20 bg-card rounded-3xl shadow-lg border border-border flex items-center justify-center mb-8 transform hover:scale-105 transition-transform duration-300">
          <Sparkles class="w-10 h-10 text-primary" />
        </div>
        <h1 class="text-3xl font-bold mb-4 text-foreground">有什么我可以帮你的？</h1>
        <p class="text-muted-foreground mb-10 max-w-md">我是你的 AI 助手，可以协助你完成编码、写作、分析等各种任务。</p>
      </template>
      
    </div>

    <!-- 消息流 -->
    <div v-else class="max-w-4xl mx-auto flex flex-col gap-8 pb-4 overflow-hidden">
      <div
        v-for="message in messages"
        :key="message.id"
        class="flex gap-5 group"
        :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
      >
        <!-- 助手头像 -->
        <div 
          class="w-10 h-10 flex items-center justify-center flex-shrink-0 mt-1"
          :class="message.role === 'assistant' ? '' : 'order-2 hidden'"
        >
          <Bot class="w-6 h-6 text-muted-foreground" />
        </div>
        
        <div 
          class="flex-1 min-w-0 max-w-[80%] overflow-hidden"
          :class="message.role === 'user' ? 'order-1 flex justify-end' : ''"
        >
          <!-- 用户消息 -->
          <div v-if="message.role === 'user'" class="flex flex-col items-end gap-2">
            <!-- 附件 -->
            <div v-if="message.files && message.files.length > 0" class="flex flex-col gap-2 mb-1">
              <div 
                v-for="(file, idx) in message.files" 
                :key="idx" 
                class="flex items-center gap-3 p-3 bg-white rounded-xl border border-border cursor-pointer hover:bg-muted transition-colors shadow-sm"
                @click="emit('file-preview', file)"
              >
                <FileText class="w-5 h-5 text-muted-foreground/50" />
                <div class="flex flex-col text-left">
                  <span class="text-sm font-medium text-foreground truncate max-w-[12rem]">{{ file.file_name }}</span>
                  <span class="text-xs text-muted-foreground">{{ getFileTypeLabel(file.file_type, file.file_name) }}</span>
                </div>
              </div>
            </div>
            <!-- 文字内容 + 悬浮操作栏 -->
            <div v-if="message.content" class="user-message-wrapper">
              <div class="bg-accent text-foreground px-5 py-3 rounded-2xl rounded-tr-sm text-sm leading-relaxed break-words max-w-full">
                <MarkdownRenderer :content="parseUserMessage(message.content)" />
              </div>
              <!-- 悬浮操作栏：发送时间 + 复制（消息下方右对齐） -->
              <div class="user-message-actions">
                <span class="text-[11px] text-muted-foreground/50 whitespace-nowrap">{{ formatMessageTime(message.timestamp) }}</span>
                <button
                  class="p-1 rounded-md transition-colors"
                  :class="copiedMessageId === message.id 
                    ? 'text-green-500' 
                    : 'text-muted-foreground/40 hover:text-foreground hover:bg-muted'"
                  :title="copiedMessageId === message.id ? '已复制' : '复制消息'"
                  @click="copyMessage(message)"
                >
                  <Check v-if="copiedMessageId === message.id" class="w-3.5 h-3.5" />
                  <Copy v-else class="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>
          
          <!-- 助手消息 -->
          <div v-else class="flex flex-col gap-3 overflow-hidden">
            <div class="text-sm leading-relaxed text-foreground px-1 overflow-x-auto">
              <!-- 有内容块时使用 MessageContent -->
              <MessageContent 
                v-if="message.contentBlocks && message.contentBlocks.length > 0"
                :content="message.contentBlocks"
                :tool-statuses="message.toolStatuses || {}"
                :is-streaming="isMessageStreaming(message)"
              />
              <!-- 无内容块时 -->
              <template v-else>
                <!-- 有思考内容 -->
                <div v-if="message.thinking" class="thinking-inline" :class="{ 'is-streaming': isMessageStreaming(message) }">
                  <div class="thinking-inline-header" @click="toggleThinking(String(message.id))">
                    <div class="thinking-inline-left">
                      <span v-if="!isThinkingExpandedInline(message)" class="thinking-inline-dot" :class="{ 'is-active': isMessageStreaming(message) }"></span>
                      <span class="toggle-icon">
                        <svg v-if="isThinkingExpandedInline(message)" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m18 15-6-6-6 6"/></svg>
                        <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
                      </span>
                      <span v-if="isMessageStreaming(message)">思考中...</span>
                      <span v-else>已思考 {{ formatDuration(String(message.id)) }}</span>
                    </div>
                  </div>
                  <div v-show="isThinkingExpandedInline(message)" class="thinking-inline-body">
                    <MarkdownRenderer :content="message.thinking || ''" />
                    <span v-if="isMessageStreaming(message)" class="typing-cursor"></span>
                  </div>
                </div>
                <!-- 有文本内容 -->
                <MarkdownRenderer 
                  v-if="message.content"
                  :content="message.content"
                  :final="!isMessageStreaming(message)"
                />
                <!-- 空消息且正在加载（仅最后一条消息显示） -->
                <div v-else-if="loading && isLastMessage(message)" class="flex items-center gap-1.5 py-2 text-muted-foreground/50">
                  <span class="w-2 h-2 bg-primary rounded-full animate-bounce" style="animation-delay: 0ms"></span>
                  <span class="w-2 h-2 bg-primary rounded-full animate-bounce" style="animation-delay: 150ms"></span>
                  <span class="w-2 h-2 bg-primary rounded-full animate-bounce" style="animation-delay: 300ms"></span>
                </div>
              </template>
            </div>

            <!-- 推荐问题 -->
            <div v-if="message.recommendedQuestions?.length" class="flex flex-wrap gap-2 ml-1">
              <button 
                v-for="(q, idx) in message.recommendedQuestions" 
                :key="idx" 
                class="px-4 py-2 bg-white border border-border rounded-full text-xs text-muted-foreground hover:text-foreground hover:bg-muted hover:border-muted-foreground/30 transition-all shadow-sm"
                @click="emit('suggestion-click', q)"
              >
                {{ q }}
              </button>
            </div>

            <!-- Playbook 策略建议（内联卡片） -->
            <PlaybookSuggestionCard
              v-if="message.playbookSuggestion"
              :suggestion="message.playbookSuggestion"
              class="ml-1 max-w-sm"
              @accept="emit('playbook-accept', message)"
              @dismiss="emit('playbook-dismiss', message)"
            />
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import type { UIMessage, AttachedFile, AgentSummary } from '@/types'
import { getFileTypeLabel as getLabel } from '@/utils'
import MarkdownRenderer from './MarkdownRenderer.vue'
import MessageContent from './MessageContent.vue'
import PlaybookSuggestionCard from './PlaybookSuggestionCard.vue'
import { Sparkles, Bot, FileText, Loader2, Copy, Check } from 'lucide-vue-next'

// ==================== Props ====================

interface Props {
  /** 消息列表 */
  messages: UIMessage[]
  /** 是否正在加载 */
  loading?: boolean
  /** 是否正在生成 */
  generating?: boolean
  /** 是否正在加载更多历史消息 */
  loadingMore?: boolean
  /** 是否有更多历史消息 */
  hasMore?: boolean
  /** Agent（项目）信息，用于在欢迎页显示项目图标/名称/描述 */
  agentInfo?: AgentSummary | null
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  generating: false,
  loadingMore: false,
  hasMore: false,
  agentInfo: null
})

/** Agent 图标（取名称首字符） */
const agentIcon = computed(() => {
  if (!props.agentInfo?.name) return 'A'
  return props.agentInfo.name.charAt(0).toUpperCase()
})

// ==================== Emits ====================

const emit = defineEmits<{
  /** 点击建议 */
  (e: 'suggestion-click', text: string): void
  /** 文件预览 */
  (e: 'file-preview', file: AttachedFile): void
  /** 加载更多历史消息 */
  (e: 'load-more'): void
  /** Playbook 策略建议：接受 */
  (e: 'playbook-accept', message: UIMessage): void
  /** Playbook 策略建议：忽略 */
  (e: 'playbook-dismiss', message: UIMessage): void
}>()

// ==================== State ====================

/** 已复制消息的 ID（用于显示"已复制"反馈） */
const copiedMessageId = ref<string | number | null>(null)

/** 复制用户消息内容到剪贴板 */
async function copyMessage(message: UIMessage) {
  const text = parseUserMessage(message.content)
  try {
    await navigator.clipboard.writeText(text)
    copiedMessageId.value = message.id
    setTimeout(() => {
      copiedMessageId.value = null
    }, 1500)
  } catch {
    // fallback
    const ta = document.createElement('textarea')
    ta.value = text
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    copiedMessageId.value = message.id
    setTimeout(() => { copiedMessageId.value = null }, 1500)
  }
}

/** 格式化消息发送时间 */
function formatMessageTime(date: Date): string {
  if (!date) return ''
  const d = new Date(date)
  const now = new Date()
  const hours = d.getHours().toString().padStart(2, '0')
  const minutes = d.getMinutes().toString().padStart(2, '0')
  
  // 如果是今天，只显示时分
  if (d.toDateString() === now.toDateString()) {
    return `${hours}:${minutes}`
  }
  // 否则显示月/日 时:分
  const month = (d.getMonth() + 1).toString().padStart(2, '0')
  const day = d.getDate().toString().padStart(2, '0')
  return `${month}/${day} ${hours}:${minutes}`
}

/** 用户是否手动滚动过 */
const userHasScrolled = ref(false)
/** 是否正在程序化滚动（防止 handleScroll 误判） */
let isProgrammaticScroll = false

// 思考计时器
const thinkingDurations = ref<Record<string, number>>({})
const thinkingTimers = ref<Record<string, any>>({})

/** 开始计时 */
function startThinkingTimer(messageId: string) {
  if (thinkingTimers.value[messageId]) return
  
  const startTime = Date.now()
  thinkingTimers.value[messageId] = setInterval(() => {
    thinkingDurations.value[messageId] = (Date.now() - startTime) / 1000
  }, 100)
}

/** 停止计时 */
function stopThinkingTimer(messageId: string) {
  if (thinkingTimers.value[messageId]) {
    clearInterval(thinkingTimers.value[messageId])
    delete thinkingTimers.value[messageId]
  }
}

/** 格式化持续时间 */
function formatDuration(id: string): string {
  const duration = thinkingDurations.value[id]
  if (!duration || duration < 1) return ''
  return `${duration.toFixed(1)}s`
}

/** 监听流式状态来控制计时器 */
watch(() => props.generating, (generating) => {
  const lastMsg = props.messages[props.messages.length - 1]
  if (!lastMsg || lastMsg.role !== 'assistant') return
  
  const id = String(lastMsg.id)
  if (generating && lastMsg.thinking) {
    startThinkingTimer(id)
  } else {
    stopThinkingTimer(id)
  }
}, { immediate: true })

/** 容器引用 */
const containerRef = ref<HTMLElement | null>(null)

/** 思考过程展开状态 */
const expandedThinking = ref<Record<string, boolean>>({})

/** 用户手动操作过的思考块 */
const userToggledThinking = ref<Record<string, boolean>>({})

/** 切换思考过程（用户手动操作） */
function toggleThinking(id: string): void {
  userToggledThinking.value[id] = true
  const currentState = isThinkingExpandedInline({ id } as UIMessage)
  expandedThinking.value[id] = !currentState
}

/** 判断内联 thinking 是否展开（支持流式自动展开） */
function isThinkingExpandedInline(message: UIMessage): boolean {
  const id = String(message.id)
  // 如果用户手动操作过，使用用户的选择
  if (userToggledThinking.value[id] !== undefined) {
    return expandedThinking.value[id] ?? false
  }
  // 流式输出时自动展开
  if (isMessageStreaming(message)) {
    return true
  }
  // 默认折叠
  return expandedThinking.value[id] ?? false
}

// ==================== Methods ====================

/**
 * 解析用户消息内容（处理 JSON 格式）
 */
function parseUserMessage(content: string): string {
  if (!content) return ''
  try {
    // 尝试判断是否为 JSON 数组格式
    if (content.trim().startsWith('[') && content.trim().endsWith(']')) {
      const parsed = JSON.parse(content)
      if (Array.isArray(parsed)) {
        // 提取所有 text 类型的块
        const textParts = parsed
          .filter((block: any) => block && block.type === 'text' && typeof block.text === 'string')
          .map((block: any) => block.text)
        
        // 如果提取到了文本，则返回连接后的文本
        if (textParts.length > 0) {
          return textParts.join('\n\n')
        }
      }
    }
  } catch (e) {
    // 解析失败，说明不是 JSON 或格式不对，按原始文本处理
  }
  return content
}

/**
 * 获取文件类型标签
 */
function getFileTypeLabel(mimeType: string, fileName?: string): string {
  return getLabel(mimeType, fileName)
}

/**
 * 判断是否是最后一条消息
 */
function isLastMessage(message: UIMessage): boolean {
  return props.messages[props.messages.length - 1]?.id === message.id
}

/**
 * 判断消息是否正在流式输出
 * 条件：是最后一条助手消息 + 正在生成中
 */
function isMessageStreaming(message: UIMessage): boolean {
  return message.role === 'assistant' && isLastMessage(message) && (props.loading || props.generating)
}

/**
 * 滚动到底部
 * @param force - 强制滚动（忽略用户手动滚动状态）
 */
function scrollToBottom(force = false): void {
  // 如果用户手动向上滚动了，且不是强制滚动，则不自动滚动
  if (!force && userHasScrolled.value) return

  if (!containerRef.value) return
  
  // 标记为程序化滚动，防止 handleScroll 误判为用户手动滚动
  isProgrammaticScroll = true
  nextTick(() => {
    if (containerRef.value) {
      containerRef.value.scrollTop = containerRef.value.scrollHeight
    }
    // 延迟重置标记，确保 scroll 事件处理完毕
    requestAnimationFrame(() => {
      isProgrammaticScroll = false
    })
  })
}

/**
 * 处理滚动事件（滚动到顶部时加载更多）
 */
function handleScroll(): void {
  if (!containerRef.value) return

  const { scrollTop, scrollHeight, clientHeight } = containerRef.value
  
  // 判断是否在底部（允许 100px 的误差）
  const isAtBottom = scrollHeight - scrollTop - clientHeight < 100

  if (isAtBottom) {
    // 如果在底部，重置滚动状态
    userHasScrolled.value = false
  } else if (!isProgrammaticScroll && scrollTop < scrollHeight - clientHeight - 100) {
    // 如果不在底部，且不是程序化滚动触发的事件，标记为已手动滚动
    // 注意：加载更多消息时也会触发 scroll 事件，需要通过 loadingMore 排除
    if (!props.loadingMore) {
      userHasScrolled.value = true
    }
  }
  
  if (props.loadingMore || !props.hasMore) return
  
  // 当滚动到距离顶部 100px 内时触发加载
  if (scrollTop < 100) {
    emit('load-more')
  }
}

/**
 * 保持滚动位置（加载更多后使用）
 * @param previousHeight - 加载前的滚动高度
 */
function maintainScrollPosition(previousHeight: number): void {
  if (!containerRef.value) return
  
  nextTick(() => {
    if (containerRef.value) {
      const newHeight = containerRef.value.scrollHeight
      containerRef.value.scrollTop = newHeight - previousHeight
    }
  })
}

/**
 * 获取当前滚动高度
 */
function getScrollHeight(): number {
  return containerRef.value?.scrollHeight || 0
}

// ==================== Watchers ====================

// 监听消息变化，自动滚动
watch(
  () => props.messages.length,
  (newLen, oldLen) => {
    if (newLen <= (oldLen ?? 0)) return // 非新增消息（如清空），不处理

    // 新消息增加时，强制滚动到底部
    // 包括：用户发送消息、assistant 回复消息添加
    // 加载更多历史消息时 loadingMore 为 true，不强制滚动
    if (props.loadingMore) {
      scrollToBottom(false)
    } else {
      // 重置手动滚动标记，确保后续流式内容也能自动滚动
      userHasScrolled.value = false
      scrollToBottom(true)
    }
  }
)

// 监听最后一条消息的文本内容变化（流式文字输出）
watch(
  () => props.messages[props.messages.length - 1]?.content,
  () => {
    scrollToBottom()
  },
  { deep: true }
)

// 监听最后一条消息的内容块数量变化（工具卡片新增）
watch(
  () => props.messages[props.messages.length - 1]?.contentBlocks?.length,
  (newLen, oldLen) => {
    if (newLen && newLen > (oldLen ?? 0)) {
      scrollToBottom()
    }
  }
)

// 监听最后一条消息的工具状态变化（工具执行完成/结果返回）
watch(
  () => {
    const last = props.messages[props.messages.length - 1]
    if (!last?.toolStatuses) return 0
    return Object.keys(last.toolStatuses).length
  },
  () => {
    scrollToBottom()
  }
)

// ==================== Expose ====================

defineExpose({
  scrollToBottom: (force = false) => scrollToBottom(force),
  maintainScrollPosition,
  getScrollHeight
})
</script>

<style scoped>
/* 消息内容中的 Markdown 样式修正 */
:deep(.prose) {
  max-width: none;
  overflow-wrap: break-word;
  word-break: break-word;
}
:deep(.prose pre) {
  background-color: var(--color-muted);
  border: 1px solid var(--color-border);
  border-radius: 0.5rem;
  overflow-x: auto;
  max-width: 100%;
}
:deep(.prose code) {
  word-break: break-all;
}

/* 内联思考过程 */
.thinking-inline {
  margin-bottom: 2px; /* 极小间距 */
  /* 移除背景和边框 */
  background: transparent;
  border-radius: 0;
  overflow: hidden;
}

.thinking-inline-header {
  display: flex;
  align-items: center;
  /* 减小内边距 */
  padding: 4px 0;
  cursor: pointer;
  opacity: 0.7;
  transition: opacity 0.2s;
  user-select: none;
}

.thinking-inline-header:hover {
  opacity: 1;
  background: transparent;
}

.thinking-inline-left {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px; /* 更小的字体 */
  font-weight: 500;
  color: var(--color-muted-foreground);
}

.toggle-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
}

.thinking-inline-dot {
  width: 5px;
  height: 5px;
  background: var(--color-muted-foreground);
  border-radius: 50%;
  margin-right: 2px;
}

.thinking-inline-dot.is-active {
  background: var(--color-primary);
  animation: pulse 1.5s infinite ease-in-out;
}

/* 移除之前的 toggle 文本样式 */
.thinking-inline-toggle {
  display: none; 
}

.thinking-inline-body {
  /* 左侧边框缩进 */
  margin-left: 6px;
  padding-left: 10px;
  border-left: 2px solid var(--color-border);
  font-size: 12px;
  color: var(--color-muted-foreground);
  opacity: 0.7; /* 降低不透明度，匹配头部视觉 */
  line-height: 1.6;
}

/* 覆盖 Markdown 样式，使其更紧凑 */
.thinking-inline-body :deep(.prose) {
  font-size: 12px;
  line-height: 1.5;
}
.thinking-inline-body :deep(.prose p) {
  margin-bottom: 0.5em;
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

.thinking-inline.is-streaming {
  /* 移除左侧高亮边框 */
  border-left: none;
}

/* 用户消息悬浮操作栏 */
.user-message-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 2px;
  padding-right: 4px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease;
  height: 22px;
}

.user-message-wrapper:hover .user-message-actions {
  opacity: 1;
  pointer-events: auto;
}
</style>

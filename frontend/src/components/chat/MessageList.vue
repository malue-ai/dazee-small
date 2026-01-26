<template>
  <div class="flex-1 overflow-y-auto overflow-x-hidden scroll-smooth p-6 md:p-8 scrollbar-thin" ref="containerRef">
    <!-- 欢迎页 -->
    <div v-if="messages.length === 0" class="h-full flex flex-col items-center justify-center text-center -mt-10">
      <div class="w-20 h-20 bg-white rounded-3xl shadow-lg border border-gray-100 flex items-center justify-center mb-8 transform hover:scale-105 transition-transform duration-300">
        <Sparkles class="w-10 h-10 text-blue-500" />
      </div>
      <h1 class="text-3xl font-bold mb-4 text-gray-900">有什么我可以帮你的？</h1>
      <p class="text-gray-500 mb-10 max-w-md">我是你的 AI 助手，可以协助你完成编码、写作、分析等各种任务。</p>
      
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 w-full max-w-3xl px-4">
        <div 
          v-for="(suggestion, index) in suggestions"
          :key="index"
          class="p-5 rounded-2xl bg-white border border-gray-200 hover:border-blue-300 hover:shadow-lg cursor-pointer transition-all duration-300 group" 
          @click="emit('suggestion-click', suggestion.text)"
        >
          <div class="w-10 h-10 rounded-xl bg-gray-50 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
            <component :is="suggestion.icon" class="w-5 h-5 text-gray-600" />
          </div>
          <h3 class="font-semibold text-gray-800 mb-1">{{ suggestion.title }}</h3>
          <p class="text-xs text-gray-400">{{ suggestion.description }}</p>
        </div>
      </div>
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
          <Bot class="w-6 h-6 text-gray-600" />
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
                class="flex items-center gap-3 p-3 bg-white rounded-xl border border-gray-200 cursor-pointer hover:bg-gray-50 transition-colors shadow-sm"
                @click="emit('file-preview', file)"
              >
                <FileText class="w-5 h-5 text-gray-400" />
                <div class="flex flex-col text-left">
                  <span class="text-sm font-medium text-gray-800 truncate max-w-[12rem]">{{ file.file_name }}</span>
                  <span class="text-xs text-gray-500">{{ getFileTypeLabel(file.file_type) }}</span>
                </div>
              </div>
            </div>
            <!-- 文字内容 -->
            <div v-if="message.content" class="bg-gray-100 text-gray-900 px-5 py-3 rounded-2xl rounded-tr-sm text-sm leading-relaxed break-words max-w-full">
              {{ message.content }}
            </div>
          </div>
          
          <!-- 助手消息 -->
          <div v-else class="flex flex-col gap-3 overflow-hidden">
            <div class="text-sm leading-relaxed text-gray-800 px-1 overflow-x-auto">
              <!-- 有内容块时使用 MessageContent -->
              <MessageContent 
                v-if="message.contentBlocks && message.contentBlocks.length > 0"
                :content="message.contentBlocks"
                :tool-statuses="message.toolStatuses || {}"
                @mermaid-detected="(charts: string[]) => emit('mermaid-detected', charts)"
              />
              <!-- 无内容块时 -->
              <template v-else>
                <!-- 有思考内容 -->
                <div v-if="message.thinking" class="thinking-inline">
                  <div class="thinking-inline-header" @click="toggleThinking(String(message.id))">
                    <div class="thinking-inline-left">
                      <span class="thinking-inline-dot"></span>
                      <span>思考过程</span>
                    </div>
                    <span class="thinking-inline-toggle">{{ expandedThinking[message.id] ? '收起' : '展开' }}</span>
                  </div>
                  <div v-show="expandedThinking[message.id]" class="thinking-inline-body">
                    {{ message.thinking }}
                  </div>
                </div>
                <!-- 有文本内容 -->
                <MarkdownRenderer 
                  v-if="message.content"
                  :content="message.content" 
                  @mermaid-detected="(charts: string[]) => emit('mermaid-detected', charts)" 
                />
                <!-- 空消息且正在加载（仅最后一条消息显示） -->
                <div v-else-if="loading && isLastMessage(message)" class="flex items-center gap-1.5 py-2 text-gray-400">
                  <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0ms"></span>
                  <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 150ms"></span>
                  <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 300ms"></span>
                </div>
              </template>
            </div>

            <!-- 推荐问题 -->
            <div v-if="message.recommendedQuestions?.length" class="flex flex-wrap gap-2 ml-1">
              <button 
                v-for="(q, idx) in message.recommendedQuestions" 
                :key="idx" 
                class="px-4 py-2 bg-white border border-gray-200 rounded-full text-xs text-gray-600 hover:text-gray-900 hover:bg-gray-50 hover:border-gray-300 transition-all shadow-sm"
                @click="emit('suggestion-click', q)"
              >
                {{ q }}
              </button>
            </div>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import type { UIMessage, AttachedFile } from '@/types'
import { getFileTypeLabel as getLabel } from '@/utils'
import MarkdownRenderer from './MarkdownRenderer.vue'
import MessageContent from './MessageContent.vue'
import { Sparkles, Bot, FileText, Gamepad2, BarChart3, Search } from 'lucide-vue-next'

// ==================== Props ====================

interface Props {
  /** 消息列表 */
  messages: UIMessage[]
  /** 是否正在加载 */
  loading?: boolean
  /** 是否正在生成 */
  generating?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  generating: false
})

// ==================== Emits ====================

const emit = defineEmits<{
  /** 点击建议 */
  (e: 'suggestion-click', text: string): void
  /** 文件预览 */
  (e: 'file-preview', file: AttachedFile): void
  /** 检测到 Mermaid 图表 */
  (e: 'mermaid-detected', charts: string[]): void
}>()

// ==================== State ====================

/** 容器引用 */
const containerRef = ref<HTMLElement | null>(null)

/** 思考过程展开状态 */
const expandedThinking = ref<Record<string, boolean>>({})

/** 切换思考过程 */
function toggleThinking(id: string): void {
  expandedThinking.value[id] = !expandedThinking.value[id]
}

/** 建议列表 */
const suggestions = [
  {
    icon: Gamepad2,
    title: '生成贪吃蛇游戏',
    description: '使用 Python 或 JavaScript',
    text: '帮我生成一个贪吃蛇游戏'
  },
  {
    icon: BarChart3,
    title: '分析项目依赖',
    description: '检查版本冲突和安全问题',
    text: '分析一下 requirements.txt'
  },
  {
    icon: Search,
    title: '搜索 RAG 论文',
    description: '获取最新的研究进展',
    text: '查询关于 RAG 的最新论文'
  }
]

// ==================== Methods ====================

/**
 * 获取文件类型标签
 */
function getFileTypeLabel(mimeType: string): string {
  return getLabel(mimeType)
}

/**
 * 判断是否是最后一条消息
 */
function isLastMessage(message: UIMessage): boolean {
  return props.messages[props.messages.length - 1]?.id === message.id
}

/**
 * 滚动到底部
 */
function scrollToBottom(): void {
  if (!containerRef.value) return
  
  nextTick(() => {
    if (containerRef.value) {
      containerRef.value.scrollTop = containerRef.value.scrollHeight
    }
  })
}

// ==================== Watchers ====================

// 监听消息变化，自动滚动
watch(
  () => props.messages.length,
  () => {
    scrollToBottom()
  }
)

// 监听最后一条消息的内容变化
watch(
  () => props.messages[props.messages.length - 1]?.content,
  () => {
    scrollToBottom()
  },
  { deep: true }
)

// ==================== Expose ====================

defineExpose({
  scrollToBottom
})
</script>

<style scoped>
/* 滚动条美化 - 默认透明，hover 时显示 */
.scrollbar-thin::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-thin::-webkit-scrollbar-thumb {
  background-color: transparent;
  border-radius: 3px;
}
.scrollbar-thin:hover::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.3);
}
.scrollbar-thin::-webkit-scrollbar-thumb:hover {
  background-color: rgba(156, 163, 175, 0.5);
}

/* Loading Dots 动画 */
.typing-dots span {
  animation: blink 1.4s infinite both;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes blink {
  0% { opacity: 0.2; }
  20% { opacity: 1; }
  100% { opacity: 0.2; }
}

/* 消息内容中的 Markdown 样式修正 */
:deep(.prose) {
  max-width: none;
  overflow-wrap: break-word;
  word-break: break-word;
}
:deep(.prose pre) {
  background-color: #f3f4f6;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  overflow-x: auto;
  max-width: 100%;
}
:deep(.prose code) {
  word-break: break-all;
}

/* 内联思考过程 - 简洁风格 */
.thinking-inline {
  margin-bottom: 12px;
  background: #f8f9fa;
  border-radius: 10px;
  overflow: hidden;
}

.thinking-inline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s;
}

.thinking-inline-header:hover {
  background: #f1f3f4;
}

.thinking-inline-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #5f6368;
}

.thinking-inline-dot {
  width: 6px;
  height: 6px;
  background: #9aa0a6;
  border-radius: 50%;
}

.thinking-inline-toggle {
  font-size: 12px;
  color: #9aa0a6;
}

.thinking-inline-body {
  padding: 0 14px 12px;
  font-size: 13px;
  color: #5f6368;
  line-height: 1.6;
  white-space: pre-wrap;
}
</style>

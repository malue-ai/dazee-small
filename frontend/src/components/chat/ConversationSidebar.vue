<template>
  <div 
    class="relative z-10 flex flex-col transition-all duration-300 ease-in-out flex-shrink-0 glass-sidebar"
    :class="collapsed ? 'w-[70px]' : 'w-[260px]'"
  >
    <!-- 头部 -->
    <div class="h-14 flex items-center justify-between px-4 pt-2">
      <div class="flex items-center gap-2 font-semibold text-foreground" v-if="!collapsed">
        <Sparkles class="w-5 h-5 text-primary fill-primary/20" />
        <span class="tracking-tight">ZenFlux</span>
      </div>
      <button 
        @click="emit('toggle-collapse')" 
        class="p-1.5 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
      >
        <PanelLeftClose v-if="!collapsed" class="w-4 h-4" />
        <PanelLeftOpen v-else class="w-4 h-4" />
      </button>
    </div>

    <!-- 内容区（展开时显示） -->
    <div v-show="!collapsed" class="flex-1 flex flex-col px-3 py-2 overflow-y-auto scrollbar-thin gap-6">
      <!-- 顶部操作 / 搜索框 -->
      <div class="flex flex-col gap-1">
        <!-- 搜索模式 -->
        <div v-if="isSearching" class="flex flex-col gap-2">
          <div class="relative">
            <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
            <input
              ref="searchInputRef"
              v-model="searchQuery"
              type="text"
              placeholder="搜索对话..."
              class="w-full pl-8 pr-8 py-2 text-sm bg-muted border border-border rounded-lg focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40 text-foreground placeholder:text-muted-foreground/60"
              @keydown.escape="closeSearch"
            />
            <button
              v-if="searchQuery"
              @click="searchQuery = ''"
              class="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-muted-foreground hover:text-foreground rounded transition-colors"
            >
              <X class="w-3.5 h-3.5" />
            </button>
            <button
              v-else
              @click="closeSearch"
              class="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-muted-foreground hover:text-foreground rounded transition-colors"
            >
              <X class="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <!-- 正常模式 -->
        <template v-else>
          <button 
            @click="emit('create')" 
            class="w-full flex items-center gap-3 px-3 py-2 text-muted-foreground hover:bg-muted hover:text-foreground rounded-lg transition-colors group"
          >
            <SquarePen class="w-4 h-4 text-muted-foreground group-hover:text-foreground" />
            <span class="text-sm font-medium">新对话</span>
          </button>
          <button 
            @click="openSearch"
            class="w-full flex items-center gap-3 px-3 py-2 text-muted-foreground hover:bg-muted hover:text-foreground rounded-lg transition-colors group"
          >
            <Search class="w-4 h-4 text-muted-foreground group-hover:text-foreground" />
            <span class="text-sm font-medium">搜索</span>
          </button>
        </template>
      </div>

      <!-- 库 -->
      <div v-if="!isSearching" class="flex flex-col gap-1">
        <div class="px-3 text-xs font-medium text-muted-foreground/60 mb-1">项目</div>
        <button 
          @click="emit('navigate', '/knowledge')" 
          class="w-full flex items-center gap-3 px-3 py-2 text-muted-foreground hover:bg-muted hover:text-foreground rounded-lg transition-colors group"
        >
          <BookOpen class="w-4 h-4 text-muted-foreground group-hover:text-foreground" />
          <span class="text-sm font-medium">知识库</span>
        </button>
        <button 
          @click="emit('navigate', '/skills')" 
          class="w-full flex items-center gap-3 px-3 py-2 text-muted-foreground hover:bg-muted hover:text-foreground rounded-lg transition-colors group"
        >
          <Puzzle class="w-4 h-4 text-muted-foreground group-hover:text-foreground" />
          <span class="text-sm font-medium">技能</span>
        </button>
        <button 
          @click="emit('navigate', '/documentation')" 
          class="w-full flex items-center gap-3 px-3 py-2 text-muted-foreground hover:bg-muted hover:text-foreground rounded-lg transition-colors group"
        >
          <FileText class="w-4 h-4 text-muted-foreground group-hover:text-foreground" />
          <span class="text-sm font-medium">文档</span>
        </button>
        <button 
          @click="emit('navigate', '/realtime')" 
          class="w-full flex items-center gap-3 px-3 py-2 text-muted-foreground hover:bg-muted hover:text-foreground rounded-lg transition-colors group"
        >
          <Headphones class="w-4 h-4 text-muted-foreground group-hover:text-foreground" />
          <span class="text-sm font-medium">实时语音</span>
        </button>
      </div>

      <!-- 搜索结果 -->
      <div v-if="isSearching" class="flex flex-col gap-1 flex-1 min-h-0">
        <div class="px-3 flex items-center justify-between mb-1">
          <span class="text-xs font-medium text-muted-foreground/60">
            {{ searchQuery ? `搜索结果（${searchResults.length}）` : '输入关键词搜索对话' }}
          </span>
        </div>

        <!-- 搜索中 -->
        <div v-if="searchLoading" class="px-3 py-4 text-xs text-muted-foreground/60 flex flex-col items-center gap-2">
          <Loader2 class="w-4 h-4 animate-spin" />
          <span>搜索中...</span>
        </div>

        <!-- 无结果 -->
        <div v-else-if="searchQuery && searchResults.length === 0" class="px-3 py-4 text-xs text-muted-foreground/60 flex flex-col items-center gap-2">
          <SearchX class="w-8 h-8 opacity-50" />
          <span>未找到匹配的对话</span>
        </div>

        <!-- 搜索结果列表 -->
        <div v-else-if="searchResults.length > 0" class="flex flex-col gap-0.5 overflow-y-auto scrollbar-thin -mx-2 px-2 pb-4">
          <div
            v-for="item in searchResults"
            :key="item.conversation.id"
            class="group relative flex flex-col gap-0.5 px-3 py-2 rounded-lg cursor-pointer transition-colors"
            :class="item.conversation.id === currentId ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'"
            @click="selectSearchResult(item.conversation.id)"
          >
            <!-- 标题行 -->
            <div class="flex items-center gap-2">
              <MessageSquare class="w-3.5 h-3.5 flex-shrink-0 text-muted-foreground/50" :class="{ 'text-accent-foreground': item.conversation.id === currentId }" />
              <span class="truncate text-sm font-medium">{{ item.conversation.title || '未命名对话' }}</span>
            </div>
            <!-- 匹配片段（内容匹配时显示） -->
            <div v-if="item.snippet" class="pl-5.5 text-xs text-muted-foreground/70 truncate">
              {{ item.snippet }}
            </div>
          </div>
        </div>

        <!-- 空状态（未输入关键词） -->
        <div v-else class="px-3 py-6 text-xs text-muted-foreground/40 flex flex-col items-center gap-2">
          <Search class="w-6 h-6 opacity-40" />
          <span>搜索对话标题和消息内容</span>
        </div>
      </div>

      <!-- 对话列表（非搜索状态） -->
      <div v-if="!isSearching" class="flex flex-col gap-1 flex-1 min-h-0">
        <div class="px-3 flex items-center justify-between group cursor-pointer mb-1">
          <span class="text-xs font-medium text-muted-foreground/60">对话记录</span>
        </div>
        
        <!-- 加载中 -->
        <div v-if="loading" class="px-3 py-4 text-xs text-muted-foreground/60 flex flex-col items-center gap-2">
          <Loader2 class="w-4 h-4 animate-spin" />
          <span>加载中...</span>
        </div>
        
        <!-- 空状态 -->
        <div v-else-if="conversations.length === 0" class="px-3 py-4 text-xs text-muted-foreground/60 flex flex-col items-center gap-2">
          <Inbox class="w-8 h-8 opacity-50" />
          <span>暂无记录</span>
        </div>
        
        <!-- 列表 -->
        <div v-else class="flex flex-col gap-0.5 overflow-y-auto scrollbar-thin -mx-2 px-2 pb-4">
          <div
            v-for="conv in conversations"
            :key="conv.id"
            class="group relative flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors"
            :class="conv.id === currentId ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'"
            @click="emit('select', conv.id)"
          >
            <!-- 图标/状态 -->
            <div class="flex-shrink-0 w-4 h-4 flex items-center justify-center">
              <span v-if="isRunning(conv.id)" class="w-2 h-2 rounded-full bg-success animate-pulse"></span>
              <MessageSquare v-else class="w-4 h-4 text-muted-foreground/50 group-hover:text-muted-foreground" :class="{ 'text-accent-foreground': conv.id === currentId }" />
            </div>
            
            <!-- 标题 -->
            <div class="flex-1 min-w-0 flex flex-col">
              <span class="truncate text-sm font-medium">{{ conv.title || '未命名对话' }}</span>
            </div>

            <!-- 删除按钮 (Hover显示) -->
            <button 
              class="opacity-0 group-hover:opacity-100 p-1 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 rounded transition-all"
              @click.stop="emit('delete', conv)"
            >
              <Trash2 class="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import type { Conversation } from '@/types'
import type { SearchConversationItem } from '@/api/chat'
import { searchConversations } from '@/api/chat'
import { formatShortTime } from '@/utils'
import { 
  PanelLeftClose, 
  PanelLeftOpen, 
  SquarePen, 
  Search,
  SearchX,
  X,
  BookOpen, 
  Puzzle, 
  FileText, 
  MessageSquare, 
  Trash2, 
  Headphones,
  Sparkles,
  Loader2,
  Inbox
} from 'lucide-vue-next'

// ==================== Props ====================

interface Props {
  /** 会话列表 */
  conversations: Conversation[]
  /** 当前会话 ID */
  currentId: string | null
  /** 是否折叠 */
  collapsed: boolean
  /** 是否加载中 */
  loading?: boolean
  /** 用户 ID */
  userId?: string
  /** 判断会话是否正在运行的函数 */
  isRunning?: (id: string) => boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  userId: '',
  isRunning: () => false
})

// ==================== Emits ====================

const emit = defineEmits<{
  /** 选择会话 */
  (e: 'select', id: string): void
  /** 创建新会话 */
  (e: 'create'): void
  /** 删除会话 */
  (e: 'delete', conv: Conversation): void
  /** 切换折叠状态 */
  (e: 'toggle-collapse'): void
  /** 导航 */
  (e: 'navigate', path: string): void
}>()

// ==================== 搜索状态 ====================

const isSearching = ref(false)
const searchQuery = ref('')
const searchResults = ref<SearchConversationItem[]>([])
const searchLoading = ref(false)
const searchInputRef = ref<HTMLInputElement | null>(null)

let debounceTimer: ReturnType<typeof setTimeout> | null = null

/**
 * 打开搜索模式
 */
function openSearch() {
  isSearching.value = true
  searchQuery.value = ''
  searchResults.value = []
  nextTick(() => {
    searchInputRef.value?.focus()
  })
}

/**
 * 关闭搜索模式
 */
function closeSearch() {
  isSearching.value = false
  searchQuery.value = ''
  searchResults.value = []
  searchLoading.value = false
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
}

/**
 * 选择搜索结果
 */
function selectSearchResult(conversationId: string) {
  emit('select', conversationId)
  closeSearch()
}

/**
 * 监听搜索关键词变化，防抖调用搜索 API
 */
watch(searchQuery, (query) => {
  if (debounceTimer) {
    clearTimeout(debounceTimer)
  }

  const trimmed = query.trim()
  if (!trimmed) {
    searchResults.value = []
    searchLoading.value = false
    return
  }

  searchLoading.value = true
  debounceTimer = setTimeout(async () => {
    try {
      const result = await searchConversations(props.userId, trimmed)
      searchResults.value = result.conversations
    } catch (err) {
      console.error('搜索对话失败:', err)
      searchResults.value = []
    } finally {
      searchLoading.value = false
    }
  }, 300)
})

// ==================== Methods ====================

/**
 * 格式化时间
 */
function formatTime(dateStr: string): string {
  return formatShortTime(dateStr)
}
</script>

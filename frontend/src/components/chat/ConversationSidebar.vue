<template>
  <div 
    class="relative z-10 flex flex-col transition-all duration-300 ease-in-out flex-shrink-0 bg-gray-50 border-r border-gray-100"
    :class="collapsed ? 'w-[70px]' : 'w-[260px]'"
  >
    <!-- 头部 -->
    <div class="h-14 flex items-center justify-between px-4 pt-2">
      <div class="flex items-center gap-2 font-semibold text-gray-700" v-if="!collapsed">
        <span class="text-xl">✨</span>
        <span class="tracking-tight">ZenFlux</span>
      </div>
      <button 
        @click="emit('toggle-collapse')" 
        class="p-1.5 rounded-md text-gray-400 hover:bg-gray-200 hover:text-gray-600 transition-colors"
      >
        <PanelLeftClose v-if="!collapsed" class="w-4 h-4" />
        <PanelLeftOpen v-else class="w-4 h-4" />
      </button>
    </div>

    <!-- 内容区（展开时显示） -->
    <div v-show="!collapsed" class="flex-1 flex flex-col px-3 py-2 overflow-y-auto scrollbar-thin gap-6">
      <!-- 顶部操作 -->
      <div class="flex flex-col gap-1">
        <button 
          @click="emit('create')" 
          class="w-full flex items-center gap-3 px-3 py-2 text-gray-600 hover:bg-gray-200 hover:text-gray-900 rounded-lg transition-colors group"
        >
          <SquarePen class="w-4 h-4 text-gray-500 group-hover:text-gray-800" />
          <span class="text-sm font-medium">新对话</span>
        </button>
        <button 
          class="w-full flex items-center gap-3 px-3 py-2 text-gray-600 hover:bg-gray-200 hover:text-gray-900 rounded-lg transition-colors group"
        >
          <Search class="w-4 h-4 text-gray-500 group-hover:text-gray-800" />
          <span class="text-sm font-medium">搜索</span>
        </button>
      </div>

      <!-- 库 -->
      <div class="flex flex-col gap-1">
        <div class="px-3 text-xs font-medium text-gray-400 mb-1">库</div>
        <button 
          @click="emit('navigate', '/knowledge')" 
          class="w-full flex items-center gap-3 px-3 py-2 text-gray-600 hover:bg-gray-200 hover:text-gray-900 rounded-lg transition-colors group"
        >
          <BookOpen class="w-4 h-4 text-gray-500 group-hover:text-gray-800" />
          <span class="text-sm font-medium">知识库</span>
        </button>
        <button 
          @click="emit('navigate', '/agents')" 
          class="w-full flex items-center gap-3 px-3 py-2 text-gray-600 hover:bg-gray-200 hover:text-gray-900 rounded-lg transition-colors group"
        >
          <Bot class="w-4 h-4 text-gray-500 group-hover:text-gray-800" />
          <span class="text-sm font-medium">智能体</span>
        </button>
        <button 
          @click="emit('navigate', '/skills')" 
          class="w-full flex items-center gap-3 px-3 py-2 text-gray-600 hover:bg-gray-200 hover:text-gray-900 rounded-lg transition-colors group"
        >
          <Puzzle class="w-4 h-4 text-gray-500 group-hover:text-gray-800" />
          <span class="text-sm font-medium">技能</span>
        </button>
        <button 
          @click="emit('navigate', '/tutorial')" 
          class="w-full flex items-center gap-3 px-3 py-2 text-gray-600 hover:bg-gray-200 hover:text-gray-900 rounded-lg transition-colors group"
        >
          <GraduationCap class="w-4 h-4 text-gray-500 group-hover:text-gray-800" />
          <span class="text-sm font-medium">教程</span>
        </button>
      </div>

      <!-- 对话列表 -->
      <div class="flex flex-col gap-1 flex-1 min-h-0">
        <div class="px-3 flex items-center justify-between group cursor-pointer mb-1">
          <span class="text-xs font-medium text-gray-400">最近对话</span>
        </div>
        
        <!-- 加载中 -->
        <div v-if="loading" class="px-3 py-2 text-xs text-gray-400">
          加载中...
        </div>
        
        <!-- 空状态 -->
        <div v-else-if="conversations.length === 0" class="px-3 py-2 text-xs text-gray-400">
          暂无记录
        </div>
        
        <!-- 列表 -->
        <div v-else class="flex flex-col gap-0.5 overflow-y-auto scrollbar-thin -mx-2 px-2 pb-4">
          <div
            v-for="conv in conversations"
            :key="conv.id"
            class="group relative flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors"
            :class="conv.id === currentId ? 'bg-gray-200/80 text-gray-900' : 'text-gray-600 hover:bg-gray-200/50 hover:text-gray-900'"
            @click="emit('select', conv.id)"
          >
            <!-- 图标/状态 -->
            <div class="flex-shrink-0 w-4 h-4 flex items-center justify-center">
              <span v-if="isRunning(conv.id)" class="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
              <MessageSquare v-else class="w-4 h-4 text-gray-400 group-hover:text-gray-500" :class="{ 'text-gray-600': conv.id === currentId }" />
            </div>
            
            <!-- 标题 -->
            <div class="flex-1 min-w-0 flex flex-col">
              <span class="truncate text-sm font-medium">{{ conv.title || '未命名对话' }}</span>
            </div>

            <!-- 删除按钮 (Hover显示) -->
            <button 
              class="opacity-0 group-hover:opacity-100 p-1 text-gray-400 hover:text-red-500 hover:bg-gray-300/50 rounded transition-all"
              @click.stop="emit('delete', conv)"
            >
              <Trash2 class="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      <!-- 底部用户栏 -->
      <div class="mt-auto border-t border-gray-200/50 pt-3 px-1">
        <div class="flex items-center justify-between group px-2 py-2 rounded-lg hover:bg-gray-200/50 cursor-pointer transition-colors">
          <div class="flex items-center gap-3 overflow-hidden">
            <div class="w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0 text-[10px] font-bold text-gray-600">
              {{ userInitial }}
            </div>
            <span class="text-sm font-medium text-gray-700 truncate">{{ username }}</span>
          </div>
          
          <button 
            v-if="isAuthenticated"
            @click.stop="emit('logout')"
            class="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-300/50 rounded-md transition-colors"
            title="退出登录"
          >
            <LogOut class="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Conversation } from '@/types'
import { formatShortTime } from '@/utils'
import { 
  PanelLeftClose, 
  PanelLeftOpen, 
  SquarePen, 
  Search, 
  BookOpen, 
  Bot, 
  Puzzle, 
  GraduationCap, 
  MessageSquare, 
  Trash2, 
  LogOut 
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
  /** 判断会话是否正在运行的函数 */
  isRunning?: (id: string) => boolean
  /** 用户名 */
  username?: string
  /** 是否已认证 */
  isAuthenticated?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  isRunning: () => false,
  username: '访客',
  isAuthenticated: false
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
  /** 登出 */
  (e: 'logout'): void
}>()

// ==================== Computed ====================

/** 用户名首字母 */
const userInitial = computed(() => {
  return props.username?.charAt(0).toUpperCase() || 'U'
})

// ==================== Methods ====================

/**
 * 格式化时间
 */
function formatTime(dateStr: string): string {
  return formatShortTime(dateStr)
}
</script>

<style scoped>
/* 滚动条美化 */
.scrollbar-thin::-webkit-scrollbar {
  width: 4px;
}
.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-thin::-webkit-scrollbar-thumb {
  background-color: transparent;
  border-radius: 4px;
}
.scrollbar-thin:hover::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.5);
}
</style>

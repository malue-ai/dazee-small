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
              placeholder="搜索项目..."
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
            ref="createProjectBtnRef"
            @click="emit('navigate', '/create-project')" 
            class="w-full flex items-center gap-3 px-3 py-2 text-muted-foreground hover:bg-muted hover:text-foreground rounded-lg transition-colors group"
          >
            <Plus class="w-4 h-4 text-muted-foreground group-hover:text-foreground" />
            <span class="text-sm font-medium">新建项目</span>
          </button>
          <button 
            @click="emit('navigate', '/skills')" 
            class="w-full flex items-center gap-3 px-3 py-2 text-muted-foreground hover:bg-muted hover:text-foreground rounded-lg transition-colors group"
          >
            <Puzzle class="w-4 h-4 text-muted-foreground group-hover:text-foreground" />
            <span class="text-sm font-medium">技能</span>
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

      <!-- 项目(Agent)区 -->
      <div class="flex flex-col gap-1">
        <div class="px-3 flex items-center justify-between mb-1">
          <span class="text-xs font-medium text-muted-foreground/60">
            {{ isSearching && searchQuery ? `搜索结果（${filteredAgents.length}）` : '项目' }}
          </span>
          <button
            v-if="!isSearching"
            @click="emit('navigate', '/create-project')"
            class="p-0.5 text-muted-foreground/50 hover:text-foreground rounded transition-colors"
            title="新建项目"
          >
            <Plus class="w-3.5 h-3.5" />
          </button>
        </div>

        <!-- Agent 列表（正常模式显示全部，搜索模式显示过滤后的） -->
        <div v-if="displayAgents.length > 0" class="flex flex-col gap-0.5">
          <div
            v-for="agent in displayAgents"
            :key="agent.agent_id"
            class="group relative flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors"
            :class="agent.agent_id === currentAgentId ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'"
            @click="handleAgentClick(agent.agent_id)"
          >
            <Bot class="w-4 h-4 flex-shrink-0" :class="agent.agent_id === currentAgentId ? 'text-primary' : 'text-muted-foreground/50 group-hover:text-muted-foreground'" />
            <span class="truncate text-sm font-medium flex-1">{{ agent.name }}</span>
            <div class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-all">
              <button
                class="p-1 text-muted-foreground/50 hover:text-primary hover:bg-primary/10 rounded transition-colors"
                @click.stop="emit('edit-agent', agent.agent_id)"
                title="编辑项目"
              >
                <Pencil class="w-3.5 h-3.5" />
              </button>
              <button
                class="p-1 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 rounded transition-colors"
                @click.stop="emit('delete-agent', agent.agent_id)"
                title="删除项目"
              >
                <Trash2 class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-else class="px-3 py-3 text-xs text-muted-foreground/40 flex flex-col items-center gap-1.5">
          <template v-if="isSearching && searchQuery">
            <SearchX class="w-6 h-6 opacity-40" />
            <span>未找到匹配的项目</span>
          </template>
          <template v-else>
            <Bot class="w-6 h-6 opacity-40" />
            <span>暂无项目</span>
          </template>
        </div>

      </div>

    </div>

    <!-- 底部用户信息（始终可见，不随内容滚动） -->
    <div v-show="!collapsed" class="border-t border-border pt-3 px-4 pb-4 flex-shrink-0">
      <div 
        ref="settingsBtnRef"
        class="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-muted cursor-pointer transition-colors group"
        @click="emit('navigate', '/settings')"
        title="设置"
      >
        <div class="w-6 h-6 rounded-full bg-muted flex items-center justify-center flex-shrink-0 text-[10px] font-bold text-muted-foreground group-hover:text-foreground">
          {{ userId ? userId.charAt(0).toUpperCase() : 'U' }}
        </div>
        <span class="text-sm font-medium text-foreground truncate">{{ userId || 'User' }}</span>
        <Settings class="w-3.5 h-3.5 ml-auto text-muted-foreground/40 opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    </div>

    <!-- 折叠状态：仅显示头像 -->
    <div v-show="collapsed" class="border-t border-border py-3 flex justify-center flex-shrink-0">
      <div 
        class="w-8 h-8 rounded-full bg-muted flex items-center justify-center text-xs font-bold text-muted-foreground hover:bg-accent hover:text-foreground cursor-pointer transition-colors"
        @click="emit('navigate', '/settings')"
        title="设置"
      >
        {{ userId ? userId.charAt(0).toUpperCase() : 'U' }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted } from 'vue'
import type { Conversation, AgentSummary } from '@/types'
import { useGuideStore } from '@/stores/guide'
import { formatShortTime } from '@/utils'
import { 
  PanelLeftClose, 
  PanelLeftOpen, 
  Search,
  SearchX,
  X,
  Plus,
  Bot,
  Puzzle, 
  Trash2,
  Pencil,
  Sparkles,
  Settings
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
  /** Agent（项目）列表 */
  agents?: AgentSummary[]
  /** 当前选中的 Agent ID */
  currentAgentId?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  userId: '',
  isRunning: () => false,
  agents: () => [],
  currentAgentId: null
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
  /** 选择 Agent（项目） */
  (e: 'select-agent', agentId: string): void
  /** 编辑 Agent（项目） */
  (e: 'edit-agent', agentId: string): void
  /** 删除 Agent（项目） */
  (e: 'delete-agent', agentId: string): void
}>()

// ==================== 引导 ====================

const guideStore = useGuideStore()
const createProjectBtnRef = ref<HTMLElement | null>(null)
const settingsBtnRef = ref<HTMLElement | null>(null)

// 引导 Step 1：高亮设置按钮 | Step 5：高亮"新建项目"按钮
onMounted(() => {
  if (guideStore.isActive) {
    if (guideStore.currentStep === 1 && settingsBtnRef.value) {
      guideStore.setTarget(settingsBtnRef.value)
    } else if (guideStore.currentStep === 5 && createProjectBtnRef.value) {
      guideStore.setTarget(createProjectBtnRef.value)
    }
  }
})

watch(() => guideStore.currentStep, (step) => {
  if (step === 1 && settingsBtnRef.value) {
    guideStore.setTarget(settingsBtnRef.value)
  } else if (step === 5 && createProjectBtnRef.value) {
    guideStore.setTarget(createProjectBtnRef.value)
  }
})

// ==================== 搜索状态 ====================

const isSearching = ref(false)
const searchQuery = ref('')
const searchInputRef = ref<HTMLInputElement | null>(null)

/** 根据搜索关键词过滤项目列表 */
const filteredAgents = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  if (!query) return props.agents
  return props.agents.filter(agent =>
    agent.name.toLowerCase().includes(query) ||
    (agent.description && agent.description.toLowerCase().includes(query)) ||
    agent.agent_id.toLowerCase().includes(query)
  )
})

/** 当前应该显示的项目列表（搜索时显示过滤结果，否则全部） */
const displayAgents = computed(() => {
  return isSearching.value ? filteredAgents.value : props.agents
})

/**
 * 打开搜索模式
 */
function openSearch() {
  isSearching.value = true
  searchQuery.value = ''
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
}

/**
 * 点击项目（搜索模式下自动关闭搜索）
 */
function handleAgentClick(agentId: string) {
  emit('select-agent', agentId)
  if (isSearching.value) {
    closeSearch()
  }
}

// ==================== Methods ====================

/**
 * 格式化时间
 */
function formatTime(dateStr: string): string {
  return formatShortTime(dateStr)
}
</script>

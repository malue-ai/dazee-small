<template>
  <div 
    class="relative z-10 flex flex-col transition-all duration-300 ease-in-out flex-shrink-0 glass-sidebar"
    :class="collapsed ? 'w-[70px]' : 'w-[260px]'"
  >
    <!-- 头部 -->
    <div class="h-14 flex items-center justify-between px-4 pt-2">
      <div class="flex items-center gap-2 font-semibold text-foreground" v-if="!collapsed">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 28 28" class="w-6 h-6 flex-shrink-0">
          <path d="M27.46 7.27L27.29 6.65L27.23 6.47L27.11 6.11L26.93 5.65L26.68 5.1L26.49 4.73L26.12 4.12L25.96 3.89L25.84 3.73L25.35 3.14L24.77 2.57L24.66 2.48L24.53 2.37L23.89 1.89L23.43 1.6L23.04 1.39L22.15 0.99L22.1 0.97L22.08 0.96L22.03 0.94L21.08 0.63L20.73 0.54L20.16 0.41L19.99 0.38L19.39 0.27L18.82 0.19L18.57 0.16L18.04 0.11L17.59 0.08L17.12 0.05L16.69 0.03L16.3 0.02L15.73 0.01L15.35 0L14.97 0L14.37 0L13.63 0L13.03 0L12.65 0L12.27 0.01L11.7 0.02L11.31 0.03L10.88 0.05L10.41 0.08L9.96 0.11L9.43 0.16L9.18 0.19L8.61 0.27L8.01 0.38L7.84 0.41L7.27 0.54L6.92 0.63L5.97 0.94L5.93 0.96L5.9 0.97L5.85 0.99L4.97 1.39L4.58 1.6L4.12 1.89L3.47 2.36L3.34 2.47L3.23 2.57L2.65 3.14L2.16 3.73L2.04 3.89L1.88 4.12L1.51 4.72L1.32 5.1L1.07 5.64L0.89 6.11L0.77 6.47L0.71 6.64L0.54 7.27L0.43 7.73L0.41 7.84L0.38 8L0.23 8.89L0.19 9.21L0.15 9.61L0.1 10.12L0.07 10.57L0.04 11.08L0.03 11.42L0.02 11.94L0.01 12.48L0.01 12.77L0.01 13.31L0.01 14.68L0.01 15.22L0.01 15.51L0.02 16.05L0.03 16.57L0.04 16.91L0.07 17.42L0.1 17.87L0.15 18.39L0.19 18.79L0.23 19.1L0.38 19.99L0.41 20.15L0.43 20.26L0.54 20.72L0.71 21.35L0.77 21.52L0.89 21.88L1.07 22.35L1.32 22.89L1.51 23.26L1.88 23.87L2.04 24.1L2.16 24.26L2.65 24.85L3.23 25.42L3.34 25.52L3.47 25.63L4.11 26.1L4.58 26.39L4.96 26.6L5.84 27L5.9 27.02L5.92 27.03L5.97 27.04L6.91 27.35L7.27 27.45L7.84 27.58L8.01 27.61L8.61 27.72L9.17 27.79L9.42 27.82L9.96 27.87L10.41 27.91L10.88 27.94L11.3 27.95L11.7 27.97L12.27 27.98L12.65 27.98L13.02 27.98L13.63 27.98L14.37 27.98L14.97 27.98L15.34 27.98L15.73 27.98L16.3 27.97L16.69 27.95L17.11 27.94L17.59 27.91L18.04 27.87L18.57 27.82L18.82 27.79L19.38 27.72L19.98 27.61L20.16 27.58L20.73 27.45L21.08 27.35L22.02 27.04L22.07 27.03L22.09 27.02L22.15 27L23.03 26.6L23.42 26.39L23.88 26.1L24.52 25.63L24.66 25.52L24.77 25.42L25.35 24.85L25.84 24.26L25.95 24.1L26.11 23.87L26.48 23.26L26.68 22.89L26.92 22.35L27.1 21.88L27.23 21.52L27.28 21.35L27.46 20.72L27.56 20.26L27.58 20.15L27.62 19.99L27.76 19.1L27.8 18.79L27.85 18.39L27.9 17.87L27.93 17.42L27.95 16.91L27.96 16.57L27.98 16.05L27.99 15.51L27.99 15.22L27.99 14.68L27.99 13.32L27.99 12.77L27.99 12.49L27.98 11.95L27.96 11.43L27.95 11.08L27.93 10.58L27.9 10.13L27.85 9.61L27.8 9.21L27.76 8.9L27.62 8L27.58 7.84L27.57 7.73L27.46 7.27Z" fill="#6BFAC8"/>
          <path d="M21.44 16.24C21.44 18.54 20.72 20.33 19.3 21.61C17.93 22.86 16.09 23.48 13.79 23.48H6.13V11.15C6.13 8.87 6.84 7.08 8.26 5.78C9.63 4.54 11.48 3.91 13.79 3.91C16.09 3.91 17.93 4.54 19.3 5.78C20.72 7.08 21.44 8.87 21.44 11.15V16.24ZM13.79 21.68C15.45 21.68 16.79 21.21 17.82 20.28C18.88 19.31 19.41 18 19.41 16.35V11.15C19.41 9.5 18.88 8.19 17.82 7.22C16.79 6.28 15.45 5.81 13.79 5.81C12.12 5.81 10.77 6.28 9.75 7.22C8.68 8.19 8.15 9.5 8.15 11.15V21.68H13.79Z" fill="#181818"/>
          <path d="M15.31 12.25C15.31 11.98 15.41 11.76 15.6 11.58C15.79 11.4 16.02 11.31 16.29 11.31H17.06C17.18 11.31 17.28 11.4 17.28 11.52V12.75C17.28 13.02 17.19 13.25 17 13.43C16.81 13.61 16.57 13.7 16.29 13.7H15.53C15.41 13.7 15.31 13.6 15.31 13.48V12.25Z" fill="#181818"/>
          <path d="M12.69 12.25C12.69 11.98 12.59 11.76 12.4 11.58C12.21 11.4 11.98 11.31 11.71 11.31H10.94C10.82 11.31 10.72 11.4 10.72 11.52V12.75C10.72 13.02 10.81 13.25 11 13.43C11.19 13.61 11.43 13.7 11.71 13.7H12.47C12.59 13.7 12.69 13.6 12.69 13.48V12.25Z" fill="#181818"/>
        </svg>
        <span class="tracking-tight">xiaodazi</span>
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
    <div v-show="!collapsed" class="flex-1 flex flex-col px-3 py-2 overflow-y-auto scrollbar-overlay gap-6">
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
            @click="emit('navigate', '/tasks')" 
            class="w-full flex items-center gap-3 px-3 py-2 text-muted-foreground hover:bg-muted hover:text-foreground rounded-lg transition-colors group"
          >
            <Clock class="w-4 h-4 text-muted-foreground group-hover:text-foreground" />
            <span class="text-sm font-medium">定时任务</span>
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
            <div 
              class="flex items-center gap-0.5 transition-all"
              :class="isGuideEditTarget(agent) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'"
            >
              <button
                :ref="(el) => setEditBtnRef(agent.agent_id, el)"
                class="p-1 text-muted-foreground/50 hover:text-primary hover:bg-primary/10 rounded transition-colors"
                @click.stop="handleEditClick(agent.agent_id)"
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
import { ref, computed, nextTick, watch, onMounted, type ComponentPublicInstance } from 'vue'
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
  Clock,
  Puzzle, 
  Trash2,
  Pencil,
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

/** Agent 编辑按钮 ref 映射（用于引导 Step 11 高亮） */
const editBtnRefs = new Map<string, HTMLElement>()

function setEditBtnRef(agentId: string, el: Element | ComponentPublicInstance | null) {
  if (el instanceof HTMLElement) {
    editBtnRefs.set(agentId, el)
  } else {
    editBtnRefs.delete(agentId)
  }
}

/** 找到默认项目（取第一个已加载的 Agent） */
function findDefaultAgent(): typeof props.agents[number] | undefined {
  return props.agents[0]
}

/** 判断某个 Agent 是否为引导步骤 11 的目标（用于保持编辑按钮可见） */
function isGuideEditTarget(agent: typeof props.agents[number]): boolean {
  if (!guideStore.isActive || guideStore.currentStep !== 11) return false
  const target = findDefaultAgent()
  return !!target && target.agent_id === agent.agent_id
}

/** 设置步骤 11 的高亮目标 */
function setupGuideStep11() {
  if (!guideStore.isActive || guideStore.currentStep !== 11) return
  const target = findDefaultAgent()
  if (!target) return
  nextTick(() => {
    const el = editBtnRefs.get(target.agent_id)
    if (el) {
      guideStore.setTarget(el)
    }
  })
}

/** 编辑按钮点击处理（引导步骤 11 推进） */
function handleEditClick(agentId: string) {
  if (guideStore.isActive && guideStore.currentStep === 11) {
    guideStore.nextStep() // → step 12
  }
  emit('edit-agent', agentId)
}

// 引导 Step 1：高亮设置按钮 | Step 6：高亮"新建项目"按钮 | Step 11：高亮编辑按钮
onMounted(() => {
  if (guideStore.isActive) {
    if (guideStore.currentStep === 1 && settingsBtnRef.value) {
      guideStore.setTarget(settingsBtnRef.value)
    } else if (guideStore.currentStep === 6 && createProjectBtnRef.value) {
      guideStore.setTarget(createProjectBtnRef.value)
    } else if (guideStore.currentStep === 11) {
      setupGuideStep11()
    }
  }
})

watch(() => guideStore.currentStep, (step) => {
  nextTick(() => {
    if (step === 1 && settingsBtnRef.value) {
      guideStore.setTarget(settingsBtnRef.value)
    } else if (step === 6 && createProjectBtnRef.value) {
      guideStore.setTarget(createProjectBtnRef.value)
    } else if (step === 11) {
      setupGuideStep11()
    }
  })
})

// 监听 agents 列表变化：步骤 11 时 Agent 列表可能异步加载完成，
// 需要在 v-for 重新渲染注册 ref 后再设置高亮目标
watch(() => props.agents.length, () => {
  if (guideStore.isActive && guideStore.currentStep === 11) {
    // agents 变化后 DOM 需要下一帧更新，ref 回调才会执行
    nextTick(() => {
      nextTick(() => {
        setupGuideStep11()
      })
    })
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

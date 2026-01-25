<template>
  <div class="h-16 flex items-center justify-between px-8 bg-white sticky top-0 z-20">
    <div class="flex items-center gap-3">
      <!-- Agent 选择器 -->
      <div class="relative">
        <button 
          @click="toggleAgentSelector"
          class="py-2 text-gray-800 text-base font-semibold hover:text-gray-600 transition-all flex items-center gap-2 cursor-pointer"
          :disabled="disabled"
        >
          <span>{{ currentAgentName }}</span>
          <ChevronUp v-if="showSelector" class="w-3 h-3 text-gray-400" />
          <ChevronDown v-else class="w-3 h-3 text-gray-400" />
        </button>
        
        <!-- Agent 下拉列表 -->
        <div 
          v-if="showSelector" 
          class="absolute top-full left-0 mt-2 w-64 bg-white rounded-xl shadow-2xl border border-gray-100 overflow-hidden z-50 animate-in fade-in slide-in-from-top-2 duration-200"
        >
          <div class="p-2 border-b border-gray-100 bg-gray-50">
            <p class="text-xs text-gray-500 px-2">选择智能体</p>
          </div>
          <div class="max-h-[300px] overflow-y-auto scrollbar-thin">
            <div v-if="loadingAgents" class="p-4 text-center text-sm text-gray-400">
              加载中...
            </div>
            <div v-else-if="agents.length === 0" class="p-4 text-center text-sm text-gray-400">
              暂无可用智能体
            </div>
            <button
              v-for="agent in agents"
              :key="agent.agent_id || 'default'"
              @click="selectAgent(agent)"
              class="w-full text-left px-4 py-3 hover:bg-blue-50 transition-colors border-b border-gray-50 last:border-0"
              :class="selectedAgentId === agent.agent_id ? 'bg-blue-50' : ''"
            >
              <div class="flex items-center justify-between">
                <div class="flex-1 min-w-0">
                  <p class="text-sm font-medium text-gray-900 truncate">
                    {{ agent.name || agent.agent_id || '默认智能体' }}
                  </p>
                  <p class="text-xs text-gray-500 truncate mt-0.5">
                    {{ agent.description || '无描述' }}
                  </p>
                </div>
                <Check v-if="selectedAgentId === agent.agent_id" class="ml-2 w-4 h-4 text-blue-600" />
              </div>
            </button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 右侧按钮：切换侧边栏 -->
    <div class="flex items-center gap-2">
      <button 
        v-if="showWorkspaceButton"
        @click="emit('toggle-sidebar')" 
        class="p-2 rounded-lg transition-all duration-200" 
        :class="sidebarActive ? 'bg-gray-100 text-gray-900' : 'text-gray-500 hover:bg-gray-100 hover:text-gray-900'"
        title="切换侧边栏"
      >
        <PanelRight class="w-5 h-5" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { Agent } from '@/types'
import { FolderOpen, ClipboardList, ChevronDown, ChevronUp, Check, PanelRight } from 'lucide-vue-next'

// ==================== Props ====================

interface Props {
  /** 标题 */
  title: string
  /** Agent 列表 */
  agents?: Agent[]
  /** 当前选择的 Agent ID */
  selectedAgentId?: string | null
  /** 是否禁用 */
  disabled?: boolean
  /** 是否正在加载 Agent */
  loadingAgents?: boolean
  /** 是否显示侧边栏按钮（仅当有会话时显示） */
  showWorkspaceButton?: boolean
  /** 侧边栏是否激活 */
  sidebarActive?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  agents: () => [],
  selectedAgentId: null,
  disabled: false,
  loadingAgents: false,
  showWorkspaceButton: false,
  sidebarActive: false
})

// ==================== Emits ====================

const emit = defineEmits<{
  /** 选择 Agent */
  (e: 'select-agent', agent: Agent): void
  /** 切换侧边栏显示/隐藏 */
  (e: 'toggle-sidebar'): void
}>()

// ==================== State ====================

/** 是否显示选择器 */
const showSelector = ref(false)

// ==================== Computed ====================

/** 当前 Agent 名称 */
const currentAgentName = computed(() => {
  const agent = props.agents.find(a => a.agent_id === props.selectedAgentId)
  return agent?.name || '默认智能体'
})

// ==================== Methods ====================

/**
 * 切换选择器显示
 */
function toggleAgentSelector(): void {
  if (!props.disabled) {
    showSelector.value = !showSelector.value
  }
}

/**
 * 选择 Agent
 */
function selectAgent(agent: Agent): void {
  emit('select-agent', agent)
  showSelector.value = false
}

/**
 * 点击外部关闭选择器
 */
function handleClickOutside(event: MouseEvent): void {
  const target = event.target as HTMLElement
  if (!target.closest('.relative')) {
    showSelector.value = false
  }
}

// ==================== Lifecycle ====================

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
.scrollbar-thin::-webkit-scrollbar {
  width: 6px;
}
.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-thin::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.3);
  border-radius: 3px;
}
</style>

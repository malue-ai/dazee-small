<template>
  <div class="h-16 flex items-center justify-between px-8 bg-background/80 backdrop-blur-sm sticky top-0 z-20 border-b border-border/40 transition-all duration-200">
    <div class="flex items-center gap-3">
      <span class="py-2 text-foreground text-base font-semibold">{{ title }}</span>
    </div>
    
    <!-- 右侧按钮：切换侧边栏 -->
    <div class="flex items-center gap-2">
      <button 
        v-if="showWorkspaceButton"
        @click="emit('toggle-sidebar')" 
        class="p-2 rounded-lg transition-all duration-200" 
        :class="sidebarActive ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'"
        title="切换侧边栏"
      >
        <PanelRight class="w-5 h-5" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { PanelRight } from 'lucide-vue-next'

// ==================== Props ====================

interface Props {
  /** 标题 */
  title: string
  /** 是否显示侧边栏按钮（仅当有会话时显示） */
  showWorkspaceButton?: boolean
  /** 侧边栏是否激活 */
  sidebarActive?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showWorkspaceButton: false,
  sidebarActive: false
})

// ==================== Emits ====================

const emit = defineEmits<{
  /** 切换侧边栏显示/隐藏 */
  (e: 'toggle-sidebar'): void
}>()
</script>

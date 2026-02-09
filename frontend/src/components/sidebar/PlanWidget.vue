<template>
  <div class="h-full overflow-y-auto scrollbar-thin" v-if="plan">
    <!-- 标题区域 -->
    <div class="mb-4">
      <h3 class="text-base font-semibold text-foreground mb-1">{{ plan.name || '任务计划' }}</h3>
      <p v-if="plan.overview" class="text-sm text-muted-foreground leading-relaxed">{{ plan.overview }}</p>
    </div>

    <!-- 详细计划（可折叠） -->
    <div v-if="plan.detailed_plan" class="mb-4">
      <button 
        @click="showDetailedPlan = !showDetailedPlan"
        class="flex items-center gap-2 text-sm text-primary hover:text-primary-hover mb-2"
      >
        <ChevronDown 
          class="w-4 h-4 transition-transform" 
          :class="{ 'rotate-180': !showDetailedPlan }"
        />
        {{ showDetailedPlan ? '收起详细计划' : '查看详细计划' }}
      </button>
      <div 
        v-if="showDetailedPlan" 
        class="bg-muted rounded-lg p-4 text-sm prose prose-sm max-w-none overflow-x-auto"
      >
        <MarkdownRenderer :content="plan.detailed_plan" :final="true" />
      </div>
    </div>

    <!-- 任务进度 -->
    <div class="mb-3">
      <div class="flex items-center justify-between mb-3">
        <span class="text-sm font-medium text-foreground">任务进度</span>
        <span class="text-xs text-muted-foreground/50">{{ completedCount }}/{{ plan.todos?.length || 0 }}</span>
      </div>
      
      <div class="flex flex-col gap-3 relative">
        <!-- 连接线 -->
        <div class="absolute top-2.5 bottom-2.5 left-[9px] w-0.5 bg-muted z-0"></div>
        
        <div 
          v-for="todo in plan.todos" 
          :key="todo.id"
          class="flex items-start gap-3 relative z-10"
        >
          <!-- 步骤图标 -->
          <div 
            class="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 border-2 bg-white"
            :class="{
              'bg-primary border-primary text-white': todo.status === 'completed',
              'border-primary animate-spin': todo.status === 'in_progress',
              'border-border': todo.status === 'pending'
            }"
          >
            <Check v-if="todo.status === 'completed'" class="w-3 h-3" />
            <div v-else-if="todo.status === 'pending'" class="w-1.5 h-1.5 rounded-full bg-muted-foreground/30"></div>
          </div>
          
          <!-- 步骤内容 -->
          <div class="flex-1">
            <div 
              class="text-sm leading-relaxed"
              :class="{
                'text-muted-foreground/50 line-through': todo.status === 'completed',
                'text-foreground font-medium': todo.status === 'in_progress',
                'text-muted-foreground': todo.status === 'pending'
              }"
            >
              {{ todo.content }}
            </div>
            <!-- 显示完成结果 -->
            <div v-if="todo.result && todo.status === 'completed'" class="text-xs text-muted-foreground/50 mt-1">
              {{ todo.result }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
  
  <!-- 空状态 -->
  <div v-else class="flex flex-col items-center justify-center h-full text-muted-foreground/50">
    <ClipboardList class="w-8 h-8 mb-3 opacity-50" />
    <p class="text-sm">暂无任务计划</p>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Check, ClipboardList, ChevronDown } from 'lucide-vue-next'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import type { PlanData } from '@/types'

const props = defineProps<{
  plan: PlanData | null
}>()

// 详细计划展开状态
const showDetailedPlan = ref(false)

// 已完成任务数
const completedCount = computed(() => {
  if (!props.plan?.todos) return 0
  return props.plan.todos.filter(t => t.status === 'completed').length
})
</script>

<style scoped>
.animate-spin {
  border-top-color: transparent !important;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.prose :deep(h2) {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-foreground);
  margin-top: 1rem;
  margin-bottom: 0.5rem;
}

.prose :deep(h3) {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--color-foreground);
  margin-top: 0.75rem;
  margin-bottom: 0.25rem;
}

.prose :deep(p) {
  font-size: 0.875rem;
  color: var(--color-muted-foreground);
  margin-bottom: 0.5rem;
}

.prose :deep(ul) {
  font-size: 0.875rem;
  color: var(--color-muted-foreground);
  padding-left: 1rem;
  margin-bottom: 0.5rem;
}

.prose :deep(li) {
  margin-bottom: 0.25rem;
}

.prose :deep(pre) {
  background-color: var(--color-muted);
  border-radius: 0.5rem;
  padding: 0.5rem;
  font-size: 0.75rem;
  overflow-x: auto;
}

.prose :deep(code) {
  font-size: 0.75rem;
  background-color: var(--color-muted);
  padding: 0 0.25rem;
  border-radius: 0.25rem;
}
</style>

<template>
  <div class="bg-white rounded-xl p-5 h-full overflow-y-auto border border-gray-100 shadow-sm" v-if="plan">
    <div class="mb-6">
      <h3 class="text-base font-semibold text-gray-900 mb-2">任务进度</h3>
      <p v-if="plan.goal" class="text-sm text-gray-500 leading-relaxed">{{ plan.goal }}</p>
    </div>
    
    <div class="flex flex-col gap-4 relative">
      <!-- 连接线 -->
      <div class="absolute top-2.5 bottom-2.5 left-[9px] w-0.5 bg-gray-100 z-0"></div>
      
      <div 
        v-for="(step, index) in steps" 
        :key="index"
        class="flex items-start gap-3 relative z-10"
      >
        <!-- 步骤图标 -->
        <div 
          class="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 border-2 bg-white"
          :class="{
            'bg-blue-500 border-blue-500 text-white': step.status === 'completed',
            'border-blue-500 animate-spin': step.status === 'in_progress',
            'border-gray-200': step.status === 'pending'
          }"
        >
          <Check v-if="step.status === 'completed'" class="w-3 h-3" />
          <div v-else-if="step.status === 'pending'" class="w-1.5 h-1.5 rounded-full bg-gray-300"></div>
        </div>
        
        <!-- 步骤内容 -->
        <div class="flex-1">
          <div 
            class="text-sm leading-relaxed"
            :class="{
              'text-gray-400 line-through': step.status === 'completed',
              'text-gray-900 font-medium': step.status === 'in_progress',
              'text-gray-600': step.status === 'pending'
            }"
          >
            {{ step.title || step.action || step }}
          </div>
        </div>
      </div>
    </div>
  </div>
  
  <!-- 空状态 -->
  <div v-else class="flex flex-col items-center justify-center h-full text-gray-400">
    <ClipboardList class="w-8 h-8 mb-3 opacity-50" />
    <p class="text-sm">暂无任务计划</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Check, ClipboardList } from 'lucide-vue-next'

const props = defineProps({
  plan: {
    type: Object,
    default: null
  }
})

const steps = computed(() => {
  if (!props.plan) return []
  return props.plan.steps || []
})
</script>

<style scoped>
/* in_progress 状态的旋转动画应用于边框 */
.animate-spin {
  border-top-color: transparent !important;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>

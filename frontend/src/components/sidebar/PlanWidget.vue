<template>
  <div class="plan-widget" v-if="plan">
    <div class="plan-header">
      <h3>任务进度</h3>
      <div class="plan-goal" v-if="plan.goal">{{ plan.goal }}</div>
    </div>
    
    <div class="plan-steps">
      <div 
        v-for="(step, index) in steps" 
        :key="index"
        class="plan-step"
        :class="{ 
          'completed': step.status === 'completed',
          'in-progress': step.status === 'in_progress',
          'pending': step.status === 'pending'
        }"
      >
        <div class="step-icon">
          <span v-if="step.status === 'completed'" class="check-icon">✓</span>
          <span v-else-if="step.status === 'in_progress'" class="spinner"></span>
          <span v-else class="pending-dot"></span>
        </div>
        <div class="step-content">
          <div class="step-title">{{ step.title || step.action || step }}</div>
        </div>
      </div>
    </div>
  </div>
  <div v-else class="empty-plan">
    <span class="icon">📋</span>
    <p>暂无任务计划</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

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
.plan-widget {
  background: #ffffff;
  border-radius: 12px;
  padding: 20px;
  height: 100%;
  overflow-y: auto;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05); /* 轻微阴影 */
  border: 1px solid #f3f4f6;
  color: #374151;
}

.plan-header {
  margin-bottom: 24px;
}

.plan-header h3 {
  margin: 0 0 8px 0;
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}

.plan-goal {
  font-size: 13px;
  color: #6b7280;
  line-height: 1.5;
}

.plan-steps {
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: relative;
}

/* 连接线 */
.plan-steps::before {
  content: '';
  position: absolute;
  top: 10px;
  bottom: 10px;
  left: 9px;
  width: 2px;
  background: #f3f4f6;
  z-index: 0;
}

.plan-step {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  position: relative;
  z-index: 1;
}

.step-icon {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #ffffff;
  border: 2px solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.plan-step.completed .step-icon {
  background: #2563eb; /* 蓝色实心 */
  border-color: #2563eb;
  color: white;
}

.check-icon {
  font-size: 12px;
  font-weight: bold;
}

.plan-step.in-progress .step-icon {
  border-color: #2563eb;
  border-top-color: transparent;
  animation: spin 1s linear infinite;
}

.plan-step.pending .pending-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #d1d5db;
}

.step-content {
  flex: 1;
}

.step-title {
  font-size: 14px;
  line-height: 1.5;
  color: #374151;
}

.plan-step.completed .step-title {
  color: #9ca3af;
  text-decoration: line-through;
}

.plan-step.in-progress .step-title {
  color: #111827;
  font-weight: 500;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-plan {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #9ca3af;
}

.empty-plan .icon {
  font-size: 32px;
  margin-bottom: 12px;
  opacity: 0.5;
}
</style>

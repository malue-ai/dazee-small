<template>
  <div :class="['card', variant]" :style="customStyle">
    <div v-if="$slots.header || title" class="card-header">
      <slot name="header">
        <h3 class="card-title">{{ title }}</h3>
      </slot>
    </div>
    
    <div class="card-body">
      <slot></slot>
    </div>
    
    <div v-if="$slots.footer" class="card-footer">
      <slot name="footer"></slot>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  title: {
    type: String,
    default: ''
  },
  variant: {
    type: String,
    default: 'default', // default, primary, success, warning, error
    validator: (value) => ['default', 'primary', 'success', 'warning', 'error'].includes(value)
  },
  padding: {
    type: String,
    default: '20px'
  }
})

const customStyle = computed(() => ({
  '--card-padding': props.padding
}))
</script>

<style scoped>
.card {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  transition: all 0.3s ease;
}

.card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  transform: translateY(-2px);
}

.card.primary {
  border-left: 4px solid #667eea;
}

.card.success {
  border-left: 4px solid #48bb78;
}

.card.warning {
  border-left: 4px solid #ed8936;
}

.card.error {
  border-left: 4px solid #f56565;
}

.card-header {
  padding: var(--card-padding);
  border-bottom: 1px solid #e5e7eb;
  background: #f9fafb;
}

.card-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #2c3e50;
}

.card-body {
  padding: var(--card-padding);
}

.card-footer {
  padding: var(--card-padding);
  border-top: 1px solid #e5e7eb;
  background: #f9fafb;
}
</style>


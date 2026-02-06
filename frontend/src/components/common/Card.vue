<template>
  <div :class="['card-base', 'card-hover', 'card-component', variant]" :style="customStyle">
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
/* 变体样式：左侧边框 */
.card-component.primary {
  border-left: 4px solid var(--color-primary);
}

.card-component.success {
  border-left: 4px solid var(--color-success);
}

.card-component.warning {
  border-left: 4px solid var(--color-primary);
}

.card-component.error {
  border-left: 4px solid var(--color-destructive);
}

.card-header {
  padding: var(--card-padding);
  border-bottom: 1px solid var(--color-border);
  background: var(--color-muted);
}

.card-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-foreground);
}

.card-body {
  padding: var(--card-padding);
}

.card-footer {
  padding: var(--card-padding);
  border-top: 1px solid var(--color-border);
  background: var(--color-muted);
}
</style>


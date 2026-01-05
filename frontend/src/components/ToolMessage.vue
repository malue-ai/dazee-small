<template>
  <div class="tool-message">
    <!-- 头部：折叠状态 -->
    <div class="tool-header" @click="toggle" :class="{ 'is-expanded': isExpanded, 'is-error': isError }">
      <div class="header-left">
        <span class="status-indicator" :class="status"></span>
        <span class="tool-name">{{ formatToolName(name) }}</span>
        <span class="status-text" v-if="isLoading">执行中...</span>
      </div>
      
      <div class="header-right">
        <span class="toggle-icon">{{ isExpanded ? '收起' : '详情' }}</span>
      </div>
    </div>
    
    <!-- 详情：展开状态 -->
    <div v-show="isExpanded" class="tool-body">
      <!-- 输入参数 -->
      <div class="section input-section">
        <div class="section-label">Input</div>
        <pre class="code-block">{{ formatJson(input) }}</pre>
      </div>
      
      <!-- 执行结果 -->
      <div class="section output-section" v-if="result">
        <div class="section-label">Output</div>
        <pre class="code-block" :class="{ 'error-text': isError }">{{ formatResult(result) }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  name: String,
  input: [Object, String],
  result: [Object, String],
  status: {
    type: String, // 'pending', 'success', 'error'
    default: 'pending'
  }
})

const isExpanded = ref(false)

const isLoading = computed(() => props.status === 'pending')
const isError = computed(() => props.status === 'error')

function toggle() {
  isExpanded.value = !isExpanded.value
}

function formatToolName(name) {
  if (!name) return 'System Tool'
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function formatJson(data) {
  if (!data) return '{}'
  try {
    const obj = typeof data === 'string' ? JSON.parse(data) : data
    return JSON.stringify(obj, null, 2)
  } catch {
    return data
  }
}

function formatResult(data) {
  if (!data) return ''
  return formatJson(data)
}
</script>

<style scoped>
.tool-message {
  margin: 12px 0;
  border-radius: 8px;
  overflow: hidden;
  font-family: 'Inter', system-ui, sans-serif;
  border: 1px solid #e5e7eb;
  background: #ffffff;
}

.tool-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: #f9fafb;
  cursor: pointer;
  transition: background 0.2s;
  user-select: none;
}

.tool-header:hover {
  background: #f3f4f6;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: #374151;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #d1d5db;
}

.status-indicator.pending {
  background: #fbbf24;
  animation: pulse 1.5s infinite;
}

.status-indicator.success {
  background: #10b981;
}

.status-indicator.error {
  background: #ef4444;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.tool-name {
  font-weight: 500;
  color: #111827;
}

.status-text {
  color: #9ca3af;
  font-size: 12px;
}

.header-right {
  font-size: 12px;
  color: #9ca3af;
}

.tool-body {
  padding: 12px;
  background: #ffffff;
  border-top: 1px solid #e5e7eb;
}

.section {
  margin-bottom: 12px;
}

.section:last-child {
  margin-bottom: 0;
}

.section-label {
  font-size: 11px;
  color: #9ca3af;
  margin-bottom: 6px;
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.05em;
}

.code-block {
  margin: 0;
  padding: 10px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  color: #4b5563;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
}

.error-text {
  color: #ef4444;
  background: #fef2f2;
  border-color: #fee2e2;
}
</style>

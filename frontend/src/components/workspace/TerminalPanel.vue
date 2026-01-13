<template>
  <div class="terminal-panel" ref="panelRef">
    <div class="terminal-header">
      <div class="header-left">
        <span class="terminal-icon">_&gt;</span>
        <span class="terminal-title">TERMINAL</span>
      </div>
      <div class="header-right">
        <button @click="clearLogs" class="clear-btn" title="清除日志">
          <span class="icon">🚫</span>
        </button>
        <button @click="$emit('close')" class="close-btn" title="关闭">
          <span class="icon">✕</span>
        </button>
      </div>
    </div>
    
    <div class="terminal-content" ref="contentRef">
      <div v-if="logs.length === 0" class="empty-state">
        <span class="prompt">user@sandbox:~$</span> <span class="cursor">_</span>
      </div>
      
      <div v-for="(log, index) in logs" :key="index" class="log-entry">
        <!-- 命令输入 -->
        <div v-if="log.type === 'command'" class="command-line">
          <span class="prompt">user@sandbox:{{ formatCwd(log.cwd) }}$</span>
          <span class="command">{{ log.content }}</span>
        </div>
        
        <!-- 命令输出 -->
        <div v-else-if="log.type === 'output'" class="output-line">
          <pre>{{ log.content }}</pre>
        </div>
        
        <!-- 错误输出 -->
        <div v-else-if="log.type === 'error'" class="error-line">
          <pre>{{ log.content }}</pre>
        </div>
        
        <!-- 信息/提示 -->
        <div v-else-if="log.type === 'info'" class="info-line">
          <span class="info-icon">ℹ️</span> {{ log.content }}
        </div>
      </div>
      
      <!-- 正在运行的命令指示器 -->
      <div v-if="isRunning" class="running-line">
        <span class="prompt">user@sandbox:~$</span>
        <span class="running-indicator">
          <span class="dot">.</span><span class="dot">.</span><span class="dot">.</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, nextTick, computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'

const props = defineProps({
  logs: {
    type: Array,
    default: () => []
  },
  isRunning: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close', 'clear'])
const workspaceStore = useWorkspaceStore()
const contentRef = ref(null)

// 自动滚动到底部
const scrollToBottom = async () => {
  await nextTick()
  if (contentRef.value) {
    contentRef.value.scrollTop = contentRef.value.scrollHeight
  }
}

// 监听日志变化
watch(() => props.logs, () => {
  scrollToBottom()
}, { deep: true })

// 监听运行状态
watch(() => props.isRunning, () => {
  scrollToBottom()
})

onMounted(() => {
  scrollToBottom()
})

const clearLogs = () => {
  emit('clear')
}

const formatCwd = (cwd) => {
  if (!cwd || cwd === '/home/user') return '~'
  if (cwd.startsWith('/home/user/')) return '~/' + cwd.substring(11)
  return cwd
}
</script>

<style scoped>
.terminal-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: #0d1117;
  color: #c9d1d9;
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 13px;
  overflow: hidden;
}

.terminal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background-color: #161b22;
  border-bottom: 1px solid #30363d;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.terminal-icon {
  color: #58a6ff;
  font-weight: bold;
}

.terminal-title {
  font-weight: 600;
  font-size: 12px;
  color: #8b949e;
  letter-spacing: 0.5px;
}

.header-right {
  display: flex;
  gap: 4px;
}

.clear-btn, .close-btn {
  background: transparent;
  border: none;
  color: #8b949e;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.clear-btn:hover, .close-btn:hover {
  background-color: #21262d;
  color: #c9d1d9;
}

.terminal-content {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.log-entry {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.command-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  color: #e6edf3;
  margin-top: 8px;
}

.prompt {
  color: #58a6ff; /* Blue prompt */
  font-weight: 600;
  white-space: nowrap;
}

.command {
  color: #e6edf3;
  word-break: break-all;
}

.output-line pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  color: #8b949e; /* Muted text for output */
  padding-left: 0;
}

.error-line pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  color: #ff7b72; /* Red for errors */
}

.info-line {
  color: #2f81f7;
  font-style: italic;
  margin: 4px 0;
}

.empty-state {
  color: #8b949e;
}

.cursor {
  animation: blink 1s step-end infinite;
}

.running-line {
  margin-top: 4px;
}

.running-indicator .dot {
  animation: blink 1.4s infinite both;
}

.running-indicator .dot:nth-child(2) { animation-delay: 0.2s; }
.running-indicator .dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* Scrollbar styling */
.terminal-content::-webkit-scrollbar {
  width: 8px;
}

.terminal-content::-webkit-scrollbar-track {
  background: #0d1117;
}

.terminal-content::-webkit-scrollbar-thumb {
  background: #30363d;
  border-radius: 4px;
}

.terminal-content::-webkit-scrollbar-thumb:hover {
  background: #484f58;
}
</style>


<template>
  <!-- 浮动触发按钮 -->
  <button
    v-if="!logStore.visible"
    @click="toggleDebugPanel"
    class="fixed bottom-4 right-4 z-[9999] w-10 h-10 rounded-full flex items-center justify-center shadow-lg transition-all hover:scale-110"
    :class="logStore.hasError
      ? 'bg-red-500 text-white animate-pulse'
      : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700'"
    title="调试面板"
  >
    <Terminal class="w-4 h-4" />
    <!-- 未读徽标 -->
    <span
      v-if="logStore.unreadCount > 0"
      class="absolute -top-1 -right-1 min-w-[18px] h-[18px] rounded-full bg-blue-500 text-white text-[10px] font-bold flex items-center justify-center px-1"
    >
      {{ logStore.unreadCount > 99 ? '99+' : logStore.unreadCount }}
    </span>
  </button>

  <!-- 调试面板 -->
  <Teleport to="body">
    <div
      v-if="logStore.visible"
      class="fixed bottom-0 right-0 z-[9999] w-full sm:w-[560px] h-[400px] flex flex-col bg-zinc-900 border-t border-l border-zinc-700 rounded-tl-xl shadow-2xl"
    >
      <!-- 标题栏 -->
      <div class="flex items-center justify-between px-4 py-2 border-b border-zinc-700 bg-zinc-800/80 rounded-tl-xl select-none">
        <div class="flex items-center gap-2 text-zinc-300 text-sm font-medium">
          <Terminal class="w-3.5 h-3.5" />
          <span>调试日志</span>
          <span class="text-[10px] text-zinc-500">({{ filteredEntries.length }})</span>
        </div>
        <div class="flex items-center gap-1">
          <!-- 模块过滤器 -->
          <select
            v-model="filterModule"
            class="bg-zinc-700 text-zinc-300 text-xs rounded px-1.5 py-1 border-none outline-none cursor-pointer"
          >
            <option value="ALL">全部模块</option>
            <option value="APP">APP</option>
            <option value="API">API</option>
            <option value="SSE">SSE</option>
            <option value="WS">WS</option>
            <option value="STORE">STORE</option>
            <option value="ROUTER">ROUTER</option>
            <option value="TAURI">TAURI</option>
          </select>
          <!-- 级别过滤器 -->
          <select
            v-model="filterLevel"
            class="bg-zinc-700 text-zinc-300 text-xs rounded px-1.5 py-1 border-none outline-none cursor-pointer"
          >
            <option value="ALL">全部级别</option>
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARN">WARN</option>
            <option value="ERROR">ERROR</option>
          </select>
          <!-- 清除 -->
          <button
            @click="clearLogs"
            class="text-zinc-400 hover:text-zinc-200 p-1 rounded hover:bg-zinc-700 transition-colors"
            title="清除日志"
          >
            <Trash2 class="w-3.5 h-3.5" />
          </button>
          <!-- 关闭 -->
          <button
            @click="toggleDebugPanel"
            class="text-zinc-400 hover:text-zinc-200 p-1 rounded hover:bg-zinc-700 transition-colors"
            title="关闭面板"
          >
            <X class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <!-- 日志列表 -->
      <div
        ref="logListRef"
        class="flex-1 overflow-y-auto overflow-x-hidden font-mono text-[11px] leading-5"
        @scroll="onScroll"
      >
        <div v-if="filteredEntries.length === 0" class="p-4 text-zinc-500 text-center text-xs">
          暂无日志
        </div>
        <div
          v-for="entry in filteredEntries"
          :key="entry.id"
          class="flex gap-2 px-3 py-0.5 border-b border-zinc-800/50 hover:bg-zinc-800/40 cursor-default"
          :class="entryRowClass(entry.level)"
        >
          <!-- 时间 -->
          <span class="text-zinc-500 flex-shrink-0 w-[60px]">{{ formatTime(entry.timestamp) }}</span>
          <!-- 级别 -->
          <span class="flex-shrink-0 w-[42px] font-semibold" :class="levelClass(entry.level)">
            {{ entry.level }}
          </span>
          <!-- 模块 -->
          <span class="flex-shrink-0 w-[50px] text-zinc-400">{{ entry.module }}</span>
          <!-- 消息 -->
          <span class="text-zinc-200 break-all flex-1">
            {{ entry.message }}
            <button
              v-if="entry.data !== undefined"
              @click="expandedId = expandedId === entry.id ? null : entry.id"
              class="ml-1 text-blue-400 hover:text-blue-300 text-[10px]"
            >
              {{ expandedId === entry.id ? '[-]' : '[+]' }}
            </button>
          </span>
        </div>
        <!-- 展开的数据 -->
        <div
          v-for="entry in filteredEntries.filter(e => e.id === expandedId && e.data !== undefined)"
          :key="'data-' + entry.id"
          class="px-3 py-2 bg-zinc-800 border-b border-zinc-700"
        >
          <pre class="text-[10px] text-emerald-400 whitespace-pre-wrap break-all max-h-[200px] overflow-y-auto">{{ formatData(entry.data) }}</pre>
        </div>
      </div>

      <!-- 底部状态栏 -->
      <div class="flex items-center justify-between px-3 py-1 border-t border-zinc-700 bg-zinc-800/60 text-[10px] text-zinc-500">
        <span>共 {{ logStore.entries.length }} 条</span>
        <div class="flex items-center gap-2">
          <label class="flex items-center gap-1 cursor-pointer">
            <input type="checkbox" v-model="autoScroll" class="w-3 h-3 accent-blue-500" />
            自动滚动
          </label>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { Terminal, X, Trash2 } from 'lucide-vue-next'
import { logStore, toggleDebugPanel, clearLogs } from '@/utils/logger'
import type { LogLevel, LogModule } from '@/utils/logger'

// ==================== 状态 ====================

const filterModule = ref<LogModule | 'ALL'>('ALL')
const filterLevel = ref<LogLevel | 'ALL'>('ALL')
const autoScroll = ref(true)
const expandedId = ref<number | null>(null)
const logListRef = ref<HTMLElement | null>(null)

// ==================== 计算属性 ====================

const filteredEntries = computed(() => {
  return logStore.entries.filter(entry => {
    if (filterModule.value !== 'ALL' && entry.module !== filterModule.value) return false
    if (filterLevel.value !== 'ALL' && entry.level !== filterLevel.value) return false
    return true
  })
})

// ==================== 自动滚动 ====================

watch(
  () => logStore.entries.length,
  () => {
    if (autoScroll.value && logListRef.value) {
      nextTick(() => {
        if (logListRef.value) {
          logListRef.value.scrollTop = logListRef.value.scrollHeight
        }
      })
    }
  }
)

function onScroll() {
  if (!logListRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = logListRef.value
  // 如果用户手动滚动到非底部，关闭自动滚动
  autoScroll.value = scrollHeight - scrollTop - clientHeight < 30
}

// ==================== 格式化 ====================

function formatTime(ts: number): string {
  const d = new Date(ts)
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  const s = String(d.getSeconds()).padStart(2, '0')
  return `${h}:${m}:${s}`
}

function formatData(data: unknown): string {
  try {
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

function levelClass(level: LogLevel): string {
  switch (level) {
    case 'ERROR': return 'text-red-400'
    case 'WARN': return 'text-yellow-400'
    case 'INFO': return 'text-blue-400'
    case 'DEBUG': return 'text-zinc-500'
  }
}

function entryRowClass(level: LogLevel): string {
  if (level === 'ERROR') return 'bg-red-950/20'
  if (level === 'WARN') return 'bg-yellow-950/10'
  return ''
}
</script>

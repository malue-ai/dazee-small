<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, RefreshCw, X, Trash2, Loader2 } from 'lucide-vue-next'
import { useBackgroundTaskStore, type StatusFilter } from '@/stores/backgroundTask'

const router = useRouter()
const store = useBackgroundTaskStore()

const statusTabs: { label: string; value: StatusFilter }[] = [
  { label: '全部', value: 'all' },
  { label: '运行中', value: 'running' },
  { label: '已完成', value: 'completed' },
  { label: '失败', value: 'failed' },
  { label: '已取消', value: 'cancelled' },
]

function statusLabel(status: string) {
  const map: Record<string, string> = {
    queued: '排队中',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return map[status] || status
}

function statusColor(status: string) {
  const map: Record<string, string> = {
    queued: 'text-yellow-500',
    running: 'text-blue-500',
    completed: 'text-green-500',
    failed: 'text-red-500',
    cancelled: 'text-muted-foreground',
  }
  return map[status] || 'text-muted-foreground'
}

function formatDuration(ms: number) {
  if (ms < 1000) return `${ms}ms`
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

onMounted(() => store.startPolling(3000))
onUnmounted(() => store.stopPolling())
</script>

<template>
  <div class="min-h-screen bg-background">
    <!-- Header -->
    <div class="sticky top-0 z-10 bg-background/80 backdrop-blur-sm border-b border-border">
      <div class="max-w-4xl mx-auto px-6 py-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <button
              @click="router.push('/')"
              class="p-1.5 rounded-lg hover:bg-muted transition-colors"
            >
              <ArrowLeft class="w-5 h-5" />
            </button>
            <h1 class="text-xl font-semibold">后台任务</h1>
            <span class="text-sm text-muted-foreground">({{ store.total }})</span>
          </div>
          <button
            @click="store.fetchTasks()"
            :disabled="store.loading"
            class="p-2 rounded-lg hover:bg-muted transition-colors disabled:opacity-50"
          >
            <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': store.loading }" />
          </button>
        </div>

        <!-- Status Tabs -->
        <div class="flex gap-1 mt-3">
          <button
            v-for="tab in statusTabs"
            :key="tab.value"
            @click="store.setStatusFilter(tab.value)"
            class="px-3 py-1.5 text-sm rounded-md transition-colors"
            :class="store.statusFilter === tab.value
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:bg-muted'"
          >
            {{ tab.label }}
          </button>
        </div>
      </div>
    </div>

    <!-- Task List -->
    <div class="max-w-4xl mx-auto px-6 py-4">
      <!-- Empty State -->
      <div v-if="store.isEmpty" class="flex flex-col items-center justify-center py-20 text-muted-foreground">
        <div class="text-4xl mb-4">📋</div>
        <p class="text-lg font-medium">暂无后台任务</p>
        <p class="text-sm mt-1">Agent 使用 Pipeline 工具提交的后台任务会显示在这里</p>
      </div>

      <!-- Task Cards -->
      <div v-else class="space-y-3">
        <div
          v-for="task in store.filteredTasks"
          :key="task.task_id"
          class="border border-border rounded-xl p-4 hover:border-primary/30 transition-colors bg-card"
        >
          <div class="flex items-start justify-between">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <Loader2 v-if="task.status === 'running'" class="w-4 h-4 animate-spin text-blue-500 shrink-0" />
                <h3 class="font-medium truncate">{{ task.name }}</h3>
              </div>
              <p v-if="task.description" class="text-sm text-muted-foreground mt-1 truncate">
                {{ task.description }}
              </p>
            </div>

            <div class="flex items-center gap-2 shrink-0 ml-4">
              <span class="text-xs px-2 py-0.5 rounded-full border" :class="statusColor(task.status)">
                {{ statusLabel(task.status) }}
              </span>

              <button
                v-if="task.status === 'running' || task.status === 'queued'"
                @click="store.cancelTask(task.task_id)"
                class="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                title="取消"
              >
                <X class="w-4 h-4" />
              </button>

              <button
                v-if="task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled'"
                @click="store.removeTask(task.task_id)"
                class="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                title="删除"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>

          <!-- Progress Bar -->
          <div v-if="task.status === 'running' || task.status === 'queued'" class="mt-3">
            <div class="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>{{ task.progress_message || '执行中...' }}</span>
              <span>{{ Math.round(task.progress * 100) }}%</span>
            </div>
            <div class="h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                class="h-full bg-primary rounded-full transition-all duration-500"
                :style="{ width: `${Math.max(task.progress * 100, 2)}%` }"
              />
            </div>
          </div>

          <!-- Result / Error -->
          <div v-if="task.result_preview && task.status === 'completed'" class="mt-3 text-sm text-muted-foreground bg-muted/50 rounded-lg p-3">
            <p class="line-clamp-3">{{ task.result_preview }}</p>
          </div>
          <div v-if="task.error && task.status === 'failed'" class="mt-3 text-sm text-red-500 bg-red-500/5 rounded-lg p-3">
            <p class="line-clamp-2">{{ task.error }}</p>
          </div>

          <!-- Footer -->
          <div class="flex items-center justify-between mt-3 text-xs text-muted-foreground">
            <span>{{ task.created_at }}</span>
            <span v-if="task.elapsed_ms > 0">耗时 {{ formatDuration(task.elapsed_ms) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

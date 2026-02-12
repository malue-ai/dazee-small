<template>
  <div class="h-full flex flex-col overflow-hidden bg-background">
    <!-- Top toolbar -->
    <div class="h-14 flex items-center justify-between px-6 border-b border-border bg-background sticky top-0 z-10 flex-shrink-0">
      <div class="flex items-center gap-4">
        <!-- Back -->
        <router-link
          to="/"
          class="flex items-center gap-1.5 px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
        >
          <ArrowLeft class="w-4 h-4" />
          <span>返回</span>
        </router-link>

        <div class="w-px h-5 bg-border"></div>

        <!-- Status filter tabs -->
        <div class="flex items-center gap-1 bg-muted rounded-lg p-1">
          <button
            v-for="tab in statusTabs"
            :key="tab.value"
            @click="taskStore.setStatusFilter(tab.value)"
            class="px-3 py-1.5 rounded-md text-sm font-medium transition-all"
            :class="taskStore.statusFilter === tab.value
              ? 'bg-card text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground'"
          >
            {{ tab.label }}
          </button>
        </div>

        <!-- Count badge -->
        <div class="text-xs text-muted-foreground bg-muted px-2 py-1 rounded-md border border-border">
          {{ taskStore.total }} 个任务
        </div>
      </div>

      <!-- Refresh -->
      <button
        @click="taskStore.fetchTasks()"
        :disabled="taskStore.loading"
        class="flex items-center gap-1.5 px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
      >
        <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': taskStore.loading }" />
        <span>刷新</span>
      </button>
    </div>

    <!-- Main content -->
    <div class="flex-1 overflow-y-auto scrollbar-thin p-6">

      <!-- Loading -->
      <div v-if="taskStore.loading && taskStore.tasks.length === 0" class="flex items-center justify-center py-20">
        <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
      </div>

      <!-- Empty state -->
      <div v-else-if="taskStore.isEmpty" class="flex flex-col items-center justify-center py-20 text-muted-foreground/50">
        <div class="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mb-4 border border-border">
          <Clock class="w-8 h-8 opacity-30" />
        </div>
        <p class="text-sm font-medium text-muted-foreground mb-1">暂无定时任务</p>
        <p class="text-xs text-muted-foreground/60">在聊天中让 AI 为你创建定时提醒或定期任务</p>
      </div>

      <!-- Task list -->
      <div v-else class="max-w-4xl mx-auto space-y-3">
        <div
          v-for="task in taskStore.tasks"
          :key="task.id"
          class="bg-card border border-border rounded-2xl p-5 hover:shadow-sm transition-all"
        >
          <!-- Header row -->
          <div class="flex items-start justify-between gap-4 mb-3">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <h3 class="text-sm font-medium text-foreground truncate">{{ task.title }}</h3>
                <span
                  class="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-lg flex-shrink-0"
                  :class="statusClass(task.status)"
                >
                  {{ statusLabel(task.status) }}
                </span>
              </div>
              <p v-if="task.description" class="text-xs text-muted-foreground line-clamp-2">{{ task.description }}</p>
            </div>

            <!-- Action buttons -->
            <div class="flex items-center gap-1 flex-shrink-0">
              <!-- Pause (active -> paused) -->
              <button
                v-if="task.status === 'active'"
                @click="handlePause(task.id)"
                class="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
                title="暂停"
              >
                <Pause class="w-4 h-4" />
              </button>
              <!-- Resume (paused -> active) -->
              <button
                v-if="task.status === 'paused'"
                @click="handleResume(task.id)"
                class="p-1.5 text-primary hover:text-primary-hover hover:bg-accent rounded-lg transition-colors"
                title="恢复"
              >
                <Play class="w-4 h-4" />
              </button>
              <!-- Cancel (active/paused -> cancelled) -->
              <button
                v-if="task.status === 'active' || task.status === 'paused'"
                @click="handleCancel(task.id, task.title)"
                class="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
                title="取消"
              >
                <XCircle class="w-4 h-4" />
              </button>
              <!-- Delete (any status) -->
              <button
                @click="handleDelete(task.id, task.title)"
                class="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
                title="删除"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>

          <!-- Meta row -->
          <div class="flex items-center gap-4 text-xs text-muted-foreground">
            <!-- Trigger type badge -->
            <span class="inline-flex items-center gap-1 px-2 py-0.5 bg-muted rounded-lg">
              <component :is="triggerIcon(task.trigger_type)" class="w-3 h-3" />
              {{ triggerLabel(task) }}
            </span>

            <!-- Action type -->
            <span class="inline-flex items-center gap-1">
              <component :is="actionIcon(task.action)" class="w-3 h-3" />
              {{ actionLabel(task.action) }}
            </span>

            <!-- Next run -->
            <span v-if="task.next_run_at" class="inline-flex items-center gap-1">
              <CalendarClock class="w-3 h-3" />
              下次: {{ formatDateTime(task.next_run_at) }}
            </span>

            <!-- Last run -->
            <span v-if="task.last_run_at" class="inline-flex items-center gap-1">
              <CheckCircle class="w-3 h-3 text-success" />
              上次: {{ formatDateTime(task.last_run_at) }}
            </span>

            <!-- Run count -->
            <span v-if="task.run_count > 0" class="inline-flex items-center gap-1">
              已执行 {{ task.run_count }} 次
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Confirm modal -->
    <Teleport to="body">
      <div
        v-if="confirmModal.show"
        class="fixed inset-0 z-50 flex items-center justify-center"
      >
        <div class="absolute inset-0 bg-black/30 backdrop-blur-sm" @click="confirmModal.show = false"></div>
        <div class="relative bg-card border border-border rounded-3xl shadow-2xl p-6 w-[360px] max-w-[90vw]">
          <h3 class="text-sm font-medium text-foreground mb-2">{{ confirmModal.title }}</h3>
          <p class="text-xs text-muted-foreground mb-5">{{ confirmModal.message }}</p>
          <div class="flex justify-end gap-2">
            <button
              @click="confirmModal.show = false"
              class="px-4 py-2 text-sm text-muted-foreground hover:text-foreground bg-muted hover:bg-muted/80 rounded-xl transition-colors"
            >
              取消
            </button>
            <button
              @click="confirmModal.onConfirm(); confirmModal.show = false"
              class="px-4 py-2 text-sm text-white bg-destructive hover:bg-destructive/90 rounded-xl transition-colors"
            >
              确认
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { useScheduledTaskStore, type StatusFilter } from '@/stores/scheduledTask'
import type { ScheduledTask } from '@/api/scheduledTasks'
import {
  ArrowLeft,
  RefreshCw,
  Loader2,
  Clock,
  Pause,
  Play,
  XCircle,
  Trash2,
  CalendarClock,
  CheckCircle,
  Timer,
  Repeat,
  MessageSquare,
  Bot,
} from 'lucide-vue-next'

const taskStore = useScheduledTaskStore()

// ==================== Status tabs ====================

const statusTabs: { label: string; value: StatusFilter }[] = [
  { label: '全部', value: 'all' },
  { label: '活跃', value: 'active' },
  { label: '已暂停', value: 'paused' },
  { label: '已完成', value: 'completed' },
  { label: '已取消', value: 'cancelled' },
]

// ==================== Confirm modal ====================

const confirmModal = reactive({
  show: false,
  title: '',
  message: '',
  onConfirm: () => {},
})

function showConfirm(title: string, message: string, onConfirm: () => void) {
  confirmModal.title = title
  confirmModal.message = message
  confirmModal.onConfirm = onConfirm
  confirmModal.show = true
}

// ==================== Actions ====================

function handlePause(taskId: string) {
  taskStore.pauseTask(taskId)
}

function handleResume(taskId: string) {
  taskStore.resumeTask(taskId)
}

function handleCancel(taskId: string, title: string) {
  showConfirm(
    '取消任务',
    `确定要取消任务「${title}」吗？取消后将不再执行。`,
    () => taskStore.cancelTask(taskId),
  )
}

function handleDelete(taskId: string, title: string) {
  showConfirm(
    '删除任务',
    `确定要永久删除任务「${title}」吗？此操作不可恢复。`,
    () => taskStore.deleteTask(taskId),
  )
}

// ==================== Formatters ====================

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    active: '活跃',
    paused: '已暂停',
    completed: '已完成',
    cancelled: '已取消',
  }
  return map[status] || status
}

function statusClass(status: string): string {
  const map: Record<string, string> = {
    active: 'bg-success/10 text-success',
    paused: 'bg-primary/10 text-primary',
    completed: 'bg-muted text-muted-foreground',
    cancelled: 'bg-destructive/10 text-destructive',
  }
  return map[status] || 'bg-muted text-muted-foreground'
}

function triggerLabel(task: ScheduledTask): string {
  if (task.trigger_type === 'once' && task.run_at) {
    return `单次: ${formatDateTime(task.run_at)}`
  }
  if (task.trigger_type === 'cron' && task.cron_expr) {
    return `Cron: ${task.cron_expr}`
  }
  if (task.trigger_type === 'interval' && task.interval_seconds) {
    return `间隔: ${formatInterval(task.interval_seconds)}`
  }
  return task.trigger_type
}

function triggerIcon(triggerType: string) {
  if (triggerType === 'cron') return Repeat
  if (triggerType === 'interval') return Timer
  return Clock
}

function actionLabel(action: Record<string, unknown>): string {
  const type = (action?.type as string) || 'send_message'
  if (type === 'agent_task') return 'Agent 任务'
  return '提醒消息'
}

function actionIcon(action: Record<string, unknown>) {
  const type = (action?.type as string) || 'send_message'
  if (type === 'agent_task') return Bot
  return MessageSquare
}

function formatDateTime(iso: string): string {
  try {
    const d = new Date(iso)
    const now = new Date()
    const isToday = d.toDateString() === now.toDateString()
    const tomorrow = new Date(now)
    tomorrow.setDate(tomorrow.getDate() + 1)
    const isTomorrow = d.toDateString() === tomorrow.toDateString()

    const time = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })

    if (isToday) return `今天 ${time}`
    if (isTomorrow) return `明天 ${time}`
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) + ' ' + time
  } catch {
    return iso
  }
}

function formatInterval(seconds: number): string {
  if (seconds < 60) return `${seconds}秒`
  if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}小时`
  return `${Math.round(seconds / 86400)}天`
}

// ==================== Lifecycle ====================

onMounted(() => {
  taskStore.fetchTasks()
})
</script>

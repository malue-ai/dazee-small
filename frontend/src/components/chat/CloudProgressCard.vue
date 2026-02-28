<template>
  <div class="cloud-progress-card rounded-lg border border-border bg-card/80 backdrop-blur-sm overflow-hidden mt-3">
    <!-- 头部 -->
    <div class="flex items-center justify-between px-4 py-2.5 border-b border-border/60 bg-muted/30">
      <div class="flex items-center gap-2">
        <div class="w-5 h-5 rounded-full flex items-center justify-center bg-primary/10">
          <Cloud class="w-3 h-3 text-primary" />
        </div>
        <span class="text-xs font-semibold text-foreground">云端任务</span>
        <span
          class="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
          :class="statusBadgeClass"
        >{{ statusLabel }}</span>
      </div>

      <!-- 取消按钮（仅运行中显示）-->
      <button
        v-if="isRunning && taskId"
        class="text-xs text-muted-foreground hover:text-destructive transition-colors px-2 py-0.5 rounded hover:bg-destructive/10"
        :disabled="canceling"
        @click="handleCancel"
      >
        {{ canceling ? '取消中...' : '取消' }}
      </button>
    </div>

    <!-- 时间线 -->
    <div class="px-4 py-3 space-y-2">
      <div
        v-for="(item, index) in displayItems"
        :key="index"
        class="flex items-start gap-2.5"
      >
        <!-- 状态图标 -->
        <div class="mt-0.5 flex-shrink-0">
          <!-- 提交 -->
          <div v-if="item.phase === 'submitted'" class="w-4 h-4 rounded-full bg-muted flex items-center justify-center">
            <span class="w-1.5 h-1.5 rounded-full bg-muted-foreground"></span>
          </div>
          <!-- 思考中 -->
          <div v-else-if="item.phase === 'thinking'" class="w-4 h-4 rounded-full bg-primary/10 flex items-center justify-center">
            <Brain class="w-2.5 h-2.5 text-primary" />
          </div>
          <!-- 工具调用进行中 -->
          <div v-else-if="item.phase === 'tool_call' && item.status === 'running'" class="w-4 h-4 rounded-full bg-amber-500/10 flex items-center justify-center">
            <Loader2 class="w-2.5 h-2.5 text-amber-500 animate-spin" />
          </div>
          <!-- 工具调用完成 -->
          <div v-else-if="item.phase === 'tool_call' && item.status === 'done'" class="w-4 h-4 rounded-full bg-success/10 flex items-center justify-center">
            <Check class="w-2.5 h-2.5 text-success" />
          </div>
          <!-- 完成 -->
          <div v-else-if="item.phase === 'done'" class="w-4 h-4 rounded-full bg-success/15 flex items-center justify-center">
            <CheckCircle2 class="w-3 h-3 text-success" />
          </div>
          <!-- 错误 -->
          <div v-else-if="item.phase === 'error'" class="w-4 h-4 rounded-full bg-destructive/10 flex items-center justify-center">
            <XCircle class="w-2.5 h-2.5 text-destructive" />
          </div>
          <!-- 工作中 -->
          <div v-else class="w-4 h-4 rounded-full bg-primary/10 flex items-center justify-center">
            <Loader2 class="w-2.5 h-2.5 text-primary animate-spin" />
          </div>
        </div>

        <!-- 内容 -->
        <div class="flex-1 min-w-0">
          <p class="text-xs text-foreground leading-relaxed">{{ item.message }}</p>
          <p v-if="item.detail" class="text-[11px] text-muted-foreground mt-0.5 line-clamp-2">{{ item.detail }}</p>
        </div>
      </div>

      <!-- 加载动画（运行中且没有最后完成事件时） -->
      <div v-if="isRunning && !isDone" class="flex items-center gap-2 pt-1">
        <div class="flex gap-0.5 ml-1">
          <div class="w-1 h-1 rounded-full bg-primary/40 animate-bounce" style="animation-delay: 0ms"></div>
          <div class="w-1 h-1 rounded-full bg-primary/40 animate-bounce" style="animation-delay: 150ms"></div>
          <div class="w-1 h-1 rounded-full bg-primary/40 animate-bounce" style="animation-delay: 300ms"></div>
        </div>
        <span class="text-[11px] text-muted-foreground">执行中...</span>
      </div>
    </div>

    <!-- 进度条（有工具调用统计时显示）-->
    <div v-if="totalToolCalls > 0" class="px-4 pb-3">
      <div class="flex justify-between items-center mb-1">
        <span class="text-[10px] text-muted-foreground">工具调用进度</span>
        <span class="text-[10px] text-muted-foreground">{{ completedToolCalls }}/{{ totalToolCalls }}</span>
      </div>
      <div class="h-1 bg-muted rounded-full overflow-hidden">
        <div
          class="h-full bg-primary rounded-full transition-all duration-500"
          :style="{ width: progressPercent + '%' }"
        ></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Cloud,
  Brain,
  Check,
  CheckCircle2,
  XCircle,
  Loader2,
} from 'lucide-vue-next'
import type { CloudProgressItem } from '@/types'

const props = defineProps<{
  cloudProgress: CloudProgressItem[]
}>()

const canceling = ref(false)

// ==================== 计算属性 ====================

const taskId = computed(() => props.cloudProgress[0]?.task_id ?? null)

const isDone = computed(() =>
  props.cloudProgress.some(item => item.phase === 'done' || item.phase === 'error')
)

const isRunning = computed(() => !isDone.value)

/** 只显示关键事件，避免重复的 thinking 事件刷屏 */
const displayItems = computed(() => {
  const items = props.cloudProgress
  if (!items.length) return []

  const result: CloudProgressItem[] = []
  let lastPhase = ''
  let lastToolName = ''

  for (const item of items) {
    // submitted/done/error 始终显示
    if (item.phase === 'submitted' || item.phase === 'done' || item.phase === 'error') {
      result.push(item)
      lastPhase = item.phase
      continue
    }

    // tool_call：显示开始和结束，跳过重复的 running 状态
    if (item.phase === 'tool_call') {
      const key = `${item.tool_name}_${item.status}`
      if (key !== `${lastToolName}_${lastPhase}`) {
        result.push(item)
        lastToolName = item.tool_name ?? ''
        lastPhase = `${item.phase}_${item.status}`
      }
      continue
    }

    // thinking：只显示最新的一条
    if (item.phase === 'thinking') {
      const idx = result.findIndex(r => r.phase === 'thinking')
      if (idx >= 0) {
        result[idx] = item
      } else {
        result.push(item)
      }
      continue
    }

    // working：跳过（loading 动画已经表示进行中）
    if (item.phase === 'working') {
      continue
    }

    result.push(item)
  }

  return result
})

const lastItem = computed(() => props.cloudProgress[props.cloudProgress.length - 1])

const statusLabel = computed(() => {
  if (!props.cloudProgress.length) return '准备中'
  const phase = lastItem.value?.phase
  const map: Record<string, string> = {
    submitted: '已提交',
    working: '执行中',
    thinking: '思考中',
    tool_call: '调用工具',
    done: '已完成',
    error: '失败',
  }
  return map[phase] ?? '执行中'
})

const statusBadgeClass = computed(() => {
  const phase = lastItem.value?.phase
  if (phase === 'done') return 'bg-success/10 text-success'
  if (phase === 'error') return 'bg-destructive/10 text-destructive'
  return 'bg-primary/10 text-primary'
})

const toolCallItems = computed(() =>
  props.cloudProgress.filter(i => i.phase === 'tool_call')
)

const totalToolCalls = computed(() => {
  const last = [...props.cloudProgress].reverse().find(i => i.total !== undefined)
  return last?.total ?? 0
})

const completedToolCalls = computed(() => {
  const last = [...props.cloudProgress].reverse().find(i => i.completed !== undefined)
  return last?.completed ?? 0
})

const progressPercent = computed(() => {
  if (!totalToolCalls.value) return 0
  return Math.round((completedToolCalls.value / totalToolCalls.value) * 100)
})

// ==================== 操作 ====================

async function handleCancel() {
  if (!taskId.value || canceling.value) return
  canceling.value = true
  try {
    const token = localStorage.getItem('acp_token') ?? ''
    if (!token) return
    const cloudUrl = localStorage.getItem('acp_cloud_url') ?? ''
    await fetch(`${cloudUrl}/acp/tasks/${taskId.value}/state`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ action: 'cancel' }),
    })
  } catch (e) {
    console.warn('取消云端任务失败:', e)
  } finally {
    canceling.value = false
  }
}
</script>

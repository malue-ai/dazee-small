<template>
  <div class="cloud-progress-card bg-card rounded-2xl border border-border p-4 my-2">
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <Cloud class="w-4 h-4 text-primary" />
        <span class="text-sm font-medium text-foreground">云端执行</span>
        <span
          v-if="block.status === 'running'"
          class="inline-flex items-center gap-1 text-xs text-primary"
        >
          <span class="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
          进行中
        </span>
        <span v-else-if="block.status === 'completed'" class="text-xs text-success">
          已完成
        </span>
        <span v-else-if="block.status === 'failed'" class="text-xs text-destructive">
          失败
        </span>
        <span v-else-if="block.status === 'connecting'" class="text-xs text-muted-foreground">
          连接中...
        </span>
      </div>
      <span class="text-xs text-muted-foreground tabular-nums">
        {{ formattedElapsed }}
      </span>
    </div>

    <div v-if="block.steps.length > 0" class="space-y-1.5">
      <div
        v-for="step in block.steps"
        :key="step.id"
        class="flex items-center gap-2 text-xs"
      >
        <CheckCircle2
          v-if="step.status === 'done'"
          class="w-3.5 h-3.5 text-success flex-shrink-0"
        />
        <Loader2
          v-else-if="step.status === 'running'"
          class="w-3.5 h-3.5 text-primary flex-shrink-0 animate-spin"
        />
        <Circle
          v-else
          class="w-3.5 h-3.5 text-muted-foreground/40 flex-shrink-0"
        />
        <span
          class="truncate"
          :class="step.status === 'done' ? 'text-muted-foreground' : 'text-foreground'"
        >
          {{ step.label }}
        </span>
        <span v-if="step.detail" class="text-muted-foreground/60 truncate ml-auto">
          {{ step.detail }}
        </span>
      </div>
    </div>

    <div
      v-if="block.status === 'running'"
      class="mt-3 h-1 rounded-full bg-muted overflow-hidden"
    >
      <div class="h-full bg-primary/60 rounded-full animate-progress-bar" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Cloud, CheckCircle2, Loader2, Circle } from 'lucide-vue-next'
import type { CloudProgressContentBlock } from '@/types/chat'

const props = defineProps<{
  block: CloudProgressContentBlock
}>()

const formattedElapsed = computed(() => {
  const ms = props.block.elapsedMs || 0
  if (ms < 1000) return ''
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return `${m}m ${s % 60}s`
})
</script>

<style scoped>
@keyframes progress-indeterminate {
  0% { transform: translateX(-100%); width: 40%; }
  50% { width: 60%; }
  100% { transform: translateX(250%); width: 40%; }
}
.animate-progress-bar {
  animation: progress-indeterminate 2s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}
</style>

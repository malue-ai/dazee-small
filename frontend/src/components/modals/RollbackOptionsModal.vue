<template>
  <Teleport to="body">
    <div
      v-if="show"
      class="fixed inset-0 bg-foreground/50 backdrop-blur-md z-50 flex items-center justify-center p-6 animate-in fade-in duration-300"
      @click.self="emit('dismiss')"
    >
      <div
        class="bg-card rounded-3xl shadow-2xl w-full max-w-lg max-h-[85vh] overflow-hidden animate-in slide-in-from-bottom-8 duration-300 ring-1 ring-white/20 flex flex-col"
      >
        <div
          class="flex items-center justify-between px-8 py-5 border-b border-border bg-muted/50 flex-shrink-0"
        >
          <span class="text-lg font-bold text-foreground flex items-center gap-2">
            <RotateCcw class="w-6 h-6 text-primary" />
            任务异常，是否回滚？
          </span>
          <button
            class="p-2 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            @click="emit('dismiss')"
          >
            ✕
          </button>
        </div>

        <div class="p-8 space-y-4 overflow-y-auto flex-1">
          <p class="text-muted-foreground">
            以下操作可被撤销，回滚将恢复为任务开始前的状态。
          </p>
          <ul
            v-if="options?.length"
            class="space-y-2 text-sm text-foreground bg-muted/50 p-4 rounded-xl border border-border"
          >
            <li
              v-for="opt in options"
              :key="opt.id"
              class="flex items-center gap-2"
            >
              <span class="font-medium text-muted-foreground">{{ opt.action }}</span>
              <span class="truncate">{{ opt.target }}</span>
            </li>
          </ul>
          <p v-if="error" class="text-destructive text-sm">{{ error }}</p>
        </div>

        <div
          class="flex items-center justify-end gap-4 px-8 py-5 bg-muted/50 border-t border-border flex-shrink-0"
        >
          <button
            class="px-6 py-2.5 rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
            @click="emit('dismiss')"
            :disabled="loading"
          >
            保持当前状态
          </button>
          <button
            class="px-6 py-2.5 rounded-xl text-sm font-medium bg-primary text-white hover:bg-primary-hover transition-all shadow-lg shadow-primary/20 disabled:opacity-50"
            @click="emit('confirm')"
            :disabled="loading"
          >
            {{ loading ? '回滚中...' : '回滚' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { RotateCcw } from 'lucide-vue-next'

interface RollbackOption {
  id: string
  action: string
  target: string
}

defineProps<{
  show: boolean
  options?: RollbackOption[]
  error?: string
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'dismiss'): void
}>()
</script>

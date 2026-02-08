<template>
  <Teleport to="body">
    <div
      v-if="show"
      class="fixed inset-0 bg-foreground/50 backdrop-blur-md z-50 flex items-center justify-center p-6 animate-in fade-in duration-300"
      @click.self="emit('dismiss')"
    >
      <div
        class="bg-card rounded-3xl shadow-2xl w-full max-w-md overflow-hidden animate-in slide-in-from-bottom-8 duration-300 ring-1 ring-white/20 flex flex-col"
      >
        <div
          class="flex items-center justify-between px-8 py-5 border-b border-border bg-muted/50 flex-shrink-0"
        >
          <span class="text-lg font-bold text-foreground flex items-center gap-2">
            <Clock class="w-6 h-6 text-primary" />
            长任务确认
          </span>
          <button
            class="p-2 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            @click="emit('dismiss')"
          >
            ✕
          </button>
        </div>

        <div class="p-8">
          <p class="text-foreground">{{ data?.message ?? '任务已执行较多轮次，是否继续？' }}</p>
        </div>

        <div
          class="flex items-center justify-end gap-4 px-8 py-5 bg-muted/50 border-t border-border flex-shrink-0"
        >
          <button
            class="px-6 py-2.5 rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
            @click="emit('dismiss')"
          >
            停止
          </button>
          <button
            class="px-6 py-2.5 rounded-xl text-sm font-medium bg-primary text-white hover:bg-primary-hover transition-all shadow-lg shadow-primary/20"
            @click="emit('confirm')"
          >
            继续
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { Clock } from 'lucide-vue-next'

defineProps<{
  show: boolean
  data: { turn: number; message: string } | null
}>()

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'dismiss'): void
}>()
</script>

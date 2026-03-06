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
            <Maximize2 class="w-6 h-6 text-primary" />
            上下文窗口扩展
          </span>
          <button
            class="p-2 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            @click="emit('dismiss')"
          >
            ✕
          </button>
        </div>

        <div class="p-8 space-y-4">
          <p class="text-foreground whitespace-pre-line leading-relaxed">
            {{ data?.message ?? '上下文即将达到窗口上限，是否扩展？' }}
          </p>
        </div>

        <div
          class="flex items-center justify-end gap-3 px-8 py-5 bg-muted/50 border-t border-border flex-shrink-0"
        >
          <button
            class="px-5 py-2.5 rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
            @click="emit('dismiss')"
            :disabled="loading"
          >
            取消
          </button>
          <template v-for="opt in data?.options" :key="opt.id">
            <button
              v-if="opt.id === 'optimize'"
              class="px-5 py-2.5 rounded-xl text-sm font-medium bg-muted text-foreground hover:bg-muted/80 transition-colors"
              @click="emit('choose', 'optimize')"
              :disabled="loading"
            >
              {{ opt.label }}
            </button>
            <button
              v-else-if="opt.id === 'expand'"
              class="px-5 py-2.5 rounded-xl text-sm font-medium bg-primary text-white hover:bg-primary-hover transition-all shadow-lg shadow-primary/20"
              @click="emit('choose', 'expand')"
              :disabled="loading"
            >
              {{ loading ? '处理中...' : opt.label }}
            </button>
          </template>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { Maximize2 } from 'lucide-vue-next'

defineProps<{
  show: boolean
  data: {
    turn: number
    current_tokens: number
    current_budget: number
    expanded_budget: number
    usage_ratio: number
    standard_price: number
    extended_price: number
    message: string
    options: { id: string; label: string }[]
  } | null
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'choose', choice: 'expand' | 'optimize'): void
  (e: 'dismiss'): void
}>()
</script>

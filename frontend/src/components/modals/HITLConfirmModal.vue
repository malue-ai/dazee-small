<template>
  <Teleport to="body">
    <div
      v-if="show"
      class="fixed inset-0 bg-foreground/50 backdrop-blur-md z-50 flex items-center justify-center p-6 animate-in fade-in duration-300"
      @click.self="emit('reject')"
    >
      <div
        class="bg-card rounded-3xl shadow-2xl w-full max-w-lg max-h-[85vh] overflow-hidden animate-in slide-in-from-bottom-8 duration-300 ring-1 ring-white/20 flex flex-col"
      >
        <!-- 头部 -->
        <div
          class="flex items-center justify-between px-8 py-5 border-b border-border bg-destructive/5 flex-shrink-0"
        >
          <span class="text-lg font-bold text-foreground flex items-center gap-2">
            <ShieldAlert class="w-6 h-6 text-destructive" />
            危险操作确认
          </span>
          <button
            class="p-2 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            @click="emit('reject')"
          >
            ✕
          </button>
        </div>

        <!-- 内容区 -->
        <div class="p-8 space-y-5 overflow-y-auto flex-1">
          <!-- 提示信息 -->
          <p class="text-foreground leading-relaxed">
            {{ data?.message || '检测到危险操作，需要您的确认后才能继续执行。' }}
          </p>

          <!-- 原因说明 -->
          <div
            v-if="data?.reason"
            class="text-sm text-muted-foreground bg-destructive/5 p-4 rounded-xl border border-destructive/20 leading-relaxed"
          >
            <span class="font-medium text-foreground">原因：</span>{{ data.reason }}
          </div>

          <!-- 涉及的工具列表 -->
          <div v-if="data?.tools?.length" class="space-y-2">
            <p class="text-sm font-medium text-muted-foreground">涉及操作：</p>
            <ul class="space-y-1.5 text-sm bg-muted/50 p-4 rounded-xl border border-border">
              <li
                v-for="tool in data.tools"
                :key="tool"
                class="flex items-center gap-2 text-foreground"
              >
                <AlertTriangle class="w-3.5 h-3.5 text-destructive flex-shrink-0" />
                <code class="text-xs bg-muted px-1.5 py-0.5 rounded font-mono">{{ tool }}</code>
              </li>
            </ul>
          </div>
        </div>

        <!-- 底部按钮 -->
        <div
          class="flex items-center justify-end gap-4 px-8 py-5 bg-muted/50 border-t border-border flex-shrink-0"
        >
          <button
            class="px-6 py-2.5 rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
            @click="emit('reject')"
            :disabled="loading"
          >
            拒绝
          </button>
          <button
            class="px-6 py-2.5 rounded-xl text-sm font-medium bg-destructive text-white hover:bg-destructive/90 transition-all shadow-lg shadow-destructive/20 transform active:scale-95 disabled:opacity-50"
            @click="emit('approve')"
            :disabled="loading"
          >
            {{ loading ? '执行中...' : '批准执行' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ShieldAlert, AlertTriangle } from 'lucide-vue-next'

interface HITLConfirmData {
  reason: string
  tools: string[]
  message: string
}

defineProps<{
  show: boolean
  data: HITLConfirmData | null
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'approve'): void
  (e: 'reject'): void
}>()
</script>

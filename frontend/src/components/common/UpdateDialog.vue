<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div
        v-if="visible"
        class="fixed inset-0 bg-foreground/50 backdrop-blur-sm z-[9999] flex items-center justify-center p-6"
      >
        <div class="bg-card rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden animate-in slide-in-from-bottom-4 duration-200">
          <!-- 图标 + 内容 -->
          <div class="px-6 pt-6 pb-4 text-center">
            <!-- 发现新版本 -->
            <template v-if="phase === 'found'">
              <div class="w-12 h-12 mx-auto mb-4 rounded-full bg-primary/10 flex items-center justify-center">
                <ArrowUpCircle class="w-6 h-6 text-primary" />
              </div>
              <h3 class="text-base font-semibold text-foreground mb-2">发现新版本</h3>
              <p class="text-sm text-muted-foreground leading-relaxed">
                新版本 <span class="font-semibold text-foreground">v{{ version }}</span> 已发布，是否立即更新？
              </p>
              <div
                v-if="changelog"
                class="mt-3 max-h-32 overflow-y-auto text-left text-xs text-muted-foreground bg-muted/50 rounded-lg p-3 leading-relaxed whitespace-pre-wrap scrollbar-thin"
              >{{ changelog }}</div>
            </template>

            <!-- 下载中 -->
            <template v-else-if="phase === 'downloading'">
              <div class="w-12 h-12 mx-auto mb-4 rounded-full bg-primary/10 flex items-center justify-center">
                <Loader2 class="w-6 h-6 text-primary animate-spin" />
              </div>
              <h3 class="text-base font-semibold text-foreground mb-2">正在下载更新</h3>
              <p class="text-sm text-muted-foreground mb-3">v{{ version }}</p>
              <div class="w-full h-1.5 rounded-full bg-muted overflow-hidden">
                <div
                  class="h-full rounded-full bg-primary transition-all duration-300 ease-out"
                  :style="{ width: `${progress}%` }"
                />
              </div>
              <p class="text-xs text-muted-foreground mt-2 tabular-nums">{{ progress }}%</p>
            </template>

            <!-- 安装中 -->
            <template v-else-if="phase === 'installing'">
              <div class="w-12 h-12 mx-auto mb-4 rounded-full bg-primary/10 flex items-center justify-center">
                <Loader2 class="w-6 h-6 text-primary animate-spin" />
              </div>
              <h3 class="text-base font-semibold text-foreground mb-2">正在安装更新</h3>
              <p class="text-sm text-muted-foreground">即将重启应用…</p>
            </template>

            <!-- 出错 -->
            <template v-else-if="phase === 'error'">
              <div class="w-12 h-12 mx-auto mb-4 rounded-full bg-red-50 flex items-center justify-center">
                <XCircle class="w-6 h-6 text-red-500" />
              </div>
              <h3 class="text-base font-semibold text-foreground mb-2">更新失败</h3>
              <p class="text-sm text-muted-foreground leading-relaxed">{{ error }}</p>
            </template>
          </div>

          <!-- 按钮区 -->
          <div class="px-6 pb-6">
            <!-- 发现新版本：确认 / 稍后 -->
            <div v-if="phase === 'found'" class="flex gap-3">
              <button
                @click="emit('dismiss')"
                class="flex-1 px-4 py-2.5 text-sm font-medium text-muted-foreground bg-muted rounded-xl hover:bg-muted/80 transition-colors"
              >
                稍后再说
              </button>
              <button
                @click="emit('confirm')"
                class="flex-1 px-4 py-2.5 text-sm font-medium text-white bg-primary rounded-xl hover:bg-primary-hover transition-colors"
              >
                立即更新
              </button>
            </div>

            <!-- 出错：关闭 -->
            <div v-else-if="phase === 'error'" class="flex justify-center">
              <button
                @click="emit('dismiss')"
                class="px-6 py-2.5 text-sm font-medium text-muted-foreground bg-muted rounded-xl hover:bg-muted/80 transition-colors"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUpCircle, Loader2, XCircle } from 'lucide-vue-next'
import type { UpdatePhase } from '@/composables/useAutoUpdate'

interface Props {
  phase: UpdatePhase
  version: string
  changelog?: string
  progress?: number
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  changelog: '',
  progress: 0,
  error: '',
})

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'dismiss'): void
}>()

const visible = computed(() =>
  props.phase === 'found' ||
  props.phase === 'downloading' ||
  props.phase === 'installing' ||
  props.phase === 'error'
)
</script>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
</style>

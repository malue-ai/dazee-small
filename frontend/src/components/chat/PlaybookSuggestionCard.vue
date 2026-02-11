<template>
  <div>
    <Transition name="playbook-card">
      <div v-if="suggestion && !isDismissed" class="playbook-suggestion-card">
        <!-- 已接受状态 -->
        <div v-if="suggestion.user_action === 'accepted'" class="flex items-center gap-2 px-4 py-2.5">
          <CheckCircle2 class="w-4 h-4 text-success flex-shrink-0" />
          <span class="text-xs text-muted-foreground">已记住：{{ suggestion.name }}</span>
        </div>

        <!-- 待操作状态 -->
        <div v-else class="flex items-start gap-3 px-4 py-3">
          <!-- 图标 -->
          <div class="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
            <Lightbulb class="w-4 h-4 text-primary" />
          </div>

          <!-- 内容 -->
          <div class="flex-1 min-w-0">
            <p class="text-xs font-medium text-foreground leading-snug">
              学到了一个新技巧
            </p>
            <p class="text-xs text-muted-foreground mt-0.5 leading-relaxed">
              {{ suggestion.description || suggestion.strategy_summary }}
            </p>

            <!-- 操作按钮 -->
            <div class="flex items-center gap-2 mt-2.5">
              <button
                class="px-3 py-1 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary-hover transition-colors shadow-sm"
                :disabled="loading"
                @click="handleAccept"
              >
                {{ loading ? '...' : '记住' }}
              </button>
              <button
                class="px-3 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
                :disabled="loading"
                @click="handleDismiss"
              >
                忽略
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 成功提示 Toast -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-300 ease-out"
        enter-from-class="opacity-0 -translate-y-3"
        enter-to-class="opacity-100 translate-y-0"
        leave-active-class="transition duration-200 ease-in"
        leave-from-class="opacity-100 translate-y-0"
        leave-to-class="opacity-0 -translate-y-3"
      >
        <div
          v-if="showToast"
          class="fixed top-6 left-1/2 -translate-x-1/2 z-[9999] flex items-center gap-2.5 px-5 py-3 bg-card rounded-xl shadow-lg border border-border"
        >
          <CheckCircle2 class="w-5 h-5 text-green-500 flex-shrink-0" />
          <span class="text-sm font-medium text-foreground">已记住「{{ toastName }}」</span>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import type { PlaybookSuggestion } from '@/types'
import { Lightbulb, CheckCircle2 } from 'lucide-vue-next'

interface Props {
  suggestion: PlaybookSuggestion | null | undefined
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'accept'): void
  (e: 'dismiss'): void
}>()

const loading = ref(false)
const showToast = ref(false)
const toastName = ref('')

const isDismissed = computed(() => props.suggestion?.user_action === 'dismissed')

let toastTimer: ReturnType<typeof setTimeout> | null = null

/** 显示成功 Toast 并自动关闭 */
function triggerToast(name: string) {
  toastName.value = name
  showToast.value = true
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { showToast.value = false }, 2500)
}

async function handleAccept() {
  loading.value = true
  emit('accept')
  // Toast 不在此处弹出，而是等父组件 API 成功后 user_action 变为 'accepted' 再触发
}

function handleDismiss() {
  emit('dismiss')
}

// 监听 user_action 变为 'accepted'（父组件 API 调用成功后设置），此时再弹 Toast
watch(
  () => props.suggestion?.user_action,
  (newVal) => {
    if (newVal === 'accepted') {
      loading.value = false
      triggerToast(props.suggestion?.name || '新技巧')
    }
  }
)

// 组件销毁时清理定时器
onUnmounted(() => {
  if (toastTimer) clearTimeout(toastTimer)
})
</script>

<style scoped>
.playbook-suggestion-card {
  background: var(--color-background);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.2s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

/* 进入/离开动画 */
.playbook-card-enter-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.playbook-card-leave-active {
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.playbook-card-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.playbook-card-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>

<template>
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
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
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

const isDismissed = computed(() => props.suggestion?.user_action === 'dismissed')

async function handleAccept() {
  loading.value = true
  emit('accept')
  // loading 状态由父组件通过 suggestion.user_action 变更来解除
}

function handleDismiss() {
  emit('dismiss')
}
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

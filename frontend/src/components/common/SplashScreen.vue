<script setup lang="ts">
/**
 * SplashScreen — 应用加载画面
 *
 * 纯白背景 + 居中 logo + 淡出动画
 * 等待后端就绪后自动消失（最少显示 1s）
 * 实时显示 sidecar 启动进度（由 Rust 侧 emit sidecar-status 事件）
 */
import { ref, onMounted, onUnmounted } from 'vue'
import { waitForBackendReady, isBackendReady } from '@/api'
import { isTauriEnv } from '@/api/tauri'
import type { UnlistenFn } from '@tauri-apps/api/event'

const emit = defineEmits<{
  (e: 'done'): void
}>()

const fadeOut = ref(false)
const statusText = ref('正在启动...')

let unlistenStatus: UnlistenFn | null = null

onMounted(async () => {
  const minDisplayTime = new Promise<void>(r => setTimeout(r, 1000))

  if (isTauriEnv()) {
    statusText.value = '正在启动服务...'

    // 监听 Rust 侧发出的细粒度启动进度
    try {
      const { listen } = await import('@tauri-apps/api/event')
      unlistenStatus = await listen<string>('sidecar-status', (event) => {
        if (event.payload) {
          statusText.value = event.payload
        }
      })
    } catch {
      // 忽略监听失败（不影响启动流程）
    }

    // 等待后端 sidecar 就绪（同时保证最少显示 1s）
    await Promise.all([minDisplayTime, waitForBackendReady()])
    statusText.value = isBackendReady() ? '准备就绪' : '启动超时，请重试'
  } else {
    // 浏览器模式：等最少显示时间
    await minDisplayTime
    statusText.value = '准备就绪'
  }

  // 短暂停留让用户看到"准备就绪"
  await new Promise(r => setTimeout(r, 300))

  fadeOut.value = true
  // 等淡出动画结束后通知父组件
  setTimeout(() => emit('done'), 500)
})

onUnmounted(() => {
  unlistenStatus?.()
})
</script>

<template>
  <Transition name="splash-fade">
    <div
      v-if="!fadeOut"
      class="fixed inset-0 z-[9999] flex items-center justify-center bg-white"
    >
      <div class="flex flex-col items-center gap-5 splash-enter">
        <!-- Logo Mark -->
        <div class="w-14 h-14 rounded-2xl bg-primary flex items-center justify-center shadow-lg shadow-primary/20">
          <span class="text-2xl font-bold text-white tracking-tight">D</span>
        </div>
        <!-- Brand Name -->
        <span class="text-lg font-semibold text-foreground tracking-wide">
          xiaodazi
        </span>
        <!-- 状态文字 -->
        <span class="text-xs text-muted-foreground mt-1">
          {{ statusText }}
        </span>
        <!-- 加载指示器 -->
        <div class="flex gap-1 mt-1">
          <span class="dot dot-1"></span>
          <span class="dot dot-2"></span>
          <span class="dot dot-3"></span>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
/* 入场动画 */
.splash-enter {
  animation: splash-in 0.6s cubic-bezier(0.25, 0.46, 0.45, 0.94) both;
}

@keyframes splash-in {
  from {
    opacity: 0;
    transform: scale(0.92) translateY(8px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

/* 淡出过渡 */
.splash-fade-leave-active {
  transition: opacity 0.45s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

.splash-fade-leave-to {
  opacity: 0;
}

/* 加载小圆点 */
.dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background-color: var(--color-primary);
  opacity: 0.3;
  animation: dot-pulse 1.2s ease-in-out infinite;
}

.dot-1 { animation-delay: 0s; }
.dot-2 { animation-delay: 0.2s; }
.dot-3 { animation-delay: 0.4s; }

@keyframes dot-pulse {
  0%, 80%, 100% { opacity: 0.3; transform: scale(1); }
  40% { opacity: 1; transform: scale(1.3); }
}
</style>

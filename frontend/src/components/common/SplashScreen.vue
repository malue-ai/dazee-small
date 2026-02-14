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
        <div class="w-14 h-14 flex items-center justify-center">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 28 28" class="w-14 h-14">
            <path d="M27.46 7.27L27.29 6.65L27.23 6.47L27.11 6.11L26.93 5.65L26.68 5.1L26.49 4.73L26.12 4.12L25.96 3.89L25.84 3.73L25.35 3.14L24.77 2.57L24.66 2.48L24.53 2.37L23.89 1.89L23.43 1.6L23.04 1.39L22.15 0.99L22.1 0.97L22.08 0.96L22.03 0.94L21.08 0.63L20.73 0.54L20.16 0.41L19.99 0.38L19.39 0.27L18.82 0.19L18.57 0.16L18.04 0.11L17.59 0.08L17.12 0.05L16.69 0.03L16.3 0.02L15.73 0.01L15.35 0L14.97 0L14.37 0L13.63 0L13.03 0L12.65 0L12.27 0.01L11.7 0.02L11.31 0.03L10.88 0.05L10.41 0.08L9.96 0.11L9.43 0.16L9.18 0.19L8.61 0.27L8.01 0.38L7.84 0.41L7.27 0.54L6.92 0.63L5.97 0.94L5.93 0.96L5.9 0.97L5.85 0.99L4.97 1.39L4.58 1.6L4.12 1.89L3.47 2.36L3.34 2.47L3.23 2.57L2.65 3.14L2.16 3.73L2.04 3.89L1.88 4.12L1.51 4.72L1.32 5.1L1.07 5.64L0.89 6.11L0.77 6.47L0.71 6.64L0.54 7.27L0.43 7.73L0.41 7.84L0.38 8L0.23 8.89L0.19 9.21L0.15 9.61L0.1 10.12L0.07 10.57L0.04 11.08L0.03 11.42L0.02 11.94L0.01 12.48L0.01 12.77L0.01 13.31L0.01 14.68L0.01 15.22L0.01 15.51L0.02 16.05L0.03 16.57L0.04 16.91L0.07 17.42L0.1 17.87L0.15 18.39L0.19 18.79L0.23 19.1L0.38 19.99L0.41 20.15L0.43 20.26L0.54 20.72L0.71 21.35L0.77 21.52L0.89 21.88L1.07 22.35L1.32 22.89L1.51 23.26L1.88 23.87L2.04 24.1L2.16 24.26L2.65 24.85L3.23 25.42L3.34 25.52L3.47 25.63L4.11 26.1L4.58 26.39L4.96 26.6L5.84 27L5.9 27.02L5.92 27.03L5.97 27.04L6.91 27.35L7.27 27.45L7.84 27.58L8.01 27.61L8.61 27.72L9.17 27.79L9.42 27.82L9.96 27.87L10.41 27.91L10.88 27.94L11.3 27.95L11.7 27.97L12.27 27.98L12.65 27.98L13.02 27.98L13.63 27.98L14.37 27.98L14.97 27.98L15.34 27.98L15.73 27.98L16.3 27.97L16.69 27.95L17.11 27.94L17.59 27.91L18.04 27.87L18.57 27.82L18.82 27.79L19.38 27.72L19.98 27.61L20.16 27.58L20.73 27.45L21.08 27.35L22.02 27.04L22.07 27.03L22.09 27.02L22.15 27L23.03 26.6L23.42 26.39L23.88 26.1L24.52 25.63L24.66 25.52L24.77 25.42L25.35 24.85L25.84 24.26L25.95 24.1L26.11 23.87L26.48 23.26L26.68 22.89L26.92 22.35L27.1 21.88L27.23 21.52L27.28 21.35L27.46 20.72L27.56 20.26L27.58 20.15L27.62 19.99L27.76 19.1L27.8 18.79L27.85 18.39L27.9 17.87L27.93 17.42L27.95 16.91L27.96 16.57L27.98 16.05L27.99 15.51L27.99 15.22L27.99 14.68L27.99 13.32L27.99 12.77L27.99 12.49L27.98 11.95L27.96 11.43L27.95 11.08L27.93 10.58L27.9 10.13L27.85 9.61L27.8 9.21L27.76 8.9L27.62 8L27.58 7.84L27.57 7.73L27.46 7.27Z" fill="#6BFAC8"/>
            <path d="M21.44 16.24C21.44 18.54 20.72 20.33 19.3 21.61C17.93 22.86 16.09 23.48 13.79 23.48H6.13V11.15C6.13 8.87 6.84 7.08 8.26 5.78C9.63 4.54 11.48 3.91 13.79 3.91C16.09 3.91 17.93 4.54 19.3 5.78C20.72 7.08 21.44 8.87 21.44 11.15V16.24ZM13.79 21.68C15.45 21.68 16.79 21.21 17.82 20.28C18.88 19.31 19.41 18 19.41 16.35V11.15C19.41 9.5 18.88 8.19 17.82 7.22C16.79 6.28 15.45 5.81 13.79 5.81C12.12 5.81 10.77 6.28 9.75 7.22C8.68 8.19 8.15 9.5 8.15 11.15V21.68H13.79Z" fill="#181818"/>
            <path d="M15.31 12.25C15.31 11.98 15.41 11.76 15.6 11.58C15.79 11.4 16.02 11.31 16.29 11.31H17.06C17.18 11.31 17.28 11.4 17.28 11.52V12.75C17.28 13.02 17.19 13.25 17 13.43C16.81 13.61 16.57 13.7 16.29 13.7H15.53C15.41 13.7 15.31 13.6 15.31 13.48V12.25Z" fill="#181818"/>
            <path d="M12.69 12.25C12.69 11.98 12.59 11.76 12.4 11.58C12.21 11.4 11.98 11.31 11.71 11.31H10.94C10.82 11.31 10.72 11.4 10.72 11.52V12.75C10.72 13.02 10.81 13.25 11 13.43C11.19 13.61 11.43 13.7 11.71 13.7H12.47C12.59 13.7 12.69 13.6 12.69 13.48V12.25Z" fill="#181818"/>
          </svg>
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

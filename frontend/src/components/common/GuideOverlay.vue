<script setup lang="ts">
/**
 * GuideOverlay — 全局引导浮层
 *
 * 使用四块遮罩 + 高亮边框 + 提示气泡实现"聚光灯"引导效果。
 * 通过 Teleport 挂载到 body，确保层级在所有内容之上。
 * 目标区域留空，允许用户直接点击被高亮的元素。
 */
import { ref, computed, watch, onUnmounted } from 'vue'
import { useGuideStore } from '@/stores/guide'

const guideStore = useGuideStore()

const PADDING = 8   // 高亮区域向外扩展的像素
const GAP = 14       // 提示气泡与高亮区域的间距

// ==================== 目标元素位置追踪 ====================

const rect = ref<DOMRect | null>(null)

function updateRect() {
  if (guideStore.targetEl) {
    rect.value = guideStore.targetEl.getBoundingClientRect()
  } else {
    rect.value = null
  }
}

// 用 rAF 持续更新位置（兼容滚动、窗口缩放等场景）
let rafId: number | null = null

function startTracking() {
  function tick() {
    updateRect()
    rafId = requestAnimationFrame(tick)
  }
  rafId = requestAnimationFrame(tick)
}

function stopTracking() {
  if (rafId !== null) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
}

watch(() => guideStore.showOverlay, (show) => {
  if (show) {
    startTracking()
  } else {
    stopTracking()
    rect.value = null
  }
}, { immediate: true })

onUnmounted(stopTracking)

// ==================== 带 padding 的矩形 ====================

const padRect = computed(() => {
  if (!rect.value) return null
  return {
    top: rect.value.top - PADDING,
    left: rect.value.left - PADDING,
    right: rect.value.right + PADDING,
    bottom: rect.value.bottom + PADDING,
    width: rect.value.width + PADDING * 2,
    height: rect.value.height + PADDING * 2,
  }
})

// ==================== 四块遮罩样式 ====================

const topStyle = computed(() => {
  if (!padRect.value) return {}
  return { top: '0px', left: '0px', width: '100vw', height: `${Math.max(0, padRect.value.top)}px` }
})

const bottomStyle = computed(() => {
  if (!padRect.value) return {}
  return { top: `${padRect.value.bottom}px`, left: '0px', width: '100vw', bottom: '0px' }
})

const leftStyle = computed(() => {
  if (!padRect.value) return {}
  return { top: `${padRect.value.top}px`, left: '0px', width: `${Math.max(0, padRect.value.left)}px`, height: `${padRect.value.height}px` }
})

const rightStyle = computed(() => {
  if (!padRect.value) return {}
  return { top: `${padRect.value.top}px`, left: `${padRect.value.right}px`, right: '0px', height: `${padRect.value.height}px` }
})

// ==================== 高亮边框样式 ====================

const highlightStyle = computed(() => {
  if (!padRect.value) return {}
  return {
    top: `${padRect.value.top}px`,
    left: `${padRect.value.left}px`,
    width: `${padRect.value.width}px`,
    height: `${padRect.value.height}px`,
  }
})

// ==================== 提示气泡定位 ====================

/** 是否为浮动模式（无目标高亮） */
const isFloating = computed(() => guideStore.currentConfig?.floating ?? false)

const tooltipStyle = computed(() => {
  if (!guideStore.currentConfig) return {}

  // 浮动模式：左侧空白区域，不遮挡表单内容
  if (isFloating.value) {
    return {
      top: '40%',
      left: '32px',
      transform: 'translateY(-50%)',
    }
  }

  if (!padRect.value) return {}
  const pos = guideStore.currentConfig.position
  const p = padRect.value

  switch (pos) {
    case 'right':
      return { top: `${p.top}px`, left: `${p.right + GAP}px` }
    case 'left':
      return { top: `${p.top}px`, right: `${window.innerWidth - p.left + GAP}px` }
    case 'top':
      return { bottom: `${window.innerHeight - p.top + GAP}px`, left: `${p.left}px` }
    case 'bottom':
      return { top: `${p.bottom + GAP}px`, left: `${p.left}px` }
    default:
      return {}
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="guide-fade">
      <div v-if="guideStore.showOverlay" class="fixed inset-0 z-[10000] pointer-events-none">

        <!-- ====== 浮动模式：无遮罩，不阻挡用户操作 ====== -->
        <template v-if="isFloating">
          <!-- 不渲染任何遮罩，用户可自由操作页面 -->
        </template>

        <!-- ====== 普通模式：四块遮罩 + 高亮边框 ====== -->
        <template v-else-if="padRect">
          <div class="absolute bg-black/50 transition-all duration-200 pointer-events-auto" :style="topStyle" />
          <div class="absolute bg-black/50 transition-all duration-200 pointer-events-auto" :style="bottomStyle" />
          <div class="absolute bg-black/50 transition-all duration-200 pointer-events-auto" :style="leftStyle" />
          <div class="absolute bg-black/50 transition-all duration-200 pointer-events-auto" :style="rightStyle" />
          <div
            class="absolute rounded-lg pointer-events-none guide-highlight-ring"
            :style="highlightStyle"
          />
        </template>

        <!-- ====== 提示气泡（两种模式共用） ====== -->
        <div :style="tooltipStyle" class="absolute z-[10001] pointer-events-auto">
          <div class="bg-card border border-border rounded-xl shadow-2xl px-5 py-4 max-w-sm guide-tooltip">
            <!-- 进度指示器 -->
            <div v-if="guideStore.currentPhase" class="flex items-center gap-2 mb-2">
              <span class="text-[10px] font-semibold text-primary bg-primary/10 px-1.5 py-0.5 rounded">
                {{ guideStore.currentPhase.label }}
              </span>
              <div class="flex-1 h-1 bg-muted rounded-full overflow-hidden">
                <div
                  class="h-full bg-primary rounded-full transition-all duration-500"
                  :style="{ width: `${(guideStore.currentPhase.current / guideStore.currentPhase.total) * 100}%` }"
                />
              </div>
              <span class="text-[10px] text-muted-foreground tabular-nums">
                {{ guideStore.currentPhase.current }}/{{ guideStore.currentPhase.total }}
              </span>
            </div>

            <p class="text-sm text-foreground font-medium leading-relaxed">
              {{ guideStore.currentConfig?.tooltip }}
            </p>

            <!-- 校验错误提示 -->
            <p v-if="guideStore.validationError" class="text-xs text-destructive mt-1.5 animate-pulse">
              {{ guideStore.validationError }}
            </p>

            <div
              class="flex items-center mt-3"
              :class="guideStore.currentConfig?.showNextButton ? 'justify-between' : 'justify-end'"
            >
              <button
                v-if="guideStore.canSkip"
                @click="guideStore.skipGuide()"
                class="text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                跳过引导
              </button>
              <span v-else class="text-[10px] text-muted-foreground/60">
                请先完成配置
              </span>
              <button
                v-if="guideStore.currentConfig?.showNextButton"
                @click="guideStore.nextStep()"
                class="px-3 py-1.5 text-xs font-medium bg-primary text-white rounded-lg hover:opacity-90 transition-opacity"
              >
                下一步
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style>
/* 引导浮层淡入淡出 */
.guide-fade-enter-active,
.guide-fade-leave-active {
  transition: opacity 0.3s ease;
}
.guide-fade-enter-from,
.guide-fade-leave-to {
  opacity: 0;
}

/* 高亮边框脉冲动画 */
.guide-highlight-ring {
  box-shadow: 0 0 0 2px #6366f1, 0 0 12px 2px rgba(99, 102, 241, 0.3);
  animation: guide-pulse 2s ease-in-out infinite;
}

@keyframes guide-pulse {
  0%, 100% {
    box-shadow: 0 0 0 2px #6366f1, 0 0 12px 2px rgba(99, 102, 241, 0.3);
  }
  50% {
    box-shadow: 0 0 0 3px #6366f1, 0 0 20px 4px rgba(99, 102, 241, 0.5);
  }
}

/* 提示气泡入场动画 */
.guide-tooltip {
  animation: guide-tooltip-in 0.3s ease-out;
}

@keyframes guide-tooltip-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>

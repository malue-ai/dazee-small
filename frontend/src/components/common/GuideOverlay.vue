<script setup lang="ts">
/**
 * GuideOverlay — 全局引导浮层
 *
 * 使用四块遮罩 + 高亮边框 + 提示气泡实现"聚光灯"引导效果。
 * 通过 Teleport 挂载到 body，确保层级在所有内容之上。
 * 目标区域留空，允许用户直接点击被高亮的元素。
 */
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import { useGuideStore } from '@/stores/guide'

const guideStore = useGuideStore()

const PADDING = 8   // 高亮区域向外扩展的像素
const GAP = 14       // 提示气泡与高亮区域的间距
const TOOLTIP_ESTIMATED_HEIGHT = 160 // tooltip 估计高度（用于边界检测）

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
    removeScrollSpacer()
  }
}, { immediate: true })

onUnmounted(() => {
  stopTracking()
  removeScrollSpacer()
})

// ==================== 可滚动模式：底部占位空间 ====================

/** 是否为可滚动模式（遮罩不拦截交互，tooltip 固定位置） */
const isScrollable = computed(() => guideStore.currentConfig?.scrollable ?? false)

const SPACER_ID = 'guide-scroll-spacer'

/** 添加底部占位，让用户能滚动到 tooltip 下方 */
function ensureScrollSpacer() {
  if (document.getElementById(SPACER_ID)) return
  const spacer = document.createElement('div')
  spacer.id = SPACER_ID
  spacer.style.height = `${TOOLTIP_ESTIMATED_HEIGHT + GAP * 2}px`
  spacer.style.pointerEvents = 'none'
  document.body.appendChild(spacer)
}

/** 移除底部占位 */
function removeScrollSpacer() {
  document.getElementById(SPACER_ID)?.remove()
}

// 进入/离开 scrollable 步骤时管理占位
watch(isScrollable, (scrollable) => {
  if (scrollable) {
    ensureScrollSpacer()
  } else {
    removeScrollSpacer()
  }
}, { immediate: true })

// ==================== 自动滚动目标元素到可见区域 ====================

watch(
  [() => guideStore.targetEl, () => guideStore.currentStep],
  () => {
    const el = guideStore.targetEl
    if (!el || guideStore.currentConfig?.floating) return

    nextTick(() => {
      const elRect = el.getBoundingClientRect()
      const pos = guideStore.currentConfig?.position

      // 计算目标元素 + tooltip 所需的总空间是否在视口内
      const tooltipSpace = TOOLTIP_ESTIMATED_HEIGHT + GAP
      const needsBelow = pos === 'bottom'
      const needsAbove = pos === 'top'

      const visibleTop = elRect.top - (needsAbove ? tooltipSpace : PADDING)
      const visibleBottom = elRect.bottom + (needsBelow ? tooltipSpace : PADDING)

      if (visibleTop < 0 || visibleBottom > window.innerHeight) {
        // 滚动使目标元素居中，给 tooltip 留出空间
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    })
  },
  { flush: 'post' }
)

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

  // 可滚动模式：tooltip 紧贴高亮区域底部下方，不遮挡高亮内容
  if (isScrollable.value && padRect.value) {
    return {
      top: `${padRect.value.bottom + GAP}px`,
      left: '50%',
      transform: 'translateX(-50%)',
    }
  }

  if (!padRect.value) return {}
  const pos = guideStore.currentConfig.position
  const p = padRect.value
  const vh = window.innerHeight
  const vw = window.innerWidth

  // 辅助函数：限制 left 不超出视口右侧
  const clampLeft = (left: number) => Math.min(left, vw - 380) // 380 ≈ max-w-sm + padding

  const topSpace = p.top - GAP           // 目标上方可用空间
  const bottomSpace = vh - p.bottom - GAP // 目标下方可用空间
  const SAFE_TOP = 16                     // 视口顶部安全边距

  switch (pos) {
    case 'right':
      return { top: `${Math.max(SAFE_TOP, Math.min(p.top, vh - TOOLTIP_ESTIMATED_HEIGHT))}px`, left: `${p.right + GAP}px` }
    case 'left':
      return { top: `${Math.max(SAFE_TOP, Math.min(p.top, vh - TOOLTIP_ESTIMATED_HEIGHT))}px`, right: `${vw - p.left + GAP}px` }
    case 'top':
      if (topSpace >= TOOLTIP_ESTIMATED_HEIGHT) {
        return { bottom: `${vh - p.top + GAP}px`, left: `${clampLeft(p.left)}px` }
      }
      // 上方不够 → 尝试下方
      if (bottomSpace >= TOOLTIP_ESTIMATED_HEIGHT) {
        return { top: `${p.bottom + GAP}px`, left: `${clampLeft(p.left)}px` }
      }
      // 上下都不够 → 固定在视口顶部
      return { top: `${SAFE_TOP}px`, left: `${clampLeft(p.left)}px` }
    case 'bottom': {
      if (bottomSpace >= TOOLTIP_ESTIMATED_HEIGHT) {
        return { top: `${p.bottom + GAP}px`, left: `${clampLeft(p.left)}px` }
      }
      // 下方不够 → 尝试上方
      if (topSpace >= TOOLTIP_ESTIMATED_HEIGHT) {
        return { bottom: `${vh - p.top + GAP}px`, left: `${clampLeft(p.left)}px` }
      }
      // 上下都不够 → 固定在视口顶部
      return { top: `${SAFE_TOP}px`, left: `${clampLeft(p.left)}px` }
    }
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

        <!-- ====== 可滚动模式：遮罩仅视觉暗化，不拦截交互 ====== -->
        <template v-else-if="isScrollable && padRect">
          <div class="absolute bg-black/40 transition-all duration-200 pointer-events-none" :style="topStyle" />
          <div class="absolute bg-black/40 transition-all duration-200 pointer-events-none" :style="bottomStyle" />
          <div class="absolute bg-black/40 transition-all duration-200 pointer-events-none" :style="leftStyle" />
          <div class="absolute bg-black/40 transition-all duration-200 pointer-events-none" :style="rightStyle" />
          <div
            class="absolute rounded-lg pointer-events-none guide-highlight-ring"
            :style="highlightStyle"
          />
        </template>

        <!-- ====== 普通模式：四块遮罩 + 高亮边框（拦截交互） ====== -->
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
        <div :style="tooltipStyle" class="absolute z-[10001] pointer-events-auto" style="max-height: calc(100vh - 32px);">
          <div class="bg-card border border-border rounded-xl shadow-2xl px-5 py-4 max-w-sm guide-tooltip overflow-y-auto" style="max-height: calc(100vh - 48px);">
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
              {{ guideStore.tooltipOverride || guideStore.currentConfig?.tooltip }}
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

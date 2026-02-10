/**
 * Guide Store — 新手引导状态管理
 *
 * 管理分步交互式引导教程。
 *
 * == 设置阶段 ==
 * Step 1:  主页面 — 高亮设置按钮，引导进入设置
 * Step 2:  设置页 — 高亮 Provider 卡片，引导填写 API Key
 * Step 3:  设置页 — 高亮 Save Settings 按钮
 * Step 4:  设置页 — 高亮语义搜索区域，推荐配置本地模型（可选，可直接下一步）
 * Step 5:  设置页 — 高亮 Back to Chat 链接
 *
 * == 创建项目阶段 ==
 * Step 6:  主页面 — 高亮"新建项目"按钮
 * Step 7:  创建项目页 — 打字机自动输入（无遮罩）
 * Step 8:  创建项目页 — 高亮左侧对话面板（含发送按钮），用户直接点击发送
 * Step 9:  创建项目页 — 高亮配置区域，引导查看/修改配置
 * Step 10: 创建项目页 — 高亮"创建"按钮
 *
 * == 编辑项目阶段（条件触发） ==
 * 创建完成或跳过引导时，若默认项目未配置 AI 模型，则自动进入此阶段，
 * 用户不可跳过，直到模型配置完成。
 * Step 11: 主页面 — 高亮默认项目的编辑按钮
 * Step 12: 编辑项目页 — 高亮左侧面板（自然语言修改）
 * Step 13: 编辑项目页 — 高亮右侧面板（表单修改 + 选择模型）
 * Step 14: 编辑项目页 — 高亮"保存"按钮
 */
import { defineStore } from 'pinia'
import { ref, shallowRef, computed } from 'vue'

const STORAGE_KEY = 'zenflux_guide_done'

export interface GuideStepConfig {
  tooltip: string
  position: 'top' | 'bottom' | 'left' | 'right' | 'center'
  showNextButton: boolean
  /** 浮动模式：无目标高亮，只显示提示 */
  floating?: boolean
  /** 可滚动模式：遮罩不拦截交互，tooltip 固定在视口底部，允许用户自由滚动内容 */
  scrollable?: boolean
}

const STEP_CONFIGS: Record<number, GuideStepConfig> = {
  // == 设置阶段 ==
  1:  { tooltip: '先来配置你的模型和 API Key', position: 'top', showNextButton: false },
  2:  { tooltip: '选择一个 Provider，填写你的 API Key，完成后点击下一步', position: 'bottom', showNextButton: true, scrollable: true },
  3:  { tooltip: '点击验证并保存，系统将自动验证 Key 有效性', position: 'top', showNextButton: false },
  4:  { tooltip: '推荐配置语义搜索。你也可以直接点击下一步跳过', position: 'top', showNextButton: true, scrollable: true },
  5:  { tooltip: '设置完成！点击返回聊天', position: 'top', showNextButton: false },
  // == 创建项目阶段 ==
  6:  { tooltip: '接下来创建你的第一个项目', position: 'right', showNextButton: false },
  // Step 7: 打字机效果，无遮罩
  8:  { tooltip: 'AI 已帮你输入消息内容，点击发送按钮发送', position: 'right', showNextButton: false },
  9:  { tooltip: 'AI 已为你生成项目配置，你可以自由修改内容，完成后点击下一步', position: 'left', showNextButton: true },
  10: { tooltip: '点击创建，完成你的第一个项目！', position: 'bottom', showNextButton: false },
  // == 编辑项目阶段（条件触发：默认项目缺少 AI 模型时激活） ==
  11: { tooltip: '默认项目还需要配置 AI 模型，请点击编辑按钮进入配置', position: 'right', showNextButton: false },
  12: { tooltip: '在左侧，你可以通过自然语言描述来修改项目内容，AI 会帮你自动更新配置', position: 'right', showNextButton: true },
  13: { tooltip: '在右侧，你可以直接修改表单内容。请务必选择一个 AI 模型，然后点击下一步', position: 'left', showNextButton: true },
  14: { tooltip: '点击保存，完成项目配置！', position: 'bottom', showNextButton: false },
}

const MAX_STEP = 14

/** 引导分为多个阶段，用于显示进度。编辑项目阶段仅在默认项目缺少模型时触发 */
const PHASES = [
  { label: '基础配置', start: 1, end: 5 },
  { label: '创建项目', start: 6, end: 10 },
  { label: '配置模型', start: 11, end: 14 },
]

export const useGuideStore = defineStore('guide', () => {
  // ==================== State ====================

  const isActive = ref(false)
  const currentStep = ref(0)
  const targetEl = shallowRef<HTMLElement | null>(null)
  const validationError = ref('')
  /** 是否允许跳过引导（由外部根据是否有有效 Key 来控制） */
  const canSkip = ref(true)
  /** 临时覆盖当前步骤的 tooltip 文本（如回退时显示错误提示），正常推进时自动清除 */
  const tooltipOverride = ref('')

  /** 外部注册的"下一步"前置校验函数 */
  const _beforeNextStep = shallowRef<(() => string | true) | null>(null)

  // ==================== Computed ====================

  /** 从 localStorage 初始化，之后通过 ref 保持响应式 */
  const isCompleted = ref(localStorage.getItem(STORAGE_KEY) === '1')
  const currentConfig = computed<GuideStepConfig | null>(() => STEP_CONFIGS[currentStep.value] ?? null)

  /** 是否显示遮罩（无配置的步骤不显示；floating 步骤无需 target） */
  const showOverlay = computed(() => {
    if (!isActive.value || !currentConfig.value) return false
    if (currentConfig.value.floating) return true
    return targetEl.value !== null
  })

  /** 当前阶段信息（用于进度指示器） */
  const currentPhase = computed(() => {
    const step = currentStep.value
    for (const phase of PHASES) {
      if (step >= phase.start && step <= phase.end) {
        return {
          label: phase.label,
          current: step - phase.start + 1,
          total: phase.end - phase.start + 1,
        }
      }
    }
    return null
  })

  // ==================== Actions ====================

  function startGuide() {
    if (isCompleted.value) return
    isActive.value = true
    currentStep.value = 1
    validationError.value = ''
    tooltipOverride.value = ''
  }

  function nextStep() {
    // 如果有前置校验函数，先执行校验
    if (_beforeNextStep.value) {
      const result = _beforeNextStep.value()
      if (result !== true) {
        validationError.value = result
        return // 校验失败，不推进
      }
    }

    validationError.value = ''
    tooltipOverride.value = ''
    _beforeNextStep.value = null
    targetEl.value = null
    currentStep.value++
    if (currentStep.value > MAX_STEP) {
      completeGuide()
    }
  }

  function goToStep(step: number, overrideTooltip?: string) {
    validationError.value = ''
    tooltipOverride.value = overrideTooltip || ''
    _beforeNextStep.value = null
    targetEl.value = null
    currentStep.value = step
  }

  function setTarget(el: HTMLElement | null) {
    targetEl.value = el
  }

  /** 注册"下一步"前置校验函数，返回 true 放行，返回 string 作为错误提示 */
  function setBeforeNextStep(fn: (() => string | true) | null) {
    _beforeNextStep.value = fn
  }

  function completeGuide() {
    isActive.value = false
    currentStep.value = 0
    targetEl.value = null
    validationError.value = ''
    tooltipOverride.value = ''
    _beforeNextStep.value = null
    isCompleted.value = true
    localStorage.setItem(STORAGE_KEY, '1')
  }

  function skipGuide() {
    completeGuide()
  }

  return {
    isActive,
    currentStep,
    targetEl,
    isCompleted,
    currentConfig,
    showOverlay,
    currentPhase,
    validationError,
    canSkip,
    tooltipOverride,
    startGuide,
    nextStep,
    goToStep,
    setTarget,
    setBeforeNextStep,
    completeGuide,
    skipGuide,
  }
})

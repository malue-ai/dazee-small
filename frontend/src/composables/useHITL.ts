/**
 * HITL (Human-in-the-Loop) Composable
 * 负责人工确认弹窗状态和提交
 */

import { ref, computed } from 'vue'
import { useSessionStore } from '@/stores/session'
import * as sessionApi from '@/api/session'
import type { HITLConfirmRequest, HITLResponse, HITLFormQuestion } from '@/types'

/**
 * HITL Composable
 */
export function useHITL() {
  const sessionStore = useSessionStore()

  // ==================== 状态 ====================

  /** 是否显示确认弹窗 */
  const showModal = ref(false)

  /** 当前确认请求 */
  const request = ref<HITLConfirmRequest | null>(null)

  /** 用户响应 */
  const response = ref<HITLResponse | null>(null)

  /** 是否正在提交 */
  const isSubmitting = ref(false)

  // ==================== 计算属性 ====================

  /** 确认类型 */
  const confirmationType = computed(() => request.value?.confirmation_type || 'yes_no')

  /** 问题文本 */
  const question = computed(() => request.value?.question || '')

  /** 选项列表 */
  const options = computed(() => request.value?.options || [])

  /** 表单问题列表 */
  const formQuestions = computed(() => request.value?.questions || [])

  /** 描述文本 */
  const description = computed(() => request.value?.description || '')

  /** 是否为 yes_no 类型 */
  const isYesNo = computed(() => confirmationType.value === 'yes_no')

  /** 是否为单选类型 */
  const isSingleChoice = computed(() => confirmationType.value === 'single_choice')

  /** 是否为多选类型 */
  const isMultipleChoice = computed(() => confirmationType.value === 'multiple_choice')

  /** 是否为文本输入类型 */
  const isTextInput = computed(() => confirmationType.value === 'text_input')

  /** 是否为表单类型 */
  const isForm = computed(() => confirmationType.value === 'form')

  // ==================== 方法 ====================

  /**
   * 显示确认弹窗
   * @param data - HITL 确认请求数据
   */
  function show(data: HITLConfirmRequest): void {
    request.value = data
    showModal.value = true

    // 根据类型初始化响应
    initializeResponse(data)

    console.log('🤝 显示 HITL 确认弹窗:', data)
  }

  /**
   * 初始化响应值
   */
  function initializeResponse(data: HITLConfirmRequest): void {
    const type = data.confirmation_type

    if (type === 'yes_no' && data.options?.length) {
      // yes_no 类型：默认选中第一个选项
      response.value = data.options[0]
    } else if (type === 'single_choice' && data.options?.length) {
      // single_choice 类型：默认选中第一个选项
      response.value = data.default_value as string || data.options[0]
    } else if (type === 'multiple_choice') {
      // multiple_choice 类型：初始化为数组
      response.value = (data.default_value as string[]) || []
    } else if (type === 'text_input') {
      // text_input 类型：初始化为空字符串
      response.value = (data.default_value as string) || ''
    } else if (type === 'form') {
      // form 类型：初始化为对象
      const formData: Record<string, string | string[]> = {}
      if (data.questions) {
        data.questions.forEach((q: HITLFormQuestion) => {
          if (q.default !== undefined) {
            formData[q.id] = q.default
          } else {
            formData[q.id] = q.type === 'multiple_choice' ? [] : ''
          }
        })
      }
      response.value = formData
    } else {
      response.value = null
    }
  }

  /**
   * 更新响应值
   * @param value - 新的响应值
   */
  function updateResponse(value: HITLResponse): void {
    response.value = value
  }

  /**
   * 更新表单字段值
   * @param fieldId - 字段 ID
   * @param value - 字段值
   */
  function updateFormField(fieldId: string, value: string | string[]): void {
    if (typeof response.value === 'object' && response.value !== null && !Array.isArray(response.value)) {
      (response.value as Record<string, string | string[]>)[fieldId] = value
    }
  }

  /**
   * 提交响应
   */
  async function submit(): Promise<boolean> {
    if (!request.value || isSubmitting.value) return false

    const sessionId = sessionStore.currentSessionId
    if (!sessionId) {
      console.error('❌ 无法提交 HITL 响应：session_id 不存在')
      return false
    }

    // 验证必填项
    if (response.value === null && confirmationType.value !== 'text_input') {
      console.warn('⚠️ 请选择一个选项')
      return false
    }

    isSubmitting.value = true

    try {
      // form 类型：将对象序列化为 JSON 字符串
      let submitResponse = response.value
      if (confirmationType.value === 'form' && typeof response.value === 'object') {
        submitResponse = JSON.stringify(response.value)
      }

      await sessionApi.submitHITLResponse(sessionId, submitResponse as string)

      console.log('✅ HITL 响应已提交:', submitResponse)

      // 关闭弹窗
      hide()
      return true
    } catch (error: unknown) {
      const err = error as { status?: number }
      console.error('❌ 提交 HITL 响应失败:', error)

      // 404/410 表示请求已过期
      if (err.status === 404 || err.status === 410) {
        console.warn('⚠️ 确认请求已过期')
        hide()
      }

      return false
    } finally {
      isSubmitting.value = false
    }
  }

  /**
   * 取消确认（发送取消响应）
   */
  async function cancel(): Promise<void> {
    if (request.value) {
      response.value = 'cancel'
      await submit()
    } else {
      hide()
    }
  }

  /**
   * 隐藏弹窗
   */
  function hide(): void {
    showModal.value = false
    request.value = null
    response.value = null
  }

  /**
   * 重置状态
   */
  function reset(): void {
    hide()
    isSubmitting.value = false
  }

  return {
    // 状态
    showModal,
    request,
    response,
    isSubmitting,

    // 计算属性
    confirmationType,
    question,
    options,
    formQuestions,
    description,
    isYesNo,
    isSingleChoice,
    isMultipleChoice,
    isTextInput,
    isForm,

    // 方法
    show,
    updateResponse,
    updateFormField,
    submit,
    cancel,
    hide,
    reset
  }
}

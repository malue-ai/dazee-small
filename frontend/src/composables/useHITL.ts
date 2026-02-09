/**
 * HITL (Human-in-the-Loop) Composable
 * 负责人工确认弹窗状态和提交
 *
 * 阻塞模式：Agent 执行过程中调用 hitl 工具时会阻塞等待用户响应。
 * SSE 流保持打开，前端通过 POST /api/v1/human-confirmation/{session_id}
 * 提交用户响应，唤醒后端 asyncio.Event，Agent 在同一个 SSE 流中继续执行。
 */

import { ref, computed } from 'vue'
import { useSessionStore } from '@/stores/session'
import { useConversationStore } from '@/stores/conversation'
import { submitHITLResponse } from '@/api/session'
import type { HITLConfirmRequest, HITLResponse, HITLFormQuestion, HITLConfirmationType } from '@/types'

/**
 * 格式化 HITL 响应为分号分隔的字符串（用于发送到后端）
 * @param response - 用户响应
 * @param type - 确认类型
 * @returns 格式化后的字符串
 */
function formatHITLResponse(
  response: HITLResponse | null,
  type: HITLConfirmationType
): string {
  if (response === null || response === undefined) {
    return ''
  }

  // 表单类型：将对象的值提取为数组，用分号连接
  if (type === 'form' && typeof response === 'object' && !Array.isArray(response)) {
    // 检查是否包含特殊字符（分号、换行等）
    const hasSpecialChars = Object.values(response).some(v =>
      String(v).includes(';') || String(v).includes('；') || String(v).includes('\n')
    )
    
    if (hasSpecialChars) {
      // 使用 JSON 格式（更可靠）
      return JSON.stringify({ hitl_response: response })
    } else {
      // 使用分号分隔（更简洁）
      const values = Object.values(response).map(v => {
        if (Array.isArray(v)) {
          return v.join(',') // 多选用逗号连接
        }
        return String(v)
      })
      return values.join(';') // 使用英文分号
    }
  }

  // 多选类型（数组）
  if (Array.isArray(response)) {
    return response.join(',') // 多选用逗号连接
  }

  // 其他情况直接转字符串
  return String(response)
}

/**
 * 格式化 HITL 响应为可读的显示文本（用于界面显示）
 * @param response - 用户响应
 * @param type - 确认类型
 * @returns 格式化后的显示文本
 */
function formatHITLResponseForDisplay(
  response: HITLResponse | null,
  type: HITLConfirmationType
): string {
  if (response === null || response === undefined) {
    return '(未选择)'
  }

  // 表单类型：显示为 "问题: 答案" 格式
  if (type === 'form' && typeof response === 'object' && !Array.isArray(response)) {
    const items = Object.entries(response).map(([key, value]) => {
      if (Array.isArray(value)) {
        return `${key}: ${value.join(', ')}`
      }
      return `${key}: ${value || '(空)'}`
    })
    
    // 如果只有一个值，简化显示
    if (items.length === 1) {
      const [_, value] = Object.entries(response)[0]
      return String(value || '(空)')
    }
    
    return items.join('\n')
  }

  // 单选/多选类型
  if (type === 'yes_no' || type === 'single_choice' || type === 'multiple_choice') {
    if (Array.isArray(response)) {
      return response.join(', ')
    }
    return String(response)
  }

  // 文本输入类型
  if (type === 'text_input') {
    return String(response)
  }

  // 兜底：返回 JSON 字符串
  return JSON.stringify(response, null, 2)
}

/**
 * HITL Composable
 */
export function useHITL() {
  const sessionStore = useSessionStore()
  const conversationStore = useConversationStore()

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
            // 如果没有设置 default
            if (q.type === 'multiple_choice') {
              formData[q.id] = []
            } else if (q.type === 'single_choice' && q.options && q.options.length > 0) {
              // single_choice 默认选中第一个选项
              formData[q.id] = q.options[0]
            } else {
              formData[q.id] = ''
            }
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
   * 提交响应（阻塞模式：通过 confirmation API 唤醒后端 Event）
   *
   * Agent 执行中调用 hitl 工具后会阻塞在 asyncio.Event 上，SSE 流保持打开。
   * 前端提交表单后调用 POST /api/v1/human-confirmation/{session_id}，
   * 后端 Event.set() 唤醒 Agent，Agent 在同一个 SSE 流中继续执行。
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
      // 构造响应数据（直接发送结构化数据，由后端传给 Agent）
      const userResponse = response.value

      console.log('📤 提交 HITL 响应:', userResponse, 'session:', sessionId)

      // 调用 confirmation API 唤醒后端 asyncio.Event
      await submitHITLResponse(sessionId, userResponse as string | string[] | Record<string, unknown>)

      console.log('✅ HITL 响应已提交，Agent 继续执行')

      // 关闭弹窗
      hide()

      return true
    } catch (error: unknown) {
      console.error('❌ 提交 HITL 响应失败:', error)
      return false
    } finally {
      isSubmitting.value = false
    }
  }

  /**
   * 取消确认（发送取消响应唤醒 Agent）
   */
  async function cancel(): Promise<void> {
    if (request.value) {
      response.value = 'cancel'
      await submit() // 通过 confirmation API 发送 "cancel"
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
    reset,
  }
}

/**
 * HITL (Human-in-the-Loop) Composable
 * 负责人工确认弹窗状态和提交
 */

import { ref, computed } from 'vue'
import { useSessionStore } from '@/stores/session'
import { useConversationStore } from '@/stores/conversation'
import { useSSE } from './useSSE'
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
  const sse = useSSE()

  // ==================== 状态 ====================

  /** 是否显示确认弹窗 */
  const showModal = ref(false)

  /** 当前确认请求 */
  const request = ref<HITLConfirmRequest | null>(null)

  /** 用户响应 */
  const response = ref<HITLResponse | null>(null)

  /** 是否正在提交 */
  const isSubmitting = ref(false)
  
  /** SSE 事件处理回调（由外部设置） */
  const onSSEEvent = ref<((event: any, assistantMsg: any) => void) | null>(null)

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
   * 提交响应（新版本：通过 SSE 流式接口提交）
   */
  async function submit(): Promise<boolean> {
    if (!request.value || isSubmitting.value) return false

    const conversationId = conversationStore.currentId
    const userId = conversationStore.userId

    if (!conversationId) {
      console.error('❌ 无法提交 HITL 响应：conversation_id 不存在')
      return false
    }

    if (!userId) {
      console.error('❌ 无法提交 HITL 响应：user_id 不存在')
      return false
    }

    // 验证必填项
    if (response.value === null && confirmationType.value !== 'text_input') {
      console.warn('⚠️ 请选择一个选项')
      return false
    }

    isSubmitting.value = true

    try {
      // 🆕 格式化用户响应为分号分隔的字符串（发送到后端）
      const formattedMessage = formatHITLResponse(response.value, confirmationType.value)
      
      // 🆕 格式化用户响应为可读的显示文本（界面显示）
      const displayMessage = formatHITLResponseForDisplay(response.value, confirmationType.value)
      
      console.log('📤 提交 HITL 响应:', formattedMessage)

      // 🆕 在界面上显示用户的选择
      conversationStore.addUserMessage(displayMessage)

      // 🆕 添加空的助手消息（用于流式填充）
      const assistantMsg = conversationStore.addAssistantMessage()

      // 🆕 通过 SSE 流式接口发送消息
      const requestBody = {
        message: formattedMessage,
        user_id: userId,
        conversation_id: conversationId,
        stream: true, // ✅ 启用流式响应
        variables: {
          hitlFlag: true // 🔑 标识这是 HITL 响应
        }
      }

      // 🔑 建立 SSE 连接（不 await，让它在后台运行）
      sse.connect(requestBody, {
        onEvent: (event) => {
          // 如果外部设置了事件处理回调，则使用它
          if (onSSEEvent.value) {
            onSSEEvent.value(event, assistantMsg)
          }
        },
        onConnected: () => {
          console.log('✅ HITL 响应 SSE 已连接')
          // 🆕 连接成功后立即关闭弹窗
          hide()
          isSubmitting.value = false
        },
        onDisconnected: () => {
          console.log('✅ HITL 响应 SSE 已断开')
        },
        onError: (error) => {
          console.error('❌ HITL 响应 SSE 错误:', error)
          // 错误时也要重置状态
          isSubmitting.value = false
        }
      }).catch((error) => {
        // 捕获连接错误
        console.error('❌ 提交 HITL 响应失败:', error)
        isSubmitting.value = false
      })

      console.log('📤 HITL 响应已发送，等待 SSE 连接建立...')
      
      // 不再等待 SSE 流结束，立即返回
      return true
    } catch (error: unknown) {
      console.error('❌ 提交 HITL 响应失败:', error)
      isSubmitting.value = false
      return false
    }
  }

  /**
   * 取消确认（发送取消响应）
   */
  async function cancel(): Promise<void> {
    if (request.value) {
      response.value = 'cancel'
      await submit() // 通过 chat 接口发送 "cancel"
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

  /**
   * 设置 SSE 事件处理回调（由 useChat 调用）
   * @param handler - 事件处理函数
   */
  function setSSEEventHandler(handler: (event: any, assistantMsg: any, convId?: string) => void): void {
    onSSEEvent.value = handler
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
    setSSEEventHandler // 🆕 新增方法
  }
}

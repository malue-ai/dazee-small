/**
 * 断线重连 Composable
 * 负责检测活跃会话、断线重连
 */

import { ref } from 'vue'
import { useConversationStore } from '@/stores/conversation'
import { useSessionStore } from '@/stores/session'
import { useSSE, type SSEEventHandler } from './useSSE'
import type { ActiveSession, UIMessage } from '@/types'

/**
 * 重连选项
 */
export interface ReconnectOptions {
  /** 事件处理回调 */
  onEvent?: SSEEventHandler
  /** 重连成功回调 */
  onSuccess?: () => void
  /** 重连失败回调 */
  onError?: (error: Error) => void
}

/**
 * 断线重连 Composable
 */
export function useReconnect() {
  const conversationStore = useConversationStore()
  const sessionStore = useSessionStore()
  const sse = useSSE()

  // ==================== 状态 ====================

  /** 活跃会话列表 */
  const activeSessions = ref<ActiveSession[]>([])

  /** 是否显示重连提示 */
  const showReconnectModal = ref(false)

  /** 正在重连的会话 */
  const reconnectingSession = ref<ActiveSession | null>(null)

  /** 是否正在重连 */
  const isReconnecting = ref(false)

  // ==================== 方法 ====================

  /**
   * 检查活跃会话
   * @returns 是否有活跃会话需要重连
   */
  async function checkActiveSessions(): Promise<boolean> {
    const userId = conversationStore.userId
    if (!userId) return false

    try {
      const sessions = await sessionStore.getActiveSessions(userId)

      if (sessions && sessions.length > 0) {
        activeSessions.value = sessions
        console.log(`🔄 发现 ${sessions.length} 个活跃 Session`)
        return true
      }

      return false
    } catch (error) {
      console.log('ℹ️ 无活跃 Session 或检查失败')
      return false
    }
  }

  /**
   * 显示重连提示
   */
  function showReconnectPrompt(): void {
    if (activeSessions.value.length > 0) {
      showReconnectModal.value = true
    }
  }

  /**
   * 忽略重连提示
   */
  function dismissReconnect(): void {
    showReconnectModal.value = false
    activeSessions.value = []
  }

  /**
   * 重连到指定会话
   * @param session - 活跃会话
   * @param options - 重连选项
   */
  async function reconnectToSession(
    session: ActiveSession,
    options: ReconnectOptions = {}
  ): Promise<void> {
    const { onEvent, onSuccess, onError } = options

    reconnectingSession.value = session
    showReconnectModal.value = false
    isReconnecting.value = true

    console.log(`🔗 开始重连 Session: ${session.session_id}`)

    try {
      // 设置当前 session_id
      sessionStore.setCurrentSessionId(session.session_id)

      // 加载会话
      if (session.conversation_id && conversationStore.currentId !== session.conversation_id) {
        await conversationStore.load(session.conversation_id)
      }

      // 查找或创建助手消息
      let assistantMsg = findOrCreateAssistantMessage(session)

      // 使用 SSE 重连
      await sse.reconnect(session.session_id, 0, {
        onEvent: (event) => {
          // 处理 reconnect_info 事件
          if (event.type === 'reconnect_info') {
            const info = event.data as { conversation_id?: string; message_id?: string }
            console.log(`📋 重连上下文: conversation_id=${info.conversation_id}`)
          }

          // 调用外部事件处理器
          onEvent?.(event)
        },
        onConnected: () => {
          console.log('✅ SSE 重连成功')
        },
        onDisconnected: () => {
          console.log('✅ SSE 重连流结束')
        },
        onError: (error) => {
          console.error('❌ SSE 重连失败:', error)
          onError?.(error)
        }
      })

      // 重新加载会话以获取最终消息
      if (session.conversation_id) {
        await conversationStore.load(session.conversation_id)
      }

      onSuccess?.()
    } catch (error) {
      console.error('❌ 重连失败:', error)
      onError?.(error as Error)
    } finally {
      isReconnecting.value = false
      reconnectingSession.value = null
    }
  }

  /**
   * 自动重连到第一个活跃会话
   * @param options - 重连选项
   */
  async function autoReconnect(options: ReconnectOptions = {}): Promise<boolean> {
    const hasActive = await checkActiveSessions()

    if (hasActive && activeSessions.value.length > 0) {
      await reconnectToSession(activeSessions.value[0], options)
      return true
    }

    return false
  }

  /**
   * 查找或创建助手消息
   */
  function findOrCreateAssistantMessage(session: ActiveSession): UIMessage {
    // 查找现有的助手消息
    const existingMsg = conversationStore.messages.find(
      m => m.role === 'assistant' && m.id === session.message_id
    )

    if (existingMsg) {
      return existingMsg
    }

    // 创建新的助手消息
    return conversationStore.addAssistantMessage()
  }

  /**
   * 重置状态
   */
  function reset(): void {
    activeSessions.value = []
    showReconnectModal.value = false
    reconnectingSession.value = null
    isReconnecting.value = false
  }

  return {
    // 状态
    activeSessions,
    showReconnectModal,
    reconnectingSession,
    isReconnecting,

    // 方法
    checkActiveSessions,
    showReconnectPrompt,
    dismissReconnect,
    reconnectToSession,
    autoReconnect,
    reset
  }
}

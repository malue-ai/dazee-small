/**
 * Session 状态管理 Store
 * 负责管理活跃会话状态、轮询、重连
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as sessionApi from '@/api/session'
import type { ActiveSession, ActiveSessionInfo, ActiveSessionsMap } from '@/types'
import { DEFAULT_CONFIG } from '@/utils'

export const useSessionStore = defineStore('session', () => {
  // ==================== 状态 ====================

  /** 当前 Session ID */
  const currentSessionId = ref<string | null>(null)

  /** 活跃会话映射（conversationId -> sessionInfo） */
  const activeSessionsMap = ref<ActiveSessionsMap>({})

  /** 轮询定时器 */
  let pollingTimer: ReturnType<typeof setInterval> | null = null

  /** 轮询间隔 */
  const pollingInterval = ref(DEFAULT_CONFIG.POLLING_INTERVAL)

  /** 是否正在连接 */
  const isConnected = ref(false)

  /** 最后事件 ID（用于断线重连） */
  const lastEventId = ref(0)

  /** 重连尝试次数 */
  const reconnectAttempts = ref(0)

  // ==================== 计算属性 ====================

  /** 活跃会话数量 */
  const activeSessionCount = computed(() => Object.keys(activeSessionsMap.value).length)

  /** 是否有活跃会话 */
  const hasActiveSessions = computed(() => activeSessionCount.value > 0)

  // ==================== 方法 ====================

  /**
   * 设置当前 Session ID
   */
  function setCurrentSessionId(sessionId: string | null): void {
    currentSessionId.value = sessionId
  }

  /**
   * 设置连接状态
   */
  function setConnected(connected: boolean): void {
    isConnected.value = connected
    if (connected) {
      reconnectAttempts.value = 0
    }
  }

  /**
   * 更新最后事件 ID
   */
  function setLastEventId(eventId: number): void {
    lastEventId.value = eventId
  }

  /**
   * 增加重连次数
   */
  function incrementReconnectAttempts(): number {
    reconnectAttempts.value++
    return reconnectAttempts.value
  }

  /**
   * 重置重连次数
   */
  function resetReconnectAttempts(): void {
    reconnectAttempts.value = 0
  }

  /**
   * 获取 Session 状态
   * @param sessionId - Session ID
   */
  async function getStatus(sessionId: string) {
    try {
      return await sessionApi.getSessionStatus(sessionId)
    } catch (error) {
      console.error('❌ 获取 Session 状态失败:', error)
      throw error
    }
  }

  /**
   * 停止 Session
   * @param sessionId - Session ID
   */
  async function stop(sessionId: string): Promise<void> {
    try {
      console.log('🛑 停止 Session:', sessionId)
      await sessionApi.stopSession(sessionId)
      console.log('✅ Session 已停止')

      // 刷新活跃会话状态
      await refreshActiveSessions()
    } catch (error) {
      console.error('❌ 停止 Session 失败:', error)
      throw error
    }
  }

  /**
   * 获取用户的所有活跃会话
   * @param userId - 用户 ID
   */
  async function getActiveSessions(userId: string): Promise<ActiveSession[]> {
    try {
      return await sessionApi.getUserSessions(userId)
    } catch (error) {
      console.error('❌ 获取活跃会话失败:', error)
      throw error
    }
  }

  /**
   * 开始轮询活跃会话状态
   * @param userId - 用户 ID
   */
  function startPolling(userId: string): void {
    // 避免重复启动
    if (pollingTimer) {
      return
    }

    console.log('🔄 开始轮询活跃会话状态')

    // 立即执行一次
    refreshActiveSessionsInternal(userId)

    // 设置定时器
    pollingTimer = setInterval(() => {
      refreshActiveSessionsInternal(userId)
    }, pollingInterval.value)
  }

  /**
   * 停止轮询
   */
  function stopPolling(): void {
    if (pollingTimer) {
      clearInterval(pollingTimer)
      pollingTimer = null
      console.log('⏹️ 停止轮询活跃会话状态')
    }
  }

  /**
   * 刷新活跃会话状态（内部方法）
   * 当没有活跃会话时自动停止轮询，减少无效请求
   */
  async function refreshActiveSessionsInternal(userId: string): Promise<void> {
    try {
      const sessions = await sessionApi.getUserSessions(userId)

      // 构建新的 activeSessionsMap
      const newMap: ActiveSessionsMap = {}
      if (sessions && sessions.length > 0) {
        for (const session of sessions) {
          if (session.conversation_id) {
            newMap[session.conversation_id] = {
              sessionId: session.session_id,
              status: session.status,
              progress: session.progress,
              startTime: session.start_time,
              messagePreview: session.message_preview
            }
          }
        }
      }

      activeSessionsMap.value = newMap

      // 如果没有活跃会话，自动停止轮询
      if (Object.keys(newMap).length === 0 && pollingTimer) {
        console.log('📭 没有活跃会话，停止轮询')
        stopPolling()
      }
    } catch (error) {
      // 静默失败，不影响用户体验
      console.warn('⚠️ 刷新活跃会话状态失败:', (error as Error).message)
    }
  }

  /**
   * 刷新活跃会话状态（公开方法）
   */
  async function refreshActiveSessions(): Promise<void> {
    const userId = localStorage.getItem('userId')
    if (userId) {
      await refreshActiveSessionsInternal(userId)
    }
  }

  /**
   * 判断指定会话是否正在运行
   * @param conversationId - 会话 ID
   */
  function isConversationRunning(conversationId: string | null): boolean {
    if (!conversationId) return false
    const sessionInfo = activeSessionsMap.value[conversationId]
    return sessionInfo?.status === 'running'
  }

  /**
   * 获取指定会话对应的 Session ID
   * @param conversationId - 会话 ID
   */
  function getSessionIdByConversation(conversationId: string | null): string | null {
    if (!conversationId) return null
    return activeSessionsMap.value[conversationId]?.sessionId || null
  }

  /**
   * 获取指定会话的运行信息
   * @param conversationId - 会话 ID
   */
  function getConversationSessionInfo(conversationId: string | null): ActiveSessionInfo | null {
    if (!conversationId) return null
    return activeSessionsMap.value[conversationId] || null
  }

  /**
   * 重置状态
   */
  function reset(): void {
    currentSessionId.value = null
    activeSessionsMap.value = {}
    isConnected.value = false
    lastEventId.value = 0
    reconnectAttempts.value = 0
    stopPolling()
  }

  return {
    // 状态
    currentSessionId,
    activeSessionsMap,
    pollingInterval,
    isConnected,
    lastEventId,
    reconnectAttempts,

    // 计算属性
    activeSessionCount,
    hasActiveSessions,

    // 方法
    setCurrentSessionId,
    setConnected,
    setLastEventId,
    incrementReconnectAttempts,
    resetReconnectAttempts,
    getStatus,
    stop,
    getActiveSessions,
    startPolling,
    stopPolling,
    refreshActiveSessions,
    isConversationRunning,
    getSessionIdByConversation,
    getConversationSessionInfo,
    reset
  }
})

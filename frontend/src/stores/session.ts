/**
 * Session 状态管理 Store
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as sessionApi from '@/api/session'
import type { ActiveSessionInfo, ActiveSessionsMap } from '@/types'

export const useSessionStore = defineStore('session', () => {
  /** 当前 Session ID */
  const currentSessionId = ref<string | null>(null)

  /** 活跃会话映射（conversationId -> sessionInfo） */
  const activeSessionsMap = ref<ActiveSessionsMap>({})

  /** 是否正在连接 */
  const isConnected = ref(false)

  /** 最后事件 ID */
  const lastEventId = ref(0)

  /** 活跃会话数量 */
  const activeSessionCount = computed(() => Object.keys(activeSessionsMap.value).length)

  /** 是否有活跃会话 */
  const hasActiveSessions = computed(() => activeSessionCount.value > 0)

  function setCurrentSessionId(sessionId: string | null): void {
    currentSessionId.value = sessionId
  }

  function setConnected(connected: boolean): void {
    isConnected.value = connected
  }

  function setLastEventId(eventId: number): void {
    lastEventId.value = eventId
  }

  /**
   * 停止 Session
   */
  async function stop(sessionId: string): Promise<void> {
    try {
      await sessionApi.stopSession(sessionId)
      // 清除该 session 对应的活跃记录
      for (const [convId, info] of Object.entries(activeSessionsMap.value)) {
        if (info.sessionId === sessionId) {
          delete activeSessionsMap.value[convId]
          break
        }
      }
    } catch (error) {
      console.error('停止 Session 失败:', error)
      throw error
    }
  }

  /**
   * 标记会话为运行中
   */
  function markRunning(conversationId: string, sessionId: string): void {
    activeSessionsMap.value[conversationId] = {
      sessionId,
      status: 'running',
      startTime: new Date().toISOString()
    }
  }

  /**
   * 标记会话完成
   */
  function markCompleted(conversationId: string): void {
    delete activeSessionsMap.value[conversationId]
  }

  /**
   * 判断指定会话是否正在运行
   */
  function isConversationRunning(conversationId: string | null): boolean {
    if (!conversationId) return false
    const sessionInfo = activeSessionsMap.value[conversationId]
    return sessionInfo?.status === 'running'
  }

  /**
   * 获取指定会话对应的 Session ID
   */
  function getSessionIdByConversation(conversationId: string | null): string | null {
    if (!conversationId) return null
    return activeSessionsMap.value[conversationId]?.sessionId || null
  }

  /**
   * 获取指定会话的运行信息
   */
  function getConversationSessionInfo(conversationId: string | null): ActiveSessionInfo | null {
    if (!conversationId) return null
    return activeSessionsMap.value[conversationId] || null
  }

  function reset(): void {
    currentSessionId.value = null
    activeSessionsMap.value = {}
    isConnected.value = false
    lastEventId.value = 0
  }

  return {
    currentSessionId,
    activeSessionsMap,
    isConnected,
    lastEventId,
    activeSessionCount,
    hasActiveSessions,
    setCurrentSessionId,
    setConnected,
    setLastEventId,
    stop,
    markRunning,
    markCompleted,
    isConversationRunning,
    getSessionIdByConversation,
    getConversationSessionInfo,
    reset
  }
})

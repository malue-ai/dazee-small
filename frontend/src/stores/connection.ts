import { defineStore } from 'pinia'
import { shallowRef, triggerRef } from 'vue'
import { useWebSocketChat } from '@/composables/useWebSocketChat'

/**
 * WebSocket 连接管理 Store
 * 用于管理多会话的并发连接 + 全局通知频道
 */
export const useConnectionStore = defineStore('connection', () => {
  /** 连接映射 (conversationId -> WebSocketChatInstance) */
  // 使用 shallowRef 避免 Vue 深层解包 composable 内部的 Ref
  const connections = shallowRef<Map<string, ReturnType<typeof useWebSocketChat>>>(new Map())

  /**
   * 全局通知频道 WebSocket 实例
   *
   * 独立于聊天会话连接，应用启动后始终保持连接，
   * 用于接收后端广播的通知事件（定时任务完成等）。
   */
  let _notificationChannel: ReturnType<typeof useWebSocketChat> | null = null

  /**
   * 初始化全局通知频道
   *
   * 在应用就绪后调用一次，建立 WebSocket 连接以接收广播通知。
   * 重复调用安全（已初始化时直接跳过）。
   */
  async function initNotificationChannel(): Promise<void> {
    if (_notificationChannel) return

    _notificationChannel = useWebSocketChat({ handleNotifications: true })

    // Register any pending playbook handler
    if (_pendingPlaybookHandler) {
      _notificationChannel.onPlaybookSuggestion(_pendingPlaybookHandler)
      _pendingPlaybookHandler = null
    }
    try {
      await _notificationChannel.ensureConnected()
    } catch {
      // 连接失败不阻塞应用启动，内部有自动重连机制
      _notificationChannel = null
    }
  }

  // Playbook suggestion handler registration
  let _pendingPlaybookHandler: ((data: any) => void) | null = null

  /**
   * Register a handler for playbook_suggestion events on the notification channel.
   * If the channel is already initialized, registers immediately;
   * otherwise queues until initNotificationChannel() is called.
   */
  function registerPlaybookHandler(handler: (data: any) => void): void {
    if (_notificationChannel) {
      _notificationChannel.onPlaybookSuggestion(handler)
    } else {
      _pendingPlaybookHandler = handler
    }
  }

  /**
   * 获取或创建指定会话的连接
   */
  function getConnection(conversationId: string) {
    if (!connections.value.has(conversationId)) {
      const ws = useWebSocketChat()
      connections.value.set(conversationId, ws)
      triggerRef(connections)
    }
    return connections.value.get(conversationId)!
  }

  /**
   * 关闭并移除连接
   */
  function closeConnection(conversationId: string) {
    const ws = connections.value.get(conversationId)
    if (ws) {
      ws.close()
      connections.value.delete(conversationId)
      triggerRef(connections)
    }
  }

  /**
   * 关闭所有连接（包括全局通知频道）
   */
  function closeAll() {
    // 关闭全局通知频道
    if (_notificationChannel) {
      _notificationChannel.close()
      _notificationChannel = null
    }

    for (const ws of connections.value.values()) {
      ws.close()
    }
    connections.value.clear()
    triggerRef(connections)
  }

  return {
    connections,
    initNotificationChannel,
    getConnection,
    closeConnection,
    closeAll,
    registerPlaybookHandler,
  }
})

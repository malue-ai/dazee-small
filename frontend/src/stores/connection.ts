import { defineStore } from 'pinia'
import { shallowRef, triggerRef } from 'vue'
import { useWebSocketChat } from '@/composables/useWebSocketChat'

/**
 * WebSocket 连接管理 Store
 * 用于管理多会话的并发连接
 */
export const useConnectionStore = defineStore('connection', () => {
  /** 连接映射 (conversationId -> WebSocketChatInstance) */
  // 使用 shallowRef 避免 Vue 深层解包 composable 内部的 Ref
  const connections = shallowRef<Map<string, ReturnType<typeof useWebSocketChat>>>(new Map())

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
   * 关闭所有连接
   */
  function closeAll() {
    for (const ws of connections.value.values()) {
      ws.close()
    }
    connections.value.clear()
    triggerRef(connections)
  }

  return {
    connections,
    getConnection,
    closeConnection,
    closeAll
  }
})

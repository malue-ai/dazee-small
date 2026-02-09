/**
 * WebSocket 聊天 Composable
 *
 * 替代 useSSE，使用持久化 WebSocket 进行聊天流式通信。
 * 接口兼容 useSSE，可在 useChat 中直接替换。
 *
 * 帧协议：
 * - 请求帧：{"type": "req", "id": "uuid", "method": "chat.send", "params": {...}}
 * - 响应帧：{"type": "res", "id": "uuid", "ok": true, "payload": {...}}
 * - 事件帧：{"type": "event", "event": "content_delta", "payload": {...}, "seq": N}
 *
 * 特性：
 * - 持久化连接（消息间复用）
 * - 指数退避自动重连（800ms → 15s 上限）
 * - 心跳保活（tick 30s + 2x 超时断连）
 * - 连接状态暴露（用于 UI 展示）
 */

import { ref } from 'vue'
import { useSessionStore } from '@/stores/session'
import { useNotificationStore } from '@/stores/notification'
import { getApiBaseUrl } from '@/api'
import { isTauriEnv } from '@/api/tauri'
import { wsLog } from '@/utils/logger'
import type { SSEEvent, ChatRequest } from '@/types'

// ==================== 类型定义 ====================

export type WsEventHandler = (event: SSEEvent) => void

/** WebSocket 连接状态 */
export type WsConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'

/** 连接选项（兼容 useSSE） */
export interface WsConnectOptions {
  onEvent: WsEventHandler
  onConnected?: () => void
  onDisconnected?: () => void
  onError?: (error: Error) => void
}

// ==================== 常量 ====================

/** 心跳间隔（秒），与后端 HEARTBEAT_INTERVAL_S 一致 */
const HEARTBEAT_INTERVAL_S = 30

/** 初始重连退避（毫秒） */
const INITIAL_BACKOFF_MS = 800

/** 最大重连退避（毫秒） */
const MAX_BACKOFF_MS = 15000

/** 最大重连次数 */
const MAX_RECONNECT_ATTEMPTS = 8

/** 退避增长因子 */
const BACKOFF_FACTOR = 1.7

/** 请求超时（毫秒）— 仅等待后端确认帧，不含 Agent 执行 */
const REQUEST_TIMEOUT_MS = 30000

// ==================== Composable ====================

/**
 * WebSocket 聊天 Composable
 *
 * 与 useSSE 接口兼容，可直接替换：
 * - connect(requestBody, options) → 发送消息并等待流结束
 * - disconnect() → 中断当前流（不关闭连接）
 * - reset() → 完全关闭连接并重置状态
 */
export function useWebSocketChat() {
  const sessionStore = useSessionStore()
  const notificationStore = useNotificationStore()

  // ==================== 响应式状态 ====================

  /** 是否已连接 */
  const isConnected = ref(false)

  /** 最后事件序号 */
  const lastEventId = ref(0)

  /** 连接状态（用于 UI 展示） */
  const connectionStatus = ref<WsConnectionStatus>('disconnected')

  // ==================== 内部状态 ====================

  let ws: WebSocket | null = null
  let connectionPromise: Promise<void> | null = null
  let closed = false

  // 重连
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let backoffMs = INITIAL_BACKOFF_MS
  let reconnectAttempts = 0

  // 心跳监测
  let tickWatchTimer: ReturnType<typeof setInterval> | null = null
  let lastTickTime = 0

  // 请求/响应匹配
  const pendingRequests = new Map<string, {
    resolve: (value: any) => void
    reject: (reason: any) => void
    timeout: ReturnType<typeof setTimeout>
  }>()

  // 当前流状态
  let currentEventHandler: WsEventHandler | null = null
  let streamCompleteResolve: ((value: string) => void) | null = null
  let fullResponse = ''

  // ==================== WebSocket URL ====================

  function getWsUrl(): string {
    const baseUrl = getApiBaseUrl()

    // 如果 baseUrl 是绝对地址（http://...），转换为 ws://...
    if (baseUrl.startsWith('http')) {
      const wsBase = baseUrl.replace(/^http/, 'ws')
      return `${wsBase}/v1/ws/chat`
    }

    // 相对地址（/api）：使用当前页面地址构造 WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}${baseUrl}/v1/ws/chat`
  }

  // ==================== 连接管理 ====================

  /**
   * 确保 WebSocket 已连接（懒连接，首次调用时建立）
   */
  async function ensureConnected(): Promise<void> {
    if (ws?.readyState === WebSocket.OPEN) return
    if (connectionPromise) return connectionPromise

    connectionPromise = new Promise<void>((resolve, reject) => {
      connectionStatus.value = 'connecting'

      const url = getWsUrl()
      wsLog.info(`WebSocket 连接中: ${url}`)

      ws = new WebSocket(url)

      ws.onopen = () => {
        wsLog.info('WebSocket 已连接')
        connectionStatus.value = 'connected'
        isConnected.value = true
        backoffMs = INITIAL_BACKOFF_MS
        reconnectAttempts = 0
        sessionStore.setConnected(true)
        startTickWatch()
        connectionPromise = null
        resolve()
      }

      ws.onmessage = (event) => {
        try {
          const frame = JSON.parse(event.data)
          handleFrame(frame)
        } catch (e) {
          wsLog.error('WebSocket 帧解析失败', e)
        }
      }

      ws.onerror = () => {
        wsLog.error('WebSocket 连接错误')
        connectionPromise = null
        reject(new Error('WebSocket 连接失败'))
      }

      ws.onclose = (e) => {
        wsLog.warn(`WebSocket 关闭: code=${e.code} reason=${e.reason}`)
        connectionStatus.value = 'disconnected'
        isConnected.value = false
        sessionStore.setConnected(false)
        stopTickWatch()
        ws = null
        connectionPromise = null

        // 通知当前流结束
        if (streamCompleteResolve) {
          streamCompleteResolve(fullResponse)
          streamCompleteResolve = null
        }

        // 自动重连（除非主动关闭）
        if (!closed) {
          scheduleReconnect()
        }
      }
    })

    return connectionPromise
  }

  // ==================== 帧处理 ====================

  /**
   * 处理收到的帧
   */
  function handleFrame(frame: any): void {
    switch (frame.type) {
      case 'res':
        handleResponseFrame(frame)
        break
      case 'event':
        handleEventFrame(frame)
        break
      case 'pong':
        lastTickTime = Date.now()
        break
    }
  }

  /**
   * 处理响应帧（匹配待处理的请求）
   */
  function handleResponseFrame(frame: any): void {
    const pending = pendingRequests.get(frame.id)
    if (!pending) return

    clearTimeout(pending.timeout)
    pendingRequests.delete(frame.id)

    if (frame.ok) {
      pending.resolve(frame.payload)
    } else {
      pending.reject(new Error(frame.error?.message || '请求失败'))
    }
  }

  /**
   * 处理事件帧
   */
  function handleEventFrame(frame: any): void {
    const eventName = frame.event
    const payload = frame.payload
    const seq = frame.seq

    // 更新事件序号
    if (seq && seq > 0) {
      lastEventId.value = seq
      sessionStore.setLastEventId(seq)
    }

    // 心跳事件（不转发给业务处理器）
    if (eventName === 'tick') {
      lastTickTime = Date.now()
      return
    }

    // 全局通知事件（定时任务完成等，不依赖 chat session）
    if (eventName === 'notification' && payload) {
      _handleNotificationEvent(payload)
      return
    }

    // 转发事件到当前业务处理器
    if (currentEventHandler && payload) {
      currentEventHandler(payload)
    }

    // 跟踪完整响应文本（用于 connect() 返回值）
    const eventType = payload?.type || eventName
    if (eventType === 'content_delta') {
      const data = payload?.data
      const delta = data?.delta
      if (typeof delta === 'string') {
        fullResponse += delta
      } else if (delta?.text) {
        fullResponse += delta.text
      }
    }

    // 流结束信号
    if (
      eventType === 'message_stop' ||
      eventType === 'session_end' ||
      eventType === 'session_stopped' ||
      eventName === 'done'
    ) {
      if (streamCompleteResolve) {
        streamCompleteResolve(fullResponse)
        streamCompleteResolve = null
      }
    }
  }

  // ==================== 全局通知处理 ====================

  /**
   * 处理后端推送的通知事件（定时任务完成、系统通知等）
   *
   * payload 格式：
   * {
   *   notification_type: 'success' | 'error' | 'message' | 'info',
   *   title: string,
   *   message: string,
   *   task_id?: string,
   *   conversation_id?: string,
   *   triggered_at?: string,
   * }
   */
  function _handleNotificationEvent(payload: any): void {
    const ntype = payload.notification_type || 'info'
    const title = payload.title || '系统通知'
    const message = payload.message || ''
    const conversationId = payload.conversation_id

    wsLog.info(`收到通知: type=${ntype}, title=${title}`)

    if (ntype === 'message' && conversationId) {
      // 聊天消息类通知（带跳转按钮）
      notificationStore.chatMessage(
        title,
        message,
        { name: 'conversation', params: { conversationId } }
      )
    } else if (ntype === 'success') {
      const action = conversationId
        ? { label: '查看', route: { name: 'conversation', params: { conversationId } } as any }
        : undefined
      notificationStore.success(title, message, action)
    } else if (ntype === 'error') {
      notificationStore.error(title, message)
    } else {
      notificationStore.info(title, message)
    }
  }

  // ==================== 请求发送 ====================

  /**
   * 发送请求帧（带超时）
   */
  async function sendRequest(method: string, params: any, timeoutMs = REQUEST_TIMEOUT_MS): Promise<any> {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket 未连接')
    }

    const id = crypto.randomUUID()

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        pendingRequests.delete(id)
        reject(new Error(`请求超时: ${method}`))
      }, timeoutMs)

      pendingRequests.set(id, { resolve, reject, timeout })

      ws!.send(JSON.stringify({
        type: 'req',
        id,
        method,
        params,
      }))
    })
  }

  // ==================== 公开接口（兼容 useSSE） ====================

  /**
   * 发送聊天消息并等待流结束
   *
   * 行为与 useSSE.connect() 一致：
   * 1. 确保 WebSocket 已连接
   * 2. 发送 chat.send 请求
   * 3. 通过 onEvent 回调推送流式事件
   * 4. 返回 Promise，在流结束时 resolve（含完整响应文本）
   */
  async function connect(
    requestBody: ChatRequest,
    options: WsConnectOptions
  ): Promise<string> {
    const { onEvent, onConnected, onDisconnected, onError } = options

    // 中断之前的流（如果有）
    disconnect()

    // 重置流状态
    fullResponse = ''
    currentEventHandler = onEvent

    try {
      // 确保 WebSocket 已连接
      await ensureConnected()

      onConnected?.()

      // 发送 chat.send 请求
      await sendRequest('chat.send', requestBody)

      // 等待流结束
      const result = await new Promise<string>((resolve) => {
        streamCompleteResolve = resolve
      })

      onDisconnected?.()
      return result

    } catch (error) {
      // 清理流状态
      streamCompleteResolve = null
      currentEventHandler = null

      wsLog.error('WebSocket chat 错误', error)
      onError?.(error as Error)

      // 非连接错误时触发 disconnect 回调
      if (isConnected.value) {
        onDisconnected?.()
      }

      throw error
    }
  }

  /**
   * 中断当前流（不关闭 WebSocket 连接）
   *
   * 兼容 useSSE.disconnect()
   */
  function disconnect(): void {
    // 结束当前流
    if (streamCompleteResolve) {
      streamCompleteResolve(fullResponse)
      streamCompleteResolve = null
    }
    currentEventHandler = null
    fullResponse = ''
  }

  /**
   * 完全关闭 WebSocket 连接
   */
  function close(): void {
    closed = true

    // 取消重连
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }

    // 停止心跳监测
    stopTickWatch()

    // 中断当前流
    disconnect()

    // 取消所有待处理请求
    for (const [, pending] of pendingRequests) {
      clearTimeout(pending.timeout)
      pending.reject(new Error('连接已关闭'))
    }
    pendingRequests.clear()

    // 关闭 WebSocket
    if (ws) {
      ws.close()
      ws = null
    }

    connectionStatus.value = 'disconnected'
    isConnected.value = false
    sessionStore.setConnected(false)
  }

  /**
   * 重置状态（兼容 useSSE.reset）
   */
  function reset(): void {
    close()
    lastEventId.value = 0
    closed = false // 允许后续重新连接
  }

  // ==================== 指数退避重连 ====================

  function scheduleReconnect(): void {
    if (closed) return

    reconnectAttempts++
    if (reconnectAttempts > MAX_RECONNECT_ATTEMPTS) {
      wsLog.error(`WebSocket 重连失败，已达最大重试次数 (${MAX_RECONNECT_ATTEMPTS})，停止重连`)
      connectionStatus.value = 'disconnected'
      return
    }

    connectionStatus.value = 'reconnecting'
    wsLog.info(`WebSocket 将在 ${Math.round(backoffMs)}ms 后重连 (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`)

    reconnectTimer = setTimeout(() => {
      if (closed) return

      ensureConnected()
        .then(() => {
          wsLog.info('WebSocket 重连成功')
          reconnectAttempts = 0
        })
        .catch(() => {
          // 重连失败，继续退避
          backoffMs = Math.min(backoffMs * BACKOFF_FACTOR, MAX_BACKOFF_MS)
          scheduleReconnect()
        })
    }, backoffMs)

    backoffMs = Math.min(backoffMs * BACKOFF_FACTOR, MAX_BACKOFF_MS)
  }

  // ==================== 心跳监测 ====================

  function startTickWatch(): void {
    lastTickTime = Date.now()
    tickWatchTimer = setInterval(() => {
      const gap = Date.now() - lastTickTime
      // 超过 2 倍心跳间隔没收到 tick，判定超时
      if (gap > HEARTBEAT_INTERVAL_S * 2 * 1000) {
        wsLog.warn('WebSocket tick 超时，断开重连')
        ws?.close(4000, 'tick timeout')
      }
    }, 10000) // 每 10s 检查一次
  }

  function stopTickWatch(): void {
    if (tickWatchTimer) {
      clearInterval(tickWatchTimer)
      tickWatchTimer = null
    }
  }

  // ==================== 导出 ====================

  return {
    // 状态（兼容 useSSE）
    isConnected,
    lastEventId,

    // WebSocket 专用状态
    connectionStatus,

    // 方法（兼容 useSSE）
    connect,
    disconnect,
    reset,

    // WebSocket 专用方法
    close,
    ensureConnected,
    sendRequest,
  }
}

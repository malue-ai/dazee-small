/**
 * SSE 连接 Composable
 * 负责管理 SSE 流连接、事件解析、断线重连
 */

import { ref } from 'vue'
import { useSessionStore } from '@/stores/session'
import type { SSEEvent, ChatRequest } from '@/types'
import { DEFAULT_CONFIG } from '@/utils'

/**
 * SSE 事件处理器类型
 */
export type SSEEventHandler = (event: SSEEvent) => void

/**
 * SSE 连接选项
 */
export interface SSEConnectOptions {
  /** 事件处理回调 */
  onEvent: SSEEventHandler
  /** 连接成功回调 */
  onConnected?: () => void
  /** 断开连接回调 */
  onDisconnected?: () => void
  /** 错误回调 */
  onError?: (error: Error) => void
}

/**
 * SSE 连接 Composable
 */
export function useSSE() {
  const sessionStore = useSessionStore()

  // ==================== 状态 ====================

  /** 是否已连接 */
  const isConnected = ref(false)

  /** 最后事件 ID */
  const lastEventId = ref(0)

  /** 重连尝试次数 */
  const reconnectAttempts = ref(0)

  /** 最大重连次数 */
  const maxReconnectAttempts = DEFAULT_CONFIG.MAX_RECONNECT_ATTEMPTS

  /** 当前 AbortController（用于取消请求） */
  let abortController: AbortController | null = null

  // ==================== 方法 ====================

  /**
   * 创建 SSE 连接（POST 请求）
   * @param requestBody - 请求体
   * @param options - 连接选项
   */
  async function connect(
    requestBody: ChatRequest,
    options: SSEConnectOptions
  ): Promise<string> {
    const { onEvent, onConnected, onDisconnected, onError } = options

    // 取消之前的连接
    disconnect()

    abortController = new AbortController()

    try {
      console.log('🔌 创建 SSE 连接...', requestBody)

      const response = await fetch('/api/v1/chat?format=zenflux', {
        method: 'POST',
        headers: {
          'Accept': 'text/event-stream',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody),
        signal: abortController.signal
      })

      console.log('📡 SSE 响应状态:', response.status, response.statusText)

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      if (!response.body) {
        throw new Error('响应体为空')
      }

      isConnected.value = true
      reconnectAttempts.value = 0
      sessionStore.setConnected(true)
      onConnected?.()

      // 读取流
      const fullResponse = await readSSEStream(response.body, onEvent)

      isConnected.value = false
      sessionStore.setConnected(false)
      onDisconnected?.()

      return fullResponse
    } catch (error) {
      isConnected.value = false
      sessionStore.setConnected(false)

      if ((error as Error).name === 'AbortError') {
        console.log('🔌 SSE 连接已取消')
        onDisconnected?.()
        return ''
      }

      console.error('❌ SSE 连接错误:', error)
      onError?.(error as Error)
      throw error
    }
  }

  /**
   * 重连 SSE（GET 请求）
   * @param sessionId - Session ID
   * @param afterSeq - 从该序号之后开始
   * @param options - 连接选项
   */
  async function reconnect(
    sessionId: string,
    afterSeq: number,
    options: SSEConnectOptions
  ): Promise<string> {
    const { onEvent, onConnected, onDisconnected, onError } = options

    // 检查重连次数
    if (reconnectAttempts.value >= maxReconnectAttempts) {
      console.error('❌ 达到最大重连次数，停止重连')
      throw new Error('SSE 连接断开，重连失败')
    }

    reconnectAttempts.value++
    console.log(`🔄 尝试断线重连 (${reconnectAttempts.value}/${maxReconnectAttempts})...`)

    // 指数退避延迟
    const delay = Math.min(
      DEFAULT_CONFIG.RECONNECT_BASE_DELAY * Math.pow(2, reconnectAttempts.value - 1),
      DEFAULT_CONFIG.RECONNECT_MAX_DELAY
    )
    await sleep(delay)

    // 检查 Session 状态
    try {
      const sessionStatus = await sessionStore.getStatus(sessionId)
      console.log('📊 Session 状态:', sessionStatus)

      // 如果已经完成，不需要重连
      if (['completed', 'failed', 'timeout', 'stopped'].includes(sessionStatus.status)) {
        console.log('✅ Session 已结束，不需要重连')
        return ''
      }
    } catch (error) {
      console.warn('⚠️ 获取 Session 状态失败，继续尝试重连')
    }

    // 创建重连请求
    abortController = new AbortController()

    const reconnectUrl = `/api/v1/chat/${sessionId}?after_seq=${afterSeq}&format=zenflux`
    console.log(`🔗 重连 SSE: ${reconnectUrl}`)

    try {
      const response = await fetch(reconnectUrl, {
        method: 'GET',
        headers: {
          'Accept': 'text/event-stream'
        },
        signal: abortController.signal
      })

      if (!response.ok) {
        if (response.status === 410) {
          console.log('ℹ️ Session 已结束 (410 Gone)')
          return ''
        }
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      if (!response.body) {
        throw new Error('响应体为空')
      }

      console.log('✅ SSE 重连成功')
      isConnected.value = true
      reconnectAttempts.value = 0
      sessionStore.setConnected(true)
      onConnected?.()

      // 读取流
      const fullResponse = await readSSEStream(response.body, onEvent)

      isConnected.value = false
      sessionStore.setConnected(false)
      onDisconnected?.()

      return fullResponse
    } catch (error) {
      isConnected.value = false
      sessionStore.setConnected(false)

      if ((error as Error).name === 'AbortError') {
        console.log('🔌 SSE 重连已取消')
        onDisconnected?.()
        return ''
      }

      console.error('❌ 断线重连失败:', error)

      // 如果还有重连次数，继续尝试
      if (reconnectAttempts.value < maxReconnectAttempts) {
        return reconnect(sessionId, afterSeq, options)
      }

      onError?.(error as Error)
      throw error
    }
  }

  /**
   * 断开 SSE 连接
   */
  function disconnect(): void {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    isConnected.value = false
    sessionStore.setConnected(false)
    console.log('🔌 SSE 连接已断开')
  }

  /**
   * 重置状态
   */
  function reset(): void {
    disconnect()
    lastEventId.value = 0
    reconnectAttempts.value = 0
  }

  /**
   * 读取 SSE 流
   */
  async function readSSEStream(
    body: ReadableStream<Uint8Array>,
    onEvent: SSEEventHandler
  ): Promise<string> {
    const reader = body.getReader()
    const decoder = new TextDecoder()

    let buffer = ''
    let fullResponse = ''
    let currentEvent: { id: string | null; event: string | null; data: string | null } = {
      id: null,
      event: null,
      data: null
    }

    try {
      while (true) {
        const { done, value } = await reader.read()

        if (done) {
          console.log('✅ SSE 连接正常关闭')
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')

        // 如果最后一行不完整，保留到下次处理
        if (!buffer.endsWith('\n')) {
          buffer = lines.pop() || ''
        } else {
          buffer = ''
        }

        for (const line of lines) {
          // 空行表示一个完整的 SSE 消息结束
          if (line === '') {
            if (currentEvent.data) {
              try {
                const data = JSON.parse(currentEvent.data)
                const eventType = data.type || currentEvent.event

                // 确保 data 包含 type 字段
                if (!data.type && eventType) {
                  data.type = eventType
                }

                // 记录事件 ID
                if (currentEvent.id) {
                  lastEventId.value = parseInt(currentEvent.id, 10) || lastEventId.value
                  sessionStore.setLastEventId(lastEventId.value)
                }

                // 回调处理事件
                onEvent(data)

                // 累积文本响应
                if (eventType === 'content_delta' && data.data?.delta) {
                  const delta = data.data.delta
                  if (typeof delta === 'string') {
                    fullResponse += delta
                  } else if (delta?.text) {
                    fullResponse += delta.text
                  }
                }

                // 处理 complete 事件
                if (eventType === 'complete' && data.data?.final_result && !fullResponse) {
                  fullResponse = data.data.final_result
                }

                // 流结束
                if (eventType === 'done' || eventType === 'session_end') {
                  console.log('✅ 流结束:', eventType)
                  return fullResponse
                }
              } catch (e) {
                console.error('❌ 解析 SSE 数据失败:', e, currentEvent.data)
              }
            }

            // 重置当前事件
            currentEvent = { id: null, event: null, data: null }
          } else if (line.startsWith('id: ')) {
            currentEvent.id = line.slice(4).trim()
          } else if (line.startsWith('event: ')) {
            currentEvent.event = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            // data 可能跨多行
            if (currentEvent.data) {
              currentEvent.data += '\n' + line.slice(6)
            } else {
              currentEvent.data = line.slice(6)
            }
          }
        }
      }
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        console.error('❌ SSE 读取错误:', error)
        throw error
      }
    }

    return fullResponse
  }

  /**
   * 辅助函数：延迟
   */
  function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  return {
    // 状态
    isConnected,
    lastEventId,
    reconnectAttempts,
    maxReconnectAttempts,

    // 方法
    connect,
    reconnect,
    disconnect,
    reset
  }
}

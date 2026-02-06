/**
 * SSE 连接 Composable
 * 负责管理 SSE 流连接、事件解析
 */

import { ref } from 'vue'
import { useSessionStore } from '@/stores/session'
import { getFullApiUrl } from '@/api'
import type { SSEEvent, ChatRequest } from '@/types'

export type SSEEventHandler = (event: SSEEvent) => void

export interface SSEConnectOptions {
  onEvent: SSEEventHandler
  onConnected?: () => void
  onDisconnected?: () => void
  onError?: (error: Error) => void
}

export function useSSE() {
  const sessionStore = useSessionStore()

  const isConnected = ref(false)
  const lastEventId = ref(0)

  let abortController: AbortController | null = null

  /**
   * 创建 SSE 连接（POST 请求）
   */
  async function connect(
    requestBody: ChatRequest,
    options: SSEConnectOptions
  ): Promise<string> {
    const { onEvent, onConnected, onDisconnected, onError } = options

    disconnect()
    abortController = new AbortController()

    try {
      const response = await fetch(getFullApiUrl('/v1/chat?format=zenflux'), {
        method: 'POST',
        headers: {
          'Accept': 'text/event-stream',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody),
        signal: abortController.signal
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      if (!response.body) {
        throw new Error('响应体为空')
      }

      isConnected.value = true
      sessionStore.setConnected(true)
      onConnected?.()

      const fullResponse = await readSSEStream(response.body, onEvent)

      isConnected.value = false
      sessionStore.setConnected(false)
      onDisconnected?.()

      return fullResponse
    } catch (error) {
      isConnected.value = false
      sessionStore.setConnected(false)

      if ((error as Error).name === 'AbortError') {
        onDisconnected?.()
        return ''
      }

      console.error('SSE 连接错误:', error)
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
  }

  /**
   * 重置状态
   */
  function reset(): void {
    disconnect()
    lastEventId.value = 0
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

        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')

        if (!buffer.endsWith('\n')) {
          buffer = lines.pop() || ''
        } else {
          buffer = ''
        }

        for (const line of lines) {
          if (line === '') {
            if (currentEvent.data) {
              try {
                const data = JSON.parse(currentEvent.data)
                const eventType = data.type || currentEvent.event

                if (!data.type && eventType) {
                  data.type = eventType
                }

                if (currentEvent.id) {
                  lastEventId.value = parseInt(currentEvent.id, 10) || lastEventId.value
                  sessionStore.setLastEventId(lastEventId.value)
                }

                onEvent(data)

                if (eventType === 'content_delta' && data.data?.delta) {
                  const delta = data.data.delta
                  if (typeof delta === 'string') {
                    fullResponse += delta
                  } else if (delta?.text) {
                    fullResponse += delta.text
                  }
                }

                if (eventType === 'complete' && data.data?.final_result && !fullResponse) {
                  fullResponse = data.data.final_result
                }

                if (
                  currentEvent.event === 'done' ||
                  eventType === 'message_stop' ||
                  eventType === 'session_end'
                ) {
                  return fullResponse
                }
              } catch (e) {
                console.error('解析 SSE 数据失败:', e, currentEvent.data)
              }
            }

            currentEvent = { id: null, event: null, data: null }
          } else if (line.startsWith('id: ')) {
            currentEvent.id = line.slice(4).trim()
          } else if (line.startsWith('event: ')) {
            currentEvent.event = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
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
        console.error('SSE 读取错误:', error)
        throw error
      }
    }

    return fullResponse
  }

  return {
    isConnected,
    lastEventId,
    connect,
    disconnect,
    reset
  }
}

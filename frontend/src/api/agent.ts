import api from './index'
import { getFullApiUrl } from './index'
import type {
  AgentSummary,
  AgentListResponse,
  AgentDetail,
  AgentCreateRequest,
  AgentUpdateRequest
} from '@/types'

/**
 * Agent（项目）管理 API
 * 对接后端 /api/v1/agents 端点
 */

/**
 * 获取 Agent 列表
 */
export async function getAgentList(): Promise<AgentSummary[]> {
  const response = await api.get<AgentListResponse>('/v1/agents')
  return response.data?.agents ?? []
}

/**
 * 获取 Agent 详情
 */
export async function getAgentDetail(agentId: string): Promise<AgentDetail> {
  const response = await api.get<AgentDetail>(`/v1/agents/${agentId}`)
  return response.data
}

/**
 * 创建 Agent
 */
export async function createAgent(data: AgentCreateRequest): Promise<AgentDetail> {
  const response = await api.post<AgentDetail>('/v1/agents', data)
  return response.data
}

/** SSE progress event from create-agent endpoint */
export interface CreateAgentProgressEvent {
  type: 'progress'
  step: number
  total: number
  message: string
}

/** SSE complete event from create-agent endpoint */
export interface CreateAgentCompleteEvent {
  type: 'complete'
  agent_id: string
  success: boolean
  [key: string]: unknown
}

/** SSE error event from create-agent endpoint */
export interface CreateAgentErrorEvent {
  type: 'error'
  code: string
  message: string
}

type CreateAgentSSEEvent = CreateAgentProgressEvent | CreateAgentCompleteEvent | CreateAgentErrorEvent

/**
 * 创建 Agent（SSE 流式进度推送）
 *
 * 通过 SSE 实时接收创建进度，避免长时间无反馈。
 *
 * @param data - 创建请求参数
 * @param onProgress - 进度回调 (step, total, message)
 * @param signal - AbortController signal for timeout/cancel
 * @returns 创建完成后的 Agent 详情
 */
export async function createAgentSSE(
  data: AgentCreateRequest,
  onProgress: (step: number, total: number, message: string) => void,
  signal?: AbortSignal,
): Promise<AgentDetail> {
  const url = getFullApiUrl('/v1/agents')
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify(data),
    signal,
  })

  if (!response.ok) {
    // Try to parse error body
    let detail = `HTTP ${response.status}`
    try {
      const body = await response.json()
      detail = body?.detail?.message || body?.detail || detail
    } catch { /* ignore parse error */ }
    throw new Error(detail)
  }

  if (!response.body) {
    throw new Error('响应体为空')
  }

  // Parse SSE stream
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: AgentDetail | null = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // Process complete SSE messages (separated by double newline)
    const parts = buffer.split('\n\n')
    // Keep the last incomplete part in the buffer
    buffer = parts.pop() || ''

    for (const part of parts) {
      if (!part.trim()) continue

      // Check for "event: done" line (stream termination)
      if (part.includes('event: done')) continue

      // Extract data from "data: ..." line
      const dataLine = part.split('\n').find(line => line.startsWith('data: '))
      if (!dataLine) continue

      const jsonStr = dataLine.slice(6) // Remove "data: " prefix
      if (!jsonStr.trim()) continue

      let event: CreateAgentSSEEvent
      try {
        event = JSON.parse(jsonStr)
      } catch {
        // JSON parse error, skip this malformed event
        continue
      }

      if (event.type === 'progress') {
        onProgress(event.step, event.total, event.message)
      } else if (event.type === 'complete') {
        result = event as unknown as AgentDetail
      } else if (event.type === 'error') {
        throw new Error(event.message || '创建失败')
      }
    }
  }

  if (!result) {
    throw new Error('SSE 流意外终止，未收到完成事件')
  }

  return result
}

/**
 * 更新 Agent
 */
export async function updateAgent(agentId: string, data: AgentUpdateRequest): Promise<AgentDetail> {
  const response = await api.put<AgentDetail>(`/v1/agents/${agentId}`, data)
  return response.data
}

/**
 * 删除 Agent
 */
export async function deleteAgent(agentId: string): Promise<void> {
  await api.delete(`/v1/agents/${agentId}`)
}

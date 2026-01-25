/**
 * Session 管理 API
 */

import api from './index'
import type {
  ApiResponse,
  SessionStatusResponse,
  UserSessionsResponse,
  ActiveSession
} from '@/types'

/**
 * 获取会话状态
 * @param sessionId - Session ID
 */
export async function getSessionStatus(sessionId: string): Promise<SessionStatusResponse> {
  const response = await api.get<ApiResponse<SessionStatusResponse>>(
    `/v1/session/${sessionId}/status`
  )
  return response.data.data
}

/**
 * 获取会话事件（用于断线重连）
 * @param sessionId - Session ID
 * @param afterId - 从该事件ID之后开始获取
 * @param limit - 获取数量限制
 */
export async function getSessionEvents(
  sessionId: string,
  afterId: number | null = null,
  limit = 100
): Promise<{ events: unknown[] }> {
  const params: Record<string, unknown> = { limit }
  if (afterId !== null) {
    params.after_id = afterId
  }

  const response = await api.get<ApiResponse<{ events: unknown[] }>>(
    `/v1/session/${sessionId}/events`,
    { params }
  )
  return response.data.data
}

/**
 * 停止会话
 * @param sessionId - Session ID
 */
export async function stopSession(sessionId: string): Promise<void> {
  await api.post(`/v1/session/${sessionId}/stop`)
}

/**
 * 获取用户的所有活跃会话
 * @param userId - 用户 ID
 */
export async function getUserSessions(userId: string): Promise<ActiveSession[]> {
  const response = await api.get<ApiResponse<UserSessionsResponse>>(
    `/v1/user/${userId}/sessions`
  )
  return response.data.data.sessions
}

/**
 * 提交 HITL 人工确认响应
 * @param sessionId - Session ID
 * @param response - 用户响应
 */
export async function submitHITLResponse(
  sessionId: string,
  userResponse: string | string[] | Record<string, unknown>
): Promise<{ success: boolean; message?: string }> {
  const response = await api.post<ApiResponse<{ success: boolean; message?: string }>>(
    `/v1/human-confirmation/${sessionId}`,
    { response: userResponse }
  )
  return response.data.data
}

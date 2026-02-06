/**
 * Session 管理 API
 */

import api from './index'
import type { ApiResponse } from '@/types'

/**
 * 停止会话
 */
export async function stopSession(sessionId: string): Promise<void> {
  await api.post(`/v1/session/${sessionId}/stop`)
}

/**
 * 提交 HITL 人工确认响应
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

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

/**
 * HITL 危险操作确认（V11.1）
 * 执行器检测到危险工具调用并发出 hitl_confirm 后，用户确认/拒绝时调用
 * - approved=true: 批准执行危险操作
 * - approved=false: 拒绝执行，触发回退策略（回滚/停止/询问回滚）
 */
export async function submitHITLConfirm(
  sessionId: string,
  approved: boolean
): Promise<void> {
  await api.post(`/v1/session/${sessionId}/hitl_confirm`, null, {
    params: { approved }
  })
}

/**
 * 确认继续长任务（V11 终止策略）
 * 执行器发出 long_running_confirm 后，用户点击「继续」时调用
 */
export async function confirmContinueSession(sessionId: string): Promise<void> {
  await api.post(`/v1/session/${sessionId}/confirm_continue`)
}

/**
 * 回滚会话状态（V11 状态一致性）
 * 将文件与环境恢复到任务开始前的快照
 */
export async function rollbackSession(
  sessionId: string
): Promise<{ session_id: string; messages: string[] }> {
  const response = await api.post<ApiResponse<{ session_id: string; messages: string[] }>>(
    `/v1/session/${sessionId}/rollback`
  )
  return response.data.data
}

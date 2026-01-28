import api from './index'
import type { ApiResponse, Conversation, Message } from '@/types'

/**
 * 创建新对话
 */
export async function createConversation(userId: string, title = '新对话'): Promise<Conversation> {
  const response = await api.post<ApiResponse<Conversation>>('/v1/conversations', null, {
    params: { user_id: userId, title }
  })
  return response.data.data
}

/**
 * 获取对话列表
 */
export async function getConversationList(
  userId: string,
  limit = 20,
  offset = 0
): Promise<{ conversations: Conversation[]; total: number }> {
  const response = await api.get<ApiResponse<{ conversations: Conversation[]; total: number }>>(
    '/v1/conversations',
    { params: { user_id: userId, limit, offset } }
  )
  return response.data.data
}

/**
 * 获取对话详情
 */
export async function getConversation(conversationId: string): Promise<Conversation> {
  const response = await api.get<ApiResponse<Conversation>>(`/v1/conversations/${conversationId}`)
  return response.data.data
}

/**
 * 更新对话标题
 */
export async function updateConversation(conversationId: string, title: string): Promise<Conversation> {
  const response = await api.put<ApiResponse<Conversation>>(
    `/v1/conversations/${conversationId}`,
    null,
    { params: { title } }
  )
  return response.data.data
}

/**
 * 删除对话
 */
export async function deleteConversation(conversationId: string): Promise<void> {
  await api.delete(`/v1/conversations/${conversationId}`)
}

/**
 * 获取对话消息列表
 */
export async function getConversationMessages(
  conversationId: string,
  limit = 50,
  offset = 0,
  order: 'asc' | 'desc' = 'asc'
): Promise<{ messages: Message[]; conversation_metadata?: Record<string, unknown> }> {
  const response = await api.get<ApiResponse<{ messages: Message[]; conversation_metadata?: Record<string, unknown> }>>(
    `/v1/conversations/${conversationId}/messages`,
    { params: { limit, offset, order } }
  )
  return response.data.data
}

/**
 * 获取会话状态
 */
export async function getSessionStatus(sessionId: string): Promise<{ status: string }> {
  const response = await api.get<ApiResponse<{ status: string }>>(`/v1/session/${sessionId}/status`)
  return response.data.data
}

/**
 * 停止会话
 */
export async function stopSession(sessionId: string): Promise<void> {
  await api.post(`/v1/session/${sessionId}/stop`)
}

/**
 * 获取用户活跃会话列表
 */
export async function getUserSessions(userId: string): Promise<{ sessions: unknown[] }> {
  const response = await api.get<ApiResponse<{ sessions: unknown[] }>>(`/v1/user/${userId}/sessions`)
  return response.data.data
}


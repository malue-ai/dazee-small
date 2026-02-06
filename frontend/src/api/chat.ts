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
  // 防御性处理：确保返回值始终包含 conversations 数组
  const data = response.data?.data
  return {
    conversations: data?.conversations ?? [],
    total: data?.total ?? 0
  }
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

/** 消息列表响应类型 */
export interface MessagesResponse {
  messages: Message[]
  conversation_metadata?: Record<string, unknown>
  total: number
  has_more: boolean
  next_cursor: string | null
}

/**
 * 获取对话消息列表（支持游标分页）
 * @param conversationId - 对话 ID
 * @param limit - 返回数量
 * @param offset - 偏移量（初始加载时使用）
 * @param order - 排序方式
 * @param beforeCursor - 游标（加载更早消息时使用）
 */
export async function getConversationMessages(
  conversationId: string,
  limit = 50,
  offset = 0,
  order: 'asc' | 'desc' = 'asc',
  beforeCursor?: string
): Promise<MessagesResponse> {
  const params: Record<string, unknown> = { limit, offset, order }
  if (beforeCursor) {
    params.before_cursor = beforeCursor
  }
  
  const response = await api.get<ApiResponse<MessagesResponse>>(
    `/v1/conversations/${conversationId}/messages`,
    { params }
  )
  // 防御性处理：确保返回值包含必要字段
  const data = response.data?.data
  return {
    messages: data?.messages ?? [],
    conversation_metadata: data?.conversation_metadata,
    total: data?.total ?? 0,
    has_more: data?.has_more ?? false,
    next_cursor: data?.next_cursor ?? null
  }
}

/** 搜索结果项 */
export interface SearchConversationItem {
  conversation: Conversation
  match_type: 'title' | 'content'
  snippet: string | null
}

/** 搜索结果响应 */
export interface SearchConversationsResponse {
  conversations: SearchConversationItem[]
  total: number
}

/**
 * 搜索对话（标题 + 消息内容全文搜索）
 */
export async function searchConversations(
  userId: string,
  query: string,
  limit = 20
): Promise<SearchConversationsResponse> {
  const response = await api.get<ApiResponse<SearchConversationsResponse>>(
    '/v1/conversations/search',
    { params: { user_id: userId, q: query, limit } }
  )
  const data = response.data?.data
  return {
    conversations: data?.conversations ?? [],
    total: data?.total ?? 0
  }
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


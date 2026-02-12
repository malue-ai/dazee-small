/**
 * API 请求/响应类型定义
 */

// ==================== 通用响应类型 ====================

/**
 * API 标准响应包装
 */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

/**
 * 分页参数
 */
export interface PaginationParams {
  limit?: number
  offset?: number
}

/**
 * 分页响应
 */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

// ==================== 对话相关 ====================

/**
 * 对话信息
 */
export interface Conversation {
  id: string
  title: string
  user_id: string
  created_at: string
  updated_at: string
  metadata?: {
    agent_id?: string
    [key: string]: unknown
  }
}

/**
 * 对话列表响应
 */
export interface ConversationListResponse {
  conversations: Conversation[]
  total: number
}

/**
 * 消息信息
 */
export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string | object[]
  conversation_id: string
  created_at: string
  metadata?: MessageMetadata
}

/**
 * 消息元数据
 */
export interface MessageMetadata {
  plan?: string | object
  recommended?: string[]
  files?: Array<{
    file_url: string
    local_path?: string
    file_name: string
    file_type: string
    file_size?: number
  }>
  [key: string]: unknown
}

/**
 * 消息列表响应
 */
export interface MessageListResponse {
  messages: Message[]
}

// ==================== Session 相关 ====================

/**
 * Session 状态
 */
export type SessionStatus = 'running' | 'completed' | 'failed' | 'timeout' | 'stopped'

/**
 * Session 状态响应
 */
export interface SessionStatusResponse {
  session_id: string
  status: SessionStatus
  progress?: number
  message?: string
}

/**
 * Session 事件
 */
export interface SessionEvent {
  id: number
  type: string
  data: object
  timestamp: string
}

/**
 * 活跃 Session 信息
 */
export interface ActiveSession {
  session_id: string
  conversation_id: string
  status: SessionStatus
  progress?: number
  start_time: string
  message_preview?: string
  message_id?: string
}

/**
 * 用户活跃 Session 列表响应
 */
export interface UserSessionsResponse {
  sessions: ActiveSession[]
}

// ==================== 知识库相关 ====================

/**
 * 文档状态
 */
export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed'

/**
 * 知识库文档
 */
export interface KnowledgeDocument {
  document_id: string
  name: string
  status: DocumentStatus
  file_type?: string
  file_size?: number
  chunk_count?: number
  created_at: string
  updated_at?: string
  metadata?: Record<string, unknown>
}

/**
 * 文档列表响应
 */
export interface DocumentListResponse {
  documents: KnowledgeDocument[]
  total: number
}

/**
 * 检索结果
 */
export interface RetrievalResult {
  chunk_id: string
  document_id: string
  document_name: string
  content: string
  score: number
  metadata?: Record<string, unknown>
}

/**
 * 检索响应
 */
export interface RetrievalResponse {
  results: RetrievalResult[]
  query: string
}

/**
 * 知识库统计
 */
export interface KnowledgeStats {
  total_documents: number
  ready_documents: number
  total_chunks: number
  total_size: number
}

// ==================== 文件上传相关 ====================

/**
 * 文件上传响应
 */
export interface FileUploadResponse {
  file_url: string
  local_path: string
  file_name: string
  file_type: string
  file_size: number
  file_id?: string
}

// ==================== 聊天请求 ====================

/**
 * 聊天请求体
 */
export interface ChatRequest {
  message: string
  user_id: string
  conversation_id?: string
  stream?: boolean
  agent_id?: string
  background_tasks?: string[]
  files?: Array<{
    file_url: string
    local_path?: string
    file_name: string
    file_type: string
    file_size?: number
  }>
  variables?: Record<string, unknown>
}

/**
 * 同步聊天响应
 */
export interface ChatResponse {
  task_id: string
  conversation_id: string
  message_id: string
  content: string
}

// ==================== HITL 相关 ====================

/**
 * HITL 响应请求
 */
export interface HITLSubmitRequest {
  response: string | string[] | Record<string, unknown>
}

/**
 * HITL 响应结果
 */
export interface HITLSubmitResponse {
  success: boolean
  message?: string
}

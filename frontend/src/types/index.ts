// API 响应类型
export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

// 用户类型
export interface User {
  id: string
  username: string
  created_at?: string
}

// 认证类型
export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  token: string
  user: User
}

// 对话类型
export interface Conversation {
  id: string
  title: string
  user_id: string
  created_at: string
  updated_at: string
}

// 消息类型
export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  conversation_id: string
  created_at: string
  metadata?: Record<string, unknown>
}

// 消息内容块类型
export interface ContentBlock {
  type: 'text' | 'thinking' | 'tool_use' | 'tool_result'
  text?: string
  thinking?: string
  id?: string
  name?: string
  input?: Record<string, unknown>
  tool_use_id?: string
  content?: string
  is_error?: boolean
  partialInput?: string
  _blockType?: string
}

// Agent 类型
export interface Agent {
  id: string
  name: string
  description?: string
  config?: Record<string, unknown>
  created_at: string
  updated_at: string
}

// 知识库类型
export interface Knowledge {
  id: string
  name: string
  description?: string
  file_count: number
  created_at: string
}

// 文件类型
export interface UploadedFile {
  file_id: string
  filename: string
  mime_type: string
  file_size?: number
  preview_url?: string
}

// SSE 事件类型
export interface SSEEvent {
  type: string
  data: Record<string, unknown>
  session_id?: string
}

// UI 消息类型（前端展示用）
export interface UIMessage {
  id: number | string
  role: 'user' | 'assistant'
  content: string
  thinking?: string
  contentBlocks: ContentBlock[]
  toolStatuses: Record<string, ToolStatus>
  files?: UploadedFile[]
  recommendedQuestions?: string[]
  planResult?: PlanData | null
  timestamp: Date
}

export interface ToolStatus {
  pending?: boolean
  success?: boolean
  result?: string
}

export interface PlanData {
  goal?: string
  steps?: PlanStep[]
}

export interface PlanStep {
  id: string
  title: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  description?: string
}


/**
 * 聊天相关类型定义
 */

// ==================== SSE 事件类型 ====================

/**
 * SSE 事件类型枚举
 */
export type SSEEventType =
  | 'session_start'
  | 'conversation_start'
  | 'message_start'
  | 'content_start'
  | 'content_delta'
  | 'content_stop'
  | 'message_delta'
  | 'message_stop'
  | 'complete'
  | 'done'
  | 'session_end'
  | 'error'
  | 'reconnect_info'

/**
 * SSE 基础事件结构
 */
export interface SSEEvent<T = unknown> {
  type: SSEEventType
  data: T
  session_id?: string
  seq?: number
}

/**
 * 会话开始事件数据
 */
export interface ConversationStartData {
  conversation_id: string
}

/**
 * 内容块开始事件数据
 */
export interface ContentStartData {
  index: number
  content_block: ContentBlock
}

/**
 * 内容增量事件数据
 */
export interface ContentDeltaData {
  index: number
  delta: string | { text?: string; thinking?: string; partial_json?: string }
}

/**
 * 内容块停止事件数据
 */
export interface ContentStopData {
  index: number
}

/**
 * 消息增量事件数据
 */
export interface MessageDeltaData {
  delta: {
    type: 'plan' | 'recommended' | 'confirmation_request' | 'preface'
    content: string | object
  }
}

/**
 * 重连信息事件数据
 */
export interface ReconnectInfoData {
  conversation_id: string
  message_id: string
  session_id: string
}

// ==================== 消息内容块类型 ====================

/**
 * 内容块类型枚举
 */
export type ContentBlockType =
  | 'text'
  | 'thinking'
  | 'tool_use'
  | 'tool_result'
  | 'server_tool_use'
  | 'image'
  | 'file'

/**
 * 基础内容块
 */
export interface BaseContentBlock {
  type: ContentBlockType
  _blockType?: string
}

/**
 * 文本内容块
 */
export interface TextContentBlock extends BaseContentBlock {
  type: 'text'
  text: string
}

/**
 * 思考内容块
 */
export interface ThinkingContentBlock extends BaseContentBlock {
  type: 'thinking'
  thinking: string
}

/**
 * 工具调用内容块
 */
export interface ToolUseContentBlock extends BaseContentBlock {
  type: 'tool_use' | 'server_tool_use'
  id: string
  name: string
  input?: Record<string, unknown>
  partialInput?: string
  _isHitlTool?: boolean
}

/**
 * 工具结果内容块
 * content 支持字符串或多模态内容块数组（如 observe_screen 返回 [text, image]）
 */
export interface ToolResultContentBlock extends BaseContentBlock {
  type: 'tool_result'
  tool_use_id: string
  content: string | ContentBlock[]
  is_error?: boolean
}

/**
 * 图片内容块
 */
export interface ImageContentBlock extends BaseContentBlock {
  type: 'image'
  source?: {
    type: 'base64' | 'url'
    media_type?: string
    data?: string
    url?: string
  }
  url?: string
  alt?: string
}

/**
 * 文件内容块
 */
export interface FileContentBlock extends BaseContentBlock {
  type: 'file'
  name: string
  url?: string
  size?: number
}

/**
 * 内容块联合类型
 */
export type ContentBlock =
  | TextContentBlock
  | ThinkingContentBlock
  | ToolUseContentBlock
  | ToolResultContentBlock
  | ImageContentBlock
  | FileContentBlock

// ==================== 工具状态 ====================

/**
 * 工具执行状态
 */
export interface ToolStatus {
  pending?: boolean
  success?: boolean
  result?: string | object
}

/**
 * 工具状态映射
 */
export type ToolStatusMap = Record<string, ToolStatus>

// ==================== UI 消息类型 ====================

/**
 * 附件文件信息
 */
export interface AttachedFile {
  file_url: string
  file_name: string
  file_type: string
  file_size?: number
  preview_url?: string
}

/**
 * 计划步骤（plan_todo 工具格式）
 */
export interface PlanStep {
  id: string
  content: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  result?: string
}

/**
 * 计划数据（plan_todo 工具格式）
 */
export interface PlanData {
  name: string
  overview?: string
  detailed_plan?: string
  todos: PlanStep[]
  created_at?: string
}

/**
 * 前端 UI 消息（用于展示）
 */
export interface UIMessage {
  id: number | string
  role: 'user' | 'assistant'
  content: string
  thinking?: string
  contentBlocks: ContentBlock[]
  toolStatuses: ToolStatusMap
  files?: AttachedFile[]
  recommendedQuestions?: string[]
  planResult?: PlanData | null
  timestamp: Date
}

// ==================== HITL 人工确认类型 ====================

/**
 * HITL 确认类型
 */
export type HITLConfirmationType =
  | 'yes_no'
  | 'single_choice'
  | 'multiple_choice'
  | 'text_input'
  | 'form'

/**
 * HITL 表单问题
 */
export interface HITLFormQuestion {
  id: string
  label: string
  type: 'single_choice' | 'multiple_choice' | 'text_input'
  options?: string[]
  hint?: string
  required?: boolean
  default?: string | string[]
}

/**
 * HITL 确认请求
 */
export interface HITLConfirmRequest {
  question: string
  options?: string[]
  confirmation_type: HITLConfirmationType
  timeout?: number
  description?: string
  questions?: HITLFormQuestion[]
  default_value?: string | string[]
  metadata?: Record<string, unknown>
}

/**
 * HITL 响应类型
 */
export type HITLResponse = string | string[] | Record<string, string | string[]>

// ==================== 发送消息选项 ====================

/**
 * 发送消息的选项
 */
export interface SendMessageOptions {
  files?: AttachedFile[]
  backgroundTasks?: string[]
  agentId?: string | null
  variables?: {
    timezone?: string
    locale?: string
    local_time?: string
    [key: string]: unknown
  }
}

// ==================== 活跃会话信息 ====================

/**
 * 活跃会话信息
 */
export interface ActiveSessionInfo {
  sessionId: string
  status: string
  progress?: number
  startTime?: string
  messagePreview?: string
}

/**
 * 活跃会话映射（conversationId -> sessionInfo）
 */
export type ActiveSessionsMap = Record<string, ActiveSessionInfo>

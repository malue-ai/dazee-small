/**
 * 类型定义入口文件
 * 从各模块重新导出所有类型
 */

// 从 api.ts 导出 API 相关类型
export type {
  ApiResponse,
  PaginationParams,
  PaginatedResponse,
  LoginRequest,
  LoginResponse,
  User,
  Conversation,
  ConversationListResponse,
  Message,
  MessageMetadata,
  MessageListResponse,
  SessionStatus,
  SessionStatusResponse,
  SessionEvent,
  ActiveSession,
  UserSessionsResponse,
  Agent,
  AgentListResponse,
  DocumentStatus,
  KnowledgeDocument,
  DocumentListResponse,
  RetrievalResult,
  RetrievalResponse,
  KnowledgeStats,
  FileUploadResponse,
  ChatRequest,
  ChatResponse,
  HITLSubmitRequest,
  HITLSubmitResponse
} from './api'

// 从 chat.ts 导出聊天相关类型
export type {
  SSEEventType,
  SSEEvent,
  ConversationStartData,
  ContentStartData,
  ContentDeltaData,
  ContentStopData,
  MessageDeltaData,
  ReconnectInfoData,
  ContentBlockType,
  BaseContentBlock,
  TextContentBlock,
  ThinkingContentBlock,
  ToolUseContentBlock,
  ToolResultContentBlock,
  ImageContentBlock,
  FileContentBlock,
  ContentBlock,
  ToolStatus,
  ToolStatusMap,
  AttachedFile,
  PlanStep,
  PlanData,
  UIMessage,
  HITLConfirmationType,
  HITLFormQuestion,
  HITLConfirmRequest,
  HITLResponse,
  SendMessageOptions,
  ActiveSessionInfo,
  ActiveSessionsMap
} from './chat'

// 从 workspace.ts 导出工作区相关类型
export type {
  FileType,
  FileItem,
  FileContentResponse,
  SandboxStatus,
  SandboxStack,
  SandboxInfo,
  SandboxStatusResponse,
  CommandResult,
  ProjectInfo,
  ProjectRunResult,
  TerminalLogType,
  TerminalLogItem,
  CodeLanguage,
  LivePreviewState
} from './workspace'

export { WORKSPACE_API_PATHS } from './workspace'

// 从 skills.ts 导出 Skill 相关类型
export type {
  SkillPriority,
  SkillStatus,
  Skill,
  SkillSummary,
  SkillListResponse,
  SkillCreateRequest,
  SkillUpdateRequest,
  SkillUpdateContentRequest,
  SkillScript,
  SkillResource,
  SkillInstallRequest,
  SkillUninstallRequest,
  SkillToggleRequest
} from './skills'

// ==================== 兼容性类型别名 ====================
// 保持向后兼容，旧代码可以继续使用这些名称

/**
 * @deprecated 请使用 KnowledgeDocument
 */
export type Knowledge = {
  id: string
  name: string
  description?: string
  file_count: number
  created_at: string
}

/**
 * @deprecated 请使用 AttachedFile
 */
export type UploadedFile = {
  file_id: string
  filename: string
  mime_type: string
  file_size?: number
  preview_url?: string
}


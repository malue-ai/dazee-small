/**
 * 类型定义入口文件
 * 从各模块重新导出所有类型
 */

// 从 api.ts 导出 API 相关类型
export type {
  ApiResponse,
  PaginationParams,
  PaginatedResponse,
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
  CloudProgressItem,
  UIMessage,
  HITLConfirmationType,
  HITLFormQuestion,
  HITLConfirmRequest,
  HITLResponse,
  PlaybookSuggestion,
  SendMessageOptions,
  ActiveSessionInfo,
  ActiveSessionsMap
} from './chat'

// 从 workspace.ts 导出工作区相关类型
export type {
  FileType,
  FileItem,
  FileContentResponse,
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
  SkillRuntimeStatus,
  EnvRequirement,
  Skill,
  SkillSummary,
  SkillListResponse,
  SkillCreateRequest,
  SkillUpdateRequest,
  SkillUpdateContentRequest,
  SkillConfigureRequest,
  SkillScript,
  SkillResource,
  SkillInstallRequest,
  SkillUninstallRequest
} from './skills'

// 从 agent.ts 导出 Agent（项目）相关类型
export type {
  AgentStatus,
  AgentSummary,
  AgentListResponse,
  AgentDetail,
  AgentMCPTool,
  AgentAPI,
  AgentCreateRequest,
  AgentCreateResponse,
  AgentUpdateRequest,
  AgentUpdateResponse,
  AgentCreationProgressEvent,
  AgentCreationCompleteEvent,
  AgentCreationErrorEvent,
  AgentCreationPingEvent,
  AgentCreationEvent
} from './agent'

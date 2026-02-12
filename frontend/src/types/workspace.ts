/**
 * 工作区相关类型定义
 */

// ==================== 文件系统类型 ====================

/**
 * 文件类型
 */
export type FileType = 'file' | 'directory'

/**
 * 文件/目录项
 */
export interface FileItem {
  name: string
  path: string
  type: FileType
  size?: number
  modified?: string
  children?: FileItem[]
}

/**
 * 文件内容响应
 */
export interface FileContentResponse {
  content: string
  path: string
  size: number
  encoding?: string
}

/**
 * 命令执行结果
 */
export interface CommandResult {
  stdout: string
  stderr: string
  exit_code: number
  duration_ms?: number
}

// ==================== 项目类型 ====================

/**
 * 项目信息
 */
export interface ProjectInfo {
  name: string
  path: string
  type: string
  entry_file?: string
  port?: number
  status?: 'stopped' | 'running' | 'error'
}

/**
 * 项目运行结果
 */
export interface ProjectRunResult {
  success: boolean
  preview_url?: string
  message?: string
  error?: string
}

// ==================== 终端类型 ====================

/**
 * 终端日志类型
 */
export type TerminalLogType = 'command' | 'output' | 'error' | 'info'

/**
 * 终端日志项
 */
export interface TerminalLogItem {
  type: TerminalLogType
  content: string
  cwd?: string | null
  timestamp: number
}

// ==================== 实时预览类型 ====================

/**
 * 代码语言类型
 */
export type CodeLanguage =
  | 'text'
  | 'python'
  | 'javascript'
  | 'typescript'
  | 'vue'
  | 'html'
  | 'css'
  | 'scss'
  | 'json'
  | 'markdown'
  | 'yaml'
  | 'bash'
  | 'sql'
  | 'xml'
  | 'java'
  | 'go'
  | 'rust'
  | 'c'
  | 'cpp'

/**
 * 实时预览状态
 */
export interface LivePreviewState {
  isActive: boolean
  toolName: string | null
  toolId: string | null
  filePath: string | null
  content: string
  accumulatedInput: string
  language: CodeLanguage
}

// ==================== API 路径定义 ====================

/**
 * Workspace API 路径
 */
export const WORKSPACE_API_PATHS = {
  FILES: (conversationId: string) => `/v1/workspace/${conversationId}/files`,
  PROJECTS: (conversationId: string) => `/v1/workspace/${conversationId}/projects`,
  FILE: (conversationId: string, path: string) => 
    `/v1/workspace/${conversationId}/file?path=${encodeURIComponent(path)}`,
  RUN_PROJECT: (conversationId: string, projectName: string) => 
    `/v1/workspace/${conversationId}/projects/${projectName}/run`,
  STOP_PROJECT: (conversationId: string, projectName: string) => 
    `/v1/workspace/${conversationId}/projects/${projectName}/stop`,
  PROJECT_LOGS: (conversationId: string, projectName: string) => 
    `/v1/workspace/${conversationId}/projects/${projectName}/logs`
} as const

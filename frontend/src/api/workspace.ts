/**
 * 工作区 API
 */

import api from './index'
import type {
  ApiResponse,
  FileItem,
  FileContentResponse,
  SandboxStatusResponse,
  SandboxInfo,
  CommandResult,
  ProjectInfo,
  ProjectRunResult,
  SandboxStack
} from '@/types'

// ==================== API 路径定义 ====================

const PATHS = {
  FILES: (conversationId: string) => `/v1/workspace/${conversationId}/files`,
  PROJECTS: (conversationId: string) => `/v1/workspace/${conversationId}/projects`,
  FILE: (conversationId: string, path: string) =>
    `/v1/workspace/${conversationId}/file?path=${encodeURIComponent(path)}`,
  SANDBOX_STATUS: (conversationId: string) => `/v1/workspace/${conversationId}/sandbox/status`,
  SANDBOX_INIT: (conversationId: string) => `/v1/workspace/${conversationId}/sandbox/init`,
  SANDBOX_PAUSE: (conversationId: string) => `/v1/workspace/${conversationId}/sandbox/pause`,
  SANDBOX_RESUME: (conversationId: string) => `/v1/workspace/${conversationId}/sandbox/resume`,
  SANDBOX_KILL: (conversationId: string) => `/v1/workspace/${conversationId}/sandbox/kill`,
  SANDBOX_COMMAND: (conversationId: string) => `/v1/workspace/${conversationId}/sandbox/command`,
  RUN_PROJECT: (conversationId: string, projectName: string) =>
    `/v1/workspace/${conversationId}/projects/${projectName}/run`,
  STOP_PROJECT: (conversationId: string, projectName: string) =>
    `/v1/workspace/${conversationId}/projects/${projectName}/stop`,
  PROJECT_LOGS: (conversationId: string, projectName: string) =>
    `/v1/workspace/${conversationId}/projects/${projectName}/logs`
}

// ==================== 文件操作 API ====================

/**
 * 获取文件列表
 * @param conversationId - 对话 ID
 * @param path - 目录路径
 * @param tree - 是否返回树形结构
 */
export async function getFiles(
  conversationId: string,
  path = '/home/user',
  tree = true
): Promise<{ files: FileItem[]; total_size: number }> {
  const response = await api.get<{ files: FileItem[]; total_size: number }>(
    PATHS.FILES(conversationId),
    { params: { path, tree } }
  )
  return response.data
}

/**
 * 获取文件内容
 * @param conversationId - 对话 ID
 * @param path - 文件路径
 */
export async function getFileContent(
  conversationId: string,
  path: string
): Promise<string> {
  const response = await api.get<string>(PATHS.FILE(conversationId, path))
  return response.data
}

/**
 * 下载文件
 * @param conversationId - 对话 ID
 * @param path - 文件路径
 */
export async function downloadFile(
  conversationId: string,
  path: string
): Promise<Blob> {
  const response = await api.get(PATHS.FILE(conversationId, path), {
    params: { download: true },
    responseType: 'blob'
  })
  return response.data
}

/**
 * 保存文件
 * @param conversationId - 对话 ID
 * @param path - 文件路径
 * @param content - 文件内容
 */
export async function saveFile(
  conversationId: string,
  path: string,
  content: string
): Promise<void> {
  await api.put(
    PATHS.FILE(conversationId, path),
    null,
    { params: { content, use_sandbox: true } }
  )
}

/**
 * 删除文件
 * @param conversationId - 对话 ID
 * @param path - 文件路径
 */
export async function deleteFile(
  conversationId: string,
  path: string
): Promise<void> {
  await api.delete(PATHS.FILE(conversationId, path))
}

// ==================== 项目操作 API ====================

/**
 * 获取项目列表
 * @param conversationId - 对话 ID
 */
export async function getProjects(
  conversationId: string
): Promise<{ projects: ProjectInfo[] }> {
  const response = await api.get<{ projects: ProjectInfo[] }>(
    PATHS.PROJECTS(conversationId)
  )
  return response.data
}

/**
 * 运行项目
 * @param conversationId - 对话 ID
 * @param projectName - 项目名称
 * @param stack - 技术栈
 */
export async function runProject(
  conversationId: string,
  projectName: string,
  stack: SandboxStack
): Promise<ProjectRunResult> {
  const response = await api.post<ProjectRunResult>(
    PATHS.RUN_PROJECT(conversationId, projectName),
    { stack }
  )
  return response.data
}

/**
 * 停止项目
 * @param conversationId - 对话 ID
 * @param projectName - 项目名称
 */
export async function stopProject(
  conversationId: string,
  projectName: string
): Promise<void> {
  await api.post(PATHS.STOP_PROJECT(conversationId, projectName))
}

/**
 * 获取项目日志
 * @param conversationId - 对话 ID
 * @param projectName - 项目名称
 * @param lines - 日志行数
 */
export async function getProjectLogs(
  conversationId: string,
  projectName: string,
  lines = 100
): Promise<{ logs: string }> {
  const response = await api.get<{ logs: string }>(
    PATHS.PROJECT_LOGS(conversationId, projectName),
    { params: { lines } }
  )
  return response.data
}

// ==================== 沙盒操作 API ====================

/**
 * 获取沙盒状态
 * @param conversationId - 对话 ID
 */
export async function getSandboxStatus(
  conversationId: string
): Promise<SandboxStatusResponse> {
  const response = await api.get<SandboxStatusResponse>(
    PATHS.SANDBOX_STATUS(conversationId)
  )
  return response.data
}

/**
 * 初始化沙盒
 * @param conversationId - 对话 ID
 * @param userId - 用户 ID
 * @param stack - 技术栈
 */
export async function initSandbox(
  conversationId: string,
  userId: string,
  stack?: SandboxStack
): Promise<SandboxStatusResponse> {
  const response = await api.post<SandboxStatusResponse>(
    PATHS.SANDBOX_INIT(conversationId),
    { user_id: userId, stack }
  )
  return response.data
}

/**
 * 暂停沙盒
 * @param conversationId - 对话 ID
 */
export async function pauseSandbox(conversationId: string): Promise<void> {
  await api.post(PATHS.SANDBOX_PAUSE(conversationId))
}

/**
 * 恢复沙盒
 * @param conversationId - 对话 ID
 */
export async function resumeSandbox(
  conversationId: string
): Promise<SandboxStatusResponse> {
  const response = await api.post<SandboxStatusResponse>(
    PATHS.SANDBOX_RESUME(conversationId)
  )
  return response.data
}

/**
 * 终止沙盒
 * @param conversationId - 对话 ID
 */
export async function killSandbox(conversationId: string): Promise<void> {
  await api.post(PATHS.SANDBOX_KILL(conversationId))
}

/**
 * 执行命令
 * @param conversationId - 对话 ID
 * @param command - 命令
 * @param timeout - 超时时间（秒）
 */
export async function runCommand(
  conversationId: string,
  command: string,
  timeout = 60
): Promise<CommandResult> {
  const response = await api.post<CommandResult>(
    PATHS.SANDBOX_COMMAND(conversationId),
    { command, timeout }
  )
  return response.data
}

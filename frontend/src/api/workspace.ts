/**
 * 工作区 API
 */

import api from './index'
import type {
  ApiResponse,
  FileItem,
  FileContentResponse,
  CommandResult,
  ProjectInfo,
  ProjectRunResult
} from '@/types'

// ==================== API 路径定义 ====================

/**
 * 规范化文件路径用于 URL
 * - 移除开头的 / 避免双斜杠
 * - 对每个路径段进行 URL 编码
 */
function normalizePathForUrl(path: string): string {
  // 移除开头的斜杠
  const cleanPath = path.startsWith('/') ? path.slice(1) : path
  // 对每个路径段进行编码，保留斜杠
  return cleanPath.split('/').map(encodeURIComponent).join('/')
}

const PATHS = {
  FILES: (conversationId: string) => `/v1/workspace/${conversationId}/files`,
  PROJECTS: (conversationId: string) => `/v1/workspace/${conversationId}/projects`,
  FILE: (conversationId: string, path: string) =>
    `/v1/workspace/${conversationId}/files/${normalizePathForUrl(path)}`,
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
  path = '/home/user/project',
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
    { params: { content } }
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
  stack: string
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


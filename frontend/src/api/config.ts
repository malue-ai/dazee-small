/**
 * API 配置文件
 * 
 * 定义各模块的 API 端点路径
 */

// API 基础路径
const API_BASE = '/api/v1'

/**
 * Workspace API 端点
 * 
 * 用于文件管理、沙盒管理和项目运行
 */
export const WORKSPACE_API = {
  // === 文件管理 ===
  
  /** 获取文件列表 */
  FILES: (conversationId: string) => `${API_BASE}/workspace/${conversationId}/files`,
  
  /** 获取/操作单个文件 */
  FILE: (conversationId: string, path: string) => `${API_BASE}/workspace/${conversationId}/files/${path}`,
  
  /** 获取项目列表 */
  PROJECTS: (conversationId: string) => `${API_BASE}/workspace/${conversationId}/projects`,
  
  // === 沙盒管理 ===
  
  /** 获取沙盒状态 */
  SANDBOX_STATUS: (conversationId: string) => `${API_BASE}/workspace/${conversationId}/sandbox/status`,
  
  /** 初始化沙盒 */
  SANDBOX_INIT: (conversationId: string) => `${API_BASE}/workspace/${conversationId}/sandbox/init`,
  
  /** 暂停沙盒 */
  SANDBOX_PAUSE: (conversationId: string) => `${API_BASE}/workspace/${conversationId}/sandbox/pause`,
  
  /** 恢复沙盒 */
  SANDBOX_RESUME: (conversationId: string) => `${API_BASE}/workspace/${conversationId}/sandbox/resume`,
  
  /** 终止沙盒 */
  SANDBOX_KILL: (conversationId: string) => `${API_BASE}/workspace/${conversationId}/sandbox/kill`,
  
  /** 执行沙盒命令 */
  SANDBOX_COMMAND: (conversationId: string) => `${API_BASE}/workspace/${conversationId}/sandbox/command`,
  
  // === 项目运行 ===
  
  /** 运行项目 */
  RUN_PROJECT: (conversationId: string, projectName: string) => 
    `${API_BASE}/workspace/${conversationId}/projects/${projectName}/run`,
  
  /** 停止项目 */
  STOP_PROJECT: (conversationId: string, projectName: string) => 
    `${API_BASE}/workspace/${conversationId}/projects/${projectName}/stop`,
  
  /** 获取项目日志 */
  PROJECT_LOGS: (conversationId: string, projectName: string) => 
    `${API_BASE}/workspace/${conversationId}/projects/${projectName}/logs`,
}


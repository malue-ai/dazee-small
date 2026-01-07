/**
 * API 配置文件
 * 
 * 统一管理所有 API 端点路径
 */

// API 基础路径
export const API_BASE_PATH = '/api/v1'

// Chat API
export const CHAT_API = {
  // 统一聊天接口（支持流式和同步）
  CHAT: `${API_BASE_PATH}/chat`,
}

// Session API
export const SESSION_API = {
  // 获取会话状态
  STATUS: (sessionId) => `${API_BASE_PATH}/session/${sessionId}/status`,
  
  // 获取会话事件
  EVENTS: (sessionId) => `${API_BASE_PATH}/session/${sessionId}/events`,
  
  // 获取会话信息
  INFO: (sessionId) => `${API_BASE_PATH}/session/${sessionId}`,
  
  // 结束会话
  END: (sessionId) => `${API_BASE_PATH}/session/${sessionId}`,
  
  // 列出所有会话
  LIST: `${API_BASE_PATH}/sessions`,
}

// User API
export const USER_API = {
  // 获取用户的所有活跃会话
  SESSIONS: (userId) => `${API_BASE_PATH}/user/${userId}/sessions`,
}

// Knowledge API
export const KNOWLEDGE_API = {
  // 知识库列表
  LIST: `${API_BASE_PATH}/knowledge`,
  
  // 上传文件
  UPLOAD: `${API_BASE_PATH}/knowledge/upload`,
  
  // 删除知识库
  DELETE: (knowledgeId) => `${API_BASE_PATH}/knowledge/${knowledgeId}`,
}

// Files API
export const FILES_API = {
  // 文件列表
  LIST: `${API_BASE_PATH}/files`,
  
  // 获取统计
  STATS: (userId) => `${API_BASE_PATH}/files/stats/${userId}`,
  
  // 下载文件
  DOWNLOAD: (fileId) => `${API_BASE_PATH}/files/${fileId}/download`,
  
  // 删除文件
  DELETE: (fileId) => `${API_BASE_PATH}/files/${fileId}`,
}

// Workspace API（注意：axios baseURL 已经是 /api，所以这里只需要 /v1）
export const WORKSPACE_API = {
  // 获取文件列表
  FILES: (conversationId) => `/v1/workspace/${conversationId}/files`,
  
  // 获取/下载单个文件
  FILE: (conversationId, path) => `/v1/workspace/${conversationId}/files/${path}`,
  
  // 获取项目列表
  PROJECTS: (conversationId) => `/v1/workspace/${conversationId}/projects`,
  
  // 运行项目
  RUN_PROJECT: (conversationId, projectName) => `/v1/workspace/${conversationId}/projects/${projectName}/run`,
  
  // 停止项目
  STOP_PROJECT: (conversationId, projectName) => `/v1/workspace/${conversationId}/projects/${projectName}/stop`,
  
  // 获取项目日志
  PROJECT_LOGS: (conversationId, projectName) => `/v1/workspace/${conversationId}/projects/${projectName}/logs`,
  
  // === 沙盒管理 ===
  
  // 获取沙盒状态
  SANDBOX_STATUS: (conversationId) => `/v1/workspace/${conversationId}/sandbox/status`,
  
  // 初始化沙盒
  SANDBOX_INIT: (conversationId) => `/v1/workspace/${conversationId}/sandbox/init`,
  
  // 暂停沙盒
  SANDBOX_PAUSE: (conversationId) => `/v1/workspace/${conversationId}/sandbox/pause`,
  
  // 恢复沙盒
  SANDBOX_RESUME: (conversationId) => `/v1/workspace/${conversationId}/sandbox/resume`,
  
  // 终止沙盒
  SANDBOX_KILL: (conversationId) => `/v1/workspace/${conversationId}/sandbox/kill`,
  
  // 执行命令
  SANDBOX_COMMAND: (conversationId) => `/v1/workspace/${conversationId}/sandbox/command`,
}

export default {
  CHAT_API,
  SESSION_API,
  USER_API,
  KNOWLEDGE_API,
  FILES_API,
  WORKSPACE_API,
}


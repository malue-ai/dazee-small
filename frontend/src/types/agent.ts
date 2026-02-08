/**
 * Agent (项目) 类型定义
 * 与后端 models/agent.py 对齐
 */

// ==================== 枚举 ====================

export type AgentStatus = 'active' | 'inactive' | 'error'

// ==================== 列表响应 ====================

export interface AgentSummary {
  agent_id: string
  name: string
  description: string
  version: string
  is_active: boolean
  total_calls: number
  created_at: string
  last_used_at: string | null
}

export interface AgentListResponse {
  total: number
  agents: AgentSummary[]
}

// ==================== 详情 ====================

export interface AgentDetail {
  agent_id: string
  name: string
  description: string
  version: string
  is_active: boolean
  model: string | null
  plan_manager_enabled: boolean
  enabled_capabilities: Record<string, boolean>
  mcp_tools: AgentMCPTool[]
  apis: AgentAPI[]
  skills: string[]
  total_calls: number
  success_calls: number
  failed_calls: number
  created_at: string | null
  updated_at: string | null
  last_used_at: string | null
  loaded_at: string | null
}

export interface AgentMCPTool {
  name: string
  server_url: string
  server_name: string
  auth_type: string
  auth_env: string | null
  capability: string | null
  description: string
}

export interface AgentAPI {
  name: string
  base_url: string
  auth_type: string
  auth_env: string | null
  doc: string | null
  capability: string | null
  description: string
}

// ==================== 创建请求 ====================

export interface AgentCreateRequest {
  agent_id?: string
  name: string
  description?: string
  prompt: string
  model?: string
  plan_manager_enabled?: boolean
}

// ==================== 更新请求 ====================

export interface AgentUpdateRequest {
  name?: string
  description?: string
  prompt?: string
  model?: string
}

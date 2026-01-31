import api from './index'
import type { ApiResponse, Agent } from '@/types'

// ============================================================
// 类型定义
// ============================================================

export interface AgentTemplate {
  id: string
  name: string
  description: string
  icon: string
  config: {
    model?: string
    max_turns?: number
    plan_manager_enabled?: boolean
    enabled_capabilities?: Record<string, boolean>
    llm?: {
      enable_thinking?: boolean
      thinking_budget?: number
      max_tokens?: number
      enable_caching?: boolean
    }
    memory?: {
      mem0_enabled?: boolean
      smart_retrieval?: boolean
      retention_policy?: string
    }
  }
}

export interface ValidationError {
  field: string
  message: string
  code?: string
}

export interface ValidationWarning {
  field: string
  message: string
}

export interface ValidationResult {
  valid: boolean
  errors: ValidationError[]
  warnings: ValidationWarning[]
}

export interface ConfigPreview {
  config_yaml: string
  prompt_md: string
}

// ============================================================
// Agent CRUD
// ============================================================

/**
 * 获取 Agent 列表
 */
export async function getAgentList(): Promise<Agent[]> {
  const response = await api.get<ApiResponse<Agent[]>>('/v1/agents')
  return response.data.data
}

/**
 * 获取 Agent 详情
 */
export async function getAgent(agentId: string): Promise<Agent> {
  const response = await api.get<ApiResponse<Agent>>(`/v1/agents/${agentId}`)
  return response.data.data
}

/**
 * 创建 Agent
 */
export async function createAgent(data: Partial<Agent>): Promise<Agent> {
  const response = await api.post<ApiResponse<Agent>>('/v1/agents', data)
  return response.data.data
}

/**
 * 更新 Agent
 */
export async function updateAgent(agentId: string, data: Partial<Agent>): Promise<Agent> {
  const response = await api.put<ApiResponse<Agent>>(`/v1/agents/${agentId}`, data)
  return response.data.data
}

/**
 * 删除 Agent
 */
export async function deleteAgent(agentId: string): Promise<void> {
  await api.delete(`/v1/agents/${agentId}`)
}

// ============================================================
// 模板、校验和预览
// ============================================================

/**
 * 获取 Agent 模板列表
 */
export async function getAgentTemplates(): Promise<AgentTemplate[]> {
  const response = await api.get('/v1/agents/templates')
  return response.data.templates || []
}

/**
 * 校验 Agent 配置
 */
export async function validateAgentConfig(data: Record<string, any>): Promise<ValidationResult> {
  const response = await api.post('/v1/agents/validate', data)
  return response.data
}

/**
 * 预览 Agent 配置
 */
export async function previewAgentConfig(data: Record<string, any>): Promise<ConfigPreview> {
  const response = await api.post('/v1/agents/preview', data)
  return response.data
}

/**
 * 热重载 Agent
 */
export async function reloadAgent(agentId?: string): Promise<void> {
  if (agentId) {
    await api.post(`/v1/agents/${agentId}/reload`)
  } else {
    await api.post('/v1/agents/reload')
  }
}


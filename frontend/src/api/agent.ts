import api from './index'
import type { ApiResponse, Agent } from '@/types'

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


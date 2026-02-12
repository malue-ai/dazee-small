import api from './index'
import type {
  AgentSummary,
  AgentListResponse,
  AgentDetail,
  AgentCreateRequest,
  AgentCreateResponse,
  AgentUpdateRequest,
  AgentUpdateResponse
} from '@/types'

/**
 * Agent（项目）管理 API
 * 对接后端 /api/v1/agents 端点
 */

/**
 * 获取 Agent 列表
 */
export async function getAgentList(): Promise<AgentSummary[]> {
  const response = await api.get<AgentListResponse>('/v1/agents')
  return response.data?.agents ?? []
}

/**
 * 获取 Agent 详情
 */
export async function getAgentDetail(agentId: string): Promise<AgentDetail> {
  const response = await api.get<AgentDetail>(`/v1/agents/${agentId}`)
  return response.data
}

/**
 * 创建 Agent（异步模式）
 *
 * POST 立即返回 agent_id + status: "creating"。
 * 前端通过 WebSocket /api/v1/agents/ws/create/{agent_id} 获取实时进度。
 */
export async function createAgent(data: AgentCreateRequest): Promise<AgentCreateResponse> {
  const response = await api.post<AgentCreateResponse>('/v1/agents', data)
  return response.data
}

/**
 * 更新 Agent（异步模式）
 *
 * PUT 立即返回 agent_id + status: "reloading"。
 * 前端通过 WebSocket /api/v1/agents/ws/create/{agent_id} 获取实时重载进度。
 */
export async function updateAgent(agentId: string, data: AgentUpdateRequest): Promise<AgentUpdateResponse> {
  const response = await api.put<AgentUpdateResponse>(`/v1/agents/${agentId}`, data)
  return response.data
}

/**
 * 删除 Agent
 */
export async function deleteAgent(agentId: string): Promise<void> {
  await api.delete(`/v1/agents/${agentId}`)
}

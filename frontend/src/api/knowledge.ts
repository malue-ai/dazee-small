import api from './index'
import type { ApiResponse, Knowledge } from '@/types'

/**
 * 获取知识库列表
 */
export async function getKnowledgeList(): Promise<Knowledge[]> {
  const response = await api.get<ApiResponse<Knowledge[]>>('/v1/knowledge')
  return response.data.data
}

/**
 * 获取知识库详情
 */
export async function getKnowledge(knowledgeId: string): Promise<Knowledge> {
  const response = await api.get<ApiResponse<Knowledge>>(`/v1/knowledge/${knowledgeId}`)
  return response.data.data
}

/**
 * 创建知识库
 */
export async function createKnowledge(data: Partial<Knowledge>): Promise<Knowledge> {
  const response = await api.post<ApiResponse<Knowledge>>('/v1/knowledge', data)
  return response.data.data
}

/**
 * 删除知识库
 */
export async function deleteKnowledge(knowledgeId: string): Promise<void> {
  await api.delete(`/v1/knowledge/${knowledgeId}`)
}

/**
 * 上传文件到知识库
 */
export async function uploadKnowledgeFile(
  knowledgeId: string,
  file: File
): Promise<{ file_id: string }> {
  const formData = new FormData()
  formData.append('file', file)
  
  const response = await api.post<ApiResponse<{ file_id: string }>>(
    `/v1/knowledge/${knowledgeId}/files`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  )
  return response.data.data
}


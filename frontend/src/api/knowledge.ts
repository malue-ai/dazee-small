/**
 * 知识库 API
 */

import api from './index'
import type {
  ApiResponse,
  KnowledgeDocument,
  DocumentListResponse,
  RetrievalResponse,
  KnowledgeStats
} from '@/types'

/**
 * 上传文档（文件）
 * @param userId - 用户 ID
 * @param file - 文件
 * @param metadata - 元数据
 */
export async function uploadDocument(
  userId: string,
  file: File,
  metadata: Record<string, unknown> = {}
): Promise<KnowledgeDocument> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('user_id', userId)
  formData.append('metadata', JSON.stringify(metadata))
  formData.append('mode', 'hi_res')

  const response = await api.post<ApiResponse<KnowledgeDocument>>(
    '/v1/knowledge/upload',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }
  )

  return response.data.data
}

/**
 * 从 URL 上传文档
 * @param userId - 用户 ID
 * @param url - 文档 URL
 * @param name - 文档名称
 * @param metadata - 元数据
 */
export async function uploadDocumentFromUrl(
  userId: string,
  url: string,
  name: string,
  metadata: Record<string, unknown> = {}
): Promise<KnowledgeDocument> {
  const response = await api.post<ApiResponse<KnowledgeDocument>>(
    '/v1/knowledge/upload-url',
    {
      user_id: userId,
      url,
      name,
      metadata,
      mode: 'hi_res'
    }
  )

  return response.data.data
}

/**
 * 从文本创建文档
 * @param userId - 用户 ID
 * @param text - 文本内容
 * @param name - 文档名称
 * @param metadata - 元数据
 */
export async function uploadDocumentFromText(
  userId: string,
  text: string,
  name: string,
  metadata: Record<string, unknown> = {}
): Promise<KnowledgeDocument> {
  const response = await api.post<ApiResponse<KnowledgeDocument>>(
    '/v1/knowledge/upload-text',
    {
      user_id: userId,
      text,
      name,
      metadata
    }
  )

  return response.data.data
}

/**
 * 列出用户的文档
 * @param userId - 用户 ID
 * @param statusFilter - 状态过滤
 * @param limit - 数量限制
 * @param offset - 偏移量
 */
export async function listDocuments(
  userId: string,
  statusFilter: string | null = null,
  limit = 100,
  offset = 0
): Promise<KnowledgeDocument[]> {
  const params: Record<string, unknown> = {
    limit,
    offset
  }
  if (statusFilter) {
    params.status_filter = statusFilter
  }

  const response = await api.get<ApiResponse<DocumentListResponse>>(
    `/v1/knowledge/documents/${userId}`,
    { params }
  )

  return response.data.data.documents
}

/**
 * 获取文档状态
 * @param userId - 用户 ID
 * @param documentId - 文档 ID
 * @param refresh - 是否刷新状态
 */
export async function getDocumentStatus(
  userId: string,
  documentId: string,
  refresh = false
): Promise<KnowledgeDocument> {
  const response = await api.get<ApiResponse<KnowledgeDocument>>(
    `/v1/knowledge/documents/${userId}/${documentId}`,
    { params: { refresh } }
  )

  return response.data.data
}

/**
 * 删除文档
 * @param userId - 用户 ID
 * @param documentId - 文档 ID
 */
export async function deleteDocument(
  userId: string,
  documentId: string
): Promise<void> {
  await api.delete(`/v1/knowledge/documents/${userId}/${documentId}`)
}

/**
 * 检索知识库
 * @param userId - 用户 ID
 * @param query - 查询文本
 * @param topK - 返回结果数量
 * @param filters - 过滤条件
 */
export async function retrieve(
  userId: string,
  query: string,
  topK = 5,
  filters: Record<string, unknown> | null = null
): Promise<RetrievalResponse> {
  const response = await api.post<ApiResponse<RetrievalResponse>>(
    '/v1/knowledge/retrieve',
    {
      user_id: userId,
      query,
      top_k: topK,
      filters,
      rerank: true
    }
  )

  return response.data.data
}

/**
 * 获取用户知识库统计
 * @param userId - 用户 ID
 */
export async function getStats(userId: string): Promise<KnowledgeStats> {
  const response = await api.get<ApiResponse<KnowledgeStats>>(
    `/v1/knowledge/stats/${userId}`
  )

  return response.data.data
}

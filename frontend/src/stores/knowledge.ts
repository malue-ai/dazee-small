/**
 * 知识库 Store
 * 负责管理知识库文档和检索
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as knowledgeApi from '@/api/knowledge'
import type { KnowledgeDocument, KnowledgeStats, RetrievalResponse } from '@/types'

export const useKnowledgeStore = defineStore('knowledge', () => {
  // ==================== 状态 ====================

  /** 文档列表 */
  const documents = ref<KnowledgeDocument[]>([])

  /** 统计信息 */
  const stats = ref<KnowledgeStats | null>(null)

  /** 加载状态 */
  const loading = ref(false)

  /** 上传状态 */
  const uploading = ref(false)

  // ==================== 计算属性 ====================

  /** 文档数量 */
  const documentCount = computed(() => documents.value.length)

  /** 就绪文档数量 */
  const readyDocumentCount = computed(() =>
    documents.value.filter(d => d.status === 'ready').length
  )

  /** 处理中文档数量 */
  const processingDocumentCount = computed(() =>
    documents.value.filter(d => d.status === 'processing' || d.status === 'pending').length
  )

  // ==================== 方法 ====================

  /**
   * 上传文档（文件）
   * @param userId - 用户 ID
   * @param file - 文件
   * @param metadata - 元数据
   */
  async function uploadDocument(
    userId: string,
    file: File,
    metadata: Record<string, unknown> = {}
  ): Promise<KnowledgeDocument> {
    uploading.value = true

    try {
      const doc = await knowledgeApi.uploadDocument(userId, file, metadata)
      console.log('✅ 文档上传成功:', doc.document_id)
      return doc
    } catch (error) {
      console.error('❌ 上传文档失败:', error)
      throw error
    } finally {
      uploading.value = false
    }
  }

  /**
   * 从 URL 上传文档
   * @param userId - 用户 ID
   * @param url - 文档 URL
   * @param name - 文档名称
   * @param metadata - 元数据
   */
  async function uploadDocumentFromUrl(
    userId: string,
    url: string,
    name: string,
    metadata: Record<string, unknown> = {}
  ): Promise<KnowledgeDocument> {
    uploading.value = true

    try {
      const doc = await knowledgeApi.uploadDocumentFromUrl(userId, url, name, metadata)
      console.log('✅ URL 文档上传成功:', doc.document_id)
      return doc
    } catch (error) {
      console.error('❌ URL 上传失败:', error)
      throw error
    } finally {
      uploading.value = false
    }
  }

  /**
   * 从文本创建文档
   * @param userId - 用户 ID
   * @param text - 文本内容
   * @param name - 文档名称
   * @param metadata - 元数据
   */
  async function uploadDocumentFromText(
    userId: string,
    text: string,
    name: string,
    metadata: Record<string, unknown> = {}
  ): Promise<KnowledgeDocument> {
    uploading.value = true

    try {
      const doc = await knowledgeApi.uploadDocumentFromText(userId, text, name, metadata)
      console.log('✅ 文本文档上传成功:', doc.document_id)
      return doc
    } catch (error) {
      console.error('❌ 文本上传失败:', error)
      throw error
    } finally {
      uploading.value = false
    }
  }

  /**
   * 列出用户的文档
   * @param userId - 用户 ID
   * @param statusFilter - 状态过滤
   * @param limit - 数量限制
   * @param offset - 偏移量
   */
  async function listDocuments(
    userId: string,
    statusFilter: string | null = null,
    limit = 100,
    offset = 0
  ): Promise<KnowledgeDocument[]> {
    loading.value = true

    try {
      const docs = await knowledgeApi.listDocuments(userId, statusFilter, limit, offset)
      documents.value = docs
      console.log('✅ 文档列表已加载:', docs.length, '个')
      return docs
    } catch (error) {
      console.error('❌ 获取文档列表失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  /**
   * 获取文档状态
   * @param userId - 用户 ID
   * @param documentId - 文档 ID
   * @param refresh - 是否刷新状态
   */
  async function getDocumentStatus(
    userId: string,
    documentId: string,
    refresh = false
  ): Promise<KnowledgeDocument> {
    try {
      const doc = await knowledgeApi.getDocumentStatus(userId, documentId, refresh)

      // 更新本地列表中的文档状态
      const index = documents.value.findIndex(d => d.document_id === documentId)
      if (index !== -1) {
        documents.value[index] = doc
      }

      return doc
    } catch (error) {
      console.error('❌ 获取文档状态失败:', error)
      throw error
    }
  }

  /**
   * 删除文档
   * @param userId - 用户 ID
   * @param documentId - 文档 ID
   */
  async function deleteDocument(userId: string, documentId: string): Promise<void> {
    try {
      await knowledgeApi.deleteDocument(userId, documentId)

      // 从本地列表中移除
      documents.value = documents.value.filter(doc => doc.document_id !== documentId)

      console.log('✅ 文档已删除:', documentId)
    } catch (error) {
      console.error('❌ 删除文档失败:', error)
      throw error
    }
  }

  /**
   * 检索知识库
   * @param userId - 用户 ID
   * @param query - 查询文本
   * @param topK - 返回结果数量
   * @param filters - 过滤条件
   */
  async function retrieve(
    userId: string,
    query: string,
    topK = 5,
    filters: Record<string, unknown> | null = null
  ): Promise<RetrievalResponse> {
    try {
      const result = await knowledgeApi.retrieve(userId, query, topK, filters)
      console.log('✅ 知识库检索完成:', result.results.length, '条结果')
      return result
    } catch (error) {
      console.error('❌ 知识库检索失败:', error)
      throw error
    }
  }

  /**
   * 获取用户知识库统计
   * @param userId - 用户 ID
   */
  async function getStats(userId: string): Promise<KnowledgeStats> {
    try {
      const data = await knowledgeApi.getStats(userId)
      stats.value = data
      console.log('✅ 知识库统计已加载')
      return data
    } catch (error) {
      console.error('❌ 获取统计信息失败:', error)
      throw error
    }
  }

  /**
   * 刷新文档状态（轮询处理中的文档）
   * @param userId - 用户 ID
   */
  async function refreshProcessingDocuments(userId: string): Promise<void> {
    const processingDocs = documents.value.filter(
      d => d.status === 'processing' || d.status === 'pending'
    )

    for (const doc of processingDocs) {
      try {
        await getDocumentStatus(userId, doc.document_id, true)
      } catch {
        // 忽略单个文档的刷新失败
      }
    }
  }

  /**
   * 重置状态
   */
  function reset(): void {
    documents.value = []
    stats.value = null
    loading.value = false
    uploading.value = false
  }

  return {
    // 状态
    documents,
    stats,
    loading,
    uploading,

    // 计算属性
    documentCount,
    readyDocumentCount,
    processingDocumentCount,

    // 方法
    uploadDocument,
    uploadDocumentFromUrl,
    uploadDocumentFromText,
    listDocuments,
    getDocumentStatus,
    deleteDocument,
    retrieve,
    getStats,
    refreshProcessingDocuments,
    reset
  }
})

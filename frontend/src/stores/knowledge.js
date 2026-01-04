import { defineStore } from 'pinia'
import axios from '@/api/axios'

export const useKnowledgeStore = defineStore('knowledge', {
  state: () => ({
    documents: [],
    stats: null
  }),

  actions: {
    /**
     * 上传文档（文件）
     */
    async uploadDocument(userId, file, metadata = {}) {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('user_id', userId)
      formData.append('metadata', JSON.stringify(metadata))
      formData.append('mode', 'hi_res')

      try {
        const response = await axios.post('/v1/knowledge/upload', formData, {
          headers: {
            'Content-Type': 'multipart/form-data'
          }
        })

        return response.data.data
      } catch (error) {
        console.error('上传文档失败:', error)
        throw error
      }
    },

    /**
     * 从 URL 上传文档
     */
    async uploadDocumentFromUrl(userId, url, name, metadata = {}) {
      try {
        const response = await axios.post('/v1/knowledge/upload-url', {
          user_id: userId,
          url: url,
          name: name,
          metadata: metadata,
          mode: 'hi_res'
        })

        return response.data.data
      } catch (error) {
        console.error('URL上传失败:', error)
        throw error
      }
    },

    /**
     * 从文本创建文档
     */
    async uploadDocumentFromText(userId, text, name, metadata = {}) {
      try {
        const response = await axios.post('/v1/knowledge/upload-text', {
          user_id: userId,
          text: text,
          name: name,
          metadata: metadata
        })

        return response.data.data
      } catch (error) {
        console.error('文本上传失败:', error)
        throw error
      }
    },

    /**
     * 列出用户的文档
     */
    async listDocuments(userId, statusFilter = null, limit = 100, offset = 0) {
      try {
        const params = {
          status_filter: statusFilter,
          limit,
          offset
        }

        const response = await axios.get(`/v1/knowledge/documents/${userId}`, {
          params
        })

        this.documents = response.data.data.documents
        return this.documents
      } catch (error) {
        console.error('获取文档列表失败:', error)
        throw error
      }
    },

    /**
     * 获取文档状态
     */
    async getDocumentStatus(userId, documentId, refresh = false) {
      try {
        const response = await axios.get(
          `/v1/knowledge/documents/${userId}/${documentId}`,
          {
            params: { refresh }
          }
        )

        return response.data.data
      } catch (error) {
        console.error('获取文档状态失败:', error)
        throw error
      }
    },

    /**
     * 删除文档
     */
    async deleteDocument(userId, documentId) {
      try {
        const response = await axios.delete(
          `/v1/knowledge/documents/${userId}/${documentId}`
        )

        // 从本地列表中移除
        this.documents = this.documents.filter(
          doc => doc.document_id !== documentId
        )

        return response.data.data
      } catch (error) {
        console.error('删除文档失败:', error)
        throw error
      }
    },

    /**
     * 检索知识库
     */
    async retrieve(userId, query, topK = 5, filters = null) {
      try {
        const response = await axios.post('/v1/knowledge/retrieve', {
          user_id: userId,
          query: query,
          top_k: topK,
          filters: filters,
          rerank: true
        })

        return response.data.data
      } catch (error) {
        console.error('知识库检索失败:', error)
        throw error
      }
    },

    /**
     * 获取用户知识库统计
     */
    async getStats(userId) {
      try {
        const response = await axios.get(`/v1/knowledge/stats/${userId}`)
        this.stats = response.data.data
        return this.stats
      } catch (error) {
        console.error('获取统计信息失败:', error)
        throw error
      }
    }
  }
})


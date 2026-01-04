import { defineStore } from 'pinia'
import axios from '@/api/axios'
import { WORKSPACE_API } from '@/api/config'

export const useWorkspaceStore = defineStore('workspace', {
  state: () => ({
    // 当前对话ID
    conversationId: null,
    
    // 文件列表
    files: [],
    
    // 项目列表
    projects: [],
    
    // 总大小
    totalSize: 0,
    
    // 加载状态
    isLoadingFiles: false,
    isLoadingProjects: false,
    
    // 展开的目录（用于树形结构）
    expandedDirs: new Set()
  }),

  actions: {
    /**
     * 获取文件列表
     * 
     * @param {string} conversationId - 对话ID
     * @param {Object} options - 选项
     * @param {string} options.path - 目录路径
     * @param {boolean} options.tree - 是否返回树形结构
     */
    async fetchFiles(conversationId, options = {}) {
      const { path = '.', tree = true } = options
      
      this.conversationId = conversationId
      this.isLoadingFiles = true
      
      try {
        const response = await axios.get(WORKSPACE_API.FILES(conversationId), {
          params: { path, tree }
        })
        
        const data = response.data
        this.files = data.files || []
        this.totalSize = data.total_size || 0
        
        console.log('✅ 文件列表获取成功:', this.files.length, '项')
        return this.files
      } catch (error) {
        console.error('❌ 获取文件列表失败:', error)
        
        // 如果是 404，可能是 workspace 还没有文件
        if (error.response?.status === 404) {
          this.files = []
          this.totalSize = 0
          return []
        }
        
        throw error
      } finally {
        this.isLoadingFiles = false
      }
    },
    
    /**
     * 获取项目列表
     * 
     * @param {string} conversationId - 对话ID
     */
    async fetchProjects(conversationId) {
      this.conversationId = conversationId
      this.isLoadingProjects = true
      
      try {
        const response = await axios.get(WORKSPACE_API.PROJECTS(conversationId))
        
        this.projects = response.data.projects || []
        console.log('✅ 项目列表获取成功:', this.projects.length, '个项目')
        return this.projects
      } catch (error) {
        console.error('❌ 获取项目列表失败:', error)
        this.projects = []
        throw error
      } finally {
        this.isLoadingProjects = false
      }
    },
    
    /**
     * 获取文件内容
     * 
     * @param {string} conversationId - 对话ID
     * @param {string} path - 文件路径
     */
    async getFileContent(conversationId, path) {
      try {
        const response = await axios.get(WORKSPACE_API.FILE(conversationId, path))
        return response.data
      } catch (error) {
        console.error('❌ 获取文件内容失败:', error)
        throw error
      }
    },
    
    /**
     * 下载文件
     * 
     * @param {string} conversationId - 对话ID
     * @param {string} path - 文件路径
     */
    async downloadFile(conversationId, path) {
      try {
        const response = await axios.get(WORKSPACE_API.FILE(conversationId, path), {
          params: { download: true },
          responseType: 'blob'
        })
        
        // 创建下载链接
        const blob = new Blob([response.data])
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = path.split('/').pop()
        link.click()
        window.URL.revokeObjectURL(url)
        
        console.log('✅ 文件下载成功:', path)
      } catch (error) {
        console.error('❌ 下载文件失败:', error)
        throw error
      }
    },
    
    /**
     * 删除文件
     * 
     * @param {string} conversationId - 对话ID
     * @param {string} path - 文件路径
     */
    async deleteFile(conversationId, path) {
      try {
        await axios.delete(WORKSPACE_API.FILE(conversationId, path))
        console.log('✅ 文件删除成功:', path)
        
        // 重新加载文件列表
        await this.fetchFiles(conversationId, { tree: true })
      } catch (error) {
        console.error('❌ 删除文件失败:', error)
        throw error
      }
    },
    
    /**
     * 切换目录展开状态
     * 
     * @param {string} path - 目录路径
     */
    toggleDir(path) {
      if (this.expandedDirs.has(path)) {
        this.expandedDirs.delete(path)
      } else {
        this.expandedDirs.add(path)
      }
    },
    
    /**
     * 检查目录是否展开
     * 
     * @param {string} path - 目录路径
     */
    isDirExpanded(path) {
      return this.expandedDirs.has(path)
    },
    
    /**
     * 展开所有目录
     */
    expandAll() {
      const expandRecursive = (items) => {
        for (const item of items) {
          if (item.type === 'directory') {
            this.expandedDirs.add(item.path)
            if (item.children) {
              expandRecursive(item.children)
            }
          }
        }
      }
      expandRecursive(this.files)
    },
    
    /**
     * 收起所有目录
     */
    collapseAll() {
      this.expandedDirs.clear()
    },
    
    /**
     * 重置状态
     */
    reset() {
      this.conversationId = null
      this.files = []
      this.projects = []
      this.totalSize = 0
      this.expandedDirs.clear()
    }
  },
  
  getters: {
    /**
     * 格式化总大小
     */
    formattedTotalSize() {
      const bytes = this.totalSize
      if (bytes === 0) return '0 B'
      
      const k = 1024
      const sizes = ['B', 'KB', 'MB', 'GB']
      const i = Math.floor(Math.log(bytes) / Math.log(k))
      
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
    },
    
    /**
     * 是否有文件
     */
    hasFiles() {
      return this.files.length > 0
    },
    
    /**
     * 是否有项目
     */
    hasProjects() {
      return this.projects.length > 0
    }
  }
})


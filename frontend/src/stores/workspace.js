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
    expandedDirs: new Set(),
    
    // === 沙盒状态 ===
    sandbox: {
      id: null,
      e2bSandboxId: null,
      status: 'none',  // none/creating/running/paused/killed
      stack: null,
      previewUrl: null,
      createdAt: null,
      lastActiveAt: null
    },
    
    // 沙盒加载状态
    isLoadingSandbox: false,
    
    // 当前选中的文件
    selectedFile: null,
    
    // 文件内容（用于编辑器）
    fileContent: '',
    
    // 是否显示预览
    showPreview: false,
    
    // 项目日志
    projectLogs: ''
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
      this.sandbox = {
        id: null,
        e2bSandboxId: null,
        status: 'none',
        stack: null,
        previewUrl: null,
        createdAt: null,
        lastActiveAt: null
      }
      this.selectedFile = null
      this.fileContent = ''
      this.showPreview = false
      this.projectLogs = ''
    },
    
    // === 沙盒管理 ===
    
    /**
     * 获取沙盒状态
     */
    async fetchSandboxStatus(conversationId) {
      this.conversationId = conversationId
      this.isLoadingSandbox = true
      
      try {
        const response = await axios.get(WORKSPACE_API.SANDBOX_STATUS(conversationId))
        this.sandbox = {
          id: response.data.sandbox_id,
          e2bSandboxId: response.data.e2b_sandbox_id,
          status: response.data.status,
          stack: response.data.stack,
          previewUrl: response.data.preview_url,
          createdAt: response.data.created_at,
          lastActiveAt: response.data.last_active_at
        }
        console.log('✅ 沙盒状态获取成功:', this.sandbox.status)
        return this.sandbox
      } catch (error) {
        console.error('❌ 获取沙盒状态失败:', error)
        throw error
      } finally {
        this.isLoadingSandbox = false
      }
    },
    
    /**
     * 初始化沙盒
     */
    async initSandbox(conversationId, userId, stack = null) {
      this.conversationId = conversationId
      this.isLoadingSandbox = true
      
      try {
        const response = await axios.post(WORKSPACE_API.SANDBOX_INIT(conversationId), {
          user_id: userId,
          stack: stack
        })
        
        this.sandbox = {
          id: response.data.sandbox_id,
          e2bSandboxId: response.data.e2b_sandbox_id,
          status: response.data.status,
          stack: response.data.stack,
          previewUrl: response.data.preview_url,
          createdAt: response.data.created_at,
          lastActiveAt: response.data.last_active_at
        }
        
        console.log('✅ 沙盒初始化成功:', this.sandbox.e2bSandboxId)
        return this.sandbox
      } catch (error) {
        console.error('❌ 初始化沙盒失败:', error)
        throw error
      } finally {
        this.isLoadingSandbox = false
      }
    },
    
    /**
     * 暂停沙盒
     */
    async pauseSandbox(conversationId) {
      try {
        await axios.post(WORKSPACE_API.SANDBOX_PAUSE(conversationId))
        this.sandbox.status = 'paused'
        console.log('✅ 沙盒已暂停')
        return true
      } catch (error) {
        console.error('❌ 暂停沙盒失败:', error)
        throw error
      }
    },
    
    /**
     * 恢复沙盒
     */
    async resumeSandbox(conversationId) {
      this.isLoadingSandbox = true
      
      try {
        const response = await axios.post(WORKSPACE_API.SANDBOX_RESUME(conversationId))
        this.sandbox = {
          id: response.data.sandbox_id,
          e2bSandboxId: response.data.e2b_sandbox_id,
          status: response.data.status,
          stack: response.data.stack,
          previewUrl: response.data.preview_url,
          createdAt: response.data.created_at,
          lastActiveAt: response.data.last_active_at
        }
        console.log('✅ 沙盒已恢复')
        return this.sandbox
      } catch (error) {
        console.error('❌ 恢复沙盒失败:', error)
        throw error
      } finally {
        this.isLoadingSandbox = false
      }
    },
    
    /**
     * 终止沙盒
     */
    async killSandbox(conversationId) {
      try {
        await axios.post(WORKSPACE_API.SANDBOX_KILL(conversationId))
        this.sandbox.status = 'killed'
        this.sandbox.previewUrl = null
        console.log('✅ 沙盒已终止')
        return true
      } catch (error) {
        console.error('❌ 终止沙盒失败:', error)
        throw error
      }
    },
    
    /**
     * 执行命令
     */
    async runCommand(conversationId, command, timeout = 60) {
      try {
        const response = await axios.post(WORKSPACE_API.SANDBOX_COMMAND(conversationId), {
          command,
          timeout
        })
        return response.data
      } catch (error) {
        console.error('❌ 执行命令失败:', error)
        throw error
      }
    },
    
    // === 项目运行 ===
    
    /**
     * 运行项目
     */
    async runProject(conversationId, projectName, stack) {
      try {
        const response = await axios.post(
          WORKSPACE_API.RUN_PROJECT(conversationId, projectName),
          { stack }
        )
        
        if (response.data.success) {
          this.sandbox.previewUrl = response.data.preview_url
          this.sandbox.stack = stack
          this.showPreview = true
          console.log('✅ 项目启动成功:', response.data.preview_url)
        }
        
        return response.data
      } catch (error) {
        console.error('❌ 运行项目失败:', error)
        throw error
      }
    },
    
    /**
     * 停止项目
     */
    async stopProject(conversationId, projectName) {
      try {
        await axios.post(WORKSPACE_API.STOP_PROJECT(conversationId, projectName))
        this.showPreview = false
        console.log('✅ 项目已停止')
        return true
      } catch (error) {
        console.error('❌ 停止项目失败:', error)
        throw error
      }
    },
    
    /**
     * 获取项目日志
     */
    async fetchProjectLogs(conversationId, projectName, lines = 100) {
      try {
        const response = await axios.get(
          WORKSPACE_API.PROJECT_LOGS(conversationId, projectName),
          { params: { lines } }
        )
        this.projectLogs = response.data.logs
        return this.projectLogs
      } catch (error) {
        console.error('❌ 获取日志失败:', error)
        throw error
      }
    },
    
    // === 文件编辑 ===
    
    /**
     * 选择文件
     */
    async selectFile(conversationId, file) {
      this.selectedFile = file
      
      if (file.type === 'file') {
        try {
          const content = await this.getFileContent(conversationId, file.path)
          this.fileContent = content
        } catch (error) {
          console.error('❌ 读取文件内容失败:', error)
          this.fileContent = `// 无法读取文件: ${error.message}`
        }
      }
    },
    
    /**
     * 保存文件
     */
    async saveFile(conversationId, path, content) {
      try {
        const response = await axios.put(
          WORKSPACE_API.FILE(conversationId, path),
          null,
          { params: { content, use_sandbox: true } }
        )
        console.log('✅ 文件保存成功:', path)
        return response.data
      } catch (error) {
        console.error('❌ 保存文件失败:', error)
        throw error
      }
    },
    
    /**
     * 切换预览显示
     */
    togglePreview() {
      this.showPreview = !this.showPreview
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
    },
    
    /**
     * 沙盒是否正在运行
     */
    isSandboxRunning() {
      return this.sandbox.status === 'running'
    },
    
    /**
     * 沙盒是否可用（running 或 paused）
     */
    isSandboxAvailable() {
      return ['running', 'paused'].includes(this.sandbox.status)
    },
    
    /**
     * 是否有预览 URL
     */
    hasPreviewUrl() {
      return !!this.sandbox.previewUrl
    },
    
    /**
     * 获取沙盒状态文字
     */
    sandboxStatusText() {
      const statusMap = {
        'none': '未创建',
        'creating': '创建中...',
        'running': '运行中',
        'paused': '已暂停',
        'killed': '已终止'
      }
      return statusMap[this.sandbox.status] || this.sandbox.status
    },
    
    /**
     * 获取沙盒状态颜色
     */
    sandboxStatusColor() {
      const colorMap = {
        'none': '#6b7280',
        'creating': '#f59e0b',
        'running': '#10b981',
        'paused': '#3b82f6',
        'killed': '#ef4444'
      }
      return colorMap[this.sandbox.status] || '#6b7280'
    }
  }
})


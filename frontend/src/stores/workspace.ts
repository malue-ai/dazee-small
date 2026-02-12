/**
 * 工作区 Store
 * 负责管理文件系统、项目运行等
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as workspaceApi from '@/api/workspace'
import type {
  FileItem,
  ProjectInfo,
  TerminalLogItem,
  TerminalLogType,
  LivePreviewState,
  CodeLanguage
} from '@/types'
import { detectLanguage, formatFileSize } from '@/utils'

export const useWorkspaceStore = defineStore('workspace', () => {
  // ==================== 状态 ====================

  /** 当前对话 ID */
  const conversationId = ref<string | null>(null)

  /** 文件列表 */
  const files = ref<FileItem[]>([])

  /** 项目列表 */
  const projects = ref<ProjectInfo[]>([])

  /** 总大小 */
  const totalSize = ref(0)

  /** 文件加载状态 */
  const isLoadingFiles = ref(false)

  /** 项目加载状态 */
  const isLoadingProjects = ref(false)

  /** 展开的目录 */
  const expandedDirs = ref<Set<string>>(new Set())

  /** 当前选中的文件 */
  const selectedFile = ref<FileItem | null>(null)

  /** 文件内容 */
  const fileContent = ref('')

  /** 是否显示预览 */
  const showPreview = ref(false)

  /** 项目日志 */
  const projectLogs = ref('')

  /** 终端日志 */
  const terminalLogs = ref<TerminalLogItem[]>([])

  /** 终端运行状态 */
  const isTerminalRunning = ref(false)

  /** 实时预览状态 */
  const livePreview = ref<LivePreviewState>({
    isActive: false,
    toolName: null,
    toolId: null,
    filePath: null,
    content: '',
    accumulatedInput: '',
    language: 'text'
  })

  // ==================== 计算属性 ====================

  /** 格式化总大小 */
  const formattedTotalSize = computed(() => formatFileSize(totalSize.value))

  /** 是否有文件 */
  const hasFiles = computed(() => files.value.length > 0)

  /** 是否有项目 */
  const hasProjects = computed(() => projects.value.length > 0)

  /** 是否正在实时预览 */
  const isLivePreviewing = computed(() => livePreview.value.isActive)

  /** 实时预览内容 */
  const livePreviewContent = computed(() => livePreview.value.content)

  /** 实时预览文件路径 */
  const livePreviewPath = computed(() => livePreview.value.filePath)

  /** 实时预览代码语言 */
  const livePreviewLanguage = computed(() => livePreview.value.language)

  // ==================== 文件操作方法 ====================

  /**
   * 获取文件列表
   */
  async function fetchFiles(
    convId: string,
    options: { path?: string; tree?: boolean } = {}
  ): Promise<FileItem[]> {
    const { path = '/home/user/project', tree = true } = options

    conversationId.value = convId
    isLoadingFiles.value = true

    try {
      const data = await workspaceApi.getFiles(convId, path, tree)
      files.value = data.files || []
      totalSize.value = data.total_size || 0

      console.log('✅ 文件列表获取成功:', files.value.length, '项')
      return files.value
    } catch (error: unknown) {
      const err = error as { response?: { status: number } }
      if (err.response?.status === 404) {
        files.value = []
        totalSize.value = 0
        return []
      }
      console.error('❌ 获取文件列表失败:', error)
      throw error
    } finally {
      isLoadingFiles.value = false
    }
  }

  /**
   * 获取文件内容
   */
  async function getFileContent(convId: string, path: string): Promise<string> {
    try {
      return await workspaceApi.getFileContent(convId, path)
    } catch (error) {
      console.error('❌ 获取文件内容失败:', error)
      throw error
    }
  }

  /**
   * 下载文件
   */
  async function downloadFile(convId: string, path: string): Promise<void> {
    try {
      const blob = await workspaceApi.downloadFile(convId, path)
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = path.split('/').pop() || 'file'
      link.click()
      window.URL.revokeObjectURL(url)

      console.log('✅ 文件下载成功:', path)
    } catch (error) {
      console.error('❌ 下载文件失败:', error)
      throw error
    }
  }

  /**
   * 删除文件
   */
  async function deleteFile(convId: string, path: string): Promise<void> {
    try {
      await workspaceApi.deleteFile(convId, path)
      console.log('✅ 文件删除成功:', path)

      // 重新加载文件列表
      await fetchFiles(convId, { tree: true })
    } catch (error) {
      console.error('❌ 删除文件失败:', error)
      throw error
    }
  }

  /**
   * 保存文件
   */
  async function saveFile(convId: string, path: string, content: string): Promise<void> {
    try {
      await workspaceApi.saveFile(convId, path, content)
      console.log('✅ 文件保存成功:', path)
    } catch (error) {
      console.error('❌ 保存文件失败:', error)
      throw error
    }
  }

  /**
   * 选择文件
   */
  async function selectFile(convId: string, file: FileItem): Promise<void> {
    selectedFile.value = file

    if (file.type === 'file') {
      try {
        fileContent.value = await getFileContent(convId, file.path)
      } catch (error) {
        console.error('❌ 读取文件内容失败:', error)
        fileContent.value = `// 无法读取文件: ${(error as Error).message}`
      }
    }
  }

  // ==================== 目录操作方法 ====================

  /**
   * 切换目录展开状态
   */
  function toggleDir(path: string): void {
    if (expandedDirs.value.has(path)) {
      expandedDirs.value.delete(path)
    } else {
      expandedDirs.value.add(path)
    }
  }

  /**
   * 检查目录是否展开
   */
  function isDirExpanded(path: string): boolean {
    return expandedDirs.value.has(path)
  }

  /**
   * 展开所有目录
   */
  function expandAll(): void {
    const expandRecursive = (items: FileItem[]) => {
      for (const item of items) {
        if (item.type === 'directory') {
          expandedDirs.value.add(item.path)
          if (item.children) {
            expandRecursive(item.children)
          }
        }
      }
    }
    expandRecursive(files.value)
  }

  /**
   * 收起所有目录
   */
  function collapseAll(): void {
    expandedDirs.value.clear()
  }

  // ==================== 项目操作方法 ====================

  /**
   * 获取项目列表
   */
  async function fetchProjects(convId: string): Promise<ProjectInfo[]> {
    conversationId.value = convId
    isLoadingProjects.value = true

    try {
      const data = await workspaceApi.getProjects(convId)
      projects.value = data.projects || []
      console.log('✅ 项目列表获取成功:', projects.value.length, '个项目')
      return projects.value
    } catch (error) {
      console.error('❌ 获取项目列表失败:', error)
      projects.value = []
      throw error
    } finally {
      isLoadingProjects.value = false
    }
  }

  /**
   * 运行项目
   */
  async function runProject(
    convId: string,
    projectName: string,
    stack: string
  ) {
    try {
      const result = await workspaceApi.runProject(convId, projectName, stack)

      if (result.success) {
        showPreview.value = true
        console.log('✅ 项目启动成功:', result.preview_url)
      }

      return result
    } catch (error) {
      console.error('❌ 运行项目失败:', error)
      throw error
    }
  }

  /**
   * 停止项目
   */
  async function stopProject(convId: string, projectName: string): Promise<void> {
    try {
      await workspaceApi.stopProject(convId, projectName)
      showPreview.value = false
    } catch (error) {
      console.error('❌ 停止项目失败:', error)
      throw error
    }
  }

  /**
   * 获取项目日志
   */
  async function fetchProjectLogs(
    convId: string,
    projectName: string,
    lines = 100
  ): Promise<string> {
    try {
      const data = await workspaceApi.getProjectLogs(convId, projectName, lines)
      projectLogs.value = data.logs
      return projectLogs.value
    } catch (error) {
      console.error('❌ 获取日志失败:', error)
      throw error
    }
  }

  // ==================== 终端方法 ====================

  /**
   * 添加终端日志
   */
  function addTerminalLog(
    type: TerminalLogType,
    content: string,
    cwd: string | null = null
  ): void {
    terminalLogs.value.push({
      type,
      content,
      cwd,
      timestamp: Date.now()
    })
  }

  /**
   * 清空终端日志
   */
  function clearTerminalLogs(): void {
    terminalLogs.value = []
  }

  /**
   * 设置终端运行状态
   */
  function setTerminalRunning(isRunning: boolean): void {
    isTerminalRunning.value = isRunning
  }

  // ==================== 实时预览方法 ====================

  /**
   * 开始实时预览
   */
  function startLivePreview(
    toolName: string,
    toolId: string,
    filePath: string | null = null
  ): void {
    livePreview.value = {
      isActive: true,
      toolName,
      toolId,
      filePath,
      content: '',
      accumulatedInput: '',
      language: detectLanguage(filePath)
    }
    console.log('🎬 开始实时预览:', toolName, filePath)
  }

  /**
   * 更新实时预览内容
   */
  function updateLivePreview(delta: string): void {
    if (!livePreview.value.isActive) return

    livePreview.value.accumulatedInput += delta

    const extracted = extractFileInfo(livePreview.value.accumulatedInput)

    if (extracted.content !== null) {
      livePreview.value.content = extracted.content
    }

    if (extracted.path && !livePreview.value.filePath) {
      livePreview.value.filePath = extracted.path
      livePreview.value.language = detectLanguage(extracted.path)
    }
  }

  /**
   * 结束实时预览
   */
  function finishLivePreview(): void {
    if (!livePreview.value.isActive) return

    console.log('🏁 实时预览结束:', livePreview.value.filePath)

    const finalPath = livePreview.value.filePath

    livePreview.value = {
      isActive: false,
      toolName: null,
      toolId: null,
      filePath: null,
      content: '',
      accumulatedInput: '',
      language: 'text'
    }

    // 如果有文件路径，延迟刷新文件树
    if (finalPath && conversationId.value) {
      setTimeout(() => {
        if (conversationId.value) {
          fetchFiles(conversationId.value, { tree: true })
        }
      }, 500)
    }
  }

  /**
   * 从部分 JSON 中提取文件信息
   */
  function extractFileInfo(partialJson: string): { content: string | null; path: string | null } {
    const result: { content: string | null; path: string | null } = {
      content: null,
      path: null
    }

    // 提取文件路径
    const pathPattern = /"(?:path|file_path|filename)"\s*:\s*"((?:[^"\\]|\\.)*)"/
    const pathMatch = partialJson.match(pathPattern)
    if (pathMatch) {
      try {
        result.path = JSON.parse('"' + pathMatch[1] + '"')
      } catch {
        result.path = pathMatch[1]
      }
    }

    // 提取文件内容
    const contentPattern = /"(?:content|file_text|new_str|text)"\s*:\s*"((?:[^"\\]|\\.)*)"/
    const contentMatch = partialJson.match(contentPattern)
    if (contentMatch) {
      try {
        result.content = JSON.parse('"' + contentMatch[1] + '"')
      } catch {
        result.content = contentMatch[1].replace(/\\n/g, '\n').replace(/\\"/g, '"')
      }
    }

    return result
  }

  // ==================== 重置方法 ====================

  /**
   * 切换预览显示
   */
  function togglePreview(): void {
    showPreview.value = !showPreview.value
  }

  /**
   * 重置状态
   */
  function reset(): void {
    conversationId.value = null
    files.value = []
    projects.value = []
    totalSize.value = 0
    expandedDirs.value.clear()
    selectedFile.value = null
    fileContent.value = ''
    showPreview.value = false
    projectLogs.value = ''
    terminalLogs.value = []
    isTerminalRunning.value = false
    livePreview.value = {
      isActive: false,
      toolName: null,
      toolId: null,
      filePath: null,
      content: '',
      accumulatedInput: '',
      language: 'text'
    }
  }

  return {
    // 状态
    conversationId,
    files,
    projects,
    totalSize,
    isLoadingFiles,
    isLoadingProjects,
    expandedDirs,
    selectedFile,
    fileContent,
    showPreview,
    projectLogs,
    terminalLogs,
    isTerminalRunning,
    livePreview,

    // 计算属性
    formattedTotalSize,
    hasFiles,
    hasProjects,
    isLivePreviewing,
    livePreviewContent,
    livePreviewPath,
    livePreviewLanguage,

    // 文件方法
    fetchFiles,
    getFileContent,
    downloadFile,
    deleteFile,
    saveFile,
    selectFile,

    // 目录方法
    toggleDir,
    isDirExpanded,
    expandAll,
    collapseAll,

    // 项目方法
    fetchProjects,
    runProject,
    stopProject,
    fetchProjectLogs,

    // 终端方法
    addTerminalLog,
    clearTerminalLogs,
    setTerminalRunning,

    // 实时预览方法
    startLivePreview,
    updateLivePreview,
    finishLivePreview,

    // 其他方法
    togglePreview,
    reset
  }
})

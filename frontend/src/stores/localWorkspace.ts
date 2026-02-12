/**
 * 本地工作区 Store
 * 
 * 管理本地文件夹浏览与操作：
 * - 多文件夹工作区
 * - 文件拖拽移动
 * - 文件/文件夹新建、删除、重命名
 * - 右键上下文菜单
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { isTauriEnv } from '@/api/tauri'

// ==================== 类型定义 ====================

export interface LocalFileEntry {
  name: string
  path: string
  is_dir: boolean
  size: number
  children?: LocalFileEntry[]
}

/** 工作区中的一个文件夹 */
export interface WorkspaceFolder {
  path: string
  name: string
  files: LocalFileEntry[]
  isLoading: boolean
  error: string | null
}

/** 右键菜单状态 */
export interface ContextMenuState {
  x: number
  y: number
  /** 右键目标项（null 表示在空白处点击） */
  item: LocalFileEntry | null
  /** 所属工作区文件夹路径 */
  folderPath: string
}

/** 内联编辑状态 */
export interface EditingState {
  /** 编辑类型 */
  type: 'new-file' | 'new-folder' | 'rename'
  /** 父目录路径（new-file / new-folder 时） */
  parentPath: string
  /** 原路径（rename 时） */
  originalPath?: string
  /** 原名称（rename 时预填） */
  originalName?: string
}

// ==================== 路径工具 ====================

/** 获取路径的父目录 */
function getParentPath(filePath: string): string {
  const normalized = filePath.replace(/\\/g, '/')
  const lastSlash = normalized.lastIndexOf('/')
  return lastSlash > 0 ? filePath.substring(0, lastSlash) : filePath
}

/** 拼接路径（兼容 Windows） */
function joinPath(dir: string, name: string): string {
  const sep = dir.includes('\\') ? '\\' : '/'
  return dir.endsWith(sep) ? dir + name : dir + sep + name
}

/** 从路径提取名称 */
function getBaseName(filePath: string): string {
  const parts = filePath.replace(/\\/g, '/').split('/')
  return parts.filter(Boolean).pop() || filePath
}

// ==================== 默认名称生成 ====================

/**
 * 根据已有文件名列表，生成不重复的默认名称
 * 如：新建文件.txt → 新建文件(2).txt → 新建文件(3).txt
 * 如：新建文件夹 → 新建文件夹(2) → 新建文件夹(3)
 */
function generateDefaultName(baseName: string, ext: string, existingNames: string[]): string {
  const nameSet = new Set(existingNames)
  const first = ext ? baseName + ext : baseName
  if (!nameSet.has(first)) return first
  let i = 2
  while (true) {
    const candidate = ext ? `${baseName}(${i})${ext}` : `${baseName}(${i})`
    if (!nameSet.has(candidate)) return candidate
    i++
  }
}

// ==================== 持久化 ====================

const STORAGE_KEY = 'workspace_folders'

function saveFolderPaths(folders: WorkspaceFolder[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(folders.map(f => f.path)))
  } catch { /* ignore */ }
}

function loadSavedFolderPaths(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const arr = JSON.parse(raw)
      if (Array.isArray(arr)) return arr.filter((p: unknown) => typeof p === 'string')
    }
  } catch { /* ignore */ }
  return []
}

// ==================== Store ====================

export const useLocalWorkspaceStore = defineStore('localWorkspace', () => {
  // ==================== 核心状态 ====================

  const folders = ref<WorkspaceFolder[]>([])
  const expandedDirs = ref<Set<string>>(new Set())
  const selectedFile = ref<LocalFileEntry | null>(null)
  const fileContent = ref<string>('')
  const isRestored = ref(false)

  // ==================== 交互状态 ====================

  /** 右键菜单 */
  const contextMenu = ref<ContextMenuState | null>(null)

  /** 内联编辑 */
  const editingState = ref<EditingState | null>(null)

  /** 当前拖拽的条目 */
  const draggedItem = ref<LocalFileEntry | null>(null)

  /** 当前拖拽悬停的目标路径 */
  const dropTargetPath = ref<string | null>(null)

  /** dragend 时的鼠标坐标（用于判断放置位置） */
  const dragEndX = ref(0)
  const dragEndY = ref(0)

  // ==================== 计算属性 ====================

  const hasFolders = computed(() => folders.value.length > 0)
  const isAnyLoading = computed(() => folders.value.some(f => f.isLoading))

  const fileCount = computed(() => {
    const count = (items: LocalFileEntry[]): number => {
      let n = 0
      for (const item of items) {
        if (!item.is_dir) n++
        if (item.children) n += count(item.children)
      }
      return n
    }
    return folders.value.reduce((sum, f) => sum + count(f.files), 0)
  })

  const dirCount = computed(() => {
    const count = (items: LocalFileEntry[]): number => {
      let n = 0
      for (const item of items) {
        if (item.is_dir) { n++; if (item.children) n += count(item.children) }
      }
      return n
    }
    return folders.value.reduce((sum, f) => sum + count(f.files), 0)
  })

  // ==================== 文件夹管理 ====================

  async function addFolder(path: string): Promise<void> {
    if (!isTauriEnv() || folders.value.some(f => f.path === path)) return

    const folder: WorkspaceFolder = {
      path, name: getBaseName(path), files: [], isLoading: true, error: null,
    }
    folders.value.push(folder)
    expandedDirs.value.add(path)
    saveFolderPaths(folders.value)
    await loadFolderContents(path)
  }

  async function loadFolderContents(folderPath: string): Promise<void> {
    const folder = folders.value.find(f => f.path === folderPath)
    if (!folder || !isTauriEnv()) return

    folder.isLoading = true
    folder.error = null
    try {
      folder.files = await invoke<LocalFileEntry[]>('read_local_dir', {
        path: folderPath, maxDepth: 3,
      })
    } catch (e: any) {
      folder.error = e?.toString() || '读取目录失败'
    } finally {
      folder.isLoading = false
    }
  }

  function removeFolder(path: string): void {
    const idx = folders.value.findIndex(f => f.path === path)
    if (idx === -1) return
    const folder = folders.value[idx]
    expandedDirs.value.delete(folder.path)
    cleanupExpandedDirs(folder.files)
    if (selectedFile.value?.path.startsWith(folder.path)) {
      selectedFile.value = null
      fileContent.value = ''
    }
    folders.value.splice(idx, 1)
    saveFolderPaths(folders.value)
  }

  function cleanupExpandedDirs(items: LocalFileEntry[]): void {
    for (const item of items) {
      if (item.is_dir) {
        expandedDirs.value.delete(item.path)
        if (item.children) cleanupExpandedDirs(item.children)
      }
    }
  }

  async function refreshFolder(path: string): Promise<void> {
    await loadFolderContents(path)
  }

  async function refreshAll(): Promise<void> {
    await Promise.all(folders.value.map(f => loadFolderContents(f.path)))
  }

  /** 找到路径所属的工作区文件夹 */
  function findOwnerFolder(filePath: string): WorkspaceFolder | undefined {
    const normalized = filePath.replace(/\\/g, '/')
    return folders.value.find(f => {
      const fp = f.path.replace(/\\/g, '/')
      return normalized === fp || normalized.startsWith(fp + '/')
    })
  }

  /** 刷新包含指定路径的工作区文件夹 */
  async function refreshContaining(filePath: string): Promise<void> {
    const folder = findOwnerFolder(filePath)
    if (folder) await loadFolderContents(folder.path)
  }

  /** 获取指定目录下的子项名称列表 */
  function getChildNames(dirPath: string): string[] {
    // 先检查是否是根工作区文件夹
    const rootFolder = folders.value.find(f => f.path === dirPath)
    if (rootFolder) return rootFolder.files.map(f => f.name)

    // 递归查找子目录
    const findChildren = (items: LocalFileEntry[]): LocalFileEntry[] | null => {
      for (const item of items) {
        if (item.is_dir && item.path === dirPath) return item.children || []
        if (item.children) {
          const found = findChildren(item.children)
          if (found) return found
        }
      }
      return null
    }
    for (const f of folders.value) {
      const found = findChildren(f.files)
      if (found) return found.map(c => c.name)
    }
    return []
  }

  /** 为新建文件/文件夹生成不重复的默认名 */
  function getDefaultNewName(parentPath: string, isFile: boolean): string {
    const existingNames = getChildNames(parentPath)
    if (isFile) {
      return generateDefaultName('新建文件', '.txt', existingNames)
    } else {
      return generateDefaultName('新建文件夹', '', existingNames)
    }
  }

  // ==================== 目录展开 ====================

  function toggleDir(path: string): void {
    if (expandedDirs.value.has(path)) expandedDirs.value.delete(path)
    else expandedDirs.value.add(path)
  }

  function isDirExpanded(path: string): boolean {
    return expandedDirs.value.has(path)
  }

  function expandAll(): void {
    const go = (items: LocalFileEntry[]) => {
      for (const item of items) {
        if (item.is_dir) { expandedDirs.value.add(item.path); if (item.children) go(item.children) }
      }
    }
    for (const f of folders.value) { expandedDirs.value.add(f.path); go(f.files) }
  }

  function collapseAll(): void {
    expandedDirs.value.clear()
    for (const f of folders.value) expandedDirs.value.add(f.path)
  }

  // ==================== 文件内容 ====================

  async function loadFileContent(file: LocalFileEntry): Promise<void> {
    if (!isTauriEnv() || file.is_dir) return
    selectedFile.value = file
    try {
      fileContent.value = await invoke<string>('read_local_file_text', { path: file.path })
    } catch (e: any) {
      fileContent.value = `// 无法读取文件: ${e}`
    }
  }

  // ==================== 右键菜单 ====================

  function showContextMenu(x: number, y: number, item: LocalFileEntry | null, folderPath: string): void {
    contextMenu.value = { x, y, item, folderPath }
  }

  function hideContextMenu(): void {
    contextMenu.value = null
  }

  // ==================== 拖拽 ====================

  function setDraggedItem(item: LocalFileEntry | null): void {
    draggedItem.value = item
    // 新拖拽开始时重置坐标，防止残留坐标导致 ChatView 误判
    if (item) {
      dragEndX.value = 0
      dragEndY.value = 0
    }
  }

  function setDropTarget(path: string | null): void {
    dropTargetPath.value = path
  }

  function setDragEndPosition(x: number, y: number): void {
    dragEndX.value = x
    dragEndY.value = y
  }

  function clearDrag(): void {
    draggedItem.value = null
    dropTargetPath.value = null
  }

  // ==================== 内联编辑 ====================

  function startNewFile(parentPath: string): void {
    hideContextMenu()
    // 确保父目录展开
    expandedDirs.value.add(parentPath)
    editingState.value = { type: 'new-file', parentPath }
  }

  function startNewFolder(parentPath: string): void {
    hideContextMenu()
    expandedDirs.value.add(parentPath)
    editingState.value = { type: 'new-folder', parentPath }
  }

  function startRename(item: LocalFileEntry): void {
    hideContextMenu()
    editingState.value = {
      type: 'rename',
      parentPath: getParentPath(item.path),
      originalPath: item.path,
      originalName: item.name,
    }
  }

  function cancelEditing(): void {
    editingState.value = null
  }

  // ==================== 文件操作 ====================

  /** 确认创建文件/文件夹或重命名 */
  async function confirmEditing(name: string): Promise<boolean> {
    if (!editingState.value || !name.trim()) {
      cancelEditing()
      return false
    }

    const state = editingState.value
    const trimmed = name.trim()

    try {
      if (state.type === 'new-file') {
        // 如果文件名不含扩展名，默认追加 .txt
        const fileName = trimmed.includes('.') ? trimmed : trimmed + '.txt'
        const fullPath = joinPath(state.parentPath, fileName)
        await invoke('create_local_file', { path: fullPath, content: null })
      } else if (state.type === 'new-folder') {
        const fullPath = joinPath(state.parentPath, trimmed)
        await invoke('create_local_dir', { path: fullPath })
      } else if (state.type === 'rename' && state.originalPath) {
        const newPath = joinPath(state.parentPath, trimmed)
        if (newPath !== state.originalPath) {
          await invoke('move_local_file', { fromPath: state.originalPath, toPath: newPath })
        }
      }

      cancelEditing()
      await refreshContaining(state.parentPath)
      return true
    } catch (e: any) {
      console.error('❌ 文件操作失败:', e)
      return false
    }
  }

  /** 移动文件到目标目录 */
  async function moveFile(fromPath: string, toDir: string): Promise<boolean> {
    const fileName = getBaseName(fromPath)
    const toPath = joinPath(toDir, fileName)

    if (fromPath === toPath) return false

    try {
      await invoke('move_local_file', { fromPath, toPath })
    } catch (e: any) {
      const errMsg = String(e)
      // 目标已存在同名文件 → 弹出确认对话框
      if (errMsg.includes('已存在')) {
        const folderName = getBaseName(toDir)
        try {
          const { ask } = await import('@tauri-apps/plugin-dialog')
          const replace = await ask(
            `目标文件夹「${folderName}」中已存在「${fileName}」，是否替换？`,
            { title: '文件冲突', kind: 'warning', okLabel: '替换', cancelLabel: '取消' }
          )
          if (replace) {
            // 先删除目标文件，再移动
            await invoke('delete_local_path', { path: toPath })
            await invoke('move_local_file', { fromPath, toPath })
          } else {
            return false
          }
        } catch (dialogErr: any) {
          console.error('❌ 对话框或替换操作失败:', dialogErr)
          return false
        }
      } else {
        console.error('❌ 移动文件失败:', e)
        return false
      }
    }

    // 刷新源和目标文件夹
    await refreshContaining(fromPath)
    const destFolder = findOwnerFolder(toDir)
    const srcFolder = findOwnerFolder(fromPath)
    if (destFolder && srcFolder && destFolder.path !== srcFolder.path) {
      await loadFolderContents(destFolder.path)
    }
    return true
  }

  /** 删除文件或目录 */
  async function deleteItem(path: string): Promise<boolean> {
    try {
      await invoke('delete_local_path', { path })
      if (selectedFile.value?.path === path) {
        selectedFile.value = null
        fileContent.value = ''
      }
      await refreshContaining(path)
      return true
    } catch (e: any) {
      console.error('❌ 删除失败:', e)
      return false
    }
  }

  /** 复制路径到剪贴板 */
  function copyPath(path: string): void {
    hideContextMenu()
    navigator.clipboard.writeText(path).catch(() => {})
  }

  /** 启动时恢复工作区：有启动参数则替换，无参数则恢复上次 */
  async function restoreFolders(): Promise<void> {
    if (isRestored.value || !isTauriEnv()) return
    isRestored.value = true

    // 1. 先检查是否有启动参数（拖拽文件夹到 exe 启动）
    let startupFolders: string[] = []
    try {
      const startupPaths = await invoke<string[]>('get_startup_paths')
      for (const p of startupPaths) {
        try {
          const isDir = await invoke<boolean>('check_is_directory', { path: p })
          if (isDir) {
            startupFolders.push(p)
          } else {
            // 文件 → 取其父目录
            const lastSep = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'))
            if (lastSep > 0) startupFolders.push(p.substring(0, lastSep))
          }
        } catch { /* skip invalid path */ }
      }
    } catch {
      // get_startup_paths 失败（开发模式等），忽略
    }

    if (startupFolders.length > 0) {
      // 有启动参数：清除旧工作区，替换为新的
      folders.value = []
      expandedDirs.value.clear()
      selectedFile.value = null
      fileContent.value = ''

      // 去重
      const unique = [...new Set(startupFolders)]
      for (const path of unique) {
        await addFolder(path) // addFolder 会自动 saveFolderPaths
      }
    } else {
      // 无启动参数：恢复上次保存的文件夹
      const savedPaths = loadSavedFolderPaths()
      for (const path of savedPaths) {
        if (folders.value.some(f => f.path === path)) continue
        const folder: WorkspaceFolder = {
          path, name: getBaseName(path), files: [], isLoading: true, error: null,
        }
        folders.value.push(folder)
        expandedDirs.value.add(path)
      }
      if (savedPaths.length) {
        await Promise.all(savedPaths.map(p => loadFolderContents(p)))
        // 仅清理"目录确实不存在"的文件夹（二次确认，避免 IPC 故障误删）
        const suspicious = folders.value.filter(f => f.error && f.files.length === 0)
        for (const f of suspicious) {
          try {
            const exists = await invoke<boolean>('check_is_directory', { path: f.path })
            if (!exists) removeFolder(f.path)
            else f.error = null
          } catch {
            f.error = '暂时无法加载'
            f.isLoading = false
          }
        }
      }
    }
  }

  function clearAll(): void {
    folders.value = []
    expandedDirs.value.clear()
    selectedFile.value = null
    fileContent.value = ''
    contextMenu.value = null
    editingState.value = null
    draggedItem.value = null
    dropTargetPath.value = null
    saveFolderPaths([])
  }

  return {
    // 核心状态
    folders, expandedDirs, selectedFile, fileContent,
    // 交互状态
    contextMenu, editingState, draggedItem, dropTargetPath, dragEndX, dragEndY,
    // 计算属性
    hasFolders, isAnyLoading, fileCount, dirCount,
    // 文件夹管理
    addFolder, removeFolder, refreshFolder, refreshAll, loadFolderContents, restoreFolders,
    findOwnerFolder, refreshContaining, getDefaultNewName,
    // 目录展开
    toggleDir, isDirExpanded, expandAll, collapseAll,
    // 文件内容
    loadFileContent,
    // 右键菜单
    showContextMenu, hideContextMenu,
    // 拖拽
    setDraggedItem, setDropTarget, setDragEndPosition, clearDrag,
    // 内联编辑
    startNewFile, startNewFolder, startRename, cancelEditing, confirmEditing,
    // 文件操作
    moveFile, deleteItem, copyPath,
    // 清空
    clearAll,
  }
})

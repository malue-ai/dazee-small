<template>
  <div class="select-none">
    <!-- 新建文件/文件夹的内联输入（显示在目录子项顶部） -->
    <template v-if="item.is_dir && isExpanded && isCreatingHere">
      <div 
        class="flex items-center gap-1.5 py-1 pr-2"
        :style="{ paddingLeft: ((depth + 1) * 12 + 12) + 'px' }"
      >
        <span class="w-3 flex-shrink-0"></span>
        <component 
          :is="store.editingState?.type === 'new-folder' ? Folder : File" 
          class="w-4 h-4 flex-shrink-0 text-primary/50" 
        />
        <input
          ref="createInputRef"
          v-model="newName"
          class="flex-1 text-xs bg-white border border-primary/40 rounded px-1.5 py-0.5 outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 min-w-0"
          :placeholder="store.editingState?.type === 'new-folder' ? '文件夹名称' : '文件名称'"
          @keydown.enter="confirmCreate"
          @keydown.escape="store.cancelEditing"
          @blur="confirmCreate"
        />
      </div>
    </template>

    <!-- 节点本体 -->
    <div 
      class="flex items-center gap-1.5 py-1 pr-2 cursor-pointer transition-colors group border-l-2"
      :class="nodeClasses"
      :style="{ paddingLeft: (depth * 12 + 12) + 'px' }"
      :data-drop-folder="item.is_dir ? item.path : undefined"
      @click="handleClick"
      @contextmenu.prevent="handleContextMenu"
      @mousedown="handleMouseDown"
    >
      <!-- 展开/收起图标 -->
      <span v-if="item.is_dir" class="w-3 h-3 flex items-center justify-center text-muted-foreground/50 flex-shrink-0">
        <ChevronDown v-if="isExpanded" class="w-3 h-3" />
        <ChevronRight v-else class="w-3 h-3" />
      </span>
      <span v-else class="w-3 flex-shrink-0"></span>
      
      <!-- 图标 -->
      <component :is="iconComponent" class="w-4 h-4 flex-shrink-0" :class="iconColorClass" />
      
      <!-- 名称 / 重命名输入 -->
      <template v-if="isRenaming">
        <input
          ref="renameInputRef"
          v-model="renameName"
          class="flex-1 text-xs bg-white border border-primary/40 rounded px-1.5 py-0.5 outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 min-w-0"
          @keydown.enter="confirmRename"
          @keydown.escape="store.cancelEditing"
          @blur="confirmRename"
          @click.stop
        />
      </template>
      <template v-else>
        <span class="flex-1 text-xs truncate" :title="item.path">
          {{ item.name }}
        </span>
      </template>

      <!-- 文件大小 -->
      <span v-if="!item.is_dir && item.size && !isRenaming" class="text-[10px] text-muted-foreground/40 flex-shrink-0 ml-1">
        {{ formatSize(item.size) }}
      </span>
    </div>
    
    <!-- 子节点 -->
    <template v-if="item.is_dir && isExpanded && item.children">
      <LocalFileTreeNode
        v-for="child in item.children"
        :key="child.path"
        :item="child"
        :depth="depth + 1"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import { useLocalWorkspaceStore, type LocalFileEntry } from '@/stores/localWorkspace'
import { 
  ChevronDown, ChevronRight, Folder, FolderOpen, FileText, FileCode, FileJson, 
  Image, File, FileArchive, Lock, Settings, Database 
} from 'lucide-vue-next'

const props = defineProps<{
  item: LocalFileEntry
  depth: number
}>()

const store = useLocalWorkspaceStore()

// ==================== Refs ====================

const createInputRef = ref<HTMLInputElement | null>(null)
const renameInputRef = ref<HTMLInputElement | null>(null)
const newName = ref('')
const renameName = ref('')

// ==================== 计算属性 ====================

const isExpanded = computed(() => store.isDirExpanded(props.item.path))
const isSelected = computed(() => store.selectedFile?.path === props.item.path)
const isDropTarget = computed(() => store.dropTargetPath === props.item.path && props.item.is_dir)

/** 当前节点是否正在重命名 */
const isRenaming = computed(() => 
  store.editingState?.type === 'rename' && store.editingState.originalPath === props.item.path
)

/** 当前目录下是否有新建操作 */
const isCreatingHere = computed(() => {
  if (!store.editingState) return false
  return (store.editingState.type === 'new-file' || store.editingState.type === 'new-folder') 
    && store.editingState.parentPath === props.item.path
})

/** 节点样式 */
const nodeClasses = computed(() => {
  if (isDropTarget.value) return 'bg-primary/10 border-primary text-primary'
  if (isSelected.value) return 'bg-accent border-primary text-accent-foreground'
  return 'border-transparent hover:bg-muted text-muted-foreground'
})

// ==================== 文件图标 ====================

const fileExtension = computed(() => {
  if (props.item.is_dir) return ''
  const parts = props.item.name.split('.')
  return parts.length > 1 ? parts.pop()!.toLowerCase() : ''
})

const iconComponent = computed(() => {
  if (props.item.is_dir) return isExpanded.value ? FolderOpen : Folder
  const ext = fileExtension.value
  const m: Record<string, any> = {
    js: FileCode, ts: FileCode, jsx: FileCode, tsx: FileCode, vue: FileCode, py: FileCode,
    html: FileCode, css: FileCode, scss: FileCode, rs: FileCode, go: FileCode, java: FileCode,
    sh: FileCode, bat: FileCode, ps1: FileCode, c: FileCode, cpp: FileCode, swift: FileCode,
    json: FileJson, yaml: FileJson, yml: FileJson, toml: FileJson, xml: FileJson,
    ini: Settings, conf: Settings,
    md: FileText, txt: FileText, log: FileText,
    png: Image, jpg: Image, jpeg: Image, gif: Image, svg: Image, webp: Image,
    zip: FileArchive, tar: FileArchive, gz: FileArchive, rar: FileArchive,
    db: Database, sqlite: Database, sql: Database,
    env: Lock, lock: Lock,
  }
  return m[ext] || File
})

const iconColorClass = computed(() => {
  if (props.item.is_dir) return 'text-primary'
  const ext = fileExtension.value
  const m: Record<string, string> = {
    js: 'text-yellow-500', ts: 'text-blue-600', jsx: 'text-cyan-500', tsx: 'text-cyan-600',
    vue: 'text-green-500', py: 'text-blue-500', html: 'text-orange-500', css: 'text-pink-500',
    rs: 'text-orange-600', go: 'text-cyan-400', java: 'text-red-400',
    json: 'text-gray-500', yaml: 'text-gray-500', md: 'text-gray-600',
    png: 'text-purple-500', svg: 'text-orange-400',
    env: 'text-yellow-600', lock: 'text-gray-400',
  }
  return m[ext] || 'text-muted-foreground/40'
})

// ==================== 事件处理 ====================

function handleClick() {
  // 拖拽刚结束时，抑制此次 click（避免误触发目录展开/文件加载）
  if (suppressNextClick) {
    suppressNextClick = false
    return
  }
  if (props.item.is_dir) {
    store.toggleDir(props.item.path)
  } else {
    store.loadFileContent(props.item)
  }
}

function handleContextMenu(e: MouseEvent) {
  const folder = store.findOwnerFolder(props.item.path)
  if (folder) {
    store.showContextMenu(e.clientX, e.clientY, props.item, folder.path)
  }
}

// ==================== 拖拽（基于 mouse 事件，完全绕过 WebView2 原生 drag 层，杜绝禁止光标） ====================

let dragGhost: HTMLElement | null = null
let dragTooltip: HTMLElement | null = null
let lastDropTarget: string | null = null
let isDragging = false
let suppressNextClick = false
let currentMouseMoveHandler: ((e: MouseEvent) => void) | null = null
let currentMouseUpHandler: ((e: MouseEvent) => void) | null = null

/** 从路径中提取文件/文件夹名 */
function pathBaseName(p: string): string {
  return p.replace(/[\\/]+$/, '').split(/[\\/]/).pop() || p
}

/** 创建跟随鼠标的拖拽幽灵标签（文件名 + 图标） */
function createDragGhost(name: string, isDir: boolean): HTMLElement {
  const el = document.createElement('div')
  el.style.cssText = `
    position: fixed; z-index: 99999;
    display: flex; align-items: center; gap: 6px;
    padding: 6px 12px; border-radius: 8px;
    background: white; border: 1px solid #e5e7eb;
    box-shadow: 0 4px 12px rgba(0,0,0,0.12);
    font-size: 12px; color: #374151; white-space: nowrap;
    pointer-events: none;
  `
  const icon = document.createElement('span')
  icon.style.fontSize = '14px'
  icon.textContent = isDir ? '📁' : '📄'
  const text = document.createElement('span')
  text.textContent = name
  el.appendChild(icon)
  el.appendChild(text)
  document.body.appendChild(el)
  return el
}

/** 创建"→ 移动到 xxx"的浮动目标提示 */
function createTargetTooltip(): HTMLElement {
  const el = document.createElement('div')
  el.style.cssText = `
    position: fixed; z-index: 99999;
    display: none; align-items: center; gap: 5px;
    padding: 4px 10px; border-radius: 6px;
    background: #fffbeb; border: 1px solid #f59e0b;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    font-size: 11px; color: #92400e; white-space: nowrap;
    pointer-events: none;
  `
  document.body.appendChild(el)
  return el
}

/** 刷新目标提示内容（使用 textContent 防止 XSS） */
function refreshTargetTooltip() {
  if (!dragTooltip) return
  const target = store.dropTargetPath

  if (target && store.draggedItem && target !== store.draggedItem.path) {
    const folderName = pathBaseName(target)
    dragTooltip.textContent = ''
    const arrow = document.createElement('span')
    arrow.textContent = '→ 移动到'
    const name = document.createElement('span')
    name.style.fontWeight = '600'
    name.textContent = folderName
    dragTooltip.appendChild(arrow)
    dragTooltip.appendChild(name)
    dragTooltip.style.display = 'flex'
  } else {
    dragTooltip.style.display = 'none'
  }
  lastDropTarget = target
}

/** 清理所有拖拽视觉元素和全局状态 */
function cleanupDrag() {
  if (dragGhost) { dragGhost.remove(); dragGhost = null }
  if (dragTooltip) { dragTooltip.remove(); dragTooltip = null }
  if (currentMouseMoveHandler) {
    document.removeEventListener('mousemove', currentMouseMoveHandler)
    currentMouseMoveHandler = null
  }
  if (currentMouseUpHandler) {
    document.removeEventListener('mouseup', currentMouseUpHandler)
    currentMouseUpHandler = null
  }
  if (isDragging) {
    document.body.classList.remove('workspace-dragging')
    isDragging = false
  }
}

/** 检查 target 是否是 source 的子路径 */
function isChildPath(target: string, source: string): boolean {
  if (target === source) return true
  // 加分隔符避免 "daziceshi2".startsWith("daziceshi") 的误判
  const normalized = source.replace(/[\\/]+$/, '')
  return target.startsWith(normalized + '\\') || target.startsWith(normalized + '/')
}

/**
 * 鼠标按下：注册 mousemove / mouseup 来实现拖拽
 * 
 * 为什么不用 HTML5 Drag API？
 * Tauri 的 WebView2 原生层会拦截 HTML5 drag 事件，
 * 在 JS 设置 dropEffect 之前就显示了禁止光标（🚫）。
 * 基于 mouse 事件完全绕过原生拖拽层，光标由我们 CSS 控制。
 */
function handleMouseDown(e: MouseEvent) {
  // 仅处理左键，且排除重命名状态
  if (e.button !== 0 || isRenaming.value) return

  const startX = e.clientX
  const startY = e.clientY
  isDragging = false

  const onMouseMove = (ev: MouseEvent) => {
    const dx = Math.abs(ev.clientX - startX)
    const dy = Math.abs(ev.clientY - startY)

    // 最小移动距离阈值（5px），区分"点击"和"拖拽"
    if (!isDragging && dx + dy < 5) return

    if (!isDragging) {
      // ---- 拖拽开始 ----
      isDragging = true
      store.setDraggedItem(props.item)

      // 创建幽灵标签和目标提示
      dragGhost = createDragGhost(props.item.name, props.item.is_dir)
      dragTooltip = createTargetTooltip()
      lastDropTarget = null

      // 全局 grabbing 光标（通过 CSS 类，覆盖所有子元素）
      document.body.classList.add('workspace-dragging')
    }

    // 更新幽灵位置（鼠标右下方偏移）
    if (dragGhost) {
      dragGhost.style.left = (ev.clientX + 16) + 'px'
      dragGhost.style.top = (ev.clientY + 8) + 'px'
    }
    if (dragTooltip) {
      dragTooltip.style.left = (ev.clientX + 16) + 'px'
      dragTooltip.style.top = (ev.clientY + 32) + 'px'
    }

    // 通过 elementFromPoint 实时检测悬停目标文件夹
    // （ghost/tooltip 设有 pointer-events: none，不会遮挡检测）
    const target = document.elementFromPoint(ev.clientX, ev.clientY)
    const folderEl = target?.closest('[data-drop-folder]') as HTMLElement | null
    if (folderEl) {
      const targetPath = folderEl.getAttribute('data-drop-folder')
      if (targetPath && store.draggedItem && targetPath !== store.draggedItem.path
          && !isChildPath(targetPath, store.draggedItem.path)) {
        store.setDropTarget(targetPath)
      } else {
        store.setDropTarget(null)
      }
    } else {
      store.setDropTarget(null)
    }

    // 更新目标提示文字
    if (store.dropTargetPath !== lastDropTarget) {
      refreshTargetTooltip()
    }
  }

  const onMouseUp = (ev: MouseEvent) => {
    // 清理全局监听
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
    currentMouseMoveHandler = null
    currentMouseUpHandler = null

    if (!isDragging) return // 这是一次普通点击，@click 会正常触发

    // 拖拽结束
    suppressNextClick = true // 阻止紧随其后的 click 事件误触发
    cleanupDrag()
    store.setDropTarget(null)

    const x = ev.clientX
    const y = ev.clientY

    // 检测放置目标
    if (store.draggedItem) {
      const target = document.elementFromPoint(x, y)
      const folderEl = target?.closest('[data-drop-folder]') as HTMLElement | null
      if (folderEl) {
        const targetPath = folderEl.getAttribute('data-drop-folder')
        if (targetPath && targetPath !== store.draggedItem.path) {
          if (!isChildPath(targetPath, store.draggedItem.path)) {
            const fromPath = store.draggedItem.path
            store.clearDrag()
            store.moveFile(fromPath, targetPath)
            return
          }
        }
      }
    }

    // 兜底：记录鼠标释放位置，供 ChatView 的 sync watch 检测是否拖入了聊天输入框
    store.setDragEndPosition(x, y)
    store.clearDrag()
  }

  currentMouseMoveHandler = onMouseMove
  currentMouseUpHandler = onMouseUp
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

// ==================== 内联编辑 ====================

/** 创建确认 */
async function confirmCreate() {
  if (newName.value.trim()) {
    await store.confirmEditing(newName.value)
  } else {
    store.cancelEditing()
  }
  newName.value = ''
}

/** 重命名确认 */
async function confirmRename() {
  if (renameName.value.trim()) {
    await store.confirmEditing(renameName.value)
  } else {
    store.cancelEditing()
  }
}

// 监听：创建输入出现时预填默认名并选中名称部分
watch(isCreatingHere, (v) => {
  if (v && store.editingState) {
    const isFile = store.editingState.type === 'new-file'
    newName.value = store.getDefaultNewName(store.editingState.parentPath, isFile)
    nextTick(() => {
      const input = createInputRef.value
      if (!input) return
      input.focus()
      // 选中名称部分（不含后缀）
      const dotIdx = newName.value.lastIndexOf('.')
      input.setSelectionRange(0, dotIdx > 0 ? dotIdx : newName.value.length)
    })
  }
})

// 监听：重命名输入出现时自动聚焦并选中
watch(isRenaming, (v) => {
  if (v && store.editingState?.originalName) {
    renameName.value = store.editingState.originalName
    nextTick(() => {
      renameInputRef.value?.focus()
      renameInputRef.value?.select()
    })
  }
})

// ==================== 组件销毁清理 ====================

onBeforeUnmount(() => {
  // 防止拖拽过程中组件卸载导致 DOM 元素和事件监听器泄漏
  cleanupDrag()
  if (store.draggedItem) {
    store.setDropTarget(null)
    store.clearDrag()
  }
})

// ==================== 工具 ====================

function formatSize(bytes: number): string {
  if (!bytes) return ''
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}
</script>

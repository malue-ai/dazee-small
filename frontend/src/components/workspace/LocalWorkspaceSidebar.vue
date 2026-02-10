<template>
  <div 
    class="h-full flex flex-col bg-white overflow-hidden" 
    @click="store.hideContextMenu"
  >
    <!-- 头部 -->
    <div class="flex items-center justify-between px-3 py-2.5 border-b border-border bg-white flex-shrink-0">
      <div class="flex items-center gap-1.5 min-w-0 flex-1">
        <FolderOpen class="w-3.5 h-3.5 text-primary flex-shrink-0" />
        <span class="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          工作区
        </span>
        <span v-if="store.hasFolders" class="text-[10px] text-muted-foreground/50 ml-1">
          {{ store.folders.length }} 个文件夹
        </span>
      </div>
      <div class="flex gap-0.5 flex-shrink-0">
        <button
          v-if="store.hasFolders"
          @click="handleExpandToggle"
          class="p-1.5 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          :title="isAllExpanded ? '收起全部' : '展开全部'"
        >
          <FolderOpen v-if="isAllExpanded" class="w-3.5 h-3.5" />
          <Folder v-else class="w-3.5 h-3.5" />
        </button>
        <button
          v-if="store.hasFolders"
          @click="store.refreshAll"
          class="p-1.5 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:opacity-40"
          :disabled="store.isAnyLoading"
          title="刷新全部"
        >
          <RefreshCw class="w-3.5 h-3.5" :class="store.isAnyLoading ? 'animate-spin' : ''" />
        </button>
        <button
          @click="handleOpenFolder"
          class="p-1.5 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          title="添加文件夹"
        >
          <FolderPlus class="w-3.5 h-3.5" />
        </button>
        <button
          @click="$emit('close')"
          class="p-1.5 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          title="关闭面板"
        >
          <X class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>

    <!-- 空状态 / 拖拽区域 -->
    <div 
      v-if="!store.hasFolders"
      class="flex-1 flex flex-col items-center justify-center p-6 text-center transition-all duration-200"
      :class="isDragOver ? 'bg-primary/5' : ''"
    >
      <div 
        class="w-16 h-16 rounded-2xl border-2 border-dashed flex items-center justify-center mb-4 transition-all duration-200"
        :class="isDragOver 
          ? 'border-primary bg-primary/10 scale-105' 
          : 'border-border bg-muted'"
      >
        <Upload v-if="isDragOver" class="w-8 h-8 text-primary animate-bounce" />
        <FolderOpen v-else class="w-8 h-8 text-muted-foreground/30" />
      </div>
      <p class="text-sm font-medium text-foreground mb-1">
        {{ isDragOver ? '释放以添加文件夹' : '拖拽文件夹到这里' }}
      </p>
      <p class="text-xs text-muted-foreground/50 mb-5">支持同时添加多个文件夹</p>
      <button
        @click="handleOpenFolder"
        class="inline-flex items-center gap-1.5 px-4 py-2 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:bg-primary/90 transition-colors shadow-sm"
      >
        <FolderPlus class="w-3.5 h-3.5" />
        选择文件夹
      </button>
    </div>

    <!-- 多文件夹列表 -->
    <div 
      v-else 
      class="flex-1 overflow-y-auto scrollbar-thin"
      :class="isDragOver ? 'bg-primary/5' : ''"
    >
      <!-- 拖拽提示条 -->
      <div 
        v-if="isDragOver" 
        class="sticky top-0 z-10 flex items-center justify-center gap-1.5 py-1.5 bg-primary/10 border-b border-primary/20 text-primary text-xs font-medium"
      >
        <Upload class="w-3.5 h-3.5" />
        释放以添加文件夹
      </div>

      <!-- 每个文件夹块 -->
      <div 
        v-for="folder in store.folders" 
        :key="folder.path" 
        class="border-b border-border last:border-b-0"
      >
        <!-- 文件夹根节点 -->
        <div 
          class="flex items-center gap-1.5 py-2 px-3 cursor-pointer transition-colors group hover:bg-muted/50 sticky top-0 bg-white z-[5]"
          :class="store.dropTargetPath === folder.path ? 'bg-primary/10' : ''"
          :data-drop-folder="folder.path"
          @click="store.toggleDir(folder.path)"
          @contextmenu.prevent="handleFolderContextMenu($event, folder)"
        >
          <span class="w-3 h-3 flex items-center justify-center text-muted-foreground/50 flex-shrink-0">
            <ChevronDown v-if="store.isDirExpanded(folder.path)" class="w-3 h-3" />
            <ChevronRight v-else class="w-3 h-3" />
          </span>
          <component 
            :is="store.isDirExpanded(folder.path) ? FolderOpen : Folder" 
            class="w-4 h-4 flex-shrink-0 text-primary" 
          />
          <span class="flex-1 text-xs font-semibold text-foreground truncate" :title="folder.path">
            {{ folder.name }}
          </span>
          <Loader2 v-if="folder.isLoading" class="w-3 h-3 animate-spin text-muted-foreground/50 flex-shrink-0" />
          <div class="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
            <button
              @click.stop="store.startNewFile(folder.path)"
              class="p-1 rounded text-muted-foreground/50 hover:bg-muted hover:text-foreground transition-colors"
              title="新建文件"
            >
              <FilePlus class="w-3 h-3" />
            </button>
            <button
              @click.stop="store.startNewFolder(folder.path)"
              class="p-1 rounded text-muted-foreground/50 hover:bg-muted hover:text-foreground transition-colors"
              title="新建文件夹"
            >
              <FolderPlus2 class="w-3 h-3" />
            </button>
            <button
              @click.stop="store.refreshFolder(folder.path)"
              class="p-1 rounded text-muted-foreground/50 hover:bg-muted hover:text-foreground transition-colors"
              title="刷新"
              :disabled="folder.isLoading"
            >
              <RefreshCw class="w-3 h-3" />
            </button>
            <button
              @click.stop="store.removeFolder(folder.path)"
              class="p-1 rounded text-muted-foreground/50 hover:bg-red-50 hover:text-red-500 transition-colors"
              title="移除"
            >
              <X class="w-3 h-3" />
            </button>
          </div>
        </div>

        <!-- 错误 -->
        <div v-if="folder.error" class="flex items-center gap-2 px-6 py-2 text-red-400">
          <AlertCircle class="w-3.5 h-3.5 flex-shrink-0" />
          <span class="text-xs truncate">{{ folder.error }}</span>
          <button @click="store.refreshFolder(folder.path)" class="text-xs text-primary hover:underline flex-shrink-0">重试</button>
        </div>

        <!-- 展开时的内容区域（新建输入 + 文件树 / 空提示） -->
        <template v-else-if="store.isDirExpanded(folder.path)">
          <!-- 根目录下的新建输入（始终在最前面，不受空状态影响） -->
          <div 
            v-if="isCreatingInFolder(folder.path)"
            class="flex items-center gap-1.5 py-1 pr-2"
            :style="{ paddingLeft: (1 * 12 + 12) + 'px' }"
          >
            <span class="w-3 flex-shrink-0"></span>
            <component 
              :is="store.editingState?.type === 'new-folder' ? Folder : FileIcon" 
              class="w-4 h-4 flex-shrink-0 text-primary/50" 
            />
            <input
              ref="rootCreateInputRef"
              v-model="rootNewName"
              class="flex-1 text-xs bg-white border border-primary/40 rounded px-1.5 py-0.5 outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 min-w-0"
              :placeholder="store.editingState?.type === 'new-folder' ? '文件夹名称' : '文件名称'"
              @keydown.enter="confirmRootCreate"
              @keydown.escape="store.cancelEditing"
              @blur="confirmRootCreate"
            />
          </div>

          <!-- 文件树 -->
          <template v-if="folder.files.length > 0">
            <LocalFileTreeNode
              v-for="item in folder.files"
              :key="item.path"
              :item="item"
              :depth="1"
            />
          </template>

          <!-- 空文件夹提示（不阻断新建输入） -->
          <div v-else-if="!folder.isLoading && !isCreatingInFolder(folder.path)" class="px-6 py-2">
            <span class="text-[10px] text-muted-foreground/40">文件夹为空</span>
          </div>
        </template>
      </div>
    </div>

    <!-- 底部统计 -->
    <div 
      v-if="store.hasFolders"
      class="flex items-center justify-between px-3 py-2 bg-white border-t border-border text-[10px] text-muted-foreground/50 flex-shrink-0"
    >
      <span>{{ store.fileCount }} 个文件 · {{ store.dirCount }} 个文件夹</span>
      <button 
        @click="store.clearAll" 
        class="hover:text-foreground transition-colors flex items-center gap-1"
      >
        <Trash2 class="w-3 h-3" />
        清空
      </button>
    </div>

    <!-- 右键上下文菜单 -->
    <FileContextMenu />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useLocalWorkspaceStore, type WorkspaceFolder } from '@/stores/localWorkspace'
import { isTauriEnv } from '@/api/tauri'
import LocalFileTreeNode from './LocalFileTreeNode.vue'
import FileContextMenu from './FileContextMenu.vue'
import { 
  FolderOpen, Folder, FolderPlus, RefreshCw, Upload, X, Loader2, AlertCircle,
  ChevronDown, ChevronRight, Trash2, FilePlus, FolderPlus as FolderPlus2,
  File as FileIcon,
} from 'lucide-vue-next'

const emit = defineEmits<{ (e: 'close'): void }>()
const store = useLocalWorkspaceStore()

// ==================== 状态 ====================

const isDragOver = ref(false)
const isAllExpanded = ref(false)
const rootCreateInputRef = ref<HTMLInputElement | null>(null)
const rootNewName = ref('')

// ==================== 根文件夹下的新建检测 ====================

function isCreatingInFolder(folderPath: string): boolean {
  if (!store.editingState) return false
  return (store.editingState.type === 'new-file' || store.editingState.type === 'new-folder')
    && store.editingState.parentPath === folderPath
}

// 自动聚焦根创建输入，并预填默认名（自动避免重名）
watch(() => store.editingState, (state) => {
  if (state && (state.type === 'new-file' || state.type === 'new-folder')) {
    // 检查是否在某个根文件夹下
    const isRoot = store.folders.some(f => f.path === state.parentPath)
    if (isRoot) {
      const isFile = state.type === 'new-file'
      rootNewName.value = store.getDefaultNewName(state.parentPath, isFile)
      nextTick(() => {
        const input = rootCreateInputRef.value
        if (!input) return
        input.focus()
        // 选中名称部分（不含后缀）
        const dotIdx = rootNewName.value.lastIndexOf('.')
        input.setSelectionRange(0, dotIdx > 0 ? dotIdx : rootNewName.value.length)
      })
    }
  }
}, { deep: true })

async function confirmRootCreate() {
  if (rootNewName.value.trim()) {
    await store.confirmEditing(rootNewName.value)
  } else {
    store.cancelEditing()
  }
  rootNewName.value = ''
}

// 根文件夹拖拽放置已改为 mouse 事件方案，由 LocalFileTreeNode.handleMouseDown 通过
// elementFromPoint + data-drop-folder 统一检测，不再需要 HTML5 drag 事件处理器。

// ==================== 右键菜单（文件夹根） ====================

function handleFolderContextMenu(e: MouseEvent, folder: WorkspaceFolder) {
  store.showContextMenu(e.clientX, e.clientY, null, folder.path)
}

// ==================== 外部拖拽状态（由父组件 ChatView 通过 props 控制） ====================

const props = defineProps<{
  /** 外部系统文件拖拽悬停在工作区上方 */
  externalDragOver?: boolean
}>()

watch(() => props.externalDragOver, (v) => {
  isDragOver.value = !!v
})

// ==================== 通用操作 ====================

async function handleOpenFolder(): Promise<void> {
  if (!isTauriEnv()) return
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({ directory: true, multiple: false, title: '选择文件夹添加到工作区' })
    if (selected && typeof selected === 'string') await store.addFolder(selected)
  } catch (e) { console.error('打开文件夹对话框失败:', e) }
}

function handleExpandToggle(): void {
  if (isAllExpanded.value) store.collapseAll()
  else store.expandAll()
  isAllExpanded.value = !isAllExpanded.value
}
</script>

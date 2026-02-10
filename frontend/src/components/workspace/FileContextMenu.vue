<template>
  <Teleport to="body">
    <!-- 遮罩（点击关闭） -->
    <div 
      v-if="store.contextMenu" 
      class="fixed inset-0 z-[9998]"
      @click="store.hideContextMenu"
      @contextmenu.prevent="store.hideContextMenu"
    />
    <!-- 菜单 -->
    <Transition name="ctx-menu">
      <div
        v-if="store.contextMenu"
        class="fixed z-[9999] min-w-[180px] py-1.5 bg-white rounded-xl shadow-xl border border-border/80 backdrop-blur-sm"
        :style="menuStyle"
      >
        <!-- 对目录：新建文件 / 新建文件夹 -->
        <template v-if="isDir">
          <button class="ctx-item" @click="handleNewFile">
            <FilePlus class="w-3.5 h-3.5" />
            <span>新建文件</span>
          </button>
          <button class="ctx-item" @click="handleNewFolder">
            <FolderPlus class="w-3.5 h-3.5" />
            <span>新建文件夹</span>
          </button>
          <div class="ctx-divider" />
        </template>

        <!-- 通用：重命名 -->
        <button v-if="store.contextMenu.item" class="ctx-item" @click="handleRename">
          <Pencil class="w-3.5 h-3.5" />
          <span>重命名</span>
        </button>

        <!-- 通用：复制路径 -->
        <button class="ctx-item" @click="handleCopyPath">
          <Copy class="w-3.5 h-3.5" />
          <span>复制路径</span>
        </button>

        <div class="ctx-divider" />

        <!-- 通用：删除 -->
        <button v-if="store.contextMenu.item" class="ctx-item ctx-danger" @click="handleDelete">
          <Trash2 class="w-3.5 h-3.5" />
          <span>删除</span>
        </button>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useLocalWorkspaceStore } from '@/stores/localWorkspace'
import { FilePlus, FolderPlus, Pencil, Copy, Trash2 } from 'lucide-vue-next'

const store = useLocalWorkspaceStore()

/** 菜单是否针对目录 */
const isDir = computed(() => {
  if (!store.contextMenu) return false
  // item 为 null 表示在文件夹根区域点击，也算目录
  return !store.contextMenu.item || store.contextMenu.item.is_dir
})

/** 目标路径 */
const targetPath = computed(() => {
  if (!store.contextMenu) return ''
  return store.contextMenu.item?.path || store.contextMenu.folderPath
})

/** 菜单位置样式（确保不超出视口） */
const menuStyle = computed(() => {
  if (!store.contextMenu) return {}
  const { x, y } = store.contextMenu
  const menuW = 200
  const menuH = 220
  const vw = window.innerWidth
  const vh = window.innerHeight
  return {
    left: (x + menuW > vw ? vw - menuW - 8 : x) + 'px',
    top: (y + menuH > vh ? vh - menuH - 8 : y) + 'px',
  }
})

function handleNewFile() {
  const dirPath = store.contextMenu?.item?.is_dir
    ? store.contextMenu.item.path
    : store.contextMenu?.folderPath
  if (dirPath) store.startNewFile(dirPath)
}

function handleNewFolder() {
  const dirPath = store.contextMenu?.item?.is_dir
    ? store.contextMenu.item.path
    : store.contextMenu?.folderPath
  if (dirPath) store.startNewFolder(dirPath)
}

function handleRename() {
  if (store.contextMenu?.item) {
    store.startRename(store.contextMenu.item)
  }
}

function handleCopyPath() {
  store.copyPath(targetPath.value)
}

async function handleDelete() {
  if (!store.contextMenu?.item) return
  const name = store.contextMenu.item.name
  const itemPath = store.contextMenu.item.path
  // 先关闭菜单，再弹确认框，确认后才删除
  store.hideContextMenu()
  try {
    const { ask } = await import('@tauri-apps/plugin-dialog')
    const confirmed = await ask(`确定要删除 "${name}" 吗？此操作不可撤销。`, {
      title: '确认删除',
      kind: 'warning',
    })
    if (confirmed) {
      await store.deleteItem(itemPath)
    }
  } catch {
    // fallback: 非 Tauri 环境用 window.confirm
    const confirmed = window.confirm(`确定要删除 "${name}" 吗？此操作不可撤销。`)
    if (confirmed) {
      await store.deleteItem(itemPath)
    }
  }
}
</script>

<style scoped>
.ctx-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 14px;
  font-size: 12px;
  color: var(--color-foreground, #1a1a1a);
  transition: background-color 0.1s;
  cursor: pointer;
  border: none;
  background: none;
  text-align: left;
}
.ctx-item:hover {
  background-color: var(--color-muted, #f5f5f5);
}
.ctx-danger {
  color: #ef4444;
}
.ctx-danger:hover {
  background-color: #fef2f2;
}
.ctx-divider {
  height: 1px;
  margin: 4px 10px;
  background-color: var(--color-border, #e5e5e5);
}

.ctx-menu-enter-active {
  transition: all 0.12s ease-out;
}
.ctx-menu-leave-active {
  transition: all 0.08s ease-in;
}
.ctx-menu-enter-from {
  opacity: 0;
  transform: scale(0.95);
}
.ctx-menu-leave-to {
  opacity: 0;
  transform: scale(0.95);
}
</style>

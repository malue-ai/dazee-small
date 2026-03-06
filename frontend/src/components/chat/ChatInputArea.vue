<template>
  <div class="px-6 pb-6 pt-2 bg-transparent pointer-events-none sticky bottom-0 z-30">
    <div 
      class="pointer-events-auto max-w-4xl mx-auto bg-white border rounded-2xl p-3 shadow-lg transition-all duration-300 focus-within:shadow-xl focus-within:border-primary/30"
      :class="(isDragOver || props.externalDragOver) ? 'border-primary border-dashed bg-primary/5' : 'border-border'"
      @dragenter.prevent
      @dragover.prevent="onDragOver"
      @dragleave="onDragLeave"
      @drop.prevent="onDrop"
    >
      <!-- 拖拽提示层 -->
      <div
        v-if="isDragOver || props.externalDragOver"
        class="absolute inset-0 flex items-center justify-center rounded-2xl z-10 pointer-events-none"
      >
        <span class="text-sm text-primary font-medium">释放以添加文件</span>
      </div>

      <div class="flex items-center gap-2">
        <!-- 添加文件按钮 -->
        <button 
          class="p-3 rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground transition-colors flex-shrink-0" 
          @click="emit('upload-click')"
          :disabled="disabled || uploading"
          title="添加文件"
        >
          <Loader2 v-if="uploading" class="w-5 h-5 animate-spin" />
          <Plus v-else class="w-5 h-5" />
        </button>
        
        <!-- 编辑区域：支持文本 + 内联文件标签（可通过 Backspace 删除） -->
        <div class="flex-1 min-w-0 relative">
          <div
            ref="editorRef"
            contenteditable="true"
            @input="onEditorInput"
            @keydown="onEditorKeydown"
            @compositionstart="isComposing = true"
            @compositionend="isComposing = false"
            @paste="onPaste"
            class="editor-content min-h-[28px] max-h-[200px] py-1 outline-none text-base text-foreground leading-relaxed overflow-y-auto whitespace-pre-wrap break-words"
          ></div>
          <!-- 占位符 -->
          <div
            v-if="editorEmpty"
            @click="focus"
            class="absolute left-0 top-1 text-base text-muted-foreground/50 pointer-events-none select-none"
          >输入消息...</div>
        </div>
        
        <div class="flex-shrink-0">
          <!-- 停止按钮：加载中且无输入 -->
          <button 
            v-if="loading && !hasInput" 
            class="p-3 rounded-xl bg-foreground text-white hover:bg-foreground/80 transition-all shadow-sm" 
            @click="emit('stop')"
            :disabled="stopping"
          >
            <SquareIcon class="w-4 h-4 fill-current" />
          </button>
          <!-- 发送按钮组（split button） -->
          <div v-else class="relative flex items-center" ref="sendMenuRef">
            <button 
              class="p-3 rounded-l-xl transition-all shadow-sm flex items-center justify-center"
              :class="canSend
                ? 'bg-primary text-white hover:bg-primary-hover shadow-primary/20'
                : 'bg-muted text-muted-foreground/30 cursor-not-allowed'"
              :disabled="!canSend"
              @click="handleSend"
            >
              <ArrowUp class="w-5 h-5" />
            </button>
            <button
              class="py-3 px-1 rounded-r-xl border-l transition-all shadow-sm flex items-center justify-center"
              :class="canSend
                ? 'bg-primary text-white/70 hover:text-white hover:bg-primary-hover border-white/20 shadow-primary/20'
                : 'bg-muted text-muted-foreground/20 border-muted-foreground/10 cursor-not-allowed'"
              :disabled="!canSend"
              @click.stop="toggleSendMenu"
            >
              <ChevronDown class="w-3.5 h-3.5" />
            </button>
            <!-- 下拉菜单 -->
            <Transition
              enter-active-class="transition duration-100 ease-out"
              enter-from-class="opacity-0 scale-95"
              enter-to-class="opacity-100 scale-100"
              leave-active-class="transition duration-75 ease-in"
              leave-from-class="opacity-100 scale-100"
              leave-to-class="opacity-0 scale-95"
            >
              <div
                v-if="showSendMenu"
                class="absolute bottom-full right-0 mb-2 w-44 bg-white border border-border rounded-xl shadow-lg overflow-hidden"
              >
                <button
                  @click="handleSendBackground"
                  class="w-full flex items-center gap-2 px-3 py-2.5 text-sm text-foreground hover:bg-muted transition-colors"
                >
                  <MonitorCog class="w-4 h-4 text-muted-foreground" />
                  后台运行
                </button>
              </div>
            </Transition>
          </div>
        </div>
      </div>
    </div>
    <div class="text-center mt-2">
      <p class="text-[10px] text-muted-foreground/50">AI 可能生成错误信息，请核对重要事实。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import type { AttachedFile } from '@/types'
import { Loader2, Plus, Square as SquareIcon, ArrowUp, ChevronDown, MonitorCog } from 'lucide-vue-next'
import { useLocalWorkspaceStore } from '@/stores/localWorkspace'

// ==================== Props ====================

interface Props {
  /** 文本内容（双向绑定） */
  modelValue: string
  /** 是否正在加载 */
  loading?: boolean
  /** 是否正在停止 */
  stopping?: boolean
  /** 是否正在上传 */
  uploading?: boolean
  /** 是否禁用 */
  disabled?: boolean
  /** 外部拖拽悬停状态（由 Tauri 全局拖拽控制） */
  externalDragOver?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  stopping: false,
  uploading: false,
  disabled: false,
  externalDragOver: false,
})

// ==================== Emits ====================

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'send'): void
  (e: 'send-background'): void
  (e: 'stop'): void
  (e: 'upload-click'): void
  (e: 'files-dropped', files: File[]): void
  (e: 'workspace-file-dropped', fileInfo: { path: string; name: string; size: number }): void
  (e: 'file-preview', file: AttachedFile): void
}>()

// ==================== State ====================

const workspaceStore = useLocalWorkspaceStore()
const editorRef = ref<HTMLDivElement | null>(null)
const isComposing = ref(false)
const editorEmpty = ref(true)
const isDragOver = ref(false)
const showSendMenu = ref(false)
const sendMenuRef = ref<HTMLDivElement | null>(null)
let dragLeaveTimer: ReturnType<typeof setTimeout> | null = null

/** 防止 input → emit → watch → 更新 DOM 的循环 */
let _syncing = false

// ==================== Computed ====================

const hasInput = computed(() => !editorEmpty.value)
const canSend = computed(() => hasInput.value)

// ==================== 文本提取 ====================

/** 从编辑器 DOM 中提取纯文本（跳过文件标签内部文字） */
function getEditorText(): string {
  if (!editorRef.value) return ''
  let text = ''
  const walk = (node: Node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      text += node.textContent || ''
    } else if (node instanceof HTMLElement) {
      // 跳过文件标签内部
      if (node.hasAttribute('data-file-chip')) return
      if (node.tagName === 'BR') text += '\n'
      Array.from(node.childNodes).forEach(walk)
    }
  }
  walk(editorRef.value)
  return text
}

/** 更新空状态 */
function updateEmptyState() {
  if (!editorRef.value) { editorEmpty.value = true; return }
  const text = getEditorText().trim()
  const hasChips = !!editorRef.value.querySelector('[data-file-chip]')
  editorEmpty.value = text.length === 0 && !hasChips
}

// ==================== 输入事件 ====================

function onEditorInput() {
  if (!editorRef.value) return

  // 清理：如果只剩空白/BR且无文件标签，真正清空（配合占位符显示）
  const text = getEditorText().trim()
  const hasChips = !!editorRef.value.querySelector('[data-file-chip]')
  if (!text && !hasChips && editorRef.value.innerHTML !== '') {
    editorRef.value.innerHTML = ''
  }

  _syncing = true
  emit('update:modelValue', getEditorText())
  updateEmptyState()
  nextTick(() => { _syncing = false })
}

function onEditorKeydown(e: KeyboardEvent) {
  // Enter 发送（Shift+Enter 换行）
  if (e.key === 'Enter' && !e.shiftKey) {
    if (isComposing.value || e.isComposing || e.keyCode === 229) return
    e.preventDefault()
    handleSend()
  }
}

/** 粘贴：仅保留纯文本，同时支持粘贴文件 */
function onPaste(e: ClipboardEvent) {
  // 如果粘贴内容包含文件（如截图），通知父组件处理
  const files = Array.from(e.clipboardData?.files || [])
  if (files.length > 0) {
    e.preventDefault()
    emit('files-dropped', files)
    return
  }

  e.preventDefault()
  const text = e.clipboardData?.getData('text/plain') || ''
  if (text) document.execCommand('insertText', false, text)
}

// ==================== 拖拽放置文件 ====================

function onDragOver(e: DragEvent) {
  // 检测是否有可接受的拖拽内容，显示视觉反馈
  const hasFiles = Array.from(e.dataTransfer?.types || []).indexOf('Files') >= 0
  const hasWorkspaceFile = !!(workspaceStore.draggedItem && !workspaceStore.draggedItem.is_dir)

  if (hasFiles || hasWorkspaceFile) {
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
    if (dragLeaveTimer) { clearTimeout(dragLeaveTimer); dragLeaveTimer = null }
    isDragOver.value = true
  }
}

function onDragLeave() {
  // 延迟隐藏：避免在子元素间移动时闪烁
  dragLeaveTimer = setTimeout(() => { isDragOver.value = false }, 100)
}

function onDrop(e: DragEvent) {
  isDragOver.value = false
  if (dragLeaveTimer) { clearTimeout(dragLeaveTimer); dragLeaveTimer = null }

  // 优先处理工作区文件拖拽（通过 store 状态检测）
  const wsItem = workspaceStore.draggedItem
  if (wsItem && !wsItem.is_dir) {
    const fileInfo = { path: wsItem.path, name: wsItem.name, size: wsItem.size }
    workspaceStore.clearDrag()
    emit('workspace-file-dropped', fileInfo)
    return
  }

  // 系统文件拖拽（非 Tauri 环境下的 fallback）
  const files = Array.from(e.dataTransfer?.files || [])
  if (files.length > 0) {
    emit('files-dropped', files)
  }
}

// ==================== 外部 modelValue 同步 ====================

watch(() => props.modelValue, (newVal) => {
  if (_syncing) return
  if (!editorRef.value) return
  if (getEditorText() === newVal) return

  // 清空或设置新文本（会移除文件标签）
  editorRef.value.innerHTML = ''
  if (newVal) {
    editorRef.value.textContent = newVal
    // 光标移到末尾
    const range = document.createRange()
    range.selectNodeContents(editorRef.value)
    range.collapse(false)
    const sel = window.getSelection()
    sel?.removeAllRanges()
    sel?.addRange(range)
  }
  updateEmptyState()
})

// ==================== 文件标签 ====================

/** 在光标位置插入文件标签（像字符一样，可 Backspace 删除） */
function insertFile(file: AttachedFile) {
  if (!editorRef.value) return

  const chip = document.createElement('span')
  chip.setAttribute('data-file-chip', '')
  chip.setAttribute('data-file-data', JSON.stringify({
    file_url: file.file_url,
    local_path: file.local_path,
    file_name: file.file_name,
    file_type: file.file_type,
    file_size: file.file_size,
  }))
  chip.contentEditable = 'false'
  chip.className = 'file-chip'

  const icon = document.createElement('span')
  icon.className = 'file-chip-icon'
  icon.textContent = '📄'

  const nameEl = document.createElement('span')
  nameEl.className = 'file-chip-name'
  nameEl.textContent = file.file_name

  const closeBtn = document.createElement('span')
  closeBtn.className = 'file-chip-close'
  closeBtn.textContent = '✕'
  closeBtn.onmousedown = (e) => {
    e.preventDefault()
    e.stopPropagation()
    chip.remove()
    onEditorInput()
  }

  chip.onclick = (e) => {
    if ((e.target as HTMLElement).classList.contains('file-chip-close')) return
    e.preventDefault()
    e.stopPropagation()
    emit('file-preview', file)
  }

  chip.appendChild(icon)
  chip.appendChild(nameEl)
  chip.appendChild(closeBtn)

  // 在当前光标位置插入
  const sel = window.getSelection()
  if (sel && sel.rangeCount > 0 && editorRef.value.contains(sel.anchorNode)) {
    const range = sel.getRangeAt(0)
    range.deleteContents()
    range.insertNode(chip)
    // 标签后加一个空格，并将光标移到空格之后
    const space = document.createTextNode('\u00A0')
    chip.after(space)
    range.setStartAfter(space)
    range.collapse(true)
    sel.removeAllRanges()
    sel.addRange(range)
  } else {
    // 无焦点时追加到末尾
    editorRef.value.appendChild(chip)
    editorRef.value.appendChild(document.createTextNode('\u00A0'))
  }

  editorRef.value.focus()
  onEditorInput()
}

/** 获取编辑器中当前所有文件 */
function getFiles(): AttachedFile[] {
  if (!editorRef.value) return []
  const files: AttachedFile[] = []
  editorRef.value.querySelectorAll('[data-file-chip]').forEach(el => {
    const raw = (el as HTMLElement).dataset.fileData
    if (raw) {
      try { files.push(JSON.parse(raw)) } catch { /* skip */ }
    }
  })
  return files
}

// ==================== 操作 ====================

function handleSend() {
  if (canSend.value) {
    emit('send')
  }
}

function handleSendBackground() {
  if (canSend.value) {
    showSendMenu.value = false
    emit('send-background')
  }
}

function toggleSendMenu() {
  if (!canSend.value) return
  showSendMenu.value = !showSendMenu.value
}

function onClickOutside(e: MouseEvent) {
  if (sendMenuRef.value && !sendMenuRef.value.contains(e.target as Node)) {
    showSendMenu.value = false
  }
}

onMounted(() => document.addEventListener('click', onClickOutside, true))
onUnmounted(() => document.removeEventListener('click', onClickOutside, true))

function focus() {
  editorRef.value?.focus()
}

function setInput(text: string) {
  if (!editorRef.value) return
  editorRef.value.innerHTML = ''
  if (text) editorRef.value.textContent = text
  updateEmptyState()
  nextTick(() => focus())
}

// ==================== Expose ====================

defineExpose({
  focus,
  setInput,
  /** 在光标位置插入文件标签 */
  insertFile,
  /** 获取编辑器中当前所有文件 */
  getFiles,
})
</script>

<style>
/* 文件标签样式（非 scoped，因为标签通过 DOM API 动态创建） */
.file-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  margin: 0 2px;
  vertical-align: middle;
  user-select: none;
  line-height: 1.5;
  background-color: hsl(var(--muted));
  color: hsl(var(--muted-foreground));
  cursor: pointer;
  transition: background-color 0.15s;
}

.file-chip:hover {
  background-color: hsl(var(--muted-foreground) / 0.12);
}

.file-chip-icon {
  opacity: 0.6;
  font-size: 11px;
}

.file-chip-name {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-chip-close {
  margin-left: 2px;
  cursor: pointer;
  opacity: 0.4;
  font-size: 10px;
  transition: opacity 0.15s, color 0.15s;
}

.file-chip-close:hover {
  opacity: 1;
  color: hsl(var(--destructive));
}
</style>

<template>
  <Teleport to="body">
    <div
      v-if="show"
      class="fixed inset-0 bg-foreground/50 backdrop-blur-md z-50 flex items-center justify-center p-6 animate-in fade-in duration-300"
      @click.self="emit('dismiss')"
    >
      <div
        class="bg-card rounded-3xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-hidden animate-in slide-in-from-bottom-8 duration-300 ring-1 ring-white/20 flex flex-col"
      >
        <!-- Header -->
        <div
          class="flex items-center justify-between px-8 py-5 border-b border-border bg-muted/50 flex-shrink-0"
        >
          <span class="text-lg font-bold text-foreground flex items-center gap-2">
            <RotateCcw class="w-6 h-6 text-primary" />
            任务异常，是否回滚？
          </span>
          <button
            class="p-2 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            @click="emit('dismiss')"
          >
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Body -->
        <div class="p-8 space-y-5 overflow-y-auto flex-1 scrollbar-thin">
          <!-- 回滚原因 -->
          <p v-if="reason" class="text-sm text-muted-foreground">
            {{ reason }}
          </p>
          <p v-else class="text-sm text-muted-foreground">
            以下文件可被恢复到任务开始前的状态。
          </p>

          <!-- 加载预览中 -->
          <div
            v-if="preview?.previewLoading"
            class="flex items-center gap-3 py-6 justify-center text-muted-foreground"
          >
            <Loader2 class="w-5 h-5 animate-spin" />
            <span class="text-sm">正在分析文件变更...</span>
          </div>

          <!-- Diff 预览：有预览数据 -->
          <div v-else-if="previewFiles.length > 0" class="space-y-3">
            <!-- 变更统计摘要 -->
            <div class="flex items-center gap-3 text-xs">
              <span
                v-if="previewSummary.modified > 0"
                class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-primary/10 text-primary font-medium"
              >
                <Pencil class="w-3 h-3" />
                {{ previewSummary.modified }} 已修改
              </span>
              <span
                v-if="previewSummary.deleted > 0"
                class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-destructive/10 text-destructive font-medium"
              >
                <Trash2 class="w-3 h-3" />
                {{ previewSummary.deleted }} 已删除
              </span>
              <span
                v-if="previewSummary.unchanged > 0"
                class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-muted text-muted-foreground font-medium"
              >
                <Check class="w-3 h-3" />
                {{ previewSummary.unchanged }} 未变更
              </span>
            </div>

            <!-- 全选/取消全选 -->
            <div
              v-if="selectableCount > 1"
              class="flex items-center gap-2 text-xs text-muted-foreground"
            >
              <button
                class="hover:text-foreground transition-colors underline underline-offset-2"
                @click="toggleSelectAll"
              >
                {{ allSelected ? '取消全选' : '全选可回滚文件' }}
              </button>
              <span class="text-muted-foreground/50">
                ({{ selectedCount }}/{{ selectableCount }})
              </span>
            </div>

            <!-- 文件列表 -->
            <ul class="space-y-1.5">
              <li
                v-for="file in previewFiles"
                :key="file.path"
                class="flex items-center gap-3 px-4 py-3 rounded-xl border transition-colors"
                :class="[
                  file.selected
                    ? 'border-primary/30 bg-primary/5'
                    : file.status === 'unchanged'
                      ? 'border-border bg-muted/30 opacity-60'
                      : 'border-border bg-muted/30'
                ]"
              >
                <!-- Checkbox（unchanged 不可选） -->
                <button
                  v-if="file.status !== 'unchanged'"
                  class="flex-shrink-0 w-5 h-5 rounded-md border-2 flex items-center justify-center transition-colors"
                  :class="
                    file.selected
                      ? 'bg-primary border-primary text-white'
                      : 'border-muted-foreground/30 hover:border-primary/50'
                  "
                  @click="toggleFile(file.path)"
                >
                  <Check v-if="file.selected" class="w-3 h-3" />
                </button>
                <div v-else class="flex-shrink-0 w-5 h-5" />

                <!-- 状态图标 -->
                <div class="flex-shrink-0">
                  <Pencil
                    v-if="file.status === 'modified'"
                    class="w-4 h-4 text-primary"
                  />
                  <Trash2
                    v-else-if="file.status === 'deleted'"
                    class="w-4 h-4 text-destructive"
                  />
                  <Check
                    v-else
                    class="w-4 h-4 text-muted-foreground/50"
                  />
                </div>

                <!-- 文件路径 + 大小变化 -->
                <div class="flex-1 min-w-0">
                  <p class="text-sm truncate font-medium" :class="file.status === 'unchanged' ? 'text-muted-foreground' : 'text-foreground'">
                    {{ shortenPath(file.path) }}
                  </p>
                  <p class="text-xs text-muted-foreground mt-0.5">
                    <template v-if="file.status === 'deleted'">
                      文件已被删除，回滚将恢复 ({{ formatSize(file.backup_size) }})
                    </template>
                    <template v-else-if="file.status === 'modified'">
                      {{ formatSize(file.current_size ?? 0) }} → {{ formatSize(file.backup_size) }}
                    </template>
                    <template v-else>
                      未变更，无需回滚
                    </template>
                  </p>
                </div>

                <!-- 状态标签 -->
                <span
                  class="flex-shrink-0 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-md"
                  :class="{
                    'bg-primary/10 text-primary': file.status === 'modified',
                    'bg-destructive/10 text-destructive': file.status === 'deleted',
                    'bg-muted text-muted-foreground': file.status === 'unchanged',
                  }"
                >
                  {{ statusLabel(file.status) }}
                </span>
              </li>
            </ul>
          </div>

          <!-- 回退兼容：无预览数据时显示旧的 options 列表 -->
          <ul
            v-else-if="options?.length"
            class="space-y-2 text-sm text-foreground bg-muted/50 p-4 rounded-xl border border-border"
          >
            <li
              v-for="opt in options"
              :key="opt.id"
              class="flex items-center gap-2"
            >
              <span class="font-medium text-muted-foreground">{{ opt.action }}</span>
              <span class="truncate">{{ opt.target }}</span>
            </li>
          </ul>

          <!-- 错误信息 -->
          <p v-if="error" class="text-destructive text-sm">{{ error }}</p>
        </div>

        <!-- Footer -->
        <div
          class="flex items-center justify-between px-8 py-5 bg-muted/50 border-t border-border flex-shrink-0"
        >
          <span v-if="selectedCount > 0" class="text-xs text-muted-foreground">
            将回滚 {{ selectedCount }} 个文件
          </span>
          <span v-else />

          <div class="flex items-center gap-3">
            <button
              class="px-6 py-2.5 rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
              @click="emit('dismiss')"
              :disabled="loading"
            >
              保持当前状态
            </button>
            <button
              class="px-6 py-2.5 rounded-xl text-sm font-medium bg-primary text-white hover:bg-primary-hover transition-all shadow-lg shadow-primary/20 disabled:opacity-50"
              @click="handleConfirm"
              :disabled="loading || selectedCount === 0"
            >
              {{ loading ? '回滚中...' : selectedCount > 0 ? `回滚 ${selectedCount} 个文件` : '回滚' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, watch, reactive } from 'vue'
import { RotateCcw, X, Loader2, Pencil, Trash2, Check } from 'lucide-vue-next'
import type { RollbackFilePreview, RollbackPreview } from '@/api/session'

interface RollbackOption {
  id: string
  action: string
  target: string
}

const props = defineProps<{
  show: boolean
  options?: RollbackOption[]
  error?: string
  loading?: boolean
  reason?: string
  preview?: {
    previewLoading?: boolean
  } & Partial<RollbackPreview> | null
}>()

const emit = defineEmits<{
  (e: 'confirm', selectedFiles?: string[]): void
  (e: 'dismiss'): void
  (e: 'load-preview'): void
}>()

// ==================== 文件选择状态 ====================

/** 用户手动切换过的选择状态 (path → selected) */
const selectionOverrides = reactive<Record<string, boolean>>({})

/** 合并后的预览文件列表 (preview 数据 + 用户选择覆盖) */
const previewFiles = computed(() => {
  const files = props.preview?.files
  if (!files) return []
  return files.map((f) => ({
    ...f,
    selected: selectionOverrides[f.path] ?? f.selected,
  }))
})

const previewSummary = computed(() => {
  return props.preview?.summary ?? { total: 0, modified: 0, deleted: 0, unchanged: 0 }
})

/** 可选中的文件数量 (排除 unchanged) */
const selectableCount = computed(() =>
  previewFiles.value.filter((f) => f.status !== 'unchanged').length
)

/** 已选中的文件数量 */
const selectedCount = computed(() =>
  previewFiles.value.filter((f) => f.selected).length
)

/** 所有可选文件是否全选 */
const allSelected = computed(() =>
  selectableCount.value > 0 &&
  previewFiles.value.filter((f) => f.status !== 'unchanged').every((f) => f.selected)
)

/** 切换单个文件选中状态 */
function toggleFile(path: string): void {
  const file = previewFiles.value.find((f) => f.path === path)
  if (file) {
    selectionOverrides[path] = !file.selected
  }
}

/** 全选 / 取消全选 */
function toggleSelectAll(): void {
  const newState = !allSelected.value
  previewFiles.value.forEach((f) => {
    if (f.status !== 'unchanged') {
      selectionOverrides[f.path] = newState
    }
  })
}

/** 确认回滚 */
function handleConfirm(): void {
  // 有预览数据 → 选择性回滚
  if (previewFiles.value.length > 0) {
    const selected = previewFiles.value
      .filter((f) => f.selected)
      .map((f) => f.path)
    // 全选 → 传 undefined 走全量回滚（更高效）
    if (selected.length === selectableCount.value) {
      emit('confirm')
    } else {
      emit('confirm', selected)
    }
  } else {
    // 无预览 → 全量回滚（兼容旧逻辑）
    emit('confirm')
  }
}

// ==================== 工具函数 ====================

function shortenPath(fullPath: string): string {
  const parts = fullPath.replace(/\\/g, '/').split('/')
  if (parts.length <= 3) return fullPath
  return '.../' + parts.slice(-3).join('/')
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function statusLabel(status: string): string {
  switch (status) {
    case 'modified': return '已修改'
    case 'deleted': return '已删除'
    case 'unchanged': return '未变更'
    default: return status
  }
}

// ==================== 弹窗打开时自动加载预览 ====================

watch(
  () => props.show,
  (visible) => {
    if (visible) {
      // 重置选择覆盖
      Object.keys(selectionOverrides).forEach((k) => delete selectionOverrides[k])
      // 触发加载预览
      emit('load-preview')
    }
  }
)
</script>

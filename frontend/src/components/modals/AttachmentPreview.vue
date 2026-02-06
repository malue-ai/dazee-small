<template>
  <Teleport to="body">
    <div 
      v-if="show && file"
      class="fixed inset-0 bg-foreground/50 backdrop-blur-md z-50 flex items-center justify-center p-6 animate-in fade-in duration-300" 
      @click.self="emit('close')"
    >
      <div class="bg-white rounded-3xl shadow-2xl max-w-[90vw] max-h-[90vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-300 ring-1 ring-white/20">
        <!-- 头部 -->
        <div class="flex items-center justify-between px-6 py-4 border-b border-border bg-muted/50">
          <span class="font-semibold text-foreground truncate max-w-md">
            {{ file.file_name }}
          </span>
          <button 
            class="p-2 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground transition-colors" 
            @click="emit('close')"
          >
            <X class="w-5 h-5" />
          </button>
        </div>
        
        <!-- 内容区 -->
        <div class="p-8 flex items-center justify-center min-w-[400px] min-h-[300px] overflow-auto bg-muted/30">
          <!-- 图片预览 -->
          <img 
            v-if="isImage" 
            :src="previewUrl"
            :alt="file.file_name"
            class="max-w-full max-h-[75vh] object-contain rounded-xl shadow-lg border border-border"
            @error="handleImageError"
          />
          
          <!-- 其他文件 -->
          <div v-else class="text-center py-12">
            <div class="w-24 h-24 bg-muted rounded-3xl flex items-center justify-center mx-auto mb-6">
              <component :is="fileIconComponent" class="w-12 h-12 text-muted-foreground" />
            </div>
            <p class="text-xl font-bold text-foreground mb-2">{{ file.file_name }}</p>
            <p class="text-sm text-muted-foreground mb-8">
              {{ fileTypeLabel }} · {{ formattedFileSize }}
            </p>
            <a 
              :href="previewUrl" 
              target="_blank" 
              class="inline-flex items-center justify-center px-8 py-3 bg-primary text-primary-foreground rounded-xl font-medium hover:bg-primary-hover transition-all shadow-lg shadow-primary/20"
            >
              <Download class="w-4 h-4 mr-2" /> 下载 / 打开
            </a>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AttachedFile } from '@/types'
import { 
  isImageFile, 
  getFileTypeLabel as getLabel, 
  formatFileSize 
} from '@/utils'
import { 
  X, 
  Download, 
  FileText, 
  Image as ImageIcon, 
  FileCode, 
  FileSpreadsheet, 
  FileArchive, 
  Video, 
  Music, 
  File 
} from 'lucide-vue-next'

// ==================== Props ====================

interface Props {
  /** 是否显示 */
  show: boolean
  /** 文件信息 */
  file: AttachedFile | null
}

const props = defineProps<Props>()

// ==================== Emits ====================

const emit = defineEmits<{
  /** 关闭 */
  (e: 'close'): void
}>()

// ==================== State ====================

/** 图片加载失败 */
const imageError = ref(false)

// ==================== Computed ====================

/** 是否为图片 */
const isImage = computed(() => {
  if (!props.file) return false
  return isImageFile(props.file.file_type) && !imageError.value
})

/** 预览 URL */
const previewUrl = computed(() => {
  if (!props.file) return ''
  return props.file.file_url || props.file.preview_url || ''
})

/** 文件图标组件 */
const fileIconComponent = computed(() => {
  if (!props.file) return File
  
  const type = props.file.file_type?.toLowerCase() || ''
  
  if (type.startsWith('image/')) return ImageIcon
  if (type === 'application/pdf') return FileText
  if (type.includes('text/') || type.includes('json') || type.includes('markdown')) return FileText
  if (type.includes('javascript') || type.includes('typescript') || type.includes('python')) return FileCode
  if (type.includes('spreadsheet') || type.includes('excel') || type === 'text/csv') return FileSpreadsheet
  if (type.includes('zip') || type.includes('compressed') || type.includes('archive')) return FileArchive
  if (type.includes('video/')) return Video
  if (type.includes('audio/')) return Music
  
  return File
})

/** 文件类型标签 */
const fileTypeLabel = computed(() => {
  if (!props.file) return 'File'
  return getLabel(props.file.file_type)
})

/** 格式化的文件大小 */
const formattedFileSize = computed(() => {
  if (!props.file?.file_size) return '未知大小'
  return formatFileSize(props.file.file_size)
})

// ==================== Methods ====================

/**
 * 处理图片加载错误
 */
function handleImageError(): void {
  imageError.value = true
  console.error('图片加载失败:', previewUrl.value)
}
</script>

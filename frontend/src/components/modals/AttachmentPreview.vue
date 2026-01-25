<template>
  <Teleport to="body">
    <div 
      v-if="show && file"
      class="fixed inset-0 bg-gray-900/60 backdrop-blur-md z-50 flex items-center justify-center p-6 animate-in fade-in duration-300" 
      @click.self="emit('close')"
    >
      <div class="bg-white rounded-3xl shadow-2xl max-w-[90vw] max-h-[90vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-300 ring-1 ring-white/20">
        <!-- 头部 -->
        <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gray-50/50">
          <span class="font-semibold text-gray-800 truncate max-w-md">
            {{ file.file_name }}
          </span>
          <button 
            class="p-2 rounded-full text-gray-400 hover:bg-gray-200 hover:text-gray-900 transition-colors" 
            @click="emit('close')"
          >
            ✕
          </button>
        </div>
        
        <!-- 内容区 -->
        <div class="p-8 flex items-center justify-center min-w-[400px] min-h-[300px] overflow-auto bg-gray-50/30">
          <!-- 图片预览 -->
          <img 
            v-if="isImage" 
            :src="previewUrl"
            :alt="file.file_name"
            class="max-w-full max-h-[75vh] object-contain rounded-xl shadow-lg border border-gray-100"
            @error="handleImageError"
          />
          
          <!-- 其他文件 -->
          <div v-else class="text-center py-12">
            <div class="w-24 h-24 bg-gray-100 rounded-3xl flex items-center justify-center mx-auto mb-6">
              <span class="text-6xl">{{ fileIcon }}</span>
            </div>
            <p class="text-xl font-bold text-gray-900 mb-2">{{ file.file_name }}</p>
            <p class="text-sm text-gray-500 mb-8">
              {{ fileTypeLabel }} · {{ formattedFileSize }}
            </p>
            <a 
              :href="previewUrl" 
              target="_blank" 
              class="inline-flex items-center justify-center px-8 py-3 bg-gray-900 text-white rounded-xl font-medium hover:bg-gray-800 transition-all shadow-lg hover:shadow-gray-900/20"
            >
              📥 下载 / 打开
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
  getFileIcon as getIcon, 
  getFileTypeLabel as getLabel, 
  formatFileSize 
} from '@/utils'

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

/** 文件图标 */
const fileIcon = computed(() => {
  if (!props.file) return '📎'
  return getIcon(props.file.file_type)
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

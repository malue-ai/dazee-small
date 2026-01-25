<template>
  <div class="px-6 pb-6 pt-2 bg-transparent pointer-events-none sticky bottom-0 z-30">
    <div class="pointer-events-auto max-w-4xl mx-auto bg-white border border-gray-200 rounded-2xl p-3 shadow-lg transition-all duration-300 focus-within:shadow-xl focus-within:border-gray-300">
      <!-- 已选文件预览 -->
      <div v-if="selectedFiles.length > 0" class="flex flex-wrap gap-2 px-2 pb-3 border-b border-gray-100 mb-2">
        <div 
          v-for="(file, index) in selectedFiles" 
          :key="index" 
          class="flex items-center gap-2 pl-3 pr-2 py-1.5 bg-gray-50 rounded-lg text-xs font-medium text-gray-700 border border-gray-100 group"
        >
          <FileText class="w-4 h-4 text-gray-400" />
          <span class="max-w-[150px] truncate">{{ file.file_name }}</span>
          <button 
            class="p-0.5 rounded-md hover:bg-gray-200 text-gray-400 hover:text-red-500 transition-colors" 
            @click="emit('remove-file', index)"
          >
            <X class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      
      <div class="flex items-end gap-2">
        <!-- 文件上传按钮 -->
        <button 
          class="p-3 rounded-xl text-gray-400 hover:bg-gray-100 hover:text-gray-900 transition-colors flex-shrink-0" 
          @click="emit('upload-click')"
          :disabled="disabled || uploading"
          title="上传文件"
        >
          <Loader2 v-if="uploading" class="w-5 h-5 animate-spin" />
          <Paperclip v-else class="w-5 h-5" />
        </button>
        
        <!-- 文本输入框 -->
        <textarea
          ref="textareaRef"
          v-model="inputValue"
          @keydown.enter.exact="handleEnter"
          @compositionstart="isComposing = true"
          @compositionend="isComposing = false"
          @input="adjustHeight"
          placeholder="输入消息..."
          :disabled="disabled"
          rows="1"
          class="flex-1 max-h-[200px] py-3 bg-transparent border-none outline-none text-base text-gray-800 placeholder:text-gray-400 resize-none leading-relaxed"
        ></textarea>
        
        <div class="pb-1">
          <!-- 停止按钮 -->
          <button 
            v-if="loading" 
            class="p-3 rounded-xl bg-red-50 text-red-500 hover:bg-red-100 transition-all shadow-sm" 
            @click="emit('stop')"
            :disabled="stopping"
          >
            <Square class="w-5 h-5" />
          </button>
          <!-- 发送按钮 -->
          <button 
            v-else 
            class="p-3 rounded-xl transition-all shadow-sm flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none" 
            :class="canSend ? 'bg-gray-900 text-white hover:bg-gray-800 hover:shadow-lg' : 'bg-gray-100 text-gray-400 cursor-not-allowed'"
            @click="handleSend"
            :disabled="!canSend"
          >
            <ArrowUp class="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
    <div class="text-center mt-2">
      <p class="text-[10px] text-gray-400">AI 可能生成错误信息，请核对重要事实。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import type { AttachedFile } from '@/types'
import { FileText, X, Loader2, Paperclip, Square, ArrowUp } from 'lucide-vue-next'

// ==================== Props ====================

interface Props {
  /** 输入值 */
  modelValue: string
  /** 已选择的文件 */
  selectedFiles?: AttachedFile[]
  /** 是否正在加载 */
  loading?: boolean
  /** 是否正在停止 */
  stopping?: boolean
  /** 是否正在上传 */
  uploading?: boolean
  /** 是否禁用 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  selectedFiles: () => [],
  loading: false,
  stopping: false,
  uploading: false,
  disabled: false
})

// ==================== Emits ====================

const emit = defineEmits<{
  /** 更新输入值 */
  (e: 'update:modelValue', value: string): void
  /** 发送消息 */
  (e: 'send'): void
  /** 停止生成 */
  (e: 'stop'): void
  /** 点击上传按钮 */
  (e: 'upload-click'): void
  /** 移除文件 */
  (e: 'remove-file', index: number): void
}>()

// ==================== State ====================

/** 文本框引用 */
const textareaRef = ref<HTMLTextAreaElement | null>(null)

/** 是否正在输入法组合 */
const isComposing = ref(false)

// ==================== Computed ====================

/** 输入值（双向绑定） */
const inputValue = computed({
  get: () => props.modelValue,
  set: (value: string) => emit('update:modelValue', value)
})

/** 是否可以发送 */
const canSend = computed(() => {
  return (inputValue.value.trim().length > 0 || props.selectedFiles.length > 0) && !props.disabled
})

// ==================== Methods ====================

/**
 * 调整文本框高度
 */
function adjustHeight(): void {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
    textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 150) + 'px'
  }
}

/**
 * 处理回车键
 */
function handleEnter(event: KeyboardEvent): void {
  if (isComposing.value) return
  event.preventDefault()
  handleSend()
}

/**
 * 处理发送
 */
function handleSend(): void {
  if (canSend.value) {
    emit('send')
    // 重置高度
    nextTick(() => {
      if (textareaRef.value) {
        textareaRef.value.style.height = 'auto'
      }
    })
  }
}

/**
 * 聚焦输入框
 */
function focus(): void {
  textareaRef.value?.focus()
}

/**
 * 设置输入值
 */
function setInput(text: string): void {
  inputValue.value = text
  nextTick(() => {
    adjustHeight()
    focus()
  })
}

// ==================== Watchers ====================

// 监听输入值变化，调整高度
watch(inputValue, () => {
  nextTick(adjustHeight)
})

// ==================== Expose ====================

defineExpose({
  focus,
  setInput
})
</script>

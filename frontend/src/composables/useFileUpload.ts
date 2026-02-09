/**
 * 文件上传 Composable
 * 负责文件选择、上传、预览
 */

import { ref, computed } from 'vue'
import type { AttachedFile } from '@/types'
import { getFileIcon, isImageFile as checkIsImage } from '@/utils'

/**
 * 文件上传 Composable
 */
export function useFileUpload() {
  // ==================== 状态 ====================

  /** 已选择的文件列表 */
  const selectedFiles = ref<AttachedFile[]>([])

  /** 是否正在上传 */
  const isUploading = ref(false)

  /** 上传进度（0-100） */
  const uploadProgress = ref(0)

  /** 文件输入元素引用 */
  const fileInputRef = ref<HTMLInputElement | null>(null)

  /** 正在预览的附件 */
  const previewingAttachment = ref<AttachedFile | null>(null)

  // ==================== 计算属性 ====================

  /** 是否有已选择的文件 */
  const hasSelectedFiles = computed(() => selectedFiles.value.length > 0)

  /** 已选择文件数量 */
  const selectedFilesCount = computed(() => selectedFiles.value.length)

  // ==================== 方法 ====================

  /**
   * 触发文件选择
   */
  function triggerFileSelect(): void {
    if (fileInputRef.value) {
      fileInputRef.value.click()
    }
  }

  /**
   * 处理文件选择
   * @param event - 文件选择事件
   */
  async function handleFileSelect(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement
    const files = input.files

    if (!files || files.length === 0) return

    isUploading.value = true
    uploadProgress.value = 0

    try {
      const totalFiles = files.length
      let uploadedCount = 0

      for (const file of Array.from(files)) {
        const result = await uploadFile(file)

        if (result) {
          selectedFiles.value.push(result)
        }

        uploadedCount++
        uploadProgress.value = Math.round((uploadedCount / totalFiles) * 100)
      }
    } catch (error) {
      console.error('文件上传失败:', error)
      throw error
    } finally {
      isUploading.value = false
      uploadProgress.value = 0

      // 清空 input，允许重复选择同一文件
      if (fileInputRef.value) {
        fileInputRef.value.value = ''
      }
    }
  }

  /**
   * 上传单个文件
   * @param file - 文件对象
   */
  async function uploadFile(file: File): Promise<AttachedFile | null> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('user_id', 'local')

    try {
      const response = await fetch('/api/v1/files/upload', {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        throw new Error(`上传失败: ${response.status}`)
      }

      const result = await response.json()
      console.log('✅ 文件上传成功:', result.data)

      return {
        file_url: result.data.file_url,
        local_path: result.data.local_path,
        file_name: result.data.file_name || file.name,
        file_type: result.data.file_type || file.type,
        file_size: result.data.file_size || file.size
      }
    } catch (error) {
      console.error('❌ 文件上传失败:', error)
      throw error
    }
  }

  /**
   * 移除已选择的文件
   * @param index - 文件索引
   */
  function removeFile(index: number): void {
    selectedFiles.value.splice(index, 1)
  }

  /**
   * 清空所有已选择的文件
   */
  function clearFiles(): void {
    selectedFiles.value = []
  }

  /**
   * 获取文件图标
   * @param file - 文件信息
   */
  function getIcon(file: AttachedFile): string {
    return getFileIcon(file.file_type)
  }

  /**
   * 判断是否为图片文件
   * @param file - 文件信息
   */
  function isImageFile(file: AttachedFile): boolean {
    return checkIsImage(file.file_type)
  }

  /**
   * 打开附件预览
   * @param file - 文件信息
   */
  function openPreview(file: AttachedFile): void {
    console.log('📄 预览附件:', file)
    previewingAttachment.value = { ...file }
  }

  /**
   * 关闭附件预览
   */
  function closePreview(): void {
    previewingAttachment.value = null
  }

  /**
   * 获取文件预览 URL
   * @param file - 文件信息
   */
  function getPreviewUrl(file: AttachedFile): string {
    return file.file_url || file.preview_url || ''
  }

  /**
   * 设置文件输入元素引用
   * @param el - 元素引用
   */
  function setFileInputRef(el: HTMLInputElement | null): void {
    fileInputRef.value = el
  }

  return {
    // 状态
    selectedFiles,
    isUploading,
    uploadProgress,
    fileInputRef,
    previewingAttachment,

    // 计算属性
    hasSelectedFiles,
    selectedFilesCount,

    // 方法
    triggerFileSelect,
    handleFileSelect,
    uploadFile,
    removeFile,
    clearFiles,
    getIcon,
    isImageFile,
    openPreview,
    closePreview,
    getPreviewUrl,
    setFileInputRef
  }
}

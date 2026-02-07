/**
 * 知识库 Store
 * 负责管理知识库相关状态
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useKnowledgeStore = defineStore('knowledge', () => {
  // ==================== 状态 ====================

  /** 加载状态 */
  const isLoading = ref(false)

  // ==================== 方法 ====================

  /** 重置状态 */
  function reset(): void {
    isLoading.value = false
  }

  return {
    isLoading,
    reset
  }
})

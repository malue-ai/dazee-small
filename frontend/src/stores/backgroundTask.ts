/**
 * Background Task Store
 *
 * 后台任务状态管理，支持轮询刷新和实时进度更新。
 */

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import {
  getBackgroundTasks,
  cancelBackgroundTask as apiCancel,
  removeBackgroundTask as apiRemove,
  submitBackgroundTask as apiSubmit,
  type BackgroundTask,
  type ListBackgroundTasksParams,
  type SubmitBackgroundTaskResponse,
} from '@/api/backgroundTasks'

export type StatusFilter = 'all' | 'running' | 'completed' | 'failed' | 'cancelled'

export const useBackgroundTaskStore = defineStore('backgroundTask', () => {
  // ==================== State ====================

  const tasks = ref<BackgroundTask[]>([])
  const total = ref(0)
  const loading = ref(false)
  const statusFilter = ref<StatusFilter>('all')
  let pollTimer: ReturnType<typeof setInterval> | null = null

  // ==================== Getters ====================

  const filteredTasks = computed(() => tasks.value)
  const isEmpty = computed(() => !loading.value && tasks.value.length === 0)
  const hasRunning = computed(() => tasks.value.some(t => t.status === 'running' || t.status === 'queued'))

  // ==================== Actions ====================

  async function fetchTasks() {
    loading.value = true
    try {
      const params: ListBackgroundTasksParams = {}
      if (statusFilter.value !== 'all') {
        params.status = statusFilter.value
      }
      const result = await getBackgroundTasks(params)
      tasks.value = result.tasks
      total.value = result.total
    } catch (error) {
      console.warn('Failed to fetch background tasks:', error)
      tasks.value = []
      total.value = 0
    } finally {
      loading.value = false
    }
  }

  function setStatusFilter(filter: StatusFilter) {
    statusFilter.value = filter
    fetchTasks()
  }

  async function cancelTask(taskId: string): Promise<boolean> {
    try {
      await apiCancel(taskId)
      await fetchTasks()
      return true
    } catch (error) {
      console.warn('Failed to cancel task:', error)
      return false
    }
  }

  async function removeTask(taskId: string): Promise<boolean> {
    try {
      await apiRemove(taskId)
      await fetchTasks()
      return true
    } catch (error) {
      console.warn('Failed to remove task:', error)
      return false
    }
  }

  const submitting = ref(false)

  async function submitTask(prompt: string): Promise<SubmitBackgroundTaskResponse | null> {
    submitting.value = true
    try {
      const result = await apiSubmit({ prompt })
      await fetchTasks()
      startPolling(3000)
      return result
    } catch (error) {
      console.warn('Failed to submit background task:', error)
      return null
    } finally {
      submitting.value = false
    }
  }

  function updateTaskProgress(taskId: string, progress: number, message: string, status: string) {
    const task = tasks.value.find(t => t.task_id === taskId)
    if (task) {
      task.progress = progress
      task.progress_message = message
      task.status = status
    }
  }

  function startPolling(intervalMs = 3000) {
    stopPolling()
    fetchTasks()
    pollTimer = setInterval(() => {
      if (hasRunning.value) {
        fetchTasks()
      }
    }, intervalMs)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  return {
    tasks,
    total,
    loading,
    submitting,
    statusFilter,
    filteredTasks,
    isEmpty,
    hasRunning,
    fetchTasks,
    setStatusFilter,
    submitTask,
    cancelTask,
    removeTask,
    updateTaskProgress,
    startPolling,
    stopPolling,
  }
})

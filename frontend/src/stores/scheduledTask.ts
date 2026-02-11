/**
 * Scheduled Task Store
 *
 * Manages scheduled task list state and CRUD actions.
 */

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import {
  getScheduledTasks,
  pauseTask as apiPause,
  resumeTask as apiResume,
  cancelTask as apiCancel,
  deleteTask as apiDelete,
  type ScheduledTask,
  type ListTasksParams,
} from '@/api/scheduledTasks'

export type StatusFilter = 'all' | 'active' | 'paused' | 'completed' | 'cancelled'

export const useScheduledTaskStore = defineStore('scheduledTask', () => {
  // ==================== State ====================

  const tasks = ref<ScheduledTask[]>([])
  const total = ref(0)
  const loading = ref(false)
  const statusFilter = ref<StatusFilter>('all')
  const page = ref(1)
  const pageSize = ref(50)

  // ==================== Getters ====================

  const filteredTasks = computed(() => tasks.value)

  const isEmpty = computed(() => !loading.value && tasks.value.length === 0)

  // ==================== Actions ====================

  async function fetchTasks() {
    loading.value = true
    try {
      const params: ListTasksParams = {
        page: page.value,
        page_size: pageSize.value,
      }
      if (statusFilter.value !== 'all') {
        params.status = statusFilter.value
      }

      const result = await getScheduledTasks(params)
      tasks.value = result.tasks
      total.value = result.total
    } catch (error) {
      console.warn('Failed to fetch scheduled tasks:', error)
      tasks.value = []
      total.value = 0
    } finally {
      loading.value = false
    }
  }

  function setStatusFilter(filter: StatusFilter) {
    statusFilter.value = filter
    page.value = 1
    fetchTasks()
  }

  async function pauseTask(taskId: string): Promise<boolean> {
    try {
      await apiPause(taskId)
      await fetchTasks()
      return true
    } catch (error) {
      console.warn('Failed to pause task:', error)
      return false
    }
  }

  async function resumeTask(taskId: string): Promise<boolean> {
    try {
      await apiResume(taskId)
      await fetchTasks()
      return true
    } catch (error) {
      console.warn('Failed to resume task:', error)
      return false
    }
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

  async function deleteTask(taskId: string): Promise<boolean> {
    try {
      await apiDelete(taskId)
      await fetchTasks()
      return true
    } catch (error) {
      console.warn('Failed to delete task:', error)
      return false
    }
  }

  return {
    // State
    tasks,
    total,
    loading,
    statusFilter,
    page,
    pageSize,
    // Getters
    filteredTasks,
    isEmpty,
    // Actions
    fetchTasks,
    setStatusFilter,
    pauseTask,
    resumeTask,
    cancelTask,
    deleteTask,
  }
})

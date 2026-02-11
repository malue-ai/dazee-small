/**
 * Scheduled Tasks API
 */

import api from './index'

// ==================== Types ====================

export interface ScheduledTask {
  id: string
  user_id: string
  title: string
  description: string | null
  trigger_type: string          // once / cron / interval
  run_at: string | null         // ISO datetime
  cron_expr: string | null
  interval_seconds: number | null
  action: Record<string, unknown>
  status: string                // active / paused / completed / cancelled
  next_run_at: string | null
  last_run_at: string | null
  run_count: number
  created_at: string
  updated_at: string | null
  conversation_id: string | null
}

export interface ScheduledTaskListResponse {
  tasks: ScheduledTask[]
  total: number
  page: number
  page_size: number
}

export interface ListTasksParams {
  status?: string
  page?: number
  page_size?: number
  user_id?: string
}

// ==================== API Functions ====================

/**
 * List scheduled tasks with optional filters
 */
export async function getScheduledTasks(params?: ListTasksParams): Promise<ScheduledTaskListResponse> {
  const response = await api.get<ScheduledTaskListResponse>('/v1/scheduled-tasks', { params })
  return response.data
}

/**
 * Get a single task detail
 */
export async function getScheduledTask(taskId: string): Promise<ScheduledTask> {
  const response = await api.get<ScheduledTask>(`/v1/scheduled-tasks/${taskId}`)
  return response.data
}

/**
 * Pause an active task
 */
export async function pauseTask(taskId: string): Promise<ScheduledTask> {
  const response = await api.post<ScheduledTask>(`/v1/scheduled-tasks/${taskId}/pause`)
  return response.data
}

/**
 * Resume a paused task
 */
export async function resumeTask(taskId: string): Promise<ScheduledTask> {
  const response = await api.post<ScheduledTask>(`/v1/scheduled-tasks/${taskId}/resume`)
  return response.data
}

/**
 * Cancel a task (soft delete)
 */
export async function cancelTask(taskId: string): Promise<{ success: boolean; message: string }> {
  const response = await api.post<{ success: boolean; message: string }>(`/v1/scheduled-tasks/${taskId}/cancel`)
  return response.data
}

/**
 * Delete a task (hard delete)
 */
export async function deleteTask(taskId: string): Promise<{ success: boolean; message: string }> {
  const response = await api.delete<{ success: boolean; message: string }>(`/v1/scheduled-tasks/${taskId}`)
  return response.data
}

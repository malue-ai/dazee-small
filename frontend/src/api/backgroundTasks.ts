/**
 * Background Tasks API
 */

import api from './index'

// ==================== Types ====================

export interface BackgroundTask {
  task_id: string
  name: string
  description: string
  status: string            // queued / running / completed / failed / cancelled
  progress: number          // 0.0 ~ 1.0
  progress_message: string
  result_preview: string | null
  error: string | null
  elapsed_ms: number
  created_at: string
}

export interface BackgroundTaskListResponse {
  tasks: BackgroundTask[]
  total: number
}

export interface ListBackgroundTasksParams {
  status?: string
  user_id?: string
}

export interface SubmitBackgroundTaskParams {
  prompt: string
  user_id?: string
}

export interface SubmitBackgroundTaskResponse {
  task_id: string
  conversation_id: string
}

// ==================== API Functions ====================

export async function getBackgroundTasks(params?: ListBackgroundTasksParams): Promise<BackgroundTaskListResponse> {
  const response = await api.get<BackgroundTaskListResponse>('/v1/background-tasks', { params })
  return response.data
}

export async function getBackgroundTask(taskId: string): Promise<BackgroundTask> {
  const response = await api.get<BackgroundTask>(`/v1/background-tasks/${taskId}`)
  return response.data
}

export async function cancelBackgroundTask(taskId: string): Promise<{ success: boolean; message: string }> {
  const response = await api.post<{ success: boolean; message: string }>(`/v1/background-tasks/${taskId}/cancel`)
  return response.data
}

export async function removeBackgroundTask(taskId: string): Promise<{ success: boolean; message: string }> {
  const response = await api.delete<{ success: boolean; message: string }>(`/v1/background-tasks/${taskId}`)
  return response.data
}

export async function cleanupBackgroundTasks(maxAgeSeconds = 3600): Promise<{ success: boolean; removed: number }> {
  const response = await api.post<{ success: boolean; removed: number }>('/v1/background-tasks/cleanup', null, { params: { max_age_seconds: maxAgeSeconds } })
  return response.data
}

export async function submitBackgroundTask(params: SubmitBackgroundTaskParams): Promise<SubmitBackgroundTaskResponse> {
  const response = await api.post<SubmitBackgroundTaskResponse>('/v1/background-tasks/submit', params)
  return response.data
}

import api from './index'
import type {
  PlaybookEntry,
  PlaybookListResponse,
  PlaybookCreateRequest,
  PlaybookUpdateRequest,
} from '@/types'

export async function getPlaybooks(
  status?: string,
  source?: string
): Promise<PlaybookListResponse> {
  const params: Record<string, string> = {}
  if (status) params.status = status
  if (source) params.source = source
  const response = await api.get<PlaybookListResponse>('/v1/playbook', { params })
  return response.data
}

export async function getPlaybook(id: string): Promise<PlaybookEntry> {
  const response = await api.get<PlaybookEntry>(`/v1/playbook/${id}`)
  return response.data
}

export async function createPlaybook(data: PlaybookCreateRequest): Promise<PlaybookEntry> {
  const response = await api.post<PlaybookEntry>('/v1/playbook', data)
  return response.data
}

export async function updatePlaybook(id: string, data: PlaybookUpdateRequest): Promise<PlaybookEntry> {
  const response = await api.put<PlaybookEntry>(`/v1/playbook/${id}`, data)
  return response.data
}

export async function deletePlaybook(id: string): Promise<{ success: boolean; message: string }> {
  const response = await api.delete(`/v1/playbook/${id}`)
  return response.data
}

export async function playbookAction(
  playbookId: string,
  action: 'approve' | 'reject' | 'dismiss' | 'deprecate',
  notes?: string
): Promise<{ success: boolean; message: string; playbook_id: string }> {
  const response = await api.post(`/v1/playbook/${playbookId}/action`, {
    action,
    reviewer: 'user',
    notes: notes || undefined,
  })
  return response.data
}

export async function rebuildPlaybookIndex(): Promise<{ success: boolean; cleared: number; indexed: number }> {
  const response = await api.post('/v1/playbook/rebuild-index')
  return response.data
}

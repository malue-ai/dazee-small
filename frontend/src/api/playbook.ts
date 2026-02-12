/**
 * Playbook 策略库 API
 */

import api from './index'

/**
 * 对策略执行操作（approve / reject / dismiss）
 */
export async function playbookAction(
  playbookId: string,
  action: 'approve' | 'reject' | 'dismiss',
  notes?: string
): Promise<{ success: boolean; message: string; playbook_id: string }> {
  const response = await api.post(`/v1/playbook/${playbookId}/action`, {
    action,
    reviewer: 'user',
    notes: notes || undefined,
  })
  return response.data
}

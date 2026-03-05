export type PlaybookStatus = 'draft' | 'pending' | 'approved' | 'rejected' | 'deprecated'
export type PlaybookSource = 'auto' | 'manual' | 'import'

export interface PlaybookTrigger {
  task_types?: string[]
  complexity_range?: number[]
}

export interface PlaybookStrategy {
  execution_strategy?: string
  suggested_tools?: string[]
  max_turns?: number
}

export interface PlaybookToolStep {
  tool: string
  purpose?: string
  reward?: number
  is_critical?: boolean
}

export interface PlaybookQualityMetrics {
  avg_reward?: number
  success_rate?: number
  avg_turns?: number
}

export interface PlaybookEntry {
  id: string
  name: string
  description: string
  trigger: PlaybookTrigger
  strategy: PlaybookStrategy
  tool_sequence: PlaybookToolStep[]
  quality_metrics: PlaybookQualityMetrics
  status: PlaybookStatus
  source: PlaybookSource
  usage_count: number
  created_at: string
  updated_at: string
  reviewed_by?: string | null
  review_notes?: string | null
  last_used_at?: string | null
  is_stale: boolean
}

export interface PlaybookListResponse {
  success: boolean
  entries: PlaybookEntry[]
  stats: Record<string, unknown>
}

export interface PlaybookCreateRequest {
  name: string
  description: string
  trigger?: PlaybookTrigger
  strategy?: PlaybookStrategy
  tool_sequence?: PlaybookToolStep[]
  quality_metrics?: PlaybookQualityMetrics
}

export interface PlaybookUpdateRequest {
  name?: string
  description?: string
  trigger?: PlaybookTrigger
  strategy?: PlaybookStrategy
  tool_sequence?: PlaybookToolStep[]
}

/**
 * 设置 API
 * 
 * 管理桌面应用配置（API Keys、模型选择、知识库等）
 */

import api from '.'

export interface SettingsFieldMeta {
  label: string
  required: boolean
  secret: boolean
  default?: string
  type?: 'text' | 'toggle' | 'select'
  description?: string
  advanced?: boolean
  options?: Array<{ value: string; label: string; description?: string }>
}

export interface SettingsSchema {
  [group: string]: {
    [key: string]: SettingsFieldMeta
  }
}

export interface SettingsData {
  [group: string]: {
    [key: string]: string
  }
}

export interface SettingsStatus {
  configured: boolean
  missing: string[]
  configured_providers: string[]
  summary: {
    [group: string]: {
      configured: number
      total: number
    }
  }
}

export interface EmbeddingStatus {
  semantic_enabled: boolean
  current_provider: string | null
  provider_setting: string
  local_available: boolean
  local_backend: string
  model_downloaded: boolean
  openai_available: boolean
  local_install_hint: string
  local_model_name: string
  local_model_size: string
  local_model_description: string
  models_dir: string
  recommendation: string
}

/**
 * 获取当前配置（API Key 脱敏）
 */
export async function getSettings(): Promise<SettingsData> {
  const { data } = await api.get('/v1/settings')
  return data.data
}

/**
 * 更新配置
 */
export async function updateSettings(updates: SettingsData): Promise<SettingsData> {
  const { data } = await api.put('/v1/settings', updates)
  return data.data
}

/**
 * 检查配置状态
 */
export async function getSettingsStatus(): Promise<SettingsStatus> {
  const { data } = await api.get('/v1/settings/status')
  return data.data
}

/**
 * 获取配置 Schema
 */
export async function getSettingsSchema(): Promise<SettingsSchema> {
  const { data } = await api.get('/v1/settings/schema')
  return data.data
}

/**
 * 获取 Embedding 状态
 * 
 * 检测本地模型 / OpenAI 可用性，指导用户配置语义搜索
 */
export async function getEmbeddingStatus(): Promise<EmbeddingStatus> {
  const { data } = await api.get('/v1/settings/embedding-status')
  return data.data
}

export interface EmbeddingDownloadResult {
  success: boolean
  model_path?: string
  source?: string
  error?: string | null
}

export interface SemanticSearchSetupResult {
  success: boolean
  mode: string
  needs_download: boolean
  downloading: boolean
  download_result?: EmbeddingDownloadResult | null
  error?: string | null
}

export interface SemanticDownloadStatus {
  status: 'idle' | 'downloading' | 'done' | 'error'
  mode: string | null
  error: string | null
  source: string | null
  elapsed_seconds: number | null
}

/**
 * 一键配置语义搜索
 *
 * 选择 local 模式时，后端会启动后台下载任务并立即返回，
 * 前端通过 getSemanticDownloadStatus() 轮询下载进度。
 */
export async function setupSemanticSearch(mode: 'disabled' | 'local' | 'cloud'): Promise<SemanticSearchSetupResult> {
  const { data } = await api.post('/v1/settings/semantic-search/setup', { mode })
  return data.data
}

/**
 * 查询后台模型下载状态
 *
 * 前端轮询此接口跟踪下载进度，即使离开设置页再回来也能恢复状态。
 */
export async function getSemanticDownloadStatus(): Promise<SemanticDownloadStatus> {
  const { data } = await api.get('/v1/settings/semantic-search/download-status')
  return data.data
}

/**
 * 重置下载状态为 idle
 *
 * 前端确认完成/失败后调用，清理状态以便下次操作。
 */
export async function resetSemanticDownloadStatus(): Promise<void> {
  await api.post('/v1/settings/semantic-search/download-status/reset')
}

/**
 * 单独触发 embedding 模型下载
 *
 * 适用于：之前选了 disabled，现在想补装本地模型
 */
export async function downloadEmbeddingModel(): Promise<EmbeddingDownloadResult> {
  const { data } = await api.post('/v1/settings/embedding-model/download', null, {
    timeout: 600_000, // 模型下载可能需要几分钟
  })
  return data.data
}

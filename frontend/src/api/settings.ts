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
  openai_available: boolean
  local_install_hint: string
  local_model_name: string
  local_model_description: string
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

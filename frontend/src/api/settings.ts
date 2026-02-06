/**
 * 设置 API
 * 
 * 管理桌面应用配置（API Keys、模型选择等）
 */

import api from '.'

export interface SettingsSchema {
  [group: string]: {
    [key: string]: {
      label: string
      required: boolean
      secret: boolean
      default?: string
    }
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

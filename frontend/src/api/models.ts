/**
 * Models API — LLM Provider / 模型管理
 */

import api from './index'

// ==================== 类型定义 ====================

export interface ModelCapabilities {
  supports_tools: boolean
  supports_vision: boolean
  supports_thinking: boolean
  supports_audio: boolean
  supports_streaming: boolean
  max_tokens: number
  max_input_tokens?: number
}

export interface ModelInfo {
  model_name: string
  display_name: string
  provider: string
  model_type: string
  description?: string
  capabilities: ModelCapabilities
}

/** Provider 下的模型摘要 */
export interface ProviderModel {
  model_name: string
  display_name: string
  description?: string
  supports_thinking: boolean
  supports_vision: boolean
  max_tokens: number
}

/** Provider 详情（含关联模型和 Key 状态） */
export interface ProviderDetail {
  name: string
  display_name: string
  icon: string
  base_url: string
  api_key_env: string
  api_key_configured: boolean
  default_model: string
  description?: string
  models: ProviderModel[]
}

/** 验证通过后的单个模型详情（匹配目录后） */
export interface ValidatedModelInfo {
  model_name: string
  display_name: string
  provider: string
  model_type: string
  context_window?: number | null
  max_output_tokens: number
  supports_tools: boolean
  supports_vision: boolean
  supports_thinking: boolean
  in_catalog: boolean
}

/** API Key 验证结果 */
export interface ValidateKeyResult {
  valid: boolean
  provider: string
  message: string
  models: string[]
  model_details: ValidatedModelInfo[]
}

/** Provider 批量激活结果 */
export interface ProviderActivateResult {
  success: boolean
  provider: string
  activated_count: number
  models: string[]
  message: string
}

// ==================== API 方法 ====================

export const modelApi = {
  /** 获取模型列表 */
  listModels(type?: string, provider?: string) {
    return api.get<ModelInfo[]>('/v1/models', {
      params: { type, provider },
    })
  },

  /** 获取支持的 Provider 列表（含模型和 Key 状态） */
  async getSupportedProviders(): Promise<ProviderDetail[]> {
    const { data } = await api.get('/v1/models/providers/supported')
    return data as ProviderDetail[]
  },

  /** 验证 API Key */
  async validateKey(
    provider: string,
    apiKey: string,
    baseUrl?: string,
  ): Promise<ValidateKeyResult> {
    const { data } = await api.post(
      '/v1/models/providers/validate-key',
      {
        provider,
        api_key: apiKey,
        ...(baseUrl ? { base_url: baseUrl } : {}),
      },
    )
    return data as ValidateKeyResult
  },

  /** 按 Provider 批量激活模型 */
  async activateProvider(
    provider: string,
    apiKey: string,
    baseUrl?: string,
  ): Promise<ProviderActivateResult> {
    const { data } = await api.post(
      '/v1/models/providers/activate',
      {
        provider,
        api_key: apiKey,
        ...(baseUrl ? { base_url: baseUrl } : {}),
      },
    )
    return data as ProviderActivateResult
  },
}

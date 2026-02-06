import api from './index'

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

export const modelApi = {
  // 获取模型列表
  listModels(type?: string, provider?: string) {
    return api.get<ModelInfo[]>('/api/v1/models', {
      params: { type, provider }
    })
  }
}

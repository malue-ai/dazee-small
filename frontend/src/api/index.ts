/**
 * API 客户端
 * 
 * 自动适配两种运行模式：
 * - Tauri 桌面应用：从 Rust 侧获取后端地址（localhost:18900）
 * - 浏览器开发模式：使用 Vite proxy（/api）
 */

import axios from 'axios'
import { invoke } from '@tauri-apps/api/core'
import { isTauriEnv } from './tauri'

// 后端基础 URL（运行时初始化）
let _baseUrl: string = '/api'
let _initialized = false

/**
 * 初始化 API 基础 URL
 * 
 * Tauri 模式下从 Rust 获取动态后端地址
 */
export async function initApiBaseUrl(): Promise<string> {
  if (_initialized) return _baseUrl

  if (isTauriEnv()) {
    try {
      _baseUrl = await invoke<string>('get_backend_url')
      console.log('[API] Tauri 模式，后端地址:', _baseUrl)
    } catch (e) {
      console.warn('[API] 获取后端地址失败，使用默认值:', e)
      _baseUrl = 'http://localhost:18900/api'
    }
  } else {
    _baseUrl = import.meta.env.VITE_API_BASE_URL || '/api'
    console.log('[API] 浏览器模式，后端地址:', _baseUrl)
  }

  // 更新 axios 实例
  api.defaults.baseURL = _baseUrl
  _initialized = true
  return _baseUrl
}

/**
 * 获取当前 API 基础 URL
 */
export function getApiBaseUrl(): string {
  return _baseUrl
}

/**
 * 获取完整的 API URL（供 fetch/SSE 使用）
 */
export function getFullApiUrl(path: string): string {
  // 如果 baseUrl 是绝对地址（http://localhost:18900/api），直接拼接
  if (_baseUrl.startsWith('http')) {
    return `${_baseUrl}${path}`
  }
  // 相对地址（/api），直接拼接
  return `${_baseUrl}${path}`
}

// 创建 axios 实例
const api = axios.create({
  baseURL: _baseUrl,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    console.error('响应错误:', error)
    
    if (error.response) {
      switch (error.response.status) {
        case 403:
          console.error('拒绝访问')
          break
        case 404:
          console.error('请求的资源不存在')
          break
        case 500:
          console.error('服务器错误')
          break
        default:
          console.error('请求失败:', error.response.data.message || '未知错误')
      }
    }
    
    return Promise.reject(error)
  }
)

export default api

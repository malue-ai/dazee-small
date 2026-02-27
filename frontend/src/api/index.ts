/**
 * API 客户端
 * 
 * 自动适配两种运行模式：
 * - Tauri 桌面应用：从 Rust 侧获取后端地址（localhost:18900）
 * - 浏览器开发模式：使用 Vite proxy（/api）
 */

import axios from 'axios'
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { isTauriEnv } from './tauri'
import { apiLog, tauriLog } from '@/utils/logger'

// 后端基础 URL（运行时初始化）
let _baseUrl: string = '/api'
let _initialized = false

// 后端就绪状态（供其他模块查询）
let _backendReady = false
let _backendReadyResolve: (() => void) | null = null
const _backendReadyPromise = new Promise<void>((resolve) => {
  _backendReadyResolve = resolve
})

/**
 * 查询后端是否就绪
 */
export function isBackendReady(): boolean {
  return _backendReady
}

/**
 * 等待后端就绪（返回 Promise）
 * 
 * - Tauri 模式：等待 sidecar 启动完成
 * - 浏览器模式：立即 resolve
 */
export function waitForBackendReady(): Promise<void> {
  return _backendReadyPromise
}

/**
 * 在后台等待后端 sidecar 启动就绪（不阻塞 UI）
 * 
 * 同时使用事件监听 + 轮询两种方式，确保不遗漏
 */
function startBackendReadyWatcher(): void {
  tauriLog.info('后台等待后端 sidecar 启动...')

  let resolved = false

  const onReady = () => {
    if (resolved) return
    resolved = true
    _backendReady = true
    _backendReadyResolve?.()
    tauriLog.info('后端已就绪，可以正常使用')
  }

  const onFailed = (reason: string) => {
    if (resolved) return
    resolved = true
    // 即使失败也 resolve，让 UI 层自行处理
    _backendReadyResolve?.()
    tauriLog.error(`后端启动失败: ${reason}`)
  }

  // 方式 1: 监听 Rust 侧发出的 backend-ready 事件
  listen<boolean>('backend-ready', (event) => {
    if (event.payload) {
      onReady()
    } else {
      onFailed('后端启动失败（可能端口被占用或进程崩溃），请关闭后重试')
    }
  }).catch((err) => {
    tauriLog.error('监听 backend-ready 事件失败', err)
  })

  // 方式 2: 轮询健康检查（兜底，防止事件在监听前已发出）
  let attempts = 0
  const MAX_ATTEMPTS = 60  // 最多 2 分钟
  const pollInterval = setInterval(async () => {
    if (resolved) {
      clearInterval(pollInterval)
      return
    }
    attempts++
    try {
      const ready = await invoke<boolean>('is_backend_ready')
      if (ready) {
        clearInterval(pollInterval)
        onReady()
      } else if (attempts >= MAX_ATTEMPTS) {
        clearInterval(pollInterval)
        onFailed(`健康检查超时 (${MAX_ATTEMPTS * 2}s)`)
      }
    } catch {
      if (attempts >= MAX_ATTEMPTS) {
        clearInterval(pollInterval)
        onFailed(`健康检查超时 (${MAX_ATTEMPTS * 2}s)`)
      }
    }
  }, 2000)
}

/**
 * 初始化 API 基础 URL
 * 
 * Tauri 模式下从 Rust 获取动态后端地址，并等待 sidecar 就绪
 */
export async function initApiBaseUrl(): Promise<string> {
  if (_initialized) return _baseUrl

  // 诊断日志：记录 Tauri 环境检测细节
  const protocol = window?.location?.protocol || 'unknown'
  const hasTauriInternals = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
  const hasTauriGlobal = typeof window !== 'undefined' && '__TAURI__' in window
  const tauriDetected = isTauriEnv()

  apiLog.info('环境检测', {
    protocol,
    hasTauriInternals,
    hasTauriGlobal,
    tauriDetected,
    origin: window?.location?.origin || 'unknown',
  })

  if (tauriDetected) {
    try {
      _baseUrl = await invoke<string>('get_backend_url')
      tauriLog.info(`Tauri 模式，后端地址: ${_baseUrl}`)
    } catch (e) {
      tauriLog.error('获取后端地址失败，使用默认值', e)
      _baseUrl = 'http://localhost:18900/api'
    }

    // 在后台等待后端 sidecar 就绪（不阻塞 UI 渲染）
    startBackendReadyWatcher()
  } else {
    _baseUrl = import.meta.env.VITE_API_BASE_URL || '/api'
    apiLog.info(`浏览器模式，后端地址: ${_baseUrl}`)
    // 浏览器模式下后端已就绪（通过 Vite proxy 访问）
    _backendReady = true
    _backendReadyResolve?.()
  }

  // 更新 axios 实例
  api.defaults.baseURL = _baseUrl
  _initialized = true
  apiLog.info('API 初始化完成', { baseUrl: _baseUrl, mode: isTauriEnv() ? 'tauri' : 'browser' })
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
  return `${_baseUrl}${path}`
}

/**
 * 解析资源 URL：将后端返回的相对路径转为浏览器可访问的完整 URL
 * 
 * 开发模式下 Vite proxy 能代理 /api/... 请求，相对路径可以直接用。
 * 但 Tauri 打包后前端从 tauri://localhost 加载，必须拼接后端绝对地址。
 * 
 * @example
 *   resolveResourceUrl('/api/v1/files/xxx.pdf')
 *   // dev:   '/api/v1/files/xxx.pdf'
 *   // tauri: 'http://127.0.0.1:18900/api/v1/files/xxx.pdf'
 */
export function resolveResourceUrl(url: string): string {
  if (!url) return ''
  // 已经是绝对 URL，直接返回
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('data:')) return url
  // 后端返回的 /api/v1/... 相对路径 → 转为完整 URL
  if (url.startsWith('/api/')) {
    return `${_baseUrl}${url.slice(4)}` // strip '/api', _baseUrl 已包含 '/api'
  }
  // 其他相对路径（如 /v1/...），通过 baseUrl 拼接
  if (url.startsWith('/')) {
    return `${_baseUrl}${url}`
  }

  // 本地文件路径或 file:/// URL → 提取 instance + storage 相对路径，转为 API URL
  // Tauri webview 禁止加载 file:/// 协议，需通过后端 /api/v1/files/@instance/ 接口代理
  const normalized = url.replace(/^file:\/\/\//, '').replace(/\\/g, '/')
  const instanceMatch = normalized.match(/\/instances\/([^/]+)\/storage\/(.+)$/)
  if (instanceMatch) {
    const [, instance, relativePath] = instanceMatch
    return `${_baseUrl}/v1/files/@${instance}/${relativePath}`
  }

  return url
}

// 创建 axios 实例
const api = axios.create({
  baseURL: _baseUrl,
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    apiLog.debug(`→ ${config.method?.toUpperCase()} ${config.url}`, config.params || config.data)
    return config
  },
  (error) => {
    apiLog.error('请求拦截器错误', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    apiLog.debug(`← ${response.status} ${response.config.url}`, {
      status: response.status,
      dataKeys: response.data ? Object.keys(response.data) : null,
    })
    return response
  },
  (error) => {
    const status = error.response?.status
    const url = error.config?.url || '未知'
    apiLog.error(`← ${status || 'NETWORK'} ${url}`, {
      status,
      message: error.response?.data?.message || error.message,
    })
    return Promise.reject(error)
  }
)

export default api

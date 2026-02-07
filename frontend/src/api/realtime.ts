/**
 * Realtime API 配置
 * 
 * 实时语音通信 WebSocket 端点
 */

import { isTauriEnv } from './tauri'
import { getApiBaseUrl } from '.'

const API_BASE = '/api/v1'

/**
 * 获取 WebSocket URL
 * 
 * Tauri 模式：ws://127.0.0.1:{port}/api/v1/...（port 从 get_backend_url 动态获取）
 * 浏览器模式：自动从 window.location 推导
 */
function getWsUrl(path: string): string {
  const baseUrl = getApiBaseUrl()

  if (baseUrl.startsWith('http')) {
    // 绝对地址（Tauri 模式）：http → ws
    const wsBase = baseUrl.replace(/^http/, 'ws')
    const relativePath = path.replace(/^\/api/, '')
    return `${wsBase}${relativePath}`
  }

  // 相对地址（浏览器开发模式）：用当前页面地址构造
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${path}`
}

/**
 * Realtime API 端点
 */
export const REALTIME_API = {
  /** 创建新的实时会话 WebSocket */
  WS: (params?: { model?: string; voice?: string; instructions?: string }) => {
    const searchParams = new URLSearchParams()
    if (params?.model) searchParams.set('model', params.model)
    if (params?.voice) searchParams.set('voice', params.voice)
    if (params?.instructions) searchParams.set('instructions', params.instructions)
    
    const query = searchParams.toString()
    return getWsUrl(`${API_BASE}/realtime/ws${query ? `?${query}` : ''}`)
  },
  
  /** 重连到已存在的会话 */
  WS_RECONNECT: (sessionId: string) => getWsUrl(`${API_BASE}/realtime/ws/${sessionId}`),
  
  /** 获取活跃会话列表 */
  SESSIONS: `${API_BASE}/realtime/sessions`,
  
  /** 关闭指定会话 */
  SESSION: (sessionId: string) => `${API_BASE}/realtime/sessions/${sessionId}`,
}

/**
 * 可用的语音类型
 */
export const VOICE_OPTIONS = [
  { value: 'alloy', label: 'Alloy', description: '中性、平衡' },
  { value: 'ash', label: 'Ash', description: '温暖、友好' },
  { value: 'ballad', label: 'Ballad', description: '柔和、舒缓' },
  { value: 'coral', label: 'Coral', description: '清晰、专业' },
  { value: 'echo', label: 'Echo', description: '深沉、稳重' },
  { value: 'sage', label: 'Sage', description: '智慧、沉稳' },
  { value: 'shimmer', label: 'Shimmer', description: '明亮、活泼' },
  { value: 'verse', label: 'Verse', description: '优雅、流畅' },
] as const

export type VoiceType = typeof VOICE_OPTIONS[number]['value']

/**
 * Realtime API 配置
 * 
 * 实时语音通信 WebSocket 端点
 */

const API_BASE = '/api/v1'

/**
 * 获取 WebSocket URL
 * 自动处理 http/https 到 ws/wss 的转换
 */
function getWsUrl(path: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return `${protocol}//${host}${path}`
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

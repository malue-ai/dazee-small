/**
 * Realtime API 类型定义
 * 
 * 实时语音通信相关类型
 */

import type { VoiceType } from '@/api/realtime'

/**
 * 实时会话状态
 */
export type RealtimeStatus = 'disconnected' | 'connecting' | 'connected' | 'error'

/**
 * 实时会话信息
 */
export interface RealtimeSession {
  id: string
  model: string
  voice: VoiceType
  connected: boolean
  createdAt: string
}

/**
 * 实时事件类型（常用）
 */
export type RealtimeEventType =
  // 会话事件
  | 'session.created'
  | 'session.updated'
  | 'session.reconnected'
  // 音频事件
  | 'input_audio_buffer.append'
  | 'input_audio_buffer.commit'
  | 'input_audio_buffer.clear'
  | 'input_audio_buffer.committed'
  | 'input_audio_buffer.cleared'
  | 'input_audio_buffer.speech_started'
  | 'input_audio_buffer.speech_stopped'
  // 响应事件
  | 'response.created'
  | 'response.audio.delta'
  | 'response.audio.done'
  | 'response.text.delta'
  | 'response.text.done'
  | 'response.audio_transcript.delta'
  | 'response.audio_transcript.done'
  | 'response.done'
  // 错误
  | 'error'

/**
 * 实时事件基础结构
 */
export interface RealtimeEvent {
  type: RealtimeEventType | string
  event_id?: string
  [key: string]: unknown
}

/**
 * 会话创建事件
 */
export interface SessionCreatedEvent extends RealtimeEvent {
  type: 'session.created' | 'session.reconnected'
  session: {
    id: string
    model: string
    voice: string
    created_at: string
  }
}

/**
 * 音频增量事件
 */
export interface AudioDeltaEvent extends RealtimeEvent {
  type: 'response.audio.delta'
  response_id: string
  item_id: string
  output_index: number
  content_index: number
  delta: string // Base64 音频数据
}

/**
 * 文本增量事件
 */
export interface TextDeltaEvent extends RealtimeEvent {
  type: 'response.text.delta'
  response_id: string
  item_id: string
  output_index: number
  content_index: number
  delta: string
}

/**
 * 转录增量事件
 */
export interface TranscriptDeltaEvent extends RealtimeEvent {
  type: 'response.audio_transcript.delta'
  response_id: string
  item_id: string
  output_index: number
  content_index: number
  delta: string
}

/**
 * 错误事件
 */
export interface ErrorEvent extends RealtimeEvent {
  type: 'error'
  error: {
    message: string
    code: string
  }
}

/**
 * 对话消息
 */
export interface RealtimeMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  isAudio?: boolean
}

/**
 * 实时配置选项
 */
export interface RealtimeOptions {
  model?: string
  voice?: VoiceType
  instructions?: string
}

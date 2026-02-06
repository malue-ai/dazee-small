/**
 * useRealtime - 实时语音通信 Composable
 * 
 * 提供与 OpenAI Realtime API 的 WebSocket 连接和音频处理
 */

import { ref, computed, onUnmounted } from 'vue'
import { REALTIME_API, type VoiceType } from '@/api/realtime'
import type {
  RealtimeStatus,
  RealtimeSession,
  RealtimeEvent,
  RealtimeMessage,
  RealtimeOptions,
  SessionCreatedEvent,
  AudioDeltaEvent,
  TextDeltaEvent,
  TranscriptDeltaEvent,
  ErrorEvent,
} from '@/types/realtime'

/**
 * 音频处理工具
 */
class AudioProcessor {
  private audioContext: AudioContext | null = null
  private audioQueue: Float32Array[] = []
  private isPlaying = false
  private nextPlayTime = 0

  constructor() {
    this.audioContext = new AudioContext({ sampleRate: 24000 })
  }

  /**
   * 解码 Base64 PCM16 音频数据并播放
   */
  async playAudioChunk(base64Audio: string): Promise<void> {
    if (!this.audioContext) return

    // 确保 AudioContext 处于运行状态
    if (this.audioContext.state === 'suspended') {
      await this.audioContext.resume()
    }

    // 解码 Base64 到 ArrayBuffer
    const binaryString = atob(base64Audio)
    const bytes = new Uint8Array(binaryString.length)
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i)
    }

    // PCM16 转 Float32
    const int16Array = new Int16Array(bytes.buffer)
    const float32Array = new Float32Array(int16Array.length)
    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / 32768
    }

    // 添加到播放队列
    this.audioQueue.push(float32Array)
    this.schedulePlayback()
  }

  /**
   * 调度音频播放
   */
  private schedulePlayback(): void {
    if (this.isPlaying || !this.audioContext || this.audioQueue.length === 0) return

    this.isPlaying = true
    const currentTime = this.audioContext.currentTime

    if (this.nextPlayTime < currentTime) {
      this.nextPlayTime = currentTime
    }

    while (this.audioQueue.length > 0) {
      const audioData = this.audioQueue.shift()!
      const buffer = this.audioContext.createBuffer(1, audioData.length, 24000)
      buffer.getChannelData(0).set(audioData)

      const source = this.audioContext.createBufferSource()
      source.buffer = buffer
      source.connect(this.audioContext.destination)
      source.start(this.nextPlayTime)

      this.nextPlayTime += buffer.duration
    }

    this.isPlaying = false
  }

  /**
   * 停止播放并清空队列
   */
  stop(): void {
    this.audioQueue = []
    this.nextPlayTime = 0
    this.isPlaying = false
  }

  /**
   * 销毁
   */
  destroy(): void {
    this.stop()
    if (this.audioContext) {
      this.audioContext.close()
      this.audioContext = null
    }
  }
}

/**
 * 麦克风录音器
 */
class MicrophoneRecorder {
  private mediaStream: MediaStream | null = null
  private audioContext: AudioContext | null = null
  private processor: ScriptProcessorNode | null = null
  private source: MediaStreamAudioSourceNode | null = null
  private onAudioData: ((base64: string) => void) | null = null

  /**
   * 开始录音
   */
  async start(onAudioData: (base64: string) => void): Promise<void> {
    this.onAudioData = onAudioData

    // 获取麦克风权限
    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: 24000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    })

    // 创建音频处理链
    this.audioContext = new AudioContext({ sampleRate: 24000 })
    this.source = this.audioContext.createMediaStreamSource(this.mediaStream)
    
    // 使用 ScriptProcessorNode（兼容性更好）
    this.processor = this.audioContext.createScriptProcessor(4096, 1, 1)
    
    this.processor.onaudioprocess = (event) => {
      const inputData = event.inputBuffer.getChannelData(0)
      
      // Float32 转 PCM16
      const pcm16 = new Int16Array(inputData.length)
      for (let i = 0; i < inputData.length; i++) {
        const s = Math.max(-1, Math.min(1, inputData[i]))
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
      }

      // 转 Base64
      const bytes = new Uint8Array(pcm16.buffer)
      let binary = ''
      for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i])
      }
      const base64 = btoa(binary)

      if (this.onAudioData) {
        this.onAudioData(base64)
      }
    }

    this.source.connect(this.processor)
    this.processor.connect(this.audioContext.destination)
  }

  /**
   * 停止录音
   */
  stop(): void {
    if (this.processor) {
      this.processor.disconnect()
      this.processor = null
    }
    if (this.source) {
      this.source.disconnect()
      this.source = null
    }
    if (this.audioContext) {
      this.audioContext.close()
      this.audioContext = null
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop())
      this.mediaStream = null
    }
    this.onAudioData = null
  }
}

/**
 * 实时语音通信 Composable
 */
export function useRealtime(options: RealtimeOptions = {}) {
  // ==================== State ====================
  
  const status = ref<RealtimeStatus>('disconnected')
  const session = ref<RealtimeSession | null>(null)
  const messages = ref<RealtimeMessage[]>([])
  const currentTranscript = ref('')
  const isRecording = ref(false)
  const isSpeaking = ref(false)
  const error = ref<string | null>(null)

  // 内部状态
  let ws: WebSocket | null = null
  let audioProcessor: AudioProcessor | null = null
  let micRecorder: MicrophoneRecorder | null = null
  let currentResponseText = ''

  // ==================== Computed ====================

  const isConnected = computed(() => status.value === 'connected')
  const canRecord = computed(() => isConnected.value && !isRecording.value)

  // ==================== WebSocket 事件处理 ====================

  /**
   * 处理 WebSocket 消息
   */
  function handleMessage(event: MessageEvent): void {
    try {
      const data: RealtimeEvent = JSON.parse(event.data)
      
      switch (data.type) {
        case 'session.created':
        case 'session.reconnected':
          handleSessionCreated(data as SessionCreatedEvent)
          break
          
        case 'response.audio.delta':
          handleAudioDelta(data as AudioDeltaEvent)
          break
          
        case 'response.text.delta':
          handleTextDelta(data as TextDeltaEvent)
          break
          
        case 'response.audio_transcript.delta':
          handleTranscriptDelta(data as TranscriptDeltaEvent)
          break
          
        case 'response.done':
          handleResponseDone()
          break
          
        case 'input_audio_buffer.speech_started':
          isSpeaking.value = true
          break
          
        case 'input_audio_buffer.speech_stopped':
          isSpeaking.value = false
          break
          
        case 'error':
          handleError(data as ErrorEvent)
          break
          
        default:
          console.log('📨 Realtime event:', data.type)
      }
    } catch (e) {
      console.error('解析 WebSocket 消息失败:', e)
    }
  }

  function handleSessionCreated(event: SessionCreatedEvent): void {
    session.value = {
      id: event.session.id,
      model: event.session.model,
      voice: event.session.voice as VoiceType,
      connected: true,
      createdAt: event.session.created_at,
    }
    status.value = 'connected'
    error.value = null
    console.log('✅ Realtime session created:', event.session.id)
  }

  function handleAudioDelta(event: AudioDeltaEvent): void {
    if (audioProcessor && event.delta) {
      audioProcessor.playAudioChunk(event.delta)
    }
  }

  function handleTextDelta(event: TextDeltaEvent): void {
    currentResponseText += event.delta
  }

  function handleTranscriptDelta(event: TranscriptDeltaEvent): void {
    currentTranscript.value += event.delta
  }

  function handleResponseDone(): void {
    // 保存助手消息
    if (currentResponseText || currentTranscript.value) {
      messages.value.push({
        id: `msg_${Date.now()}`,
        role: 'assistant',
        content: currentTranscript.value || currentResponseText,
        timestamp: new Date(),
        isAudio: !!currentTranscript.value,
      })
    }
    
    // 重置
    currentResponseText = ''
    currentTranscript.value = ''
  }

  function handleError(event: ErrorEvent): void {
    error.value = event.error.message
    console.error('❌ Realtime error:', event.error)
  }

  // ==================== Public Methods ====================

  /**
   * 连接到实时 API
   */
  async function connect(): Promise<void> {
    if (ws) {
      console.warn('已存在连接')
      return
    }

    status.value = 'connecting'
    error.value = null

    try {
      const url = REALTIME_API.WS({
        model: options.model,
        voice: options.voice,
        instructions: options.instructions,
      })

      ws = new WebSocket(url)
      audioProcessor = new AudioProcessor()

      ws.onopen = () => {
        console.log('🔗 WebSocket 已连接')
      }

      ws.onmessage = handleMessage

      ws.onerror = (e) => {
        console.error('WebSocket 错误:', e)
        error.value = '连接错误'
        status.value = 'error'
      }

      ws.onclose = (e) => {
        console.log('WebSocket 关闭:', e.code, e.reason)
        status.value = 'disconnected'
        session.value = null
        ws = null
      }
    } catch (e) {
      console.error('连接失败:', e)
      error.value = '连接失败'
      status.value = 'error'
    }
  }

  /**
   * 断开连接
   */
  function disconnect(): void {
    stopRecording()
    
    if (audioProcessor) {
      audioProcessor.destroy()
      audioProcessor = null
    }

    if (ws) {
      ws.close()
      ws = null
    }

    status.value = 'disconnected'
    session.value = null
  }

  /**
   * 发送文本消息
   */
  function sendText(text: string): void {
    if (!ws || status.value !== 'connected') {
      console.warn('未连接，无法发送消息')
      return
    }

    // 添加用户消息到列表
    messages.value.push({
      id: `msg_${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date(),
    })

    // 发送到服务器
    ws.send(JSON.stringify({ type: 'text', text }))
  }

  /**
   * 开始录音
   */
  async function startRecording(): Promise<void> {
    if (!ws || status.value !== 'connected') {
      console.warn('未连接，无法录音')
      return
    }

    if (isRecording.value) return

    try {
      micRecorder = new MicrophoneRecorder()
      await micRecorder.start((base64Audio) => {
        // 发送音频数据
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: 'input_audio_buffer.append',
            audio: base64Audio,
          }))
        }
      })

      isRecording.value = true
      console.log('🎤 开始录音')
    } catch (e) {
      console.error('启动录音失败:', e)
      error.value = '无法访问麦克风'
    }
  }

  /**
   * 停止录音
   */
  function stopRecording(): void {
    if (!isRecording.value) return

    if (micRecorder) {
      micRecorder.stop()
      micRecorder = null
    }

    // 提交音频缓冲区
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'input_audio_buffer.commit' }))
    }

    // 添加用户语音消息占位
    messages.value.push({
      id: `msg_${Date.now()}`,
      role: 'user',
      content: '[语音消息]',
      timestamp: new Date(),
      isAudio: true,
    })

    isRecording.value = false
    console.log('🎤 停止录音')
  }

  /**
   * 清空消息
   */
  function clearMessages(): void {
    messages.value = []
  }

  // ==================== Lifecycle ====================

  onUnmounted(() => {
    disconnect()
  })

  // ==================== Return ====================

  return {
    // State
    status,
    session,
    messages,
    currentTranscript,
    isRecording,
    isSpeaking,
    error,
    
    // Computed
    isConnected,
    canRecord,
    
    // Methods
    connect,
    disconnect,
    sendText,
    startRecording,
    stopRecording,
    clearMessages,
  }
}

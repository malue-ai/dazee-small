<template>
  <div class="realtime-voice flex flex-col h-full bg-gradient-to-b from-gray-50 to-white">
    <!-- 顶部状态栏 -->
    <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100">
      <div class="flex items-center gap-3">
        <div 
          class="w-3 h-3 rounded-full transition-colors"
          :class="statusColor"
        />
        <span class="text-sm font-medium text-gray-600">{{ statusText }}</span>
      </div>
      
      <!-- 语音选择 -->
      <select 
        v-model="selectedVoice"
        :disabled="isConnected"
        class="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
      >
        <option v-for="voice in voiceOptions" :key="voice.value" :value="voice.value">
          {{ voice.label }}
        </option>
      </select>
    </div>

    <!-- 消息列表 -->
    <div ref="messagesContainer" class="flex-1 overflow-y-auto p-6 space-y-4">
      <!-- 空状态 -->
      <div v-if="messages.length === 0" class="h-full flex flex-col items-center justify-center text-gray-400">
        <Mic class="w-16 h-16 mb-4 opacity-50" />
        <p class="text-lg font-medium">实时语音对话</p>
        <p class="text-sm mt-1">点击下方按钮开始对话</p>
      </div>

      <!-- 消息 -->
      <div 
        v-for="msg in messages" 
        :key="msg.id"
        class="flex"
        :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
      >
        <div 
          class="max-w-[80%] px-4 py-3 rounded-2xl"
          :class="msg.role === 'user' 
            ? 'bg-blue-500 text-white rounded-br-md' 
            : 'bg-white shadow-sm border border-gray-100 rounded-bl-md'"
        >
          <div class="flex items-start gap-2">
            <Volume2 v-if="msg.isAudio" class="w-4 h-4 mt-0.5 flex-shrink-0 opacity-60" />
            <p class="text-sm leading-relaxed">{{ msg.content }}</p>
          </div>
          <p 
            class="text-xs mt-1 opacity-60"
            :class="msg.role === 'user' ? 'text-right' : ''"
          >
            {{ formatTime(msg.timestamp) }}
          </p>
        </div>
      </div>

      <!-- 实时转录 -->
      <div v-if="currentTranscript" class="flex justify-start">
        <div class="max-w-[80%] px-4 py-3 rounded-2xl bg-gray-100 rounded-bl-md">
          <p class="text-sm text-gray-600 italic">{{ currentTranscript }}...</p>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="p-6 border-t border-gray-100 bg-white">
      <!-- 文本输入 -->
      <div class="flex gap-3 mb-4">
        <input
          v-model="textInput"
          type="text"
          placeholder="输入文字消息..."
          :disabled="!isConnected"
          class="flex-1 px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:bg-gray-50"
          @keyup.enter="handleSendText"
        />
        <button
          :disabled="!isConnected || !textInput.trim()"
          class="px-6 py-3 bg-blue-500 text-white rounded-xl font-medium hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          @click="handleSendText"
        >
          <Send class="w-5 h-5" />
        </button>
      </div>

      <!-- 控制按钮 -->
      <div class="flex items-center justify-center gap-4">
        <!-- 连接/断开按钮 -->
        <button
          v-if="!isConnected"
          :disabled="status === 'connecting'"
          class="flex items-center gap-2 px-6 py-3 bg-green-500 text-white rounded-xl font-medium hover:bg-green-600 disabled:opacity-50 transition-all"
          @click="handleConnect"
        >
          <Loader2 v-if="status === 'connecting'" class="w-5 h-5 animate-spin" />
          <Phone v-else class="w-5 h-5" />
          <span>{{ status === 'connecting' ? '连接中...' : '开始通话' }}</span>
        </button>

        <template v-else>
          <!-- 录音按钮 -->
          <button
            :class="[
              'relative w-20 h-20 rounded-full font-medium transition-all shadow-lg',
              isRecording 
                ? 'bg-red-500 hover:bg-red-600 scale-110' 
                : 'bg-blue-500 hover:bg-blue-600'
            ]"
            @mousedown="handleStartRecording"
            @mouseup="handleStopRecording"
            @mouseleave="handleStopRecording"
            @touchstart.prevent="handleStartRecording"
            @touchend.prevent="handleStopRecording"
          >
            <!-- 录音动画 -->
            <div 
              v-if="isRecording" 
              class="absolute inset-0 rounded-full bg-red-400 animate-ping opacity-75"
            />
            <Mic class="w-8 h-8 text-white relative z-10 mx-auto" />
          </button>

          <!-- 断开连接 -->
          <button
            class="flex items-center gap-2 px-6 py-3 bg-gray-100 text-gray-700 rounded-xl font-medium hover:bg-gray-200 transition-colors"
            @click="handleDisconnect"
          >
            <PhoneOff class="w-5 h-5" />
            <span>结束通话</span>
          </button>
        </template>
      </div>

      <!-- 提示文字 -->
      <p v-if="isConnected" class="text-center text-sm text-gray-400 mt-4">
        {{ isRecording ? '松开发送语音' : '按住说话，松开发送' }}
      </p>

      <!-- 说话检测指示 -->
      <div v-if="isSpeaking" class="flex items-center justify-center gap-2 mt-3">
        <div class="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
        <span class="text-sm text-green-600">检测到语音...</span>
      </div>

      <!-- 错误提示 -->
      <div v-if="error" class="mt-4 p-3 bg-red-50 border border-red-200 rounded-xl">
        <p class="text-sm text-red-600">{{ error }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { Mic, Phone, PhoneOff, Send, Volume2, Loader2 } from 'lucide-vue-next'
import { useRealtime } from '@/composables/useRealtime'
import { VOICE_OPTIONS, type VoiceType } from '@/api/realtime'

// ==================== Props ====================

interface Props {
  instructions?: string
}

const props = defineProps<Props>()

// ==================== State ====================

const selectedVoice = ref<VoiceType>('alloy')
const textInput = ref('')
const messagesContainer = ref<HTMLElement | null>(null)

// ==================== Composable ====================

const realtime = useRealtime({
  voice: selectedVoice.value,
  instructions: props.instructions,
})

const {
  status,
  messages,
  currentTranscript,
  isRecording,
  isSpeaking,
  error,
  isConnected,
  connect,
  disconnect,
  sendText,
  startRecording,
  stopRecording,
} = realtime

// ==================== Computed ====================

const voiceOptions = VOICE_OPTIONS

const statusColor = computed(() => {
  switch (status.value) {
    case 'connected': return 'bg-green-500'
    case 'connecting': return 'bg-yellow-500 animate-pulse'
    case 'error': return 'bg-red-500'
    default: return 'bg-gray-300'
  }
})

const statusText = computed(() => {
  switch (status.value) {
    case 'connected': return '已连接'
    case 'connecting': return '连接中...'
    case 'error': return '连接错误'
    default: return '未连接'
  }
})

// ==================== Methods ====================

async function handleConnect(): Promise<void> {
  await connect()
}

function handleDisconnect(): void {
  disconnect()
}

function handleSendText(): void {
  const text = textInput.value.trim()
  if (!text) return
  
  sendText(text)
  textInput.value = ''
}

function handleStartRecording(): void {
  startRecording()
}

function handleStopRecording(): void {
  if (isRecording.value) {
    stopRecording()
  }
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ==================== Watch ====================

// 自动滚动到底部
watch(
  () => messages.value.length,
  async () => {
    await nextTick()
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  }
)

// 实时转录时也滚动
watch(currentTranscript, async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
})
</script>

<style scoped>
/* 录音按钮动画 */
@keyframes pulse-ring {
  0% {
    transform: scale(1);
    opacity: 1;
  }
  100% {
    transform: scale(1.5);
    opacity: 0;
  }
}
</style>

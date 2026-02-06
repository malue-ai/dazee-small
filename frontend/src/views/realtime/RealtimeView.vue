<template>
  <div class="h-screen w-full flex bg-white">
    <!-- 左侧边栏 -->
    <div class="w-72 bg-gray-50 border-r border-gray-200 flex flex-col">
      <!-- Logo -->
      <div class="h-16 flex items-center px-6 border-b border-gray-200">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl flex items-center justify-center">
            <Headphones class="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 class="font-bold text-gray-900">实时语音</h1>
            <p class="text-xs text-gray-500">Realtime Voice</p>
          </div>
        </div>
      </div>

      <!-- 设置面板 -->
      <div class="flex-1 p-6 space-y-6 overflow-y-auto">
        <!-- 系统指令 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">
            系统指令
          </label>
          <textarea
            v-model="instructions"
            rows="4"
            placeholder="设置 AI 助手的行为和角色..."
            class="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <!-- 预设场景 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">
            预设场景
          </label>
          <div class="space-y-2">
            <button
              v-for="preset in presets"
              :key="preset.id"
              class="w-full p-3 text-left border border-gray-200 rounded-lg hover:border-blue-500 hover:bg-blue-50 transition-colors"
              :class="selectedPreset === preset.id ? 'border-blue-500 bg-blue-50' : ''"
              @click="selectPreset(preset)"
            >
              <div class="flex items-center gap-2">
                <component :is="preset.icon" class="w-4 h-4 text-gray-500" />
                <span class="text-sm font-medium text-gray-900">{{ preset.name }}</span>
              </div>
              <p class="text-xs text-gray-500 mt-1">{{ preset.description }}</p>
            </button>
          </div>
        </div>
      </div>

      <!-- 底部导航 -->
      <div class="p-4 border-t border-gray-200">
        <button
          class="w-full flex items-center gap-2 px-4 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
          @click="goBack"
        >
          <ArrowLeft class="w-4 h-4" />
          <span class="text-sm">返回聊天</span>
        </button>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="flex-1 flex flex-col">
      <RealtimeVoice :instructions="instructions" :key="voiceKey" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, markRaw } from 'vue'
import { useRouter } from 'vue-router'
import { Headphones, ArrowLeft, MessageSquare, Globe, BookOpen, Briefcase } from 'lucide-vue-next'
import RealtimeVoice from '@/components/realtime/RealtimeVoice.vue'

// ==================== Router ====================

const router = useRouter()

// ==================== State ====================

const instructions = ref('')
const selectedPreset = ref<string | null>(null)
const voiceKey = ref(0)

// ==================== Presets ====================

const presets = [
  {
    id: 'assistant',
    name: '智能助手',
    description: '通用对话助手，友好专业',
    icon: markRaw(MessageSquare),
    instructions: '你是一个友好、专业的 AI 助手。用简洁清晰的语言回答问题，保持对话自然流畅。',
  },
  {
    id: 'translator',
    name: '实时翻译',
    description: '中英文实时翻译',
    icon: markRaw(Globe),
    instructions: '你是一个实时翻译助手。用户说中文时，你翻译成英文；用户说英文时，你翻译成中文。只输出翻译结果，不要解释。',
  },
  {
    id: 'teacher',
    name: '语言老师',
    description: '英语口语练习',
    icon: markRaw(BookOpen),
    instructions: '你是一个英语口语老师。用英语与用户对话，如果用户有语法或发音错误，友好地指出并纠正。鼓励用户多说，保持对话轻松愉快。',
  },
  {
    id: 'interviewer',
    name: '面试官',
    description: '模拟面试练习',
    icon: markRaw(Briefcase),
    instructions: '你是一个专业的面试官。根据用户的背景进行模拟面试，提出专业问题，并在回答后给出建设性反馈。保持专业但友好的态度。',
  },
]

// ==================== Methods ====================

function selectPreset(preset: typeof presets[0]): void {
  selectedPreset.value = preset.id
  instructions.value = preset.instructions
  // 重新渲染组件以应用新的 instructions
  voiceKey.value++
}

function goBack(): void {
  router.push('/')
}
</script>

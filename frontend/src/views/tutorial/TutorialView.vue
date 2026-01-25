<template>
  <div class="h-full flex overflow-hidden bg-white">
    <!-- 左侧教程目录 -->
    <div class="w-[280px] flex-shrink-0 border-r border-gray-100 bg-gray-50 overflow-y-auto">
      <!-- 头部 -->
      <div class="p-4 border-b border-gray-100">
        <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2">
          <GraduationCap class="w-6 h-6 text-blue-500" />
          Agent 教程
        </h2>
        <p class="text-xs text-gray-500 mt-1">从零开始掌握 ZenFlux Agent</p>
      </div>

      <!-- 教程列表 -->
      <div class="p-3">
        <div
          v-for="(tutorial, tIndex) in tutorials"
          :key="tutorial.id"
          class="mb-4"
        >
          <!-- 教程标题 -->
          <div 
            class="flex items-center gap-2 px-3 py-2 text-sm font-semibold text-gray-700 cursor-pointer hover:bg-white rounded-lg transition-colors"
            @click="toggleTutorial(tutorial.id)"
          >
            <span class="text-lg">{{ tutorial.icon }}</span>
            <span class="flex-1">{{ tutorial.title }}</span>
            <span class="text-xs text-gray-400">{{ tutorial.totalDuration }}min</span>
            <ChevronDown v-if="expandedTutorials.includes(tutorial.id)" class="w-3 h-3 text-gray-400" />
            <ChevronRight v-else class="w-3 h-3 text-gray-400" />
          </div>

          <!-- 章节列表 -->
          <div 
            v-show="expandedTutorials.includes(tutorial.id)"
            class="ml-4 mt-1 space-y-0.5"
          >
            <div
              v-for="(chapter, cIndex) in tutorial.chapters"
              :key="chapter.id"
              @click="selectChapter(tutorial.id, chapter.id)"
              class="flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-all text-sm"
              :class="currentChapterId === chapter.id 
                ? 'bg-white shadow-sm text-blue-600 font-medium border border-gray-100' 
                : 'text-gray-600 hover:bg-white hover:text-gray-900'"
            >
              <div class="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0"
                :class="isChapterCompleted(chapter.id) 
                  ? 'bg-green-100 text-green-600' 
                  : currentChapterId === chapter.id 
                    ? 'bg-blue-100 text-blue-600' 
                    : 'bg-gray-200 text-gray-500'"
              >
                <Check v-if="isChapterCompleted(chapter.id)" class="w-3 h-3" />
                <span v-else>{{ cIndex + 1 }}</span>
              </div>
              <span class="flex-1 truncate">{{ chapter.title }}</span>
              <span class="text-[10px] text-gray-400">{{ chapter.duration }}m</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 进度统计 -->
      <div class="p-4 border-t border-gray-100 mt-auto bg-gray-50">
        <div class="flex items-center justify-between text-xs text-gray-500 mb-2">
          <span class="font-medium">学习进度</span>
          <span>{{ completedChapters.length }}/{{ totalChapters }}</span>
        </div>
        <div class="h-1.5 bg-gray-200 rounded-full overflow-hidden">
          <div 
            class="h-full bg-blue-500 transition-all duration-500 rounded-full"
            :style="{ width: progressPercent + '%' }"
          ></div>
        </div>
      </div>
    </div>

    <!-- 中间内容区 -->
    <div class="flex-1 flex flex-col overflow-hidden bg-white">
      <!-- 内容头部 -->
      <div class="h-16 flex items-center justify-between px-8 border-b border-gray-100 bg-white sticky top-0 z-10">
        <div v-if="currentChapter">
          <h1 class="text-lg font-bold text-gray-800">{{ currentChapter.title }}</h1>
          <p class="text-xs text-gray-500 mt-0.5 flex items-center gap-1">
            <Clock class="w-3 h-3" /> 预计 {{ currentChapter.duration }} 分钟
          </p>
        </div>
        <div v-else class="text-gray-400 text-sm">
          选择一个章节开始学习
        </div>

        <div class="flex items-center gap-2">
          <button 
            @click="prevChapter"
            :disabled="!hasPrevChapter"
            class="px-4 py-2 rounded-lg text-sm font-medium bg-white border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            ← 上一章
          </button>
          <button 
            @click="nextChapter"
            :disabled="!hasNextChapter"
            class="px-4 py-2 rounded-lg text-sm font-medium bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
          >
            下一章 →
          </button>
        </div>
      </div>

      <!-- 教程内容 -->
      <div class="flex-1 overflow-y-auto bg-gray-50/30">
        <!-- 未选择章节 -->
        <div v-if="!currentChapter" class="h-full flex flex-col items-center justify-center text-gray-400 p-8">
          <div class="w-24 h-24 bg-gray-50 rounded-3xl flex items-center justify-center mb-6 border border-gray-100">
            <BookOpen class="w-10 h-10 text-gray-300" />
          </div>
          <h2 class="text-xl font-bold text-gray-700 mb-2">欢迎学习 ZenFlux Agent</h2>
          <p class="text-sm text-center max-w-md mb-8 text-gray-500 leading-relaxed">
            通过交互式教程，你将学会如何创建和配置智能体、添加 Skills、使用知识库等核心功能。
          </p>
          <button 
            @click="startFirstChapter"
            class="px-8 py-3 bg-gray-900 text-white rounded-xl font-medium hover:bg-gray-800 transition-all shadow-lg shadow-gray-900/10 active:scale-95"
          >
            🚀 开始学习
          </button>
        </div>

        <!-- 章节内容 -->
        <div v-else class="max-w-4xl mx-auto p-8 pb-24">
          <!-- 步骤列表 -->
          <div class="space-y-8">
            <div
              v-for="(step, index) in currentChapter.steps"
              :key="step.id"
              class="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm transition-all duration-300"
              :class="{ 'ring-2 ring-blue-500/20 border-blue-200': currentStepId === step.id }"
            >
              <!-- 步骤标题 -->
              <div class="flex items-start gap-4 mb-4">
                <div 
                  class="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0 transition-colors"
                  :class="isStepCompleted(step.id) 
                    ? 'bg-green-100 text-green-600' 
                    : 'bg-blue-50 text-blue-600'"
                >
                  <Check v-if="isStepCompleted(step.id)" class="w-4 h-4" />
                  <span v-else>{{ index + 1 }}</span>
                </div>
                <div class="flex-1">
                  <h3 class="text-lg font-bold text-gray-800">{{ step.title }}</h3>
                </div>
              </div>

              <!-- 步骤内容 -->
              <div class="ml-12">
                <div class="prose prose-sm max-w-none text-gray-600 leading-relaxed whitespace-pre-wrap">{{ step.content }}</div>

                <!-- 提示 -->
                <div v-if="step.tip" class="mt-4 p-4 bg-blue-50/50 rounded-xl border border-blue-100 flex items-start gap-3">
                  <Lightbulb class="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
                  <p class="text-sm text-blue-700">{{ step.tip }}</p>
                </div>

                <!-- 警告 -->
                <div v-if="step.warning" class="mt-4 p-4 bg-yellow-50/50 rounded-xl border border-yellow-100 flex items-start gap-3">
                  <AlertTriangle class="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" />
                  <p class="text-sm text-yellow-700">{{ step.warning }}</p>
                </div>

                <!-- 代码块 -->
                <div v-if="step.code" class="mt-4 border border-gray-200 rounded-xl overflow-hidden shadow-sm">
                  <div class="flex items-center justify-between px-4 py-2 bg-gray-50 border-b border-gray-200">
                    <span class="text-xs text-gray-500 font-mono font-medium">{{ step.codeLanguage || 'yaml' }}</span>
                    <button 
                      @click="copyCode(step.code)"
                      class="text-xs text-gray-500 hover:text-gray-900 transition-colors flex items-center gap-1"
                    >
                      <Copy class="w-3 h-3" /> 复制
                    </button>
                  </div>
                  <pre class="p-4 bg-white overflow-x-auto text-sm font-mono text-gray-800 leading-relaxed">{{ step.code }}</pre>
                </div>

                <!-- 操作按钮 -->
                <div v-if="step.action" class="mt-6">
                  <button 
                    @click="handleAction(step.action)"
                    class="inline-flex items-center gap-2 px-5 py-2.5 bg-white border border-gray-200 text-gray-700 rounded-xl text-sm font-medium hover:bg-gray-50 hover:border-gray-300 transition-all shadow-sm group"
                  >
                    <span class="text-lg group-hover:scale-110 transition-transform">{{ getActionIcon(step.action.type) }}</span>
                    {{ step.action.label }}
                    <ArrowRight class="w-4 h-4 text-gray-400 group-hover:translate-x-1 transition-transform" />
                  </button>
                </div>

                <!-- 完成按钮 -->
                <div class="mt-6 pt-4 border-t border-gray-100 flex justify-end">
                  <button 
                    v-if="!isStepCompleted(step.id)"
                    @click="completeStep(step.id)"
                    class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-gray-500 hover:text-green-600 hover:bg-green-50 transition-all"
                  >
                    <Square class="w-4 h-4" /> 标记为已完成
                  </button>
                  <span v-else class="flex items-center gap-2 text-sm text-green-600 font-medium px-4 py-2 bg-green-50 rounded-lg">
                    <CheckSquare class="w-4 h-4" /> 已完成
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- 章节完成 -->
          <div v-if="isCurrentChapterCompleted" class="mt-12 p-8 bg-green-50 rounded-3xl border border-green-100 text-center animate-in fade-in zoom-in duration-500">
            <div class="w-16 h-16 bg-white rounded-full flex items-center justify-center mx-auto mb-4 shadow-sm text-3xl">🎉</div>
            <h3 class="text-xl font-bold text-green-800 mb-2">章节完成！</h3>
            <p class="text-sm text-green-600 mb-6">太棒了，你已掌握本章节的所有内容</p>
            <button 
              v-if="hasNextChapter"
              @click="nextChapter"
              class="px-8 py-3 bg-green-600 text-white rounded-xl font-medium hover:bg-green-700 transition-all shadow-lg shadow-green-600/20 active:scale-95"
            >
              继续下一章 →
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧实践面板（可折叠） -->
    <div 
      v-if="showPracticePanel"
      class="w-[400px] flex-shrink-0 border-l border-gray-200 bg-white shadow-xl z-20 flex flex-col"
    >
      <div class="h-16 flex items-center justify-between px-6 border-b border-gray-100">
        <h3 class="font-bold text-gray-800 flex items-center gap-2">
          <FlaskConical class="w-5 h-5 text-purple-500" />
          实践区
        </h3>
        <button 
          @click="showPracticePanel = false"
          class="p-2 rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
        >
          <X class="w-5 h-5" />
        </button>
      </div>
      
      <div class="flex-1 p-6 overflow-y-auto">
        <div class="bg-gray-50 rounded-xl border border-gray-200 p-5">
          <p class="text-sm text-gray-600 mb-4 font-medium">
            在这里尝试与 Agent 对话，测试你学到的内容。
          </p>
          <textarea 
            v-model="practiceInput"
            rows="4"
            placeholder="输入你想测试的 Prompt..."
            class="w-full px-4 py-3 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 mb-4 resize-none transition-all"
          ></textarea>
          <button 
            @click="sendPractice"
            class="w-full py-2.5 bg-gray-900 text-white rounded-xl text-sm font-medium hover:bg-gray-800 transition-all flex items-center justify-center gap-2"
          >
            发送到聊天 <ArrowRight class="w-4 h-4" />
          </button>
        </div>

        <!-- 快捷示例 -->
        <div class="mt-8">
          <h4 class="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3 px-1">快捷示例</h4>
          <div class="space-y-2">
            <button 
              v-for="example in practiceExamples"
              :key="example"
              @click="practiceInput = example"
              class="w-full text-left px-4 py-3 bg-white border border-gray-200 rounded-xl text-sm text-gray-600 hover:border-gray-300 hover:shadow-sm transition-all"
            >
              {{ example }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 实践面板开关按钮 -->
    <button 
      v-if="!showPracticePanel && currentChapter"
      @click="showPracticePanel = true"
      class="fixed right-6 bottom-6 px-5 py-3 bg-gray-900 text-white rounded-full shadow-lg hover:bg-gray-800 transition-all z-10 flex items-center gap-2 font-medium active:scale-95"
    >
      <FlaskConical class="w-5 h-5" /> 打开实践区
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { tutorials } from '@/data/tutorials'
import type { Tutorial, TutorialChapter, TutorialAction, TutorialActionType } from '@/types'
import { 
  GraduationCap, 
  ChevronDown, 
  ChevronRight, 
  Check, 
  Clock, 
  BookOpen, 
  Lightbulb, 
  AlertTriangle, 
  Copy, 
  ArrowRight, 
  Square, 
  CheckSquare, 
  FlaskConical, 
  X 
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()

// ==================== 状态 ====================

const expandedTutorials = ref<string[]>(['getting-started'])
const currentTutorialId = ref<string>('getting-started')
const currentChapterId = ref<string>('')
const currentStepId = ref<string>('')
const completedSteps = ref<string[]>([])
const completedChapters = ref<string[]>([])
const showPracticePanel = ref(false)
const practiceInput = ref('')

// ==================== 计算属性 ====================

const currentTutorial = computed(() => 
  tutorials.find(t => t.id === currentTutorialId.value) || null
)

const currentChapter = computed(() => {
  if (!currentTutorial.value || !currentChapterId.value) return null
  return currentTutorial.value.chapters.find(c => c.id === currentChapterId.value) || null
})

const totalChapters = computed(() => 
  tutorials.reduce((sum, t) => sum + t.chapters.length, 0)
)

const progressPercent = computed(() => 
  totalChapters.value > 0 ? (completedChapters.value.length / totalChapters.value) * 100 : 0
)

const isCurrentChapterCompleted = computed(() => {
  if (!currentChapter.value) return false
  return currentChapter.value.steps.every(s => completedSteps.value.includes(s.id))
})

const hasPrevChapter = computed(() => {
  if (!currentTutorial.value || !currentChapterId.value) return false
  const index = currentTutorial.value.chapters.findIndex(c => c.id === currentChapterId.value)
  return index > 0
})

const hasNextChapter = computed(() => {
  if (!currentTutorial.value || !currentChapterId.value) return false
  const index = currentTutorial.value.chapters.findIndex(c => c.id === currentChapterId.value)
  return index < currentTutorial.value.chapters.length - 1
})

const practiceExamples = [
  '帮我制作一个产品介绍 PPT',
  '搜索最新的 AI 技术趋势',
  '分析这份数据并生成报告',
  '创建一个任务计划'
]

// ==================== 方法 ====================

function toggleTutorial(tutorialId: string) {
  const index = expandedTutorials.value.indexOf(tutorialId)
  if (index === -1) {
    expandedTutorials.value.push(tutorialId)
  } else {
    expandedTutorials.value.splice(index, 1)
  }
}

function selectChapter(tutorialId: string, chapterId: string) {
  currentTutorialId.value = tutorialId
  currentChapterId.value = chapterId
  
  if (!expandedTutorials.value.includes(tutorialId)) {
    expandedTutorials.value.push(tutorialId)
  }
  
  // 设置第一个步骤为当前步骤
  const tutorial = tutorials.find(t => t.id === tutorialId)
  const chapter = tutorial?.chapters.find(c => c.id === chapterId)
  if (chapter && chapter.steps.length > 0) {
    currentStepId.value = chapter.steps[0].id
  }
}

function startFirstChapter() {
  if (tutorials.length > 0 && tutorials[0].chapters.length > 0) {
    selectChapter(tutorials[0].id, tutorials[0].chapters[0].id)
  }
}

function prevChapter() {
  if (!currentTutorial.value || !hasPrevChapter.value) return
  const index = currentTutorial.value.chapters.findIndex(c => c.id === currentChapterId.value)
  if (index > 0) {
    currentChapterId.value = currentTutorial.value.chapters[index - 1].id
  }
}

function nextChapter() {
  if (!currentTutorial.value || !hasNextChapter.value) return
  const index = currentTutorial.value.chapters.findIndex(c => c.id === currentChapterId.value)
  if (index < currentTutorial.value.chapters.length - 1) {
    currentChapterId.value = currentTutorial.value.chapters[index + 1].id
  }
}

function isChapterCompleted(chapterId: string): boolean {
  return completedChapters.value.includes(chapterId)
}

function isStepCompleted(stepId: string): boolean {
  return completedSteps.value.includes(stepId)
}

function completeStep(stepId: string) {
  if (!completedSteps.value.includes(stepId)) {
    completedSteps.value.push(stepId)
    
    // 检查是否完成当前章节
    if (currentChapter.value) {
      const allCompleted = currentChapter.value.steps.every(s => completedSteps.value.includes(s.id))
      if (allCompleted && !completedChapters.value.includes(currentChapterId.value)) {
        completedChapters.value.push(currentChapterId.value)
      }
    }
    
    // 保存进度到 localStorage
    saveProgress()
  }
}

function saveProgress() {
  localStorage.setItem('tutorial_completed_steps', JSON.stringify(completedSteps.value))
  localStorage.setItem('tutorial_completed_chapters', JSON.stringify(completedChapters.value))
}

function loadProgress() {
  const steps = localStorage.getItem('tutorial_completed_steps')
  const chapters = localStorage.getItem('tutorial_completed_chapters')
  if (steps) completedSteps.value = JSON.parse(steps)
  if (chapters) completedChapters.value = JSON.parse(chapters)
}

function copyCode(code: string) {
  navigator.clipboard.writeText(code)
  alert('代码已复制到剪贴板')
}

function getActionIcon(type: TutorialActionType): string {
  const icons: Record<TutorialActionType, string> = {
    try_prompt: '💬',
    create_agent: '🤖',
    add_skill: '🧩',
    navigate: '🔗',
    copy_code: '📋'
  }
  return icons[type] || '▶'
}

function handleAction(action: TutorialAction) {
  switch (action.type) {
    case 'try_prompt':
      if (action.prompt) {
        practiceInput.value = action.prompt
        showPracticePanel.value = true
      }
      break
    case 'navigate':
      if (action.path) {
        router.push(action.path)
      }
      break
    case 'copy_code':
      if (action.code) {
        copyCode(action.code)
      }
      break
    case 'create_agent':
      router.push('/agents/create')
      break
    case 'add_skill':
      router.push('/skills')
      break
  }
}

function sendPractice() {
  if (practiceInput.value.trim()) {
    // 保存到 sessionStorage，然后跳转到聊天页面
    sessionStorage.setItem('pending_message', practiceInput.value)
    router.push('/')
  }
}

// ==================== 生命周期 ====================

onMounted(() => {
  loadProgress()
  
  // 从路由参数加载章节
  const chapterId = route.params.chapterId as string
  if (chapterId) {
    // 查找章节所属的教程
    for (const tutorial of tutorials) {
      const chapter = tutorial.chapters.find(c => c.id === chapterId)
      if (chapter) {
        selectChapter(tutorial.id, chapterId)
        break
      }
    }
  }
})

// 监听路由变化
watch(() => route.params.chapterId, (newId) => {
  if (newId && typeof newId === 'string') {
    for (const tutorial of tutorials) {
      const chapter = tutorial.chapters.find(c => c.id === newId)
      if (chapter) {
        selectChapter(tutorial.id, newId)
        break
      }
    }
  }
})
</script>

<style scoped>
/* 样式已移除，使用 Tailwind Utility Classes */
</style>
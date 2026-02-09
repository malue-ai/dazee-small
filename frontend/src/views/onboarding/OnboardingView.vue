<script setup lang="ts">
/**
 * OnboardingView — 首次使用引导页
 *
 * 3 步引导流程：欢迎 → 配置 → 完成
 * 完成后标记 localStorage，不再显示
 */
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Sparkles, Settings, Rocket, ArrowRight, ArrowLeft, Check } from 'lucide-vue-next'

const router = useRouter()
const currentStep = ref(0)

interface Step {
  icon: any
  title: string
  subtitle: string
  description: string
}

const steps: Step[] = [
  {
    icon: Sparkles,
    title: '欢迎使用 ZenFlux',
    subtitle: '你的智能助手',
    description: '基于大语言模型的智能体框架，帮助你高效完成各种任务。支持多轮对话、工具调用和自动规划。',
  },
  {
    icon: Settings,
    title: '快速配置',
    subtitle: '几步即可开始',
    description: '进入设置页面，配置你的 API Key 和模型偏好。支持 Claude、GPT、Qwen 等多种模型。',
  },
  {
    icon: Rocket,
    title: '准备就绪',
    subtitle: '开始你的第一次对话',
    description: '一切就绪！你可以直接开始对话，或者探索知识库和技能管理功能。',
  },
]

const step = computed(() => steps[currentStep.value])
const isFirst = computed(() => currentStep.value === 0)
const isLast = computed(() => currentStep.value === steps.length - 1)

function next() {
  if (isLast.value) {
    complete()
  } else {
    currentStep.value++
  }
}

function prev() {
  if (!isFirst.value) {
    currentStep.value--
  }
}

function skip() {
  complete()
}

function complete() {
  localStorage.setItem('zenflux_onboarding_done', '1')
  router.replace('/')
}
</script>

<template>
  <div class="min-h-screen bg-white flex flex-col items-center justify-center px-6">
    <!-- 跳过按钮 -->
    <button
      v-if="!isLast"
      @click="skip"
      class="absolute top-6 right-6 text-sm text-muted-foreground hover:text-foreground transition-colors"
    >
      跳过
    </button>

    <!-- 内容区域 -->
    <div class="w-full max-w-md flex flex-col items-center text-center">
      <!-- 图标 -->
      <Transition name="step-slide" mode="out-in">
        <div
          :key="currentStep"
          class="w-20 h-20 rounded-3xl bg-primary/10 flex items-center justify-center mb-8"
        >
          <component :is="step.icon" class="w-10 h-10 text-primary" />
        </div>
      </Transition>

      <!-- 标题 -->
      <Transition name="step-slide" mode="out-in">
        <div :key="currentStep" class="mb-8">
          <h1 class="text-2xl font-bold text-foreground mb-2">
            {{ step.title }}
          </h1>
          <p class="text-sm text-muted-foreground mb-4">
            {{ step.subtitle }}
          </p>
          <p class="text-base text-muted-foreground leading-relaxed max-w-sm mx-auto">
            {{ step.description }}
          </p>
        </div>
      </Transition>

      <!-- 步骤指示器 -->
      <div class="flex items-center gap-2 mb-10">
        <div
          v-for="(_, i) in steps"
          :key="i"
          :class="[
            'h-1.5 rounded-full transition-all duration-300',
            i === currentStep
              ? 'w-8 bg-primary'
              : i < currentStep
                ? 'w-4 bg-primary/40'
                : 'w-4 bg-muted'
          ]"
        />
      </div>

      <!-- 操作按钮 -->
      <div class="flex items-center gap-3 w-full max-w-xs">
        <!-- 上一步 -->
        <button
          v-if="!isFirst"
          @click="prev"
          class="btn btn-secondary flex-1 gap-2"
        >
          <ArrowLeft class="w-4 h-4" />
          上一步
        </button>

        <!-- 下一步 / 开始使用 -->
        <button
          @click="next"
          :class="[
            'btn btn-primary flex-1 gap-2',
            isFirst ? 'w-full' : ''
          ]"
        >
          <template v-if="isLast">
            <Check class="w-4 h-4" />
            开始使用
          </template>
          <template v-else>
            下一步
            <ArrowRight class="w-4 h-4" />
          </template>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 步骤切换动画 */
.step-slide-enter-active,
.step-slide-leave-active {
  transition: all 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

.step-slide-enter-from {
  opacity: 0;
  transform: translateX(20px);
}

.step-slide-leave-to {
  opacity: 0;
  transform: translateX(-20px);
}
</style>

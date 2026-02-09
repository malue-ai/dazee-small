<template>
  <Teleport to="body">
    <div 
      v-if="show"
      class="fixed inset-0 bg-foreground/50 backdrop-blur-md z-50 flex items-center justify-center p-6 animate-in fade-in duration-300" 
      @click.self="emit('cancel')"
    >
      <div class="bg-card rounded-3xl shadow-2xl w-full max-w-lg max-h-[85vh] overflow-hidden animate-in slide-in-from-bottom-8 duration-300 ring-1 ring-white/20 flex flex-col">
        <!-- 头部 -->
        <div class="flex items-center justify-between px-8 py-5 border-b border-border bg-muted/50 flex-shrink-0">
          <span class="text-lg font-bold text-foreground flex items-center gap-2">
            <Handshake class="w-6 h-6 text-primary" />
            需要您的确认
          </span>
          <button 
            class="p-2 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground transition-colors" 
            @click="emit('cancel')"
          >
            ✕
          </button>
        </div>
        
        <!-- 内容区 -->
        <div class="p-8 space-y-6 overflow-y-auto flex-1">
          <!-- 问题内容 -->
          <div class="text-lg text-foreground font-medium leading-relaxed whitespace-pre-wrap">
            {{ request?.question }}
          </div>
          
          <!-- 描述 -->
          <div 
            v-if="request?.description" 
            class="text-sm text-muted-foreground bg-accent p-4 rounded-xl border border-primary/30 leading-relaxed"
          >
            {{ request.description }}
          </div>
          
          <!-- yes_no / single_choice 类型 -->
          <div v-if="isYesNoOrSingleChoice" class="flex flex-col gap-3">
            <label 
              v-for="option in request?.options" 
              :key="option" 
              class="flex items-center p-4 rounded-xl border-2 cursor-pointer transition-all hover:bg-muted"
              :class="selectedValue === option ? 'border-primary bg-accent ring-1 ring-primary/20' : 'border-border'"
            >
              <input 
                type="radio" 
                :value="option" 
                v-model="selectedValue"
                name="hitl-option"
                class="mr-4 accent-amber-500 w-5 h-5"
              />
              <span class="text-base font-medium text-foreground flex items-center gap-2">
                <template v-if="option === 'confirm'">
                  <CheckCircle2 class="w-4 h-4 text-success" /> 确认
                </template>
                <template v-else-if="option === 'cancel'">
                  <XCircle class="w-4 h-4 text-destructive" /> 取消
                </template>
                <span v-else>{{ option }}</span>
              </span>
            </label>
          </div>
          
          <!-- multiple_choice 类型 -->
          <div v-if="isMultipleChoice" class="flex flex-col gap-3">
            <label 
              v-for="option in request?.options" 
              :key="option" 
              class="flex items-center p-4 rounded-xl border-2 cursor-pointer transition-all hover:bg-muted"
              :class="selectedValues.includes(option) ? 'border-primary bg-accent ring-1 ring-primary/20' : 'border-border'"
            >
              <input 
                type="checkbox" 
                :value="option" 
                v-model="selectedValues"
                class="mr-4 accent-amber-500 w-5 h-5 rounded"
              />
              <span class="text-base font-medium text-foreground">{{ option }}</span>
            </label>
          </div>
          
          <!-- text_input 类型 -->
          <div v-if="isTextInput" class="w-full">
            <textarea 
              v-model="textValue" 
              placeholder="请输入您的回复..."
              rows="4"
              class="w-full px-4 py-3 bg-muted border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all resize-none text-foreground"
            ></textarea>
          </div>
          
          <!-- form 类型 -->
          <div v-if="isForm" class="space-y-5">
            <div v-for="question in request?.questions" :key="question.id" class="space-y-2">
              <!-- 问题标签 -->
              <label class="block text-sm font-medium text-foreground">
                {{ question.label }}
                <span v-if="question.required !== false" class="text-destructive">*</span>
              </label>
              
              <!-- 提示文字 -->
              <div v-if="question.hint" class="text-xs text-muted-foreground mb-2">
                {{ question.hint }}
              </div>
              
              <!-- 单选题 -->
              <div v-if="question.type === 'single_choice'" class="flex flex-col gap-2">
                <label 
                  v-for="option in question.options" 
                  :key="option" 
                  class="flex items-center p-3 rounded-lg border cursor-pointer transition-all hover:bg-muted"
                  :class="formData[question.id] === option ? 'border-primary bg-accent' : 'border-border'"
                >
                  <input 
                    type="radio" 
                    :value="option" 
                    v-model="formData[question.id]"
                    :name="`form-${question.id}`"
                    class="mr-3 accent-amber-500"
                  />
                  <span class="text-sm text-foreground">{{ option }}</span>
                </label>
              </div>
              
              <!-- 多选题 -->
              <div v-if="question.type === 'multiple_choice'" class="flex flex-col gap-2">
                <label 
                  v-for="option in question.options" 
                  :key="option" 
                  class="flex items-center p-3 rounded-lg border cursor-pointer transition-all hover:bg-muted"
                  :class="(formData[question.id] as string[] || []).includes(option) ? 'border-primary bg-accent' : 'border-border'"
                >
                  <input 
                    type="checkbox" 
                    :value="option" 
                    v-model="formData[question.id]"
                    class="mr-3 accent-amber-500 rounded"
                  />
                  <span class="text-sm text-foreground">{{ option }}</span>
                </label>
              </div>
              
              <!-- 文本输入 -->
              <div v-if="question.type === 'text_input'">
                <input 
                  v-model="formData[question.id]" 
                  :placeholder="question.hint || '请输入...'"
                  class="w-full px-4 py-2.5 bg-muted border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all text-sm text-foreground"
                />
              </div>
            </div>
          </div>
        </div>
        
        <!-- 底部按钮 -->
        <div class="flex items-center justify-end gap-4 px-8 py-5 bg-muted/50 border-t border-border flex-shrink-0">
          <button 
            class="px-6 py-2.5 rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors" 
            @click="emit('cancel')" 
            :disabled="submitting"
          >
            取消
          </button>
          <button 
            class="px-6 py-2.5 rounded-xl text-sm font-medium bg-primary text-white hover:bg-primary-hover transition-all shadow-lg shadow-primary/20 transform active:scale-95 disabled:opacity-50" 
            @click="handleSubmit" 
            :disabled="submitting"
          >
            {{ submitting ? '提交中...' : '提交' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Handshake, CheckCircle2, XCircle } from 'lucide-vue-next'
import type { HITLConfirmRequest, HITLFormQuestion, HITLResponse } from '@/types'

// ==================== Props ====================

interface Props {
  /** 是否显示 */
  show: boolean
  /** 确认请求数据 */
  request: HITLConfirmRequest | null
  /** 是否正在提交 */
  submitting?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  submitting: false
})

// ==================== Emits ====================

const emit = defineEmits<{
  /** 提交响应 */
  (e: 'submit', response: HITLResponse): void
  /** 取消 */
  (e: 'cancel'): void
}>()

// ==================== State ====================

/** 单选值 */
const selectedValue = ref<string>('')

/** 多选值 */
const selectedValues = ref<string[]>([])

/** 文本值 */
const textValue = ref('')

/** 表单数据 */
const formData = ref<Record<string, string | string[]>>({})

// ==================== Computed ====================

/** 确认类型 */
const confirmationType = computed(() => props.request?.confirmation_type || 'yes_no')

/** 是否为 yes_no 或 single_choice */
const isYesNoOrSingleChoice = computed(() => 
  ['yes_no', 'single_choice'].includes(confirmationType.value)
)

/** 是否为 multiple_choice */
const isMultipleChoice = computed(() => confirmationType.value === 'multiple_choice')

/** 是否为 text_input */
const isTextInput = computed(() => confirmationType.value === 'text_input')

/** 是否为 form */
const isForm = computed(() => confirmationType.value === 'form')

// ==================== Watchers ====================

// 监听 request 变化，重置状态
watch(() => props.request, (newRequest) => {
  if (newRequest) {
    initializeResponse(newRequest)
  }
}, { immediate: true })

// ==================== Methods ====================

/**
 * 初始化响应值
 */
function initializeResponse(request: HITLConfirmRequest): void {
  const type = request.confirmation_type

  if (type === 'yes_no' && request.options?.length) {
    selectedValue.value = request.options[0]
  } else if (type === 'single_choice' && request.options?.length) {
    selectedValue.value = (request.default_value as string) || request.options[0]
  } else if (type === 'multiple_choice') {
    selectedValues.value = (request.default_value as string[]) || []
  } else if (type === 'text_input') {
    textValue.value = (request.default_value as string) || ''
  } else if (type === 'form') {
    const data: Record<string, string | string[]> = {}
    if (request.questions) {
      request.questions.forEach((q: HITLFormQuestion) => {
        if (q.default !== undefined) {
          data[q.id] = q.default
        } else {
          // 如果没有设置 default
          if (q.type === 'multiple_choice') {
            data[q.id] = []
          } else if (q.type === 'single_choice' && q.options && q.options.length > 0) {
            // single_choice 默认选中第一个选项
            data[q.id] = q.options[0]
          } else {
            data[q.id] = ''
          }
        }
      })
    }
    formData.value = data
  }
}

/**
 * 处理提交
 */
function handleSubmit(): void {
  let response: HITLResponse

  if (isYesNoOrSingleChoice.value) {
    response = selectedValue.value
  } else if (isMultipleChoice.value) {
    response = selectedValues.value
  } else if (isTextInput.value) {
    response = textValue.value
  } else if (isForm.value) {
    response = formData.value
  } else {
    response = ''
  }

  emit('submit', response)
}
</script>

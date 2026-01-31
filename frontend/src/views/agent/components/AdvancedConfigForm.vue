<template>
  <div class="flex flex-col gap-6">
    <!-- LLM 配置 -->
    <div class="bg-white border border-gray-200 rounded-xl p-6">
      <div class="flex items-center gap-2 mb-4">
        <Brain class="w-5 h-5 text-gray-600" />
        <h3 class="text-sm font-semibold text-gray-900">LLM 参数</h3>
      </div>
      
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- Extended Thinking -->
        <label class="flex items-start gap-3 p-4 bg-gray-50 rounded-xl border border-gray-200 cursor-pointer hover:border-gray-300 transition-all group">
          <input 
            type="checkbox" 
            v-model="localConfig.llm.enable_thinking"
            class="mt-1 w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          >
          <div class="flex-1">
            <div class="text-sm font-medium text-gray-800 group-hover:text-gray-900 transition-colors">启用深度思考 (Extended Thinking)</div>
            <div class="text-xs text-gray-500 mt-1">让模型在回答前进行更深入的推理</div>
          </div>
        </label>

        <!-- Prompt Caching -->
        <label class="flex items-start gap-3 p-4 bg-gray-50 rounded-xl border border-gray-200 cursor-pointer hover:border-gray-300 transition-all group">
          <input 
            type="checkbox" 
            v-model="localConfig.llm.enable_caching"
            class="mt-1 w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          >
          <div class="flex-1">
            <div class="text-sm font-medium text-gray-800 group-hover:text-gray-900 transition-colors">启用提示词缓存</div>
            <div class="text-xs text-gray-500 mt-1">减少重复内容的 API 调用成本</div>
          </div>
        </label>
      </div>

      <!-- Thinking Budget -->
      <div v-if="localConfig.llm.enable_thinking" class="mt-4 animate-in slide-in-from-top-2">
        <div class="flex flex-col gap-2">
          <label class="text-sm font-medium text-gray-700">思考 Token 预算</label>
          <div class="flex items-center gap-4">
            <input 
              type="range"
              v-model.number="localConfig.llm.thinking_budget"
              min="1000"
              max="32000"
              step="1000"
              class="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
            >
            <span class="text-sm font-mono text-gray-600 w-20 text-right">{{ localConfig.llm.thinking_budget?.toLocaleString() }}</span>
          </div>
          <span class="text-xs text-gray-400">建议值：简单任务 4000-8000，复杂任务 10000-16000</span>
        </div>
      </div>

      <!-- Max Tokens -->
      <div class="mt-4">
        <div class="flex flex-col gap-2">
          <label class="text-sm font-medium text-gray-700">最大输出 Token</label>
          <div class="relative">
            <select 
              v-model.number="localConfig.llm.max_tokens"
              class="w-full pl-4 pr-10 py-2.5 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-gray-400 transition-all cursor-pointer appearance-none"
            >
              <option :value="4096">4,096 (快速响应)</option>
              <option :value="8192">8,192 (标准)</option>
              <option :value="16384">16,384 (推荐)</option>
              <option :value="32768">32,768 (长文本)</option>
              <option :value="65536">65,536 (最大)</option>
            </select>
            <ChevronDown class="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>
        </div>
      </div>
    </div>

    <!-- Memory 配置 -->
    <div class="bg-white border border-gray-200 rounded-xl p-6">
      <div class="flex items-center gap-2 mb-4">
        <Database class="w-5 h-5 text-gray-600" />
        <h3 class="text-sm font-semibold text-gray-900">记忆配置</h3>
      </div>
      
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- Mem0 Enable -->
        <label class="flex items-start gap-3 p-4 bg-gray-50 rounded-xl border border-gray-200 cursor-pointer hover:border-gray-300 transition-all group">
          <input 
            type="checkbox" 
            v-model="localConfig.memory.mem0_enabled"
            class="mt-1 w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          >
          <div class="flex-1">
            <div class="text-sm font-medium text-gray-800 group-hover:text-gray-900 transition-colors">启用用户记忆 (Mem0)</div>
            <div class="text-xs text-gray-500 mt-1">记住用户偏好和历史信息</div>
          </div>
        </label>

        <!-- Smart Retrieval -->
        <label class="flex items-start gap-3 p-4 bg-gray-50 rounded-xl border border-gray-200 cursor-pointer hover:border-gray-300 transition-all group">
          <input 
            type="checkbox" 
            v-model="localConfig.memory.smart_retrieval"
            class="mt-1 w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          >
          <div class="flex-1">
            <div class="text-sm font-medium text-gray-800 group-hover:text-gray-900 transition-colors">智能记忆检索</div>
            <div class="text-xs text-gray-500 mt-1">根据对话意图自动检索相关记忆</div>
          </div>
        </label>
      </div>

      <!-- Retention Policy -->
      <div class="mt-4">
        <div class="flex flex-col gap-2">
          <label class="text-sm font-medium text-gray-700">记忆保留策略</label>
          <div class="grid grid-cols-3 gap-3">
            <label 
              v-for="policy in retentionPolicies" 
              :key="policy.value"
              class="flex flex-col items-center gap-2 p-4 bg-gray-50 rounded-xl border cursor-pointer transition-all"
              :class="localConfig.memory.retention_policy === policy.value ? 'border-gray-900 bg-gray-100' : 'border-gray-200 hover:border-gray-300'"
            >
              <input 
                type="radio"
                :value="policy.value"
                v-model="localConfig.memory.retention_policy"
                class="sr-only"
              >
              <span class="text-lg">{{ policy.icon }}</span>
              <span class="text-sm font-medium text-gray-800">{{ policy.label }}</span>
              <span class="text-xs text-gray-500 text-center">{{ policy.description }}</span>
            </label>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import { Brain, Database, ChevronDown } from 'lucide-vue-next'

interface LLMConfig {
  enable_thinking?: boolean
  thinking_budget?: number
  max_tokens?: number
  enable_caching?: boolean
  temperature?: number
  top_p?: number
}

interface MemoryConfig {
  mem0_enabled?: boolean
  smart_retrieval?: boolean
  retention_policy?: string
}

interface AdvancedConfig {
  llm: LLMConfig
  memory: MemoryConfig
}

const props = defineProps<{
  modelValue: AdvancedConfig
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: AdvancedConfig): void
}>()

const localConfig = reactive<AdvancedConfig>({
  llm: {
    enable_thinking: props.modelValue.llm?.enable_thinking ?? false,
    thinking_budget: props.modelValue.llm?.thinking_budget ?? 8000,
    max_tokens: props.modelValue.llm?.max_tokens ?? 16384,
    enable_caching: props.modelValue.llm?.enable_caching ?? true,
  },
  memory: {
    mem0_enabled: props.modelValue.memory?.mem0_enabled ?? true,
    smart_retrieval: props.modelValue.memory?.smart_retrieval ?? true,
    retention_policy: props.modelValue.memory?.retention_policy ?? 'user',
  },
})

const retentionPolicies = [
  { value: 'session', label: '会话级', icon: '⏱️', description: '会话结束后清除' },
  { value: 'user', label: '用户级', icon: '👤', description: '跨会话保留' },
  { value: 'persistent', label: '持久化', icon: '💾', description: '永久保存' },
]

// 同步本地配置到父组件
watch(
  () => localConfig,
  (newValue) => {
    emit('update:modelValue', JSON.parse(JSON.stringify(newValue)))
  },
  { deep: true }
)

// 监听父组件传入的值变化
watch(
  () => props.modelValue,
  (newValue) => {
    if (newValue.llm) {
      Object.assign(localConfig.llm, newValue.llm)
    }
    if (newValue.memory) {
      Object.assign(localConfig.memory, newValue.memory)
    }
  },
  { deep: true }
)
</script>

<template>
  <div class="flex flex-col gap-6">
    <div class="text-center mb-2">
      <h2 class="text-xl font-semibold text-gray-900">选择一个模板开始</h2>
      <p class="text-sm text-gray-500 mt-1">选择预设模板快速配置，或从空白开始</p>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="flex justify-center py-12">
      <Loader2 class="w-8 h-8 animate-spin text-gray-400" />
    </div>

    <!-- 模板卡片 -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <!-- 空白模板 -->
      <div
        @click="selectTemplate(null)"
        class="group relative p-6 bg-white border-2 rounded-2xl cursor-pointer transition-all hover:shadow-lg"
        :class="selectedTemplateId === null ? 'border-gray-900 shadow-lg' : 'border-gray-200 hover:border-gray-300'"
      >
        <div class="flex flex-col items-center text-center gap-3">
          <div class="w-12 h-12 rounded-xl bg-gray-100 flex items-center justify-center text-2xl group-hover:bg-gray-200 transition-colors">
            📝
          </div>
          <div>
            <h3 class="font-semibold text-gray-900">从空白开始</h3>
            <p class="text-xs text-gray-500 mt-1">自定义所有配置项</p>
          </div>
        </div>
        <div 
          v-if="selectedTemplateId === null"
          class="absolute top-3 right-3 w-5 h-5 bg-gray-900 rounded-full flex items-center justify-center"
        >
          <Check class="w-3 h-3 text-white" />
        </div>
      </div>

      <!-- 预设模板 -->
      <div
        v-for="template in templates"
        :key="template.id"
        @click="selectTemplate(template)"
        class="group relative p-6 bg-white border-2 rounded-2xl cursor-pointer transition-all hover:shadow-lg"
        :class="selectedTemplateId === template.id ? 'border-gray-900 shadow-lg' : 'border-gray-200 hover:border-gray-300'"
      >
        <div class="flex flex-col items-center text-center gap-3">
          <div class="w-12 h-12 rounded-xl bg-gray-100 flex items-center justify-center text-2xl group-hover:bg-gray-200 transition-colors">
            {{ template.icon }}
          </div>
          <div>
            <h3 class="font-semibold text-gray-900">{{ template.name }}</h3>
            <p class="text-xs text-gray-500 mt-1 line-clamp-2">{{ template.description }}</p>
          </div>
        </div>
        <div 
          v-if="selectedTemplateId === template.id"
          class="absolute top-3 right-3 w-5 h-5 bg-gray-900 rounded-full flex items-center justify-center"
        >
          <Check class="w-3 h-3 text-white" />
        </div>
      </div>
    </div>

    <!-- 模板详情预览 -->
    <div v-if="selectedTemplate" class="bg-gray-50 rounded-xl p-4 border border-gray-200">
      <h4 class="text-sm font-medium text-gray-700 mb-3">{{ selectedTemplate.name }} 包含的配置：</h4>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full" :class="selectedTemplate.config.enabled_capabilities?.tavily_search ? 'bg-green-500' : 'bg-gray-300'"></span>
          <span class="text-gray-600">网络搜索</span>
        </div>
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full" :class="selectedTemplate.config.enabled_capabilities?.knowledge_search ? 'bg-green-500' : 'bg-gray-300'"></span>
          <span class="text-gray-600">知识库</span>
        </div>
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full" :class="selectedTemplate.config.enabled_capabilities?.sandbox_tools ? 'bg-green-500' : 'bg-gray-300'"></span>
          <span class="text-gray-600">代码沙盒</span>
        </div>
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full" :class="selectedTemplate.config.llm?.enable_thinking ? 'bg-green-500' : 'bg-gray-300'"></span>
          <span class="text-gray-600">深度思考</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Check, Loader2 } from 'lucide-vue-next'
import api from '@/api/index'

interface AgentTemplate {
  id: string
  name: string
  description: string
  icon: string
  config: {
    model?: string
    max_turns?: number
    plan_manager_enabled?: boolean
    enabled_capabilities?: Record<string, boolean>
    llm?: {
      enable_thinking?: boolean
      thinking_budget?: number
      max_tokens?: number
      enable_caching?: boolean
    }
    memory?: {
      mem0_enabled?: boolean
      smart_retrieval?: boolean
      retention_policy?: string
    }
  }
}

const emit = defineEmits<{
  (e: 'select', template: AgentTemplate | null): void
}>()

const loading = ref(false)
const templates = ref<AgentTemplate[]>([])
const selectedTemplateId = ref<string | null>(null)

const selectedTemplate = computed(() => {
  if (selectedTemplateId.value === null) return null
  return templates.value.find(t => t.id === selectedTemplateId.value) || null
})

const fetchTemplates = async () => {
  try {
    loading.value = true
    const response = await api.get('/v1/agents/templates')
    templates.value = response.data.templates || []
  } catch (error) {
    console.error('获取模板列表失败:', error)
    // 使用默认模板作为回退
    templates.value = []
  } finally {
    loading.value = false
  }
}

const selectTemplate = (template: AgentTemplate | null) => {
  selectedTemplateId.value = template?.id ?? null
  emit('select', template)
}

onMounted(() => {
  fetchTemplates()
})
</script>

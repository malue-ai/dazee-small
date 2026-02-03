<template>
  <div class="h-full flex flex-col overflow-hidden bg-white">
    <!-- 主内容区 -->
    <div class="flex-1 overflow-y-auto p-8 flex justify-center bg-gray-50/30">
      <div class="w-full max-w-4xl bg-white border border-gray-200 rounded-3xl shadow-sm p-10 flex flex-col gap-8">
        <!-- 步骤条 -->
        <div class="flex items-center justify-between px-4">
          <template v-for="(step, index) in steps" :key="step.id">
            <div class="flex flex-col items-center gap-3 relative z-10">
              <div 
                class="w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm transition-all shadow-sm border cursor-pointer"
                :class="getStepClass(index)"
                @click="goToStep(index)"
              >
                <Check v-if="currentStep > index" class="w-5 h-5" />
                <span v-else>{{ index + 1 }}</span>
              </div>
              <span 
                class="text-xs font-semibold uppercase tracking-wide whitespace-nowrap" 
                :class="currentStep === index ? 'text-gray-900' : 'text-gray-400'"
              >
                {{ step.name }}
              </span>
            </div>
            <div 
              v-if="index < steps.length - 1" 
              class="flex-1 h-0.5 bg-gray-100 mx-2 relative -top-4 overflow-hidden rounded-full"
            >
              <div 
                class="h-full bg-green-500 transition-all duration-500" 
                :style="{ width: currentStep > index ? '100%' : '0%' }"
              ></div>
            </div>
          </template>
        </div>

        <!-- 校验反馈 -->
        <ValidationFeedback
          v-if="currentStep > 0"
          :errors="validationErrors"
          :warnings="validationWarnings"
          :loading="validating"
          :is-valid="isConfigValid"
        />

        <!-- 步骤 0: 模板选择 -->
        <div v-if="currentStep === 0" class="flex-1 animate-in fade-in slide-in-from-right-4 duration-300">
          <TemplateSelector @select="applyTemplate" />
        </div>

        <!-- 步骤 1: 基础信息 -->
        <div v-if="currentStep === 1" class="flex flex-col gap-6 flex-1 animate-in fade-in slide-in-from-right-4 duration-300">
          <div class="flex flex-col gap-2">
            <label class="text-sm font-medium text-gray-700">
              Agent ID <span class="text-red-500">*</span>
            </label>
            <input 
              v-model="form.agent_id" 
              type="text" 
              placeholder="例如: coding_assistant"
              class="w-full px-4 py-2.5 bg-white border rounded-lg text-sm transition-all focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-gray-400"
              :class="hasFieldError('agent_id') ? 'border-red-300 bg-red-50/50' : 'border-gray-200'"
              @input="debouncedValidate"
            >
            <span class="text-xs text-gray-400 ml-1">唯一标识符，仅支持小写字母、数字和下划线</span>
          </div>

          <div class="flex flex-col gap-2">
            <label class="text-sm font-medium text-gray-700">描述</label>
            <textarea 
              v-model="form.description" 
              rows="2" 
              placeholder="描述智能体的功能和用途"
              class="w-full px-4 py-2.5 bg-white border border-gray-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-gray-400 transition-all"
            ></textarea>
          </div>

          <div class="flex flex-col gap-2">
            <label class="text-sm font-medium text-gray-700">
              系统提示词 (Prompt) <span class="text-red-500">*</span>
            </label>
            <textarea 
              v-model="form.prompt" 
              rows="10" 
              placeholder="设定智能体的角色和行为准则..."
              class="w-full px-4 py-3 bg-white border rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-gray-400 transition-all font-mono leading-relaxed"
              :class="hasFieldError('prompt') ? 'border-red-300 bg-red-50/50' : 'border-gray-200'"
              @input="debouncedValidate"
            ></textarea>
          </div>
        </div>

        <!-- 步骤 2: 能力配置 -->
        <div v-if="currentStep === 2" class="flex flex-col gap-6 flex-1 animate-in fade-in slide-in-from-right-4 duration-300">
          <div class="flex flex-col gap-2">
            <label class="text-sm font-medium text-gray-700">模型选择</label>
            <div class="relative">
              <select 
                v-model="form.model"
                class="w-full pl-4 pr-10 py-2.5 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-gray-400 transition-all cursor-pointer appearance-none"
              >
                <option value="claude-sonnet-4-5-20250929">Claude Sonnet 4.5 (推荐)</option>
                <option value="claude-3-5-sonnet-20241022">Claude 3.5 Sonnet</option>
                <option value="gpt-4o">GPT-4o</option>
                <option value="gemini-1.5-pro">Gemini 1.5 Pro</option>
              </select>
              <ChevronDown class="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>
          </div>

          <div class="flex flex-col gap-2">
            <label class="text-sm font-medium text-gray-700">最大对话轮数</label>
            <input 
              v-model.number="form.max_turns" 
              type="number" 
              min="1" 
              max="100"
              class="w-full px-4 py-2.5 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-gray-400 transition-all"
            >
          </div>

          <label class="flex items-start gap-3 p-4 bg-gray-50 rounded-xl border border-gray-200 cursor-pointer hover:border-gray-300 transition-all group">
            <input 
              type="checkbox" 
              v-model="form.plan_manager_enabled"
              class="mt-1 w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            >
            <div class="flex-1">
              <div class="text-sm font-medium text-gray-800 group-hover:text-gray-900 transition-colors">启用计划管理器 (Plan Manager)</div>
              <div class="text-xs text-gray-500 mt-1">适合处理复杂的长流程任务，智能体会自动拆解步骤</div>
            </div>
          </label>

          <div class="flex flex-col gap-3">
            <h3 class="text-sm font-medium text-gray-700">基础能力</h3>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <label class="flex items-center gap-3 p-4 bg-white border border-gray-200 rounded-xl cursor-pointer hover:border-gray-300 hover:shadow-sm transition-all group">
                <input type="checkbox" v-model="form.enabled_capabilities.tavily_search" class="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500">
                <span class="text-sm font-medium text-gray-600 group-hover:text-gray-900 flex items-center gap-2">
                  <Globe class="w-4 h-4" /> 网络搜索
                </span>
              </label>
              <label class="flex items-center gap-3 p-4 bg-white border border-gray-200 rounded-xl cursor-pointer hover:border-gray-300 hover:shadow-sm transition-all group">
                <input type="checkbox" v-model="form.enabled_capabilities.knowledge_search" class="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500">
                <span class="text-sm font-medium text-gray-600 group-hover:text-gray-900 flex items-center gap-2">
                  <BookOpen class="w-4 h-4" /> 知识库
                </span>
              </label>
              <label class="flex items-center gap-3 p-4 bg-white border border-gray-200 rounded-xl cursor-pointer hover:border-gray-300 hover:shadow-sm transition-all group">
                <input type="checkbox" v-model="form.enabled_capabilities.code_execution" class="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500">
                <span class="text-sm font-medium text-gray-600 group-hover:text-gray-900 flex items-center gap-2">
                  <Code2 class="w-4 h-4" /> 代码执行
                </span>
              </label>
              <label class="flex items-center gap-3 p-4 bg-white border border-gray-200 rounded-xl cursor-pointer hover:border-gray-300 hover:shadow-sm transition-all group">
                <input type="checkbox" v-model="form.enabled_capabilities.sandbox_tools" class="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500">
                <span class="text-sm font-medium text-gray-600 group-hover:text-gray-900 flex items-center gap-2">
                  <Terminal class="w-4 h-4" /> 沙盒工具
                </span>
              </label>
            </div>
          </div>
        </div>

        <!-- 步骤 3: MCP 工具 -->
        <div v-if="currentStep === 3" class="flex flex-col gap-6 flex-1 animate-in fade-in slide-in-from-right-4 duration-300">
          <div class="mb-2">
            <h3 class="text-sm font-medium text-gray-700 flex items-center gap-2">
              <Plug class="w-4 h-4" /> MCP 工具 <span class="text-xs font-normal text-gray-400">（可选）</span>
            </h3>
            <p class="text-xs text-gray-500 mt-1 pl-6">选择要启用的外部服务（如 Dify、Coze 工作流）</p>
          </div>
          <div v-if="loadingMcps" class="text-center py-12 text-gray-400 text-sm flex flex-col items-center">
            <Loader2 class="w-8 h-8 animate-spin mb-3 text-gray-300" />
            加载 MCP 列表中...
          </div>
          <div v-else-if="availableMcps.length === 0" class="text-center py-12 text-gray-400 bg-gray-50 rounded-xl border border-dashed border-gray-200">
            <Plug class="w-8 h-8 text-gray-300 mx-auto mb-2" />
            <p class="text-sm text-gray-500">没有可用的 MCP 工具</p>
            <p class="text-xs mt-1">可跳过此步骤</p>
          </div>
          <div v-else class="flex flex-col gap-3 max-h-96 overflow-y-auto">
            <div 
              v-for="mcp in availableMcps" 
              :key="mcp.server_name" 
              class="bg-white border border-gray-200 rounded-xl p-4 hover:border-gray-300 hover:shadow-sm transition-all group"
            >
              <div class="flex items-start justify-between gap-4 mb-2">
                <label class="flex items-center gap-3 cursor-pointer flex-1">
                  <input 
                    type="checkbox" 
                    :value="mcp.server_name" 
                    v-model="selectedMcps"
                    class="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  >
                  <span class="font-medium text-sm text-gray-800 group-hover:text-gray-900">{{ mcp.server_name }}</span>
                </label>
                <span class="px-2 py-0.5 bg-gray-50 rounded text-[10px] text-gray-500 font-mono border border-gray-100 truncate max-w-48">{{ mcp.server_url }}</span>
              </div>
              <p class="text-xs text-gray-500 mb-3 pl-7 leading-relaxed">{{ mcp.description || '暂无描述' }}</p>
              
              <!-- 认证配置 -->
              <div v-if="selectedMcps.includes(mcp.server_name) && mcp.auth_type !== 'none'" class="ml-7 pt-3 border-t border-dashed border-gray-100 animate-in slide-in-from-top-1">
                <div class="flex flex-col gap-1.5">
                  <label class="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">认证环境变量 (Auth Env)</label>
                  <input 
                    type="text" 
                    v-model="mcpAuthConfigs[mcp.server_name]"
                    :placeholder="mcp.auth_env || '例如: NOTION_API_KEY'"
                    class="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-gray-400 transition-all font-mono"
                  >
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 步骤 4: 高级配置 -->
        <div v-if="currentStep === 4" class="flex flex-col gap-6 flex-1 animate-in fade-in slide-in-from-right-4 duration-300">
          <div class="mb-2">
            <h3 class="text-sm font-medium text-gray-700 flex items-center gap-2">
              <Settings class="w-4 h-4" /> 高级配置 <span class="text-xs font-normal text-gray-400">（可选）</span>
            </h3>
            <p class="text-xs text-gray-500 mt-1 pl-6">配置 LLM 参数和记忆策略，使用默认值即可满足大多数场景</p>
          </div>
          <AdvancedConfigForm v-model="advancedConfig" />
        </div>

        <!-- 步骤 5: 预览确认 -->
        <div v-if="currentStep === 5" class="flex flex-col gap-6 flex-1 animate-in fade-in slide-in-from-right-4 duration-300">
          <div class="mb-2">
            <h3 class="text-sm font-medium text-gray-700 flex items-center gap-2">
              <Eye class="w-4 h-4" /> 配置预览
            </h3>
            <p class="text-xs text-gray-500 mt-1 pl-6">确认配置无误后点击创建</p>
          </div>
          <ConfigPreview :form-data="getFormDataForPreview()" :agent-id="form.agent_id" />
        </div>

        <!-- 底部按钮 -->
        <div class="flex items-center justify-between pt-6 border-t border-gray-100 mt-auto">
          <button 
            v-if="currentStep > 0" 
            @click="currentStep--" 
            class="px-5 py-2.5 bg-white border border-gray-200 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors"
          >
            上一步
          </button>
          <div v-else></div>
          
          <div class="flex items-center gap-3">
            <button 
              v-if="currentStep < steps.length - 1" 
              @click="nextStep" 
              class="px-6 py-2.5 bg-gray-900 text-white rounded-lg text-sm font-medium hover:bg-gray-800 transition-all shadow-sm"
            >
              下一步
            </button>
            
            <button 
              v-if="currentStep === steps.length - 1" 
              @click="submitForm" 
              class="px-6 py-2.5 bg-gray-900 text-white rounded-lg text-sm font-medium hover:bg-gray-800 transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2" 
              :disabled="submitting || !isConfigValid"
            >
              <Loader2 v-if="submitting" class="w-4 h-4 animate-spin" />
              {{ submitting ? '创建中...' : '确认创建' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/index'
import { 
  Check, 
  ChevronDown, 
  Globe, 
  BookOpen, 
  Code2, 
  Terminal,
  Plug, 
  Loader2,
  Settings,
  Eye,
} from 'lucide-vue-next'
import TemplateSelector from './components/TemplateSelector.vue'
import AdvancedConfigForm from './components/AdvancedConfigForm.vue'
import ValidationFeedback from './components/ValidationFeedback.vue'
import ConfigPreview from './components/ConfigPreview.vue'

interface ValidationError {
  field: string
  message: string
  code?: string
}

interface ValidationWarning {
  field: string
  message: string
}

interface AgentTemplate {
  id: string
  name: string
  description: string
  icon: string
  config: Record<string, any>
}

const router = useRouter()

// 步骤定义
const steps = [
  { id: 'template', name: '选择模板' },
  { id: 'basic', name: '基础信息' },
  { id: 'capabilities', name: '能力配置' },
  { id: 'mcp', name: 'MCP 工具' },
  { id: 'advanced', name: '高级配置' },
  { id: 'preview', name: '预览确认' },
]

const currentStep = ref(0)
const submitting = ref(false)
const validating = ref(false)
const loadingMcps = ref(false)
const availableMcps = ref<any[]>([])
const selectedMcps = ref<string[]>([])
const mcpAuthConfigs = reactive<Record<string, string>>({})
const validationErrors = ref<ValidationError[]>([])
const validationWarnings = ref<ValidationWarning[]>([])

// 表单数据
const form = reactive({
  agent_id: '',
  description: '',
  prompt: '',
  model: 'claude-sonnet-4-5-20250929',
  max_turns: 20,
  plan_manager_enabled: true,
  enabled_capabilities: {
    tavily_search: true,
    knowledge_search: true,
    code_execution: false,
    sandbox_tools: false,
  } as Record<string, boolean>,
})

// 高级配置
const advancedConfig = reactive({
  llm: {
    enable_thinking: true,
    thinking_budget: 8000,
    max_tokens: 16384,
    enable_caching: true,
  },
  memory: {
    mem0_enabled: true,
    smart_retrieval: true,
    retention_policy: 'user',
  },
})

// 计算属性
const isConfigValid = computed(() => {
  return !!(validationErrors.value.length === 0 && form.agent_id && form.prompt)
})

// 检查字段是否有错误
const hasFieldError = (field: string): boolean => {
  return validationErrors.value.some(e => e.field === field)
}

// 获取步骤样式
const getStepClass = (index: number): string => {
  if (currentStep.value === index) {
    return 'bg-gray-900 text-white border-gray-900 transform scale-110'
  }
  if (currentStep.value > index) {
    return 'bg-green-500 text-white border-green-500'
  }
  return 'bg-white text-gray-400 border-gray-200 hover:border-gray-300'
}

// 跳转到指定步骤（只能跳转到已完成的步骤）
const goToStep = (index: number) => {
  if (index <= currentStep.value) {
    currentStep.value = index
  }
}

// 应用模板
const applyTemplate = (template: AgentTemplate | null) => {
  if (!template) {
    // 从空白开始，使用默认值
    Object.assign(form, {
      model: 'claude-sonnet-4-5-20250929',
      max_turns: 20,
      plan_manager_enabled: false,
      enabled_capabilities: {
        tavily_search: false,
        knowledge_search: false,
        code_execution: false,
        sandbox_tools: false,
      },
    })
    Object.assign(advancedConfig, {
      llm: {
        enable_thinking: false,
        thinking_budget: 8000,
        max_tokens: 8192,
        enable_caching: true,
      },
      memory: {
        mem0_enabled: true,
        smart_retrieval: true,
        retention_policy: 'session',
      },
    })
  } else {
    // 应用模板配置
    const config = template.config
    Object.assign(form, {
      model: config.model || form.model,
      max_turns: config.max_turns || form.max_turns,
      plan_manager_enabled: config.plan_manager_enabled ?? form.plan_manager_enabled,
      enabled_capabilities: config.enabled_capabilities || form.enabled_capabilities,
    })
    if (config.llm) {
      Object.assign(advancedConfig.llm, config.llm)
    }
    if (config.memory) {
      Object.assign(advancedConfig.memory, config.memory)
    }
  }
  
  // 自动进入下一步
  currentStep.value = 1
}

// 获取预览数据
const getFormDataForPreview = () => {
  return {
    agent_id: form.agent_id,
    description: form.description,
    prompt: form.prompt,
    model: form.model,
    max_turns: form.max_turns,
    plan_manager_enabled: form.plan_manager_enabled,
    enabled_capabilities: form.enabled_capabilities,
    llm: advancedConfig.llm,
    memory: advancedConfig.memory,
    mcp_tools: selectedMcps.value.map(name => {
      const mcp = availableMcps.value.find(m => m.server_name === name)
      return {
        name: mcp?.server_name || name,
        server_url: mcp?.server_url || '',
        server_name: mcp?.server_name || name,
        auth_type: mcp?.auth_type || 'none',
        auth_env: mcpAuthConfigs[name] || mcp?.auth_env,
        description: mcp?.description || '',
      }
    }),
  }
}

// 验证配置
const validateConfig = async () => {
  if (!form.agent_id && !form.prompt) {
    validationErrors.value = []
    validationWarnings.value = []
    return
  }

  try {
    validating.value = true
    const response = await api.post('/v1/agents/validate', getFormDataForPreview())
    validationErrors.value = response.data.errors || []
    validationWarnings.value = response.data.warnings || []
  } catch (error) {
    console.error('校验失败:', error)
  } finally {
    validating.value = false
  }
}

// 防抖验证
let validateTimer: ReturnType<typeof setTimeout> | null = null
const debouncedValidate = () => {
  if (validateTimer) clearTimeout(validateTimer)
  validateTimer = setTimeout(validateConfig, 500)
}

// 加载 MCP 列表
const fetchMcps = async () => {
  try {
    loadingMcps.value = true
    const response = await api.get('/v1/tools/mcp')
    availableMcps.value = response.data.servers || []
  } catch (error) {
    console.error('获取 MCP 列表失败:', error)
  } finally {
    loadingMcps.value = false
  }
}

// 下一步
const nextStep = () => {
  if (currentStep.value === 1) {
    // 验证基础信息
    if (!form.agent_id || !form.prompt) {
      validateConfig()
      return
    }
    // 验证 ID 格式
    if (!/^[a-z0-9_-]+$/.test(form.agent_id)) {
      validationErrors.value = [{
        field: 'agent_id',
        message: 'Agent ID 只能包含小写字母、数字、下划线和连字符',
        code: 'INVALID_FORMAT',
      }]
      return
    }
  }
  
  if (currentStep.value === 2) {
    // 进入 MCP 步骤前加载列表
    if (availableMcps.value.length === 0) {
      fetchMcps()
    }
  }
  
  currentStep.value++
}

// 提交表单
const submitForm = async () => {
  try {
    submitting.value = true
    
    // 构建请求数据
    const agentData = {
      agent_id: form.agent_id,
      description: form.description || `${form.agent_id} 智能助手`,
      prompt: form.prompt,
      model: form.model,
      max_turns: form.max_turns,
      plan_manager_enabled: form.plan_manager_enabled,
      enabled_capabilities: form.enabled_capabilities,
      llm: advancedConfig.llm,
      memory: advancedConfig.memory,
    }
    
    await api.post('/v1/agents', agentData)
    
    // 关联选中的 MCP
    if (selectedMcps.value.length > 0) {
      for (const serverName of selectedMcps.value) {
        try {
          const authEnv = mcpAuthConfigs[serverName]
          await api.post(`/v1/agents/${form.agent_id}/mcp/${serverName}`, {
            auth_env: authEnv || undefined
          })
        } catch (mcpError) {
          console.error(`关联 MCP ${serverName} 失败:`, mcpError)
        }
      }
    }
    
    // 跳转到详情页
    router.push(`/agents/${form.agent_id}`)
    
  } catch (error: any) {
    console.error('创建 Agent 失败:', error)
    const msg = error.response?.data?.detail?.message || error.message
    alert(`创建失败: ${msg}`)
  } finally {
    submitting.value = false
  }
}

// 监听表单变化，触发验证
watch(
  () => [form.agent_id, form.prompt],
  () => {
    if (currentStep.value >= 1) {
      debouncedValidate()
    }
  }
)
</script>

<style scoped>
/* 页面样式 */
</style>

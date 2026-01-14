<template>
  <div class="h-screen w-full flex flex-col bg-gray-50 relative overflow-hidden text-gray-900 font-sans">
    <!-- 背景装饰 -->
    <div class="absolute inset-0 z-0 opacity-20 pointer-events-none">
      <div class="absolute top-0 left-0 w-[500px] h-[500px] bg-blue-200 rounded-full mix-blend-multiply filter blur-3xl animate-blob"></div>
      <div class="absolute top-0 right-0 w-[500px] h-[500px] bg-purple-200 rounded-full mix-blend-multiply filter blur-3xl animate-blob animation-delay-2000"></div>
      <div class="absolute -bottom-8 left-20 w-[500px] h-[500px] bg-pink-200 rounded-full mix-blend-multiply filter blur-3xl animate-blob animation-delay-4000"></div>
    </div>

    <!-- 顶部导航 -->
    <div class="h-16 flex items-center justify-between px-8 border-b border-white/20 bg-white/40 backdrop-blur-md sticky top-0 z-20">
      <h1 class="text-lg font-bold text-gray-800">创建新智能体</h1>
      <button 
        @click="$router.push('/agents')" 
        class="px-5 py-2.5 bg-white/60 border border-white/40 text-gray-600 text-sm font-medium rounded-xl hover:bg-white hover:text-gray-900 transition-all shadow-sm"
      >
        ← 返回列表
      </button>
    </div>

    <!-- 主内容区 -->
    <div class="flex-1 overflow-y-auto p-8 relative z-10 flex justify-center">
      <div class="w-full max-w-3xl bg-white/60 backdrop-blur-xl border border-white/40 rounded-3xl shadow-xl p-10 flex flex-col gap-8">
        <!-- 步骤条 -->
        <div class="flex items-center justify-between px-8">
          <div class="flex flex-col items-center gap-3 relative z-10">
            <div 
              class="w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm transition-all shadow-md"
              :class="currentStep === 1 ? 'bg-gray-900 text-white transform scale-110' : currentStep > 1 ? 'bg-green-500 text-white' : 'bg-white text-gray-400 border border-gray-200'"
            >
              {{ currentStep > 1 ? '✓' : '1' }}
            </div>
            <span class="text-xs font-semibold uppercase tracking-wide" :class="currentStep === 1 ? 'text-gray-900' : 'text-gray-400'">基础信息</span>
          </div>
          <div class="flex-1 h-0.5 bg-gray-200 mx-4 relative -top-4">
            <div class="h-full bg-green-500 transition-all duration-500" :style="{ width: currentStep > 1 ? '100%' : '0%' }"></div>
          </div>
          <div class="flex flex-col items-center gap-3 relative z-10">
            <div 
              class="w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm transition-all shadow-md"
              :class="currentStep === 2 ? 'bg-gray-900 text-white transform scale-110' : currentStep > 2 ? 'bg-green-500 text-white' : 'bg-white text-gray-400 border border-gray-200'"
            >
              {{ currentStep > 2 ? '✓' : '2' }}
            </div>
            <span class="text-xs font-semibold uppercase tracking-wide" :class="currentStep === 2 ? 'text-gray-900' : 'text-gray-400'">能力配置</span>
          </div>
          <div class="flex-1 h-0.5 bg-gray-200 mx-4 relative -top-4">
            <div class="h-full bg-green-500 transition-all duration-500" :style="{ width: currentStep > 2 ? '100%' : '0%' }"></div>
          </div>
          <div class="flex flex-col items-center gap-3 relative z-10">
            <div 
              class="w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm transition-all shadow-md"
              :class="currentStep === 3 ? 'bg-gray-900 text-white transform scale-110' : 'bg-white text-gray-400 border border-gray-200'"
            >
              3
            </div>
            <span class="text-xs font-semibold uppercase tracking-wide" :class="currentStep === 3 ? 'text-gray-900' : 'text-gray-400'">工具配置</span>
          </div>
        </div>

        <!-- 步骤 1: 基础信息 -->
        <div v-if="currentStep === 1" class="flex flex-col gap-6 flex-1 animate-in fade-in slide-in-from-right-4 duration-300">
          <div class="flex flex-col gap-2">
            <label class="text-sm font-semibold text-gray-700">
              Agent ID <span class="text-red-500">*</span>
            </label>
            <input 
              v-model="form.agent_id" 
              type="text" 
              placeholder="例如: coding_assistant"
              class="w-full px-4 py-3 bg-white/50 border rounded-xl text-sm transition-all focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 shadow-sm"
              :class="errors.agent_id ? 'border-red-300 bg-red-50/50' : 'border-gray-200'"
            >
            <span class="text-xs text-gray-400 ml-1">唯一标识符，仅支持小写字母、数字和下划线</span>
          </div>

          <div class="flex flex-col gap-2">
            <label class="text-sm font-semibold text-gray-700">名称</label>
            <input 
              v-model="form.name" 
              type="text" 
              placeholder="给智能体起个名字"
              class="w-full px-4 py-3 bg-white/50 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm"
            >
          </div>

          <div class="flex flex-col gap-2">
            <label class="text-sm font-semibold text-gray-700">描述</label>
            <textarea 
              v-model="form.description" 
              rows="3" 
              placeholder="描述智能体的功能和用途"
              class="w-full px-4 py-3 bg-white/50 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm"
            ></textarea>
          </div>

          <div class="flex flex-col gap-2">
            <label class="text-sm font-semibold text-gray-700">
              系统提示词 (Prompt) <span class="text-red-500">*</span>
            </label>
            <textarea 
              v-model="form.prompt" 
              rows="8" 
              placeholder="设定智能体的角色和行为准则..."
              class="w-full px-4 py-3 bg-white/50 border rounded-xl text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm font-mono"
              :class="errors.prompt ? 'border-red-300 bg-red-50/50' : 'border-gray-200'"
            ></textarea>
          </div>
        </div>

        <!-- 步骤 2: 能力配置 -->
        <div v-if="currentStep === 2" class="flex flex-col gap-6 flex-1 animate-in fade-in slide-in-from-right-4 duration-300">
          <div class="flex flex-col gap-2">
            <label class="text-sm font-semibold text-gray-700">模型选择</label>
            <div class="relative">
              <select 
                v-model="form.model"
                class="w-full px-4 py-3 bg-white/50 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all cursor-pointer appearance-none shadow-sm"
              >
                <option value="claude-3-5-sonnet-20241022">Claude 3.5 Sonnet (推荐)</option>
                <option value="gpt-4o">GPT-4o</option>
                <option value="gemini-1.5-pro">Gemini 1.5 Pro</option>
              </select>
              <div class="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-gray-400">▼</div>
            </div>
          </div>

          <div class="flex flex-col gap-2">
            <label class="text-sm font-semibold text-gray-700">最大对话轮数</label>
            <input 
              v-model.number="form.max_turns" 
              type="number" 
              min="1" 
              max="100"
              class="w-full px-4 py-3 bg-white/50 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm"
            >
          </div>

          <label class="flex items-center gap-4 p-4 bg-white/50 rounded-xl border border-gray-200 cursor-pointer hover:border-blue-300 transition-all shadow-sm group">
            <input 
              type="checkbox" 
              v-model="form.plan_manager_enabled"
              class="w-5 h-5 accent-blue-600 cursor-pointer rounded"
            >
            <div class="flex-1">
              <div class="text-sm font-semibold text-gray-800 group-hover:text-blue-700 transition-colors">启用计划管理器 (Plan Manager)</div>
              <div class="text-xs text-gray-500 mt-0.5">适合处理复杂的长流程任务，智能体会自动拆解步骤</div>
            </div>
          </label>

          <div class="flex flex-col gap-3">
            <h3 class="text-sm font-semibold text-gray-700">基础能力</h3>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <label class="flex items-center gap-3 p-4 bg-white/50 border border-gray-200 rounded-xl cursor-pointer hover:bg-white hover:border-blue-300 hover:shadow-md transition-all group">
                <input type="checkbox" v-model="form.enabled_capabilities.web_search" class="w-5 h-5 accent-blue-600 rounded">
                <span class="text-sm font-medium text-gray-700 group-hover:text-blue-700">🌐 网络搜索</span>
              </label>
              <label class="flex items-center gap-3 p-4 bg-white/50 border border-gray-200 rounded-xl cursor-pointer hover:bg-white hover:border-blue-300 hover:shadow-md transition-all group">
                <input type="checkbox" v-model="form.enabled_capabilities.knowledge_search" class="w-5 h-5 accent-blue-600 rounded">
                <span class="text-sm font-medium text-gray-700 group-hover:text-blue-700">📚 知识库</span>
              </label>
              <label class="flex items-center gap-3 p-4 bg-white/50 border border-gray-200 rounded-xl cursor-pointer hover:bg-white hover:border-blue-300 hover:shadow-md transition-all group">
                <input type="checkbox" v-model="form.enabled_capabilities.code_execution" class="w-5 h-5 accent-blue-600 rounded">
                <span class="text-sm font-medium text-gray-700 group-hover:text-blue-700">💻 代码执行</span>
              </label>
            </div>
          </div>
        </div>

        <!-- 步骤 3: 工具配置（MCP 工具） -->
        <div v-if="currentStep === 3" class="flex flex-col gap-6 flex-1 animate-in fade-in slide-in-from-right-4 duration-300">
          <div class="mb-2">
            <h3 class="text-sm font-semibold text-gray-700 flex items-center gap-2">
              🔌 MCP 工具 <span class="text-xs font-normal text-gray-400">（可选）</span>
            </h3>
            <p class="text-xs text-gray-500 mt-1">选择要启用的外部服务（如 Dify、Coze 工作流）</p>
          </div>
          <div v-if="loadingMcps" class="text-center py-12 text-gray-400 text-sm flex flex-col items-center">
            <div class="w-8 h-8 border-2 border-gray-200 border-t-blue-500 rounded-full animate-spin mb-3"></div>
            加载 MCP 列表中...
          </div>
          <div v-else-if="availableMcps.length === 0" class="text-center py-12 text-gray-400 bg-white/30 rounded-2xl border border-dashed border-gray-200">
            <span class="text-2xl block mb-2">🔌</span>
            没有可用的 MCP 工具，可跳过此步骤
          </div>
          <div v-else class="flex flex-col gap-4">
            <div 
              v-for="mcp in availableMcps" 
              :key="mcp.server_name" 
              class="bg-white/50 border border-gray-200 rounded-xl p-5 hover:bg-white hover:border-blue-300 hover:shadow-md transition-all group"
            >
              <div class="flex items-start justify-between gap-4 mb-2">
                <label class="flex items-center gap-3 cursor-pointer flex-1">
                  <input 
                    type="checkbox" 
                    :value="mcp.server_name" 
                    v-model="selectedMcps"
                    class="w-5 h-5 accent-blue-600 rounded"
                  >
                  <span class="font-bold text-base text-gray-800 group-hover:text-blue-700">{{ mcp.server_name }}</span>
                </label>
                <span class="px-2 py-1 bg-gray-100 rounded text-xs text-gray-500 font-mono">{{ mcp.server_url }}</span>
              </div>
              <p class="text-sm text-gray-500 mb-4 pl-8">{{ mcp.description || '暂无描述' }}</p>
              
              <!-- 认证配置 -->
              <div v-if="selectedMcps.includes(mcp.server_name) && mcp.auth_type !== 'none'" class="ml-8 pt-4 border-t border-dashed border-gray-200 animate-in slide-in-from-top-2">
                <div class="flex flex-col gap-2">
                  <label class="text-xs font-semibold text-gray-600 uppercase tracking-wide">认证环境变量 (Auth Env)</label>
                  <input 
                    type="text" 
                    v-model="mcpAuthConfigs[mcp.server_name]"
                    :placeholder="mcp.auth_env || '例如: NOTION_API_KEY'"
                    class="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all font-mono"
                  >
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 底部按钮 -->
        <div class="flex items-center justify-end gap-4 pt-8 border-t border-gray-200/50 mt-auto">
          <button 
            v-if="currentStep > 1" 
            @click="currentStep--" 
            class="px-6 py-3 bg-white border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors shadow-sm"
          >
            上一步
          </button>
          
          <button 
            v-if="currentStep < 3" 
            @click="nextStep" 
            class="px-8 py-3 bg-gray-900 text-white rounded-xl text-sm font-medium hover:bg-gray-800 transition-all shadow-lg shadow-gray-900/10 transform active:scale-95"
          >
            下一步
          </button>
          
          <button 
            v-if="currentStep === 3" 
            @click="submitForm" 
            class="px-8 py-3 bg-gray-900 text-white rounded-xl text-sm font-medium hover:bg-gray-800 transition-all shadow-lg shadow-gray-900/10 transform active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed" 
            :disabled="submitting"
          >
            {{ submitting ? '创建中...' : '确认创建' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/index'

const router = useRouter()
const currentStep = ref(1)
const submitting = ref(false)
const loadingMcps = ref(false)
const availableMcps = ref([])
const selectedMcps = ref([])
const mcpAuthConfigs = reactive({})

const form = reactive({
  agent_id: '',
  name: '',
  description: '',
  prompt: '',
  model: 'claude-3-5-sonnet-20241022',
  max_turns: 20,
  plan_manager_enabled: false,
  enabled_capabilities: {
    web_search: false,
    knowledge_search: true,
    code_execution: false
  }
})

const errors = reactive({
  agent_id: false,
  prompt: false
})

const fetchMcps = async () => {
  try {
    loadingMcps.value = true
    // 正确的后端路由: /api/v1/tools/mcp
    const response = await api.get('/v1/tools/mcp')
    availableMcps.value = response.data.servers || []
  } catch (error) {
    console.error('获取 MCP 列表失败:', error)
  } finally {
    loadingMcps.value = false
  }
}

const nextStep = () => {
  if (currentStep.value === 1) {
    // 验证第一步
    errors.agent_id = !form.agent_id
    errors.prompt = !form.prompt
    
    if (errors.agent_id || errors.prompt) return
    
    // 验证 ID 格式
    if (!/^[a-z0-9_]+$/.test(form.agent_id)) {
      alert('Agent ID 只能包含小写字母、数字和下划线')
      errors.agent_id = true
      return
    }
  }
  
  if (currentStep.value === 2) {
    // 进入第三步前加载 MCP
    if (availableMcps.value.length === 0) {
      fetchMcps()
    }
  }
  
  currentStep.value++
}

const submitForm = async () => {
  try {
    submitting.value = true
    
    // 1. 创建 Agent
    const agentData = {
      agent_id: form.agent_id,
      description: form.description || form.name, // 使用名称作为默认描述
      prompt: form.prompt,
      model: form.model,
      max_turns: form.max_turns,
      plan_manager_enabled: form.plan_manager_enabled,
      enabled_capabilities: form.enabled_capabilities,
      // 暂时不直接在创建时关联 MCP，而是创建后关联
    }
    
    await api.post('/v1/agents', agentData)
    
    // 2. 关联选中的 MCP
    if (selectedMcps.value.length > 0) {
      for (const serverName of selectedMcps.value) {
        try {
          const authEnv = mcpAuthConfigs[serverName]
          await api.post(`/v1/agents/${form.agent_id}/mcp/${serverName}/enable`, {
            auth_env: authEnv || undefined
          })
        } catch (mcpError) {
          console.error(`关联 MCP ${serverName} 失败:`, mcpError)
          // 继续关联其他 MCP，不中断流程
        }
      }
    }
    
    alert('Agent 创建成功！')
    router.push('/agents')
    
  } catch (error) {
    console.error('创建 Agent 失败:', error)
    const msg = error.response?.data?.detail?.message || error.message
    alert(`创建失败: ${msg}`)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
@keyframes blob {
  0% { transform: translate(0px, 0px) scale(1); }
  33% { transform: translate(30px, -50px) scale(1.1); }
  66% { transform: translate(-20px, 20px) scale(0.9); }
  100% { transform: translate(0px, 0px) scale(1); }
}
.animate-blob {
  animation: blob 15s infinite;
}
.animation-delay-2000 {
  animation-delay: 2s;
}
.animation-delay-4000 {
  animation-delay: 4s;
}
</style>

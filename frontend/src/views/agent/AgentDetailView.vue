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
      <div class="flex items-center gap-4">
        <button 
          @click="$router.push('/agents')" 
          class="p-2 rounded-lg text-gray-500 hover:bg-white hover:text-gray-900 transition-all"
        >
          ←
        </button>
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 text-white flex items-center justify-center font-bold text-lg shadow-md">
            {{ agent?.name?.[0]?.toUpperCase() || 'A' }}
          </div>
          <div>
            <h1 class="text-lg font-bold text-gray-800">{{ agent?.name || agentId }}</h1>
            <span class="text-xs text-gray-400 font-mono">{{ agentId }}</span>
          </div>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <button 
          @click="reloadAgent" 
          :disabled="reloading"
          class="flex items-center gap-2 px-4 py-2 bg-white/60 border border-white/40 text-gray-600 text-sm font-medium rounded-xl hover:bg-white hover:text-blue-600 transition-all shadow-sm disabled:opacity-50"
        >
          <span :class="reloading ? 'animate-spin' : ''">🔄</span>
          {{ reloading ? '重载中...' : '热重载' }}
        </button>
        <button 
          @click="saveChanges" 
          :disabled="saving || !hasChanges"
          class="flex items-center gap-2 px-5 py-2 bg-gray-900 text-white text-sm font-medium rounded-xl hover:bg-gray-800 transition-all shadow-lg shadow-gray-900/10 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ saving ? '保存中...' : '保存更改' }}
        </button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <div class="flex flex-col items-center gap-4">
        <div class="w-10 h-10 border-3 border-gray-200 border-t-gray-900 rounded-full animate-spin"></div>
        <p class="text-sm text-gray-500">加载智能体配置...</p>
      </div>
    </div>

    <!-- 主内容区 -->
    <div v-else class="flex-1 flex overflow-hidden relative z-10">
      <!-- 左侧导航 -->
      <div class="w-56 border-r border-white/20 bg-white/40 backdrop-blur-xl p-4 flex flex-col gap-2">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id"
          class="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all text-left"
          :class="activeTab === tab.id 
            ? 'bg-white shadow-md text-gray-900' 
            : 'text-gray-600 hover:bg-white/60 hover:text-gray-800'"
        >
          <span class="text-lg">{{ tab.icon }}</span>
          {{ tab.label }}
        </button>
      </div>

      <!-- 右侧内容 -->
      <div class="flex-1 overflow-y-auto p-8 scrollbar-thin">
        <!-- 基础信息 -->
        <div v-if="activeTab === 'basic'" class="max-w-3xl space-y-6">
          <div class="bg-white/60 backdrop-blur-sm border border-white/40 rounded-2xl p-6 space-y-6">
            <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2">
              📋 基础信息
            </h2>
            
            <div class="grid grid-cols-2 gap-6">
              <div class="flex flex-col gap-2">
                <label class="text-sm font-semibold text-gray-700">Agent ID</label>
                <input 
                  :value="agentId" 
                  disabled
                  class="w-full px-4 py-3 bg-gray-100 border border-gray-200 rounded-xl text-sm text-gray-500 cursor-not-allowed font-mono"
                >
              </div>
              
              <div class="flex flex-col gap-2">
                <label class="text-sm font-semibold text-gray-700">版本</label>
                <input 
                  v-model="form.version" 
                  type="text"
                  class="w-full px-4 py-3 bg-white/50 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all font-mono"
                >
              </div>
            </div>

            <div class="flex flex-col gap-2">
              <label class="text-sm font-semibold text-gray-700">名称</label>
              <input 
                v-model="form.name" 
                type="text"
                placeholder="智能体名称"
                class="w-full px-4 py-3 bg-white/50 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
              >
            </div>

            <div class="flex flex-col gap-2">
              <label class="text-sm font-semibold text-gray-700">描述</label>
              <textarea 
                v-model="form.description" 
                rows="3"
                placeholder="描述智能体的功能和用途"
                class="w-full px-4 py-3 bg-white/50 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
              ></textarea>
            </div>

            <div class="flex items-center gap-4">
              <label class="text-sm font-semibold text-gray-700">状态</label>
              <label class="flex items-center gap-3 cursor-pointer">
                <input 
                  type="checkbox" 
                  v-model="form.is_active"
                  class="w-5 h-5 accent-green-600 rounded"
                >
                <span class="text-sm" :class="form.is_active ? 'text-green-600 font-medium' : 'text-gray-500'">
                  {{ form.is_active ? '已激活' : '未激活' }}
                </span>
              </label>
            </div>
          </div>
        </div>

        <!-- Prompt 配置 -->
        <div v-if="activeTab === 'prompt'" class="max-w-4xl space-y-6">
          <div class="bg-white/60 backdrop-blur-sm border border-white/40 rounded-2xl p-6 space-y-6">
            <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2">
              ✍️ 系统提示词
            </h2>
            
            <div class="flex flex-col gap-2">
              <div class="flex items-center justify-between">
                <label class="text-sm font-semibold text-gray-700">System Prompt</label>
                <span class="text-xs text-gray-400">{{ form.prompt?.length || 0 }} 字符</span>
              </div>
              <textarea 
                v-model="form.prompt" 
                rows="20"
                placeholder="设定智能体的角色、能力和行为准则..."
                class="w-full px-4 py-3 bg-white/50 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all font-mono leading-relaxed"
              ></textarea>
            </div>
          </div>
        </div>

        <!-- 模型配置 -->
        <div v-if="activeTab === 'model'" class="max-w-3xl space-y-6">
          <div class="bg-white/60 backdrop-blur-sm border border-white/40 rounded-2xl p-6 space-y-6">
            <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2">
              🧠 模型配置
            </h2>
            
            <div class="flex flex-col gap-2">
              <label class="text-sm font-semibold text-gray-700">模型选择</label>
              <div class="relative">
                <select 
                  v-model="form.model"
                  class="w-full px-4 py-3 bg-white/50 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all cursor-pointer appearance-none"
                >
                  <option value="claude-sonnet-4-20250514">Claude Sonnet 4 (最新)</option>
                  <option value="claude-3-5-sonnet-20241022">Claude 3.5 Sonnet</option>
                  <option value="gpt-4o">GPT-4o</option>
                  <option value="gpt-4o-mini">GPT-4o Mini</option>
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
                class="w-full px-4 py-3 bg-white/50 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
              >
              <span class="text-xs text-gray-400">限制单次对话的最大工具调用轮数</span>
            </div>

            <label class="flex items-center gap-4 p-4 bg-white/50 rounded-xl border border-gray-200 cursor-pointer hover:border-blue-300 transition-all group">
              <input 
                type="checkbox" 
                v-model="form.plan_manager_enabled"
                class="w-5 h-5 accent-blue-600 cursor-pointer rounded"
              >
              <div class="flex-1">
                <div class="text-sm font-semibold text-gray-800 group-hover:text-blue-700 transition-colors">启用计划管理器</div>
                <div class="text-xs text-gray-500 mt-0.5">适合处理复杂的长流程任务</div>
              </div>
            </label>
          </div>
        </div>

        <!-- 工具配置 -->
        <div v-if="activeTab === 'tools'" class="max-w-4xl space-y-6">
          <!-- 内置工具 -->
          <div class="bg-white/60 backdrop-blur-sm border border-white/40 rounded-2xl p-6 space-y-6">
            <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2">
              ⚡ 内置工具
            </h2>
            <p class="text-sm text-gray-500 -mt-2">选择该智能体可使用的内置功能</p>
            
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <label 
                v-for="cap in availableCapabilities" 
                :key="cap.id"
                class="flex items-center gap-3 p-4 bg-white/50 border border-gray-200 rounded-xl cursor-pointer hover:bg-white hover:border-blue-300 hover:shadow-md transition-all group"
              >
                <input 
                  type="checkbox" 
                  :checked="form.enabled_capabilities?.[cap.id]"
                  @change="toggleCapability(cap.id)"
                  class="w-5 h-5 accent-blue-600 rounded"
                >
                <div class="flex-1">
                  <div class="text-sm font-medium text-gray-700 group-hover:text-blue-700 flex items-center gap-2">
                    <span>{{ cap.icon }}</span>
                    {{ cap.label }}
                  </div>
                  <div class="text-xs text-gray-400 mt-0.5">{{ cap.description }}</div>
                </div>
              </label>
            </div>
          </div>

          <!-- MCP 工具 -->
          <div class="bg-white/60 backdrop-blur-sm border border-white/40 rounded-2xl p-6 space-y-6">
            <div class="flex items-center justify-between">
              <div>
                <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2">
                  🔌 MCP 工具
                </h2>
                <p class="text-sm text-gray-500 mt-1">通过 MCP 协议连接的外部服务（如 Dify、Coze 工作流）</p>
              </div>
              <button 
                @click="fetchAvailableMcps"
                class="text-sm text-blue-600 hover:text-blue-700 font-medium"
              >
                刷新列表
              </button>
            </div>

            <!-- 已启用的 MCP -->
            <div v-if="enabledMcps.length > 0" class="space-y-3">
              <h3 class="text-sm font-semibold text-gray-600">已启用 ({{ enabledMcps.length }})</h3>
              <div 
                v-for="mcp in enabledMcps" 
                :key="mcp.server_name"
                class="flex items-center justify-between p-4 bg-green-50/50 border border-green-200 rounded-xl"
              >
                <div class="flex items-center gap-3">
                  <span class="w-8 h-8 bg-green-100 rounded-lg flex items-center justify-center text-green-600">✓</span>
                  <div>
                    <div class="font-medium text-gray-800">{{ mcp.name || mcp.server_name }}</div>
                    <div class="text-xs text-gray-500">{{ mcp.description || '暂无描述' }}</div>
                    <div class="text-xs text-gray-400 mt-1 font-mono">{{ mcp.server_url }}</div>
                  </div>
                </div>
                <button 
                  @click="disableMcp(mcp.server_name || mcp.name)"
                  class="px-3 py-1.5 text-xs font-medium text-red-500 bg-white border border-red-200 rounded-lg hover:bg-red-50 transition-colors"
                >
                  禁用
                </button>
              </div>
            </div>

            <!-- 可用的 MCP（全局模板） -->
            <div v-if="availableMcps.length > 0" class="space-y-3">
              <h3 class="text-sm font-semibold text-gray-600">可添加 ({{ availableMcps.length }})</h3>
              <div 
                v-for="mcp in availableMcps" 
                :key="mcp.server_name"
                class="flex items-center justify-between p-4 bg-white/50 border border-gray-200 rounded-xl hover:border-blue-300 transition-colors"
              >
                <div class="flex items-center gap-3">
                  <span class="w-8 h-8 bg-gray-100 rounded-lg flex items-center justify-center text-gray-400">🔌</span>
                  <div>
                    <div class="font-medium text-gray-800">{{ mcp.server_name }}</div>
                    <div class="text-xs text-gray-500">{{ mcp.description || '暂无描述' }}</div>
                  </div>
                </div>
                <button 
                  @click="enableMcp(mcp.server_name)"
                  class="px-3 py-1.5 text-xs font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors"
                >
                  启用
                </button>
              </div>
            </div>

            <div v-if="enabledMcps.length === 0 && availableMcps.length === 0" class="text-center py-8 text-gray-400">
              <span class="text-3xl block mb-2">🔌</span>
              <p class="text-sm">暂无可用的 MCP 工具</p>
              <p class="text-xs mt-1">在 config.yaml 的 mcp_tools 中配置</p>
            </div>
          </div>

          <!-- REST APIs -->
          <div class="bg-white/60 backdrop-blur-sm border border-white/40 rounded-2xl p-6 space-y-6">
            <div>
              <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2">
                🌐 REST APIs
              </h2>
              <p class="text-sm text-gray-500 mt-1">通过 api_calling 工具调用的 REST 接口</p>
            </div>

            <div v-if="agent?.apis?.length > 0" class="space-y-3">
              <div 
                v-for="api in agent.apis" 
                :key="api.name"
                class="flex items-center justify-between p-4 bg-blue-50/50 border border-blue-200 rounded-xl"
              >
                <div class="flex items-center gap-3">
                  <span class="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center text-blue-600">🌐</span>
                  <div>
                    <div class="font-medium text-gray-800">{{ api.name }}</div>
                    <div class="text-xs text-gray-500">{{ api.description || '暂无描述' }}</div>
                    <div class="text-xs text-gray-400 mt-1 font-mono">{{ api.base_url }}</div>
                  </div>
                </div>
                <span class="px-2 py-1 text-xs bg-blue-100 text-blue-700 rounded-md">{{ api.auth_type || 'none' }}</span>
              </div>
            </div>

            <div v-else class="text-center py-8 text-gray-400">
              <span class="text-3xl block mb-2">🌐</span>
              <p class="text-sm">暂无 REST API 配置</p>
              <p class="text-xs mt-1">在 config.yaml 的 apis 中配置</p>
            </div>
          </div>
        </div>

        <!-- 危险操作 -->
        <div v-if="activeTab === 'danger'" class="max-w-3xl space-y-6">
          <div class="bg-red-50/50 backdrop-blur-sm border border-red-200 rounded-2xl p-6 space-y-6">
            <h2 class="text-lg font-bold text-red-700 flex items-center gap-2">
              ⚠️ 危险操作
            </h2>
            
            <div class="p-4 bg-white/80 rounded-xl border border-red-100">
              <h3 class="font-semibold text-gray-800 mb-2">删除智能体</h3>
              <p class="text-sm text-gray-500 mb-4">此操作将永久删除该智能体的所有配置文件，无法恢复。</p>
              <button 
                @click="deleteAgent"
                :disabled="deleting"
                class="px-5 py-2.5 bg-red-500 text-white text-sm font-medium rounded-xl hover:bg-red-600 transition-all disabled:opacity-50"
              >
                {{ deleting ? '删除中...' : '删除智能体' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '@/api/index'

const router = useRouter()
const route = useRoute()

// 从路由获取 agent_id
const agentId = computed(() => route.params.agentId)

// 状态
const loading = ref(true)
const saving = ref(false)
const reloading = ref(false)
const deleting = ref(false)
const agent = ref(null)
const activeTab = ref('basic')

// 原始数据（用于检测变更）
const originalData = ref(null)

// 表单数据
const form = reactive({
  name: '',
  description: '',
  version: '1.0.0',
  is_active: true,
  prompt: '',
  model: 'claude-3-5-sonnet-20241022',
  max_turns: 20,
  plan_manager_enabled: false,
  enabled_capabilities: {
    web_search: false,
    knowledge_search: false,
    code_execution: false,
    file_operations: false,
  }
})

// MCP 数据
const enabledMcps = ref([])
const availableMcps = ref([])

// 标签页配置
const tabs = [
  { id: 'basic', label: '基础信息', icon: '📋' },
  { id: 'prompt', label: '提示词', icon: '✍️' },
  { id: 'model', label: '模型配置', icon: '🧠' },
  { id: 'tools', label: '工具配置', icon: '🔧' },
  { id: 'danger', label: '危险操作', icon: '⚠️' },
]

// 可用能力列表
const availableCapabilities = [
  { id: 'web_search', label: '网络搜索', icon: '🌐', description: '允许搜索互联网获取信息' },
  { id: 'knowledge_search', label: '知识库检索', icon: '📚', description: '从用户知识库中检索相关内容' },
  { id: 'code_execution', label: '代码执行', icon: '💻', description: '在沙盒环境中执行代码' },
  { id: 'file_operations', label: '文件操作', icon: '📁', description: '读写文件系统' },
]

// 检测是否有变更
const hasChanges = computed(() => {
  if (!originalData.value) return false
  return JSON.stringify(form) !== JSON.stringify(originalData.value)
})

// 加载 Agent 详情
const fetchAgent = async () => {
  try {
    loading.value = true
    
    // 并行获取详情和 prompt
    const [detailResponse, promptResponse] = await Promise.all([
      api.get(`/v1/agents/${agentId.value}`),
      api.get(`/v1/agents/${agentId.value}/prompt`).catch(() => ({ data: { prompt: '' } }))
    ])
    
    agent.value = detailResponse.data
    
    // 填充表单
    form.name = detailResponse.data.name || agentId.value
    form.description = detailResponse.data.description || ''
    form.version = detailResponse.data.version || '1.0.0'
    form.is_active = detailResponse.data.is_active ?? true
    form.model = detailResponse.data.model || 'claude-3-5-sonnet-20241022'
    form.max_turns = detailResponse.data.max_turns || 20
    form.plan_manager_enabled = detailResponse.data.plan_manager_enabled || false
    
    // 处理 enabled_capabilities（后端现在返回对象格式）
    if (detailResponse.data.enabled_capabilities && typeof detailResponse.data.enabled_capabilities === 'object') {
      form.enabled_capabilities = {
        web_search: !!detailResponse.data.enabled_capabilities.web_search,
        knowledge_search: !!detailResponse.data.enabled_capabilities.knowledge_search,
        code_execution: !!detailResponse.data.enabled_capabilities.code_execution,
        file_operations: !!detailResponse.data.enabled_capabilities.file_operations,
      }
    }
    
    // 加载 Prompt
    form.prompt = promptResponse.data.prompt || ''
    
    // 保存原始数据
    originalData.value = JSON.parse(JSON.stringify(form))
    
  } catch (error) {
    console.error('获取 Agent 详情失败:', error)
    alert('获取 Agent 详情失败')
    router.push('/agents')
  } finally {
    loading.value = false
  }
}

// 加载 MCP 列表
const fetchMcps = async () => {
  try {
    // 已启用的 MCP 从 agent 详情获取（config.yaml 中定义的）
    enabledMcps.value = agent.value?.mcp_tools || []
    
    // 获取全局可用的 MCP 模板
    const availableResponse = await api.get(`/v1/agents/${agentId.value}/mcp/available`)
    // 过滤掉已启用的
    const enabledNames = new Set(enabledMcps.value.map(m => m.name || m.server_name))
    availableMcps.value = (availableResponse.data.mcps || []).filter(
      mcp => !enabledNames.has(mcp.server_name) && !mcp.is_enabled_by_agent
    )
  } catch (error) {
    console.error('获取 MCP 列表失败:', error)
    // 至少显示 agent 详情中的 MCP
    enabledMcps.value = agent.value?.mcp_tools || []
  }
}

const fetchAvailableMcps = fetchMcps

// 保存更改
const saveChanges = async () => {
  try {
    saving.value = true
    
    // 构建更新数据
    const updateData = {
      description: form.description,
      model: form.model,
      max_turns: form.max_turns,
      plan_manager_enabled: form.plan_manager_enabled,
      enabled_capabilities: form.enabled_capabilities,
      is_active: form.is_active,
    }
    
    // 如果 prompt 有变化，也一起保存
    if (form.prompt !== originalData.value?.prompt) {
      updateData.prompt = form.prompt
    }
    
    await api.put(`/v1/agents/${agentId.value}`, updateData)
    
    // 更新原始数据
    originalData.value = JSON.parse(JSON.stringify(form))
    
    alert('保存成功！')
  } catch (error) {
    console.error('保存失败:', error)
    alert('保存失败: ' + (error.response?.data?.detail?.message || error.message))
  } finally {
    saving.value = false
  }
}

// 热重载
const reloadAgent = async () => {
  try {
    reloading.value = true
    await api.post(`/v1/agents/${agentId.value}/reload`)
    await fetchAgent()
    alert('热重载成功！')
  } catch (error) {
    console.error('热重载失败:', error)
    alert('热重载失败: ' + (error.response?.data?.detail?.message || error.message))
  } finally {
    reloading.value = false
  }
}

// 删除 Agent
const deleteAgent = async () => {
  if (!confirm(`确定要删除智能体 "${agentId.value}" 吗？此操作无法恢复！`)) return
  
  try {
    deleting.value = true
    await api.delete(`/v1/agents/${agentId.value}`)
    alert('删除成功！')
    router.push('/agents')
  } catch (error) {
    console.error('删除失败:', error)
    alert('删除失败: ' + (error.response?.data?.detail?.message || error.message))
  } finally {
    deleting.value = false
  }
}

// 切换能力
const toggleCapability = (capId) => {
  form.enabled_capabilities[capId] = !form.enabled_capabilities[capId]
}

// 启用 MCP
const enableMcp = async (serverName) => {
  try {
    await api.post(`/v1/agents/${agentId.value}/mcp/${serverName}`, {})
    await fetchMcps()
  } catch (error) {
    console.error('启用 MCP 失败:', error)
    alert('启用 MCP 失败: ' + (error.response?.data?.detail?.message || error.message))
  }
}

// 禁用 MCP
const disableMcp = async (serverName) => {
  if (!confirm(`确定要禁用 MCP "${serverName}" 吗？`)) return
  
  try {
    await api.delete(`/v1/agents/${agentId.value}/mcp/${serverName}`)
    await fetchMcps()
  } catch (error) {
    console.error('禁用 MCP 失败:', error)
    alert('禁用 MCP 失败: ' + (error.response?.data?.detail?.message || error.message))
  }
}

// 生命周期
onMounted(async () => {
  await fetchAgent()
  await fetchMcps()
})

// 监听路由变化
watch(() => route.params.agentId, async (newId) => {
  if (newId) {
    await fetchAgent()
    await fetchMcps()
  }
})
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

/* 滚动条优化 */
.scrollbar-thin::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-thin::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.3);
  border-radius: 3px;
}
.scrollbar-thin::-webkit-scrollbar-thumb:hover {
  background-color: rgba(156, 163, 175, 0.5);
}
</style>


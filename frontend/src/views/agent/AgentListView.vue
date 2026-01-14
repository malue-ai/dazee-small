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
      <div class="flex items-center gap-6">
        <h1 class="text-lg font-bold flex items-center gap-2 text-gray-800">
          <span class="text-2xl">🤖</span> 智能体管理
        </h1>
        <!-- 搜索框 -->
        <div class="relative">
          <span class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">🔍</span>
          <input 
            v-model="searchQuery" 
            type="text" 
            placeholder="搜索智能体..."
            class="pl-9 pr-4 py-2 w-64 bg-white/60 border border-white/40 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm placeholder-gray-400"
          >
        </div>
      </div>
      <div class="flex items-center gap-3">
        <button 
          @click="fetchAgents" 
          :disabled="loading"
          class="p-2.5 bg-white/60 border border-white/40 rounded-xl text-gray-600 hover:bg-white hover:text-blue-600 transition-all shadow-sm"
          title="刷新"
        >
          <span :class="loading ? 'animate-spin inline-block' : ''">🔄</span>
        </button>
        <button 
          @click="$router.push('/agents/create')" 
          class="flex items-center gap-2 px-5 py-2.5 bg-gray-900 text-white text-sm font-medium rounded-xl hover:bg-gray-800 transition-all shadow-lg shadow-gray-900/10 transform active:scale-95"
        >
          <span class="text-lg leading-none">＋</span> 创建智能体
        </button>
        <button 
          @click="$router.push('/')" 
          class="px-5 py-2.5 bg-white/60 border border-white/40 text-gray-600 text-sm font-medium rounded-xl hover:bg-white hover:text-gray-900 transition-all shadow-sm"
        >
          ← 返回聊天
        </button>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="flex-1 overflow-y-auto p-8 relative z-10 scrollbar-thin">
      <div v-if="loading" class="flex flex-col items-center justify-center h-[60vh] text-gray-400">
        <div class="w-10 h-10 border-3 border-gray-200 border-t-gray-900 rounded-full animate-spin mb-6"></div>
        <p class="text-sm font-medium">加载智能体列表...</p>
      </div>
      
      <!-- 无智能体状态 -->
      <div v-else-if="agents.length === 0" class="flex flex-col items-center justify-center h-[60vh] text-gray-400">
        <div class="w-24 h-24 bg-white/60 rounded-3xl flex items-center justify-center mb-6 shadow-sm border border-white/40">
          <span class="text-5xl opacity-50">🤖</span>
        </div>
        <h3 class="text-xl font-bold text-gray-800 mb-2">暂无智能体</h3>
        <p class="mb-8 text-gray-500">创建您的第一个智能体来开始使用</p>
        <button 
          @click="$router.push('/agents/create')" 
          class="px-8 py-3 bg-gray-900 text-white font-medium rounded-xl hover:bg-gray-800 transition-all shadow-lg shadow-gray-900/20 transform hover:-translate-y-1"
        >
          创建智能体
        </button>
      </div>

      <!-- 搜索无结果状态 -->
      <div v-else-if="filteredAgents.length === 0 && searchQuery" class="flex flex-col items-center justify-center h-[60vh] text-gray-400">
        <div class="w-24 h-24 bg-white/60 rounded-3xl flex items-center justify-center mb-6 shadow-sm border border-white/40">
          <span class="text-5xl opacity-50">🔍</span>
        </div>
        <h3 class="text-xl font-bold text-gray-800 mb-2">未找到匹配的智能体</h3>
        <p class="mb-4 text-gray-500">尝试使用不同的关键词搜索</p>
        <button 
          @click="searchQuery = ''" 
          class="px-6 py-2 text-blue-600 font-medium hover:text-blue-700"
        >
          清除搜索
        </button>
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        <div 
          v-for="agent in filteredAgents" 
          :key="agent.agent_id" 
          class="group relative bg-white/60 backdrop-blur-sm border border-white/40 rounded-2xl p-6 flex flex-col gap-4 hover:bg-white/80 hover:shadow-xl hover:shadow-gray-200/50 transition-all duration-300 transform hover:-translate-y-1"
        >
          <div class="flex items-start justify-between gap-4">
            <div class="flex items-center gap-4 min-w-0">
              <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 text-white flex items-center justify-center font-bold text-xl flex-shrink-0 shadow-md">
                {{ agent.name[0].toUpperCase() }}
              </div>
              <div class="flex flex-col min-w-0">
                <h3 class="font-bold text-gray-800 truncate text-lg">{{ agent.name }}</h3>
                <span class="text-xs text-gray-400 truncate font-mono opacity-80">{{ agent.agent_id }}</span>
              </div>
            </div>
            <div 
              class="px-2.5 py-1 rounded-full text-[10px] font-bold border uppercase tracking-wide"
              :class="agent.is_active ? 'bg-green-100 text-green-700 border-green-200' : 'bg-gray-100 text-gray-500 border-gray-200'"
            >
              {{ agent.is_active ? 'active' : 'inactive' }}
            </div>
          </div>
          
          <div class="flex-1">
            <p class="text-sm text-gray-500 line-clamp-2 h-10 mb-4 leading-relaxed">{{ agent.description || '暂无描述' }}</p>
            <div class="flex items-center gap-2 text-xs text-gray-500">
              <span class="bg-gray-100/80 px-2.5 py-1 rounded-md border border-gray-200/50 font-mono">v{{ agent.version }}</span>
              <span class="bg-gray-100/80 px-2.5 py-1 rounded-md border border-gray-200/50 truncate max-w-[140px]">{{ agent.model || '默认模型' }}</span>
            </div>
          </div>
          
          <div class="flex items-center gap-3 pt-5 border-t border-gray-100 mt-auto opacity-80 group-hover:opacity-100 transition-opacity">
            <button 
              @click="manageAgent(agent.agent_id)" 
              class="flex-1 py-2 px-4 bg-white border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-colors shadow-sm"
            >
              管理
            </button>
            <button 
              @click="deleteAgent(agent.agent_id)" 
              class="flex-1 py-2 px-4 bg-white border border-gray-200 rounded-lg text-sm font-medium text-red-500 hover:bg-red-50 hover:border-red-200 transition-colors shadow-sm"
            >
              删除
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/index'

const router = useRouter()
const agents = ref([])
const loading = ref(true)
const searchQuery = ref('')

// 搜索过滤
const filteredAgents = computed(() => {
  if (!searchQuery.value.trim()) return agents.value
  
  const query = searchQuery.value.toLowerCase()
  return agents.value.filter(agent => 
    agent.agent_id.toLowerCase().includes(query) ||
    agent.name?.toLowerCase().includes(query) ||
    agent.description?.toLowerCase().includes(query)
  )
})

const fetchAgents = async () => {
  try {
    loading.value = true
    const response = await api.get('/v1/agents')
    agents.value = response.data.agents || []
  } catch (error) {
    console.error('获取智能体列表失败:', error)
    alert('获取智能体列表失败')
  } finally {
    loading.value = false
  }
}

const manageAgent = (agentId) => {
  router.push(`/agents/${agentId}`)
}

const deleteAgent = async (agentId) => {
  if (!confirm(`确定要删除智能体 ${agentId} 吗？`)) return
  
  try {
    await api.delete(`/v1/agents/${agentId}`)
    await fetchAgents() // 刷新列表
  } catch (error) {
    console.error('删除失败:', error)
    alert('删除失败: ' + (error.response?.data?.detail?.message || error.message))
  }
}

onMounted(() => {
  fetchAgents()
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

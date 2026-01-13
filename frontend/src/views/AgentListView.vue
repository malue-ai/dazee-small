<template>
  <div class="agent-view">
    <!-- 顶部导航 -->
    <div class="top-bar">
      <div class="left-section">
        <h1 class="page-title">🤖 智能体管理</h1>
      </div>
      <div class="right-section">
        <button @click="$router.push('/agents/create')" class="create-btn">
          <span class="icon">＋</span> 创建智能体
        </button>
        <button @click="$router.push('/')" class="back-button">
          ← 返回聊天
        </button>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="main-content">
      <div v-if="loading" class="loading-state">
        <div class="spinner"></div>
        <p>加载智能体列表...</p>
      </div>
      
      <div v-else-if="agents.length === 0" class="empty-state">
        <div class="empty-icon">🤖</div>
        <h3>暂无智能体</h3>
        <p>创建您的第一个智能体来开始使用</p>
        <button @click="$router.push('/agents/create')" class="primary-btn">
          创建智能体
        </button>
      </div>

      <div v-else class="agent-grid">
        <div v-for="agent in agents" :key="agent.agent_id" class="agent-card">
          <div class="agent-header">
            <div class="agent-icon">{{ agent.name[0].toUpperCase() }}</div>
            <div class="agent-info">
              <h3 class="agent-name">{{ agent.name }}</h3>
              <span class="agent-id">{{ agent.agent_id }}</span>
            </div>
            <div class="agent-status" :class="{ active: agent.is_active }">
              {{ agent.is_active ? '活跃' : '停用' }}
            </div>
          </div>
          
          <div class="agent-body">
            <p class="agent-desc">{{ agent.description || '暂无描述' }}</p>
            <div class="agent-meta">
              <span class="version">v{{ agent.version }}</span>
              <span class="model">{{ agent.model || '默认模型' }}</span>
            </div>
          </div>
          
          <div class="agent-footer">
            <button @click="manageAgent(agent.agent_id)" class="action-btn">管理</button>
            <button @click="deleteAgent(agent.agent_id)" class="action-btn delete">删除</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { AGENT_API } from '@/api/config'

const router = useRouter()
const agents = ref([])
const loading = ref(true)

const fetchAgents = async () => {
  try {
    loading.value = true
    const response = await axios.get(AGENT_API.LIST)
    agents.value = response.data.agents
  } catch (error) {
    console.error('获取智能体列表失败:', error)
    alert('获取智能体列表失败')
  } finally {
    loading.value = false
  }
}

const manageAgent = (agentId) => {
  // TODO: 实现编辑/详情页面
  alert(`管理功能开发中: ${agentId}`)
}

const deleteAgent = async (agentId) => {
  if (!confirm(`确定要删除智能体 ${agentId} 吗？`)) return
  
  try {
    await axios.delete(AGENT_API.DELETE(agentId))
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
.agent-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: #f5f7f9;
}

.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  background-color: white;
  border-bottom: 1px solid #e1e4e8;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.page-title {
  font-size: 1.5rem;
  font-weight: 600;
  color: #1a202c;
  margin: 0;
}

.right-section {
  display: flex;
  gap: 1rem;
}

.create-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background-color: #3182ce;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.2s;
}

.create-btn:hover {
  background-color: #2c5282;
}

.back-button {
  padding: 0.5rem 1rem;
  background-color: white;
  border: 1px solid #e2e8f0;
  color: #4a5568;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.back-button:hover {
  background-color: #f7fafc;
  border-color: #cbd5e0;
}

.main-content {
  flex: 1;
  padding: 2rem;
  overflow-y: auto;
}

.agent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1.5rem;
}

.agent-card {
  background: white;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  transition: transform 0.2s, box-shadow 0.2s;
}

.agent-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.agent-header {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.agent-icon {
  width: 40px;
  height: 40px;
  background-color: #ebf8ff;
  color: #3182ce;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 1.2rem;
}

.agent-info {
  flex: 1;
  min-width: 0;
}

.agent-name {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: #2d3748;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-id {
  font-size: 0.85rem;
  color: #718096;
}

.agent-status {
  font-size: 0.75rem;
  padding: 0.2rem 0.5rem;
  border-radius: 999px;
  background-color: #edf2f7;
  color: #718096;
}

.agent-status.active {
  background-color: #c6f6d5;
  color: #276749;
}

.agent-body {
  flex: 1;
}

.agent-desc {
  color: #4a5568;
  font-size: 0.9rem;
  margin-bottom: 1rem;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.agent-meta {
  display: flex;
  gap: 0.5rem;
  font-size: 0.8rem;
  color: #718096;
}

.agent-meta span {
  background: #f7fafc;
  padding: 2px 6px;
  border-radius: 4px;
}

.agent-footer {
  display: flex;
  gap: 0.5rem;
  border-top: 1px solid #e2e8f0;
  padding-top: 1rem;
  margin-top: auto;
}

.action-btn {
  flex: 1;
  padding: 0.5rem;
  border: 1px solid #e2e8f0;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
  color: #4a5568;
  transition: all 0.2s;
}

.action-btn:hover {
  background-color: #f7fafc;
  color: #2d3748;
}

.action-btn.delete:hover {
  background-color: #fff5f5;
  color: #e53e3e;
  border-color: #feb2b2;
}

.loading-state, .empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 400px;
  color: #718096;
}

.spinner {
  border: 3px solid #f3f3f3;
  border-radius: 50%;
  border-top: 3px solid #3182ce;
  width: 24px;
  height: 24px;
  animation: spin 1s linear infinite;
  margin-bottom: 1rem;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.empty-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.primary-btn {
  margin-top: 1rem;
  padding: 0.6rem 1.2rem;
  background-color: #3182ce;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
}
</style>

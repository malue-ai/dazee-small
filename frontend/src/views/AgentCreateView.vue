<template>
  <div class="agent-create-view">
    <div class="top-bar">
      <div class="left-section">
        <h1 class="page-title">创建新智能体</h1>
      </div>
      <div class="right-section">
        <button @click="$router.push('/agents')" class="back-button">
          ← 返回列表
        </button>
      </div>
    </div>

    <div class="main-content">
      <div class="form-container">
        <!-- 步骤条 -->
        <div class="steps">
          <div class="step" :class="{ active: currentStep === 1, completed: currentStep > 1 }">
            <div class="step-number">1</div>
            <div class="step-label">基础信息</div>
          </div>
          <div class="step-line"></div>
          <div class="step" :class="{ active: currentStep === 2, completed: currentStep > 2 }">
            <div class="step-number">2</div>
            <div class="step-label">能力配置</div>
          </div>
          <div class="step-line"></div>
          <div class="step" :class="{ active: currentStep === 3 }">
            <div class="step-number">3</div>
            <div class="step-label">MCP 工具</div>
          </div>
        </div>

        <!-- 步骤 1: 基础信息 -->
        <div v-if="currentStep === 1" class="step-content">
          <div class="form-group">
            <label>Agent ID <span class="required">*</span></label>
            <input 
              v-model="form.agent_id" 
              type="text" 
              placeholder="例如: coding_assistant"
              :class="{ error: errors.agent_id }"
            >
            <span class="hint">唯一标识符，仅支持小写字母、数字和下划线</span>
          </div>

          <div class="form-group">
            <label>名称</label>
            <input v-model="form.name" type="text" placeholder="给智能体起个名字">
          </div>

          <div class="form-group">
            <label>描述</label>
            <textarea v-model="form.description" rows="3" placeholder="描述智能体的功能和用途"></textarea>
          </div>

          <div class="form-group">
            <label>系统提示词 (Prompt) <span class="required">*</span></label>
            <textarea 
              v-model="form.prompt" 
              rows="6" 
              placeholder="设定智能体的角色和行为准则..."
              :class="{ error: errors.prompt }"
            ></textarea>
          </div>
        </div>

        <!-- 步骤 2: 能力配置 -->
        <div v-if="currentStep === 2" class="step-content">
          <div class="form-group">
            <label>模型选择</label>
            <select v-model="form.model">
              <option value="claude-3-5-sonnet-20241022">Claude 3.5 Sonnet (推荐)</option>
              <option value="gpt-4o">GPT-4o</option>
              <option value="gemini-1.5-pro">Gemini 1.5 Pro</option>
            </select>
          </div>

          <div class="form-group">
            <label>最大对话轮数</label>
            <input v-model.number="form.max_turns" type="number" min="1" max="100">
          </div>

          <div class="form-group checkbox-group">
            <label class="checkbox-label">
              <input type="checkbox" v-model="form.plan_manager_enabled">
              启用计划管理器 (Plan Manager)
            </label>
            <span class="hint">适合处理复杂的长流程任务</span>
          </div>

          <div class="capabilities-section">
            <h3>基础能力</h3>
            <div class="capability-grid">
              <label class="capability-item">
                <input type="checkbox" v-model="form.enabled_capabilities.web_search">
                <span class="cap-name">🌐 网络搜索</span>
              </label>
              <label class="capability-item">
                <input type="checkbox" v-model="form.enabled_capabilities.knowledge_search">
                <span class="cap-name">📚 知识库检索</span>
              </label>
              <label class="capability-item">
                <input type="checkbox" v-model="form.enabled_capabilities.code_execution">
                <span class="cap-name">💻 代码执行</span>
              </label>
            </div>
          </div>
        </div>

        <!-- 步骤 3: MCP 工具 -->
        <div v-if="currentStep === 3" class="step-content">
          <div v-if="loadingMcps" class="loading-text">加载 MCP 列表中...</div>
          <div v-else class="mcp-list">
            <div v-for="mcp in availableMcps" :key="mcp.server_name" class="mcp-item">
              <div class="mcp-header">
                <label class="checkbox-label">
                  <input type="checkbox" :value="mcp.server_name" v-model="selectedMcps">
                  <span class="mcp-name">{{ mcp.server_name }}</span>
                </label>
                <span class="mcp-url">{{ mcp.server_url }}</span>
              </div>
              <p class="mcp-desc">{{ mcp.description || '暂无描述' }}</p>
              
              <!-- 认证配置（如果选中且需要认证） -->
              <div v-if="selectedMcps.includes(mcp.server_name) && mcp.auth_type !== 'none'" class="mcp-config">
                <div class="form-group small">
                  <label>认证环境变量 (Auth Env)</label>
                  <input 
                    type="text" 
                    v-model="mcpAuthConfigs[mcp.server_name]"
                    :placeholder="mcp.auth_env || '例如: NOTION_API_KEY'"
                  >
                </div>
              </div>
            </div>
          </div>
          
          <div v-if="availableMcps.length === 0 && !loadingMcps" class="empty-text">
            没有可用的 MCP 工具。请联系管理员添加。
          </div>
        </div>

        <!-- 底部按钮 -->
        <div class="form-actions">
          <button 
            v-if="currentStep > 1" 
            @click="currentStep--" 
            class="secondary-btn"
          >
            上一步
          </button>
          
          <button 
            v-if="currentStep < 3" 
            @click="nextStep" 
            class="primary-btn"
          >
            下一步
          </button>
          
          <button 
            v-if="currentStep === 3" 
            @click="submitForm" 
            class="primary-btn submit" 
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
import axios from 'axios'
import { AGENT_API, MCP_API } from '@/api/config'

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
    const response = await axios.get(MCP_API.LIST)
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
    
    await axios.post(AGENT_API.CREATE, agentData)
    
    // 2. 关联选中的 MCP
    if (selectedMcps.value.length > 0) {
      for (const serverName of selectedMcps.value) {
        try {
          const authEnv = mcpAuthConfigs[serverName]
          await axios.post(AGENT_API.MCP.ENABLE(form.agent_id, serverName), {
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
.agent-create-view {
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
}

.page-title {
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0;
}

.back-button {
  padding: 0.5rem 1rem;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  cursor: pointer;
}

.main-content {
  flex: 1;
  padding: 2rem;
  overflow-y: auto;
  display: flex;
  justify-content: center;
}

.form-container {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  padding: 2rem;
  width: 100%;
  max-width: 800px;
  display: flex;
  flex-direction: column;
}

/* 步骤条 */
.steps {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 2rem;
  padding: 0 1rem;
}

.step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  position: relative;
  z-index: 1;
}

.step-number {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #e2e8f0;
  color: #718096;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  transition: all 0.3s;
}

.step.active .step-number {
  background: #3182ce;
  color: white;
}

.step.completed .step-number {
  background: #48bb78;
  color: white;
}

.step-label {
  font-size: 0.9rem;
  color: #718096;
}

.step-line {
  flex: 1;
  height: 2px;
  background: #e2e8f0;
  margin: 0 1rem;
  position: relative;
  top: -14px;
}

/* 表单样式 */
.step-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-group label {
  font-weight: 500;
  color: #2d3748;
}

.required {
  color: #e53e3e;
}

input[type="text"],
input[type="number"],
select,
textarea {
  padding: 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 1rem;
  transition: border-color 0.2s;
}

input:focus,
textarea:focus,
select:focus {
  outline: none;
  border-color: #3182ce;
  box-shadow: 0 0 0 3px rgba(49, 130, 206, 0.1);
}

.error {
  border-color: #e53e3e !important;
}

.hint {
  font-size: 0.85rem;
  color: #718096;
}

.checkbox-group {
  flex-direction: row;
  align-items: center;
  gap: 1rem;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
}

/* 能力配置 */
.capability-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
  margin-top: 0.5rem;
}

.capability-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 1rem;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.capability-item:hover {
  background-color: #f7fafc;
  border-color: #cbd5e0;
}

/* MCP 列表 */
.mcp-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.mcp-item {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 1rem;
}

.mcp-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.mcp-name {
  font-weight: 600;
  color: #2d3748;
}

.mcp-url {
  font-size: 0.85rem;
  color: #718096;
  background: #f7fafc;
  padding: 2px 6px;
  border-radius: 4px;
}

.mcp-desc {
  font-size: 0.9rem;
  color: #4a5568;
  margin-bottom: 0.5rem;
}

.mcp-config {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px dashed #e2e8f0;
}

.form-group.small {
  margin-bottom: 0;
}

.form-group.small input {
  padding: 0.5rem;
  font-size: 0.9rem;
}

/* 底部按钮 */
.form-actions {
  margin-top: 2rem;
  padding-top: 2rem;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
}

.primary-btn, .secondary-btn {
  padding: 0.75rem 1.5rem;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
}

.primary-btn {
  background-color: #3182ce;
  color: white;
  border: none;
}

.primary-btn:hover {
  background-color: #2c5282;
}

.primary-btn:disabled {
  background-color: #a0aec0;
  cursor: not-allowed;
}

.secondary-btn {
  background-color: white;
  color: #4a5568;
  border: 1px solid #e2e8f0;
}

.secondary-btn:hover {
  background-color: #f7fafc;
}
</style>

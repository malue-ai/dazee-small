<template>
  <div class="chat-layout">
    <!-- 侧边栏 -->
    <div class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <h2>🤖 ZenFlux</h2>
        <button @click="sidebarCollapsed = !sidebarCollapsed" class="collapse-btn">
          {{ sidebarCollapsed ? '→' : '←' }}
        </button>
      </div>

      <div v-if="!sidebarCollapsed" class="sidebar-content">
        <button @click="$router.push('/knowledge')" class="sidebar-button primary">
          📚 知识库
        </button>
        <button @click="createNewConversation" class="sidebar-button">
          ➕ 新建对话
        </button>

        <!-- 🆕 对话列表 -->
        <div class="conversations-section">
          <h3 class="section-title">对话列表</h3>
          <div v-if="loadingConversations" class="loading-text">加载中...</div>
          <div v-else-if="conversations.length === 0" class="empty-text">暂无对话</div>
          <div v-else class="conversation-list">
            <div
              v-for="conv in conversations"
              :key="conv.id"
              class="conversation-item"
              :class="{ active: conv.id === chatStore.conversationId }"
              @click="loadConversation(conv.id)"
            >
              <div class="conversation-content">
              <div class="conversation-title">{{ conv.title }}</div>
              <div class="conversation-info">
                <span class="message-count">{{ conv.message_count }} 条</span>
                <span class="last-time">{{ formatShortTime(conv.updated_at) }}</span>
              </div>
              </div>
              <!-- 删除按钮 -->
              <button 
                class="delete-btn"
                @click.stop="confirmDeleteConversation(conv)"
                title="删除对话"
              >
                🗑️
              </button>
            </div>
          </div>
        </div>

        <div class="user-info">
          <div class="user-id">用户: {{ userId }}</div>
        </div>
      </div>
    </div>

    <!-- 主要内容区域 -->
    <div class="main-content" :class="{ 'with-workspace': showWorkspacePanel && chatStore.conversationId }">
      <!-- 知识库面板 -->
      <div v-if="showKnowledgePanel" class="knowledge-panel">
        <div class="panel-header">
          <h3>知识库管理</h3>
          <button @click="showKnowledgePanel = false" class="close-btn">✕</button>
        </div>
        <div class="panel-body">
          <KnowledgeUpload :user-id="userId" />
        </div>
      </div>

      <!-- 聊天区域 -->
      <div class="chat-container">
        <div class="chat-header">
          <div class="header-content">
            <h1>智能 AI 对话助手</h1>
            <p class="subtitle">
              支持知识库检索、多轮对话、工具调用
              <span v-if="chatStore.conversationId" class="conversation-badge">
                对话ID: {{ chatStore.conversationId.slice(5, 13) }}
              </span>
            </p>
          </div>
          <!-- 工作区切换按钮 -->
          <button 
            v-if="chatStore.conversationId"
            @click="showWorkspacePanel = !showWorkspacePanel" 
            class="workspace-toggle-btn"
            :class="{ active: showWorkspacePanel }"
          >
            {{ showWorkspacePanel ? '📂 隐藏文件' : '📁 查看文件' }}
          </button>
        </div>

        <div class="chat-messages" ref="messagesContainer">
          <!-- 欢迎消息 -->
          <Card v-if="messages.length === 0" variant="primary" class="welcome-card">
            <div class="welcome-content">
              <div class="welcome-icon">👋</div>
              <h2>欢迎使用 ZenFlux Agent</h2>
              <p>我可以帮你：</p>
              <ul>
                <li>💬 智能对话和问答</li>
                <li>📊 生成 PPT 演示文稿</li>
                <li>🔍 搜索和检索信息</li>
                <li>📚 基于知识库回答问题</li>
              </ul>
              <p class="hint">试着问我一些问题吧！</p>
            </div>
          </Card>

          <!-- 消息列表 -->
          <div
            v-for="message in messages"
            :key="message.id"
            :class="['message', message.role === 'user' ? 'user-message' : 'assistant-message']"
          >
            <div class="message-avatar">
              {{ message.role === 'user' ? '👤' : '🤖' }}
            </div>
            <Card class="message-card" :variant="message.role === 'user' ? 'default' : 'primary'">
              <!-- 用户消息：简单文本 -->
              <template v-if="message.role === 'user'">
                <div class="message-text">{{ message.content }}</div>
              </template>
              
              <!-- 助手消息：支持多种内容块 -->
              <template v-else>
                <!-- 如果有原始内容块数组，使用 MessageContent 渲染 -->
                <MessageContent 
                  v-if="message.contentBlocks && message.contentBlocks.length > 0"
                  :content="message.contentBlocks"
                  :tool-statuses="message.toolStatuses || {}"
                />
                <!-- 否则使用传统渲染方式 -->
                <template v-else>
                  <!-- 显示 thinking 过程 -->
                  <div v-if="message.thinking" class="thinking-section">
                    <div class="thinking-header">💭 思考过程</div>
                    <div class="thinking-content">{{ message.thinking }}</div>
                  </div>
                  <!-- 显示文本内容 -->
                  <MarkdownRenderer :content="message.content" />
                </template>
                
                <!-- 🆕 Plan 结果 UI -->
                <div v-if="message.planResult" class="special-result plan-result">
                  <div class="result-header">
                    <span class="result-icon">📋</span>
                    <span class="result-title">任务计划</span>
                  </div>
                  <div class="plan-content">
                    <div v-if="message.planResult.goal" class="plan-goal">
                      <strong>目标：</strong>{{ message.planResult.goal }}
                    </div>
                    <div v-if="message.planResult.steps" class="plan-steps">
                      <div 
                        v-for="(step, idx) in message.planResult.steps" 
                        :key="idx"
                        class="plan-step"
                        :class="{ 
                          'completed': step.status === 'completed',
                          'in-progress': step.status === 'in_progress' 
                        }"
                      >
                        <span class="step-number">{{ idx + 1 }}</span>
                        <span class="step-action">{{ step.action || step }}</span>
                        <span v-if="step.status" class="step-status">
                          {{ step.status === 'completed' ? '✅' : step.status === 'in_progress' ? '⏳' : '⬜' }}
                        </span>
                      </div>
                    </div>
                    <!-- 原始内容回退 -->
                    <pre v-if="message.planResult.raw" class="raw-content">{{ message.planResult.raw }}</pre>
                  </div>
                </div>
                
                <!-- 🆕 搜索结果 UI -->
                <div v-if="message.searchResults" class="special-result search-result">
                  <div class="result-header">
                    <span class="result-icon">🔍</span>
                    <span class="result-title">网页搜索结果</span>
                  </div>
                  <div class="search-content">
                    <div v-if="Array.isArray(message.searchResults)" class="search-items">
                      <a 
                        v-for="(item, idx) in message.searchResults.slice(0, 5)" 
                        :key="idx"
                        :href="item.url || item.link"
                        target="_blank"
                        class="search-item"
                      >
                        <span class="item-title">{{ item.title || item.name }}</span>
                        <span class="item-snippet">{{ item.snippet || item.description }}</span>
                      </a>
                    </div>
                    <!-- 原始内容回退 -->
                    <pre v-else class="raw-content">{{ JSON.stringify(message.searchResults, null, 2) }}</pre>
                  </div>
                </div>
                
                <!-- 🆕 知识库结果 UI -->
                <div v-if="message.knowledgeResults" class="special-result knowledge-result">
                  <div class="result-header">
                    <span class="result-icon">📚</span>
                    <span class="result-title">知识库检索结果</span>
                  </div>
                  <div class="knowledge-content">
                    <div v-if="Array.isArray(message.knowledgeResults)" class="knowledge-items">
                      <div 
                        v-for="(item, idx) in message.knowledgeResults.slice(0, 5)" 
                        :key="idx"
                        class="knowledge-item"
                      >
                        <div class="item-source">
                          📄 {{ item.source || item.filename || '文档' }}
                          <span v-if="item.score" class="item-score">相关度: {{ (item.score * 100).toFixed(0) }}%</span>
                        </div>
                        <div class="item-content">{{ item.content || item.text }}</div>
                      </div>
                    </div>
                    <!-- 原始内容回退 -->
                    <pre v-else class="raw-content">{{ JSON.stringify(message.knowledgeResults, null, 2) }}</pre>
                  </div>
                </div>
                
                <!-- 🆕 推荐问题 UI -->
                <div v-if="message.recommendedQuestions && message.recommendedQuestions.length > 0" class="recommended-questions">
                  <div class="recommended-header">💡 您可能还想问：</div>
                  <div class="recommended-list">
                    <button 
                      v-for="(question, idx) in message.recommendedQuestions" 
                      :key="idx"
                      class="recommended-btn"
                      @click="askRecommendedQuestion(question)"
                    >
                      {{ question }}
                    </button>
                  </div>
                </div>
              </template>
              
              <div class="message-time">{{ formatTime(message.timestamp) }}</div>
            </Card>
          </div>

          <!-- 加载指示器 -->
          <div v-if="isLoading" class="message assistant-message">
            <div class="message-avatar">🤖</div>
            <Card class="message-card" variant="primary">
              <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </Card>
          </div>
        </div>

        <div class="chat-input-container">
          <div class="chat-input-wrapper">
            <textarea
              v-model="inputMessage"
              @keydown.enter.exact="handleEnter"
              @compositionstart="isComposing = true"
              @compositionend="isComposing = false"
              placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
              class="chat-input"
              rows="1"
              ref="inputTextarea"
              :disabled="isLoading"
            ></textarea>
            <!-- 🆕 停止按钮（AI 正在回复时显示） -->
            <button
              v-if="isLoading"
              @click="stopGeneration"
              :disabled="isStopping"
              class="stop-button"
            >
              <span v-if="!isStopping">⏸️ 停止</span>
              <span v-else>停止中...</span>
            </button>
            <!-- 发送按钮（正常状态显示） -->
            <button
              v-else
              @click="sendMessage"
              :disabled="!inputMessage.trim()"
              class="send-button"
            >
              发送 📤
            </button>
          </div>
        </div>
      </div>
      
      <!-- 🆕 工作区文件面板 -->
      <div v-if="showWorkspacePanel && chatStore.conversationId" class="workspace-panel">
        <!-- 文件浏览器 -->
        <div class="workspace-explorer" :class="{ 'with-preview': previewFile }">
          <FileExplorer 
            :conversation-id="chatStore.conversationId"
            @file-select="handleFileSelect"
            @project-click="handleProjectClick"
            @run-project="handleRunProject"
          />
        </div>
        
        <!-- 文件预览 -->
        <div v-if="previewFile" class="workspace-preview">
          <FilePreview
            :conversation-id="chatStore.conversationId"
            :file-path="previewFile.path"
            @close="closePreview"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import Card from '@/components/Card.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import MessageContent from '@/components/MessageContent.vue'
import KnowledgeUpload from '@/components/KnowledgeUpload.vue'
import FileExplorer from '@/components/FileExplorer.vue'
import FilePreview from '@/components/FilePreview.vue'

const router = useRouter()
const route = useRoute()
const chatStore = useChatStore()
const messages = ref([])
const inputMessage = ref('')
const isLoading = ref(false)
const isComposing = ref(false)  // 中文输入法状态
const messagesContainer = ref(null)
const inputTextarea = ref(null)
const sidebarCollapsed = ref(false)
const showKnowledgePanel = ref(false)
const userId = ref('')

// 🆕 对话列表相关状态
const conversations = ref([])
const loadingConversations = ref(false)

// 🆕 停止控制相关状态
const currentSessionId = ref(null)
const isStopping = ref(false)

// 🆕 工作区面板状态
const showWorkspacePanel = ref(false)
const previewFile = ref(null)  // 当前预览的文件

// 🆕 删除对话相关状态
const showDeleteConfirm = ref(false)
const conversationToDelete = ref(null)

// 🔧 辅助函数：从 Claude API 格式提取文本
function extractTextFromContent(content) {
  // 如果已经是字符串，直接返回
  if (typeof content === 'string') {
    return content
  }
  
  // 如果是数组（Claude API 格式）
  if (Array.isArray(content)) {
    const textBlocks = content.filter(block => block.type === 'text')
    return textBlocks.map(block => block.text).join('\n')
  }
  
  // 其他情况
  return String(content)
}

// 🔧 辅助函数：从 Claude API 格式提取 thinking 内容
function extractThinkingFromContent(content) {
  // 如果是数组（Claude API 格式），提取 thinking block
  if (Array.isArray(content)) {
    const thinkingBlock = content.find(block => block.type === 'thinking')
    return thinkingBlock?.thinking || ''
  }
  
  // 非数组格式，没有 thinking
  return ''
}

// 🆕 辅助函数：解析内容块数组
function parseContentBlocks(content) {
  // 如果已经是数组，直接返回
  if (Array.isArray(content)) {
    return content
  }
  
  // 如果是字符串，尝试解析 JSON
  if (typeof content === 'string') {
    try {
      const parsed = JSON.parse(content)
      if (Array.isArray(parsed)) {
        return parsed
      }
    } catch {
      // 解析失败，返回空数组（会使用 content 文本渲染）
    }
  }
  
  // 其他情况返回空数组
  return []
}

onMounted(async () => {
  // 初始化用户ID
  userId.value = chatStore.initUserId()
  
  // 🆕 加载对话列表
  await loadConversationList()
  
  // 🆕 检查路由参数，如果有 conversationId 则自动加载
  const conversationId = route.params.conversationId
  if (conversationId) {
    console.log('📂 从路由加载对话:', conversationId)
    await loadConversation(conversationId)
  }
})

// 🆕 监听路由变化
watch(() => route.params.conversationId, async (newId) => {
  if (newId) {
    console.log('📂 路由变化，加载对话:', newId)
    await loadConversation(newId)
  }
})

// 自动调整输入框高度
watch(inputMessage, () => {
  nextTick(() => {
    if (inputTextarea.value) {
      inputTextarea.value.style.height = 'auto'
      inputTextarea.value.style.height = inputTextarea.value.scrollHeight + 'px'
    }
  })
})

// 🆕 加载对话列表
async function loadConversationList() {
  loadingConversations.value = true
  try {
    const result = await chatStore.getConversationList(20, 0)
    conversations.value = result.conversations
    console.log('✅ 对话列表加载成功:', conversations.value.length)
  } catch (error) {
    console.error('❌ 加载对话列表失败:', error)
  } finally {
    loadingConversations.value = false
  }
}

// 🆕 加载对话历史
async function loadConversation(conversationId) {
  try {
    console.log('📂 加载对话:', conversationId)
    
    // 🛡️ 切换会话时断开当前 SSE 连接（避免事件错乱）
    if (chatStore.isConnected) {
      console.log('🔌 切换会话，断开当前 SSE 连接')
      chatStore.disconnectSSE()
    }
    
    // 重置加载状态
    isLoading.value = false
    currentSessionId.value = null
    
    // 清空当前消息
    messages.value = []
    
    // 设置当前对话ID
    chatStore.conversationId = conversationId
    
    // 🆕 更新 URL（如果当前 URL 不匹配）
    if (route.params.conversationId !== conversationId) {
      router.push({ name: 'conversation', params: { conversationId } })
    }
    
    // 获取历史消息
    const result = await chatStore.getConversationMessages(conversationId, 100, 0, 'asc')
    
    // 转换为消息格式（保留原始内容块，同时提取文本用于简单显示）
    messages.value = result.messages.map(msg => ({
      id: msg.id,
      role: msg.role,
      content: extractTextFromContent(msg.content),  // 提取纯文本（兼容旧格式）
      thinking: extractThinkingFromContent(msg.content),  // 提取 thinking
      contentBlocks: parseContentBlocks(msg.content),  // 🆕 解析原始内容块
      toolStatuses: {},  // 历史消息的工具状态默认为空
      timestamp: new Date(msg.created_at)
    }))
    
    console.log('✅ 历史消息加载成功:', messages.value.length)
    
    // 滚动到底部
    await nextTick()
    scrollToBottom()
  } catch (error) {
    console.error('❌ 加载对话失败:', error)
  }
}

// 🆕 创建新对话
async function createNewConversation() {
  try {
    console.log('➕ 创建新对话')
    
    // 清空消息
    messages.value = []
    
    // 重置对话ID（发送第一条消息时会自动创建）
    chatStore.conversationId = null
    
    // 🆕 跳转到首页
    router.push({ name: 'chat' })
    
    // 刷新对话列表
    await loadConversationList()
  } catch (error) {
    console.error('❌ 创建对话失败:', error)
  }
}

// 🆕 确认删除对话
function confirmDeleteConversation(conv) {
  conversationToDelete.value = conv
  // 使用浏览器原生确认对话框
  const confirmed = confirm(`确定要删除对话 "${conv.title}" 吗？\n\n此操作不可恢复！`)
  if (confirmed) {
    deleteConversation(conv.id)
  }
}

// 🆕 删除对话
async function deleteConversation(conversationId) {
  try {
    console.log('🗑️ 删除对话:', conversationId)
    
    await chatStore.deleteConversation(conversationId)
    
    // 如果删除的是当前对话，跳转到首页
    if (chatStore.conversationId === conversationId) {
      chatStore.conversationId = null
      messages.value = []
      router.push({ name: 'chat' })
    }
    
    // 刷新对话列表
    await loadConversationList()
    
    console.log('✅ 对话删除成功')
  } catch (error) {
    console.error('❌ 删除对话失败:', error)
    alert('删除失败: ' + error.message)
  }
}

// 🆕 点击推荐问题
function askRecommendedQuestion(question) {
  inputMessage.value = question
  sendMessage()
}

// 处理回车键（区分中文输入法）
function handleEnter(event) {
  // 中文输入法正在输入时，不发送（让用户确认拼音）
  if (isComposing.value) {
    return
  }
  // 阻止默认换行，发送消息
  event.preventDefault()
  sendMessage()
}

async function sendMessage() {
  const content = inputMessage.value.trim()
  if (!content || isLoading.value) return

  // 添加用户消息
  const userMessage = {
    id: Date.now(),
    role: 'user',
    content: content,
    timestamp: new Date()
  }
  messages.value.push(userMessage)
  inputMessage.value = ''

  // 重置输入框高度
  if (inputTextarea.value) {
    inputTextarea.value.style.height = 'auto'
  }

  // 滚动到底部
  await nextTick()
  scrollToBottom()

  // 发送到后端（流式）
  isLoading.value = true
  currentSessionId.value = null  // 重置 session_id
  
  try {
    // 🔧 创建助手消息并添加到数组
    messages.value.push({
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
      thinking: '',
      contentBlocks: [],  // 原始内容块数组
      toolStatuses: {},   // 工具调用状态
      // 🆕 特殊工具结果
      recommendedQuestions: [],  // 推荐问题
      planResult: null,          // Plan 结果
      searchResults: null,       // Web 搜索结果
      knowledgeResults: null,    // 知识库搜索结果
      timestamp: new Date()
    })
    
    // 🔧 获取助手消息在数组中的索引（用于响应式更新）
    const assistantMsgIndex = messages.value.length - 1

    // 🆕 使用流式发送（启用标题生成后台任务）
    await chatStore.sendMessageStream(
      content,
      chatStore.conversationId,
      (event) => {
        // 🔧 通过索引获取响应式消息对象
        const assistantMessage = messages.value[assistantMsgIndex]
        
        // 处理流式事件
        console.log('📨 收到事件:', event.type, event)
        
        // ==================== Session 事件 ====================
        
        // 会话开始
        if (event.type === 'session_start') {
          console.log('🔌 会话开始:', event.data)
          // 🆕 记录 session_id（用于停止）
          if (event.data?.session_id) {
            currentSessionId.value = event.data.session_id
            console.log('✅ 记录 session_id:', currentSessionId.value)
          }
        }
        // 会话已停止
        else if (event.type === 'session_stopped') {
          console.log('🛑 会话已停止:', event.data)
          // 添加停止提示
          if (assistantMessage.content) {
            assistantMessage.content += '\n\n_[用户已停止生成]_'
          } else {
            assistantMessage.content = '_[用户已停止生成，未生成内容]_'
          }
          // 重置状态
          isLoading.value = false
          isStopping.value = false
          currentSessionId.value = null
        }
        // 会话结束
        else if (event.type === 'session_end') {
          console.log('✅ 会话结束:', event.data)
          // 会话正常结束，不需要特殊处理
        }
        
        // ==================== Conversation 事件 ====================
        
        // 对话开始
        else if (event.type === 'conversation_start') {
          // 兼容两种数据格式
          const newConversationId = event.data?.conversation?.id || event.data?.conversation_id
          console.log('🆕 对话开始:', newConversationId, event.data)
          
          if (newConversationId) {
          chatStore.conversationId = newConversationId
          
            // 更新 URL
          if (route.params.conversationId !== newConversationId) {
            router.push({ name: 'conversation', params: { conversationId: newConversationId } })
          }
          
          // 刷新对话列表
          loadConversationList()
        }
        }
        // 对话增量更新（统一处理：标题、plan、compression 等）
        else if (event.type === 'conversation_delta') {
          console.log('📝 对话增量更新:', event.data)
          const { conversation_id, delta } = event.data || {}
          
          if (conversation_id && delta) {
            const conv = conversations.value.find(c => c.id === conversation_id)
            if (conv) {
              // 直接合并 delta 到 conversation
              Object.assign(conv, delta)
              
              // 处理 metadata（深度合并）
              if (delta.metadata) {
                conv.metadata = { ...(conv.metadata || {}), ...delta.metadata }
                
                // 🆕 处理 plan 更新
                if (delta.metadata.plan) {
                  console.log('📋 Plan 更新:', delta.metadata.plan)
                  // 可以在这里触发 Plan UI 更新
                }
                
                // 🆕 处理 compression 更新
                if (delta.metadata.compression) {
                  console.log('🗜️ 上下文已压缩:', delta.metadata.compression)
                }
              }
              
              // 处理顶层字段
              if (delta.title) {
                console.log('✅ 对话标题已更新:', delta.title)
              }
            }
          }
        }
        
        // ==================== Message 事件 ====================
        
        // 消息开始
        else if (event.type === 'message_start') {
          console.log('💬 消息开始:', event.data)
        }
        // 🆕 消息增量更新（通用：stop_reason、recommended、plan、search 等）
        else if (event.type === 'message_delta') {
          console.log('💬 消息增量:', event.data)
          const { delta, usage } = event.data || {}
          const deltaType = delta?.type
          
          // 根据 delta.type 分发处理
          if (deltaType === 'plan') {
            // 📋 Plan 更新
            console.log('📋 收到 Plan:', delta.content)
            try {
              const planData = typeof delta.content === 'string' 
                ? JSON.parse(delta.content) 
                : delta.content
              assistantMessage.planResult = planData
            } catch (e) {
              console.warn('解析 Plan 失败:', e)
              assistantMessage.planResult = { raw: delta.content }
            }
          }
          else if (deltaType === 'search') {
            // 🔍 Web 搜索结果
            console.log('🔍 收到搜索结果:', delta.content)
            try {
              const searchData = typeof delta.content === 'string' 
                ? JSON.parse(delta.content) 
                : delta.content
              // 提取 results 数组（后端可能返回 { success, results: [...] } 或直接数组）
              assistantMessage.searchResults = searchData.results || searchData
              console.log('🔍 搜索结果列表:', assistantMessage.searchResults)
            } catch (e) {
              console.warn('解析搜索结果失败:', e)
              assistantMessage.searchResults = { raw: delta.content }
            }
          }
          else if (deltaType === 'knowledge') {
            // 📚 知识库搜索结果
            console.log('📚 收到知识库结果:', delta.content)
            try {
              const knowledgeData = typeof delta.content === 'string' 
                ? JSON.parse(delta.content) 
                : delta.content
              // 提取 chunks 数组（后端返回 { success, message, chunks: [...] }）
              assistantMessage.knowledgeResults = knowledgeData.chunks || knowledgeData
              console.log('📚 知识库结果列表:', assistantMessage.knowledgeResults)
            } catch (e) {
              console.warn('解析知识库结果失败:', e)
              assistantMessage.knowledgeResults = { raw: delta.content }
            }
          }
          else if (deltaType === 'ppt') {
            // 📊 PPT 生成结果（暂不处理，使用 tool_result 展示）
            console.log('📊 收到 PPT 结果:', delta.content)
          }
          else if (deltaType === 'recommended') {
            // 💡 推荐问题
            console.log('💡 收到推荐问题:', delta.content)
            try {
              const recommended = typeof delta.content === 'string'
                ? JSON.parse(delta.content)
                : delta.content
              assistantMessage.recommendedQuestions = recommended.questions || []
              console.log('💡 推荐问题列表:', assistantMessage.recommendedQuestions)
            } catch (e) {
              console.warn('解析推荐问题失败:', e)
            }
          }
          else if (deltaType === 'intent') {
            // 🎯 意图识别结果
            console.log('🎯 收到意图识别:', delta.content)
            try {
              const intentData = typeof delta.content === 'string'
                ? JSON.parse(delta.content)
                : delta.content
              assistantMessage.intentResult = intentData
              console.log('🎯 意图识别结果:', intentData)
            } catch (e) {
              console.warn('解析意图识别失败:', e)
            }
          }
          
          // 处理 usage 统计
          if (usage) {
            console.log('📊 Token 使用:', usage)
          }
          
          // 处理 stop_reason
          if (delta?.stop_reason) {
            console.log('🛑 停止原因:', delta.stop_reason)
          }
        }
        // 消息停止
        else if (event.type === 'message_stop') {
          console.log('💬 消息停止:', event.data)
        }
        
        // ==================== Content 事件 ====================
        
        // 内容块开始（text/thinking/tool_use/tool_result）
        else if (event.type === 'content_start') {
          const contentBlock = event.data?.content_block
          const blockType = contentBlock?.type
          const blockIndex = event.data?.index
          
          console.log('📝 内容块开始:', blockType, blockIndex, event.data)
          
          // 初始化内容块
          if (contentBlock) {
            // 确保 contentBlocks 数组足够长
            while (assistantMessage.contentBlocks.length <= blockIndex) {
              assistantMessage.contentBlocks.push(null)
            }
            // 存储内容块（后续 delta 会更新）
            assistantMessage.contentBlocks[blockIndex] = { ...contentBlock }
          }
          
          // 🔧 如果是新的 thinking 块开始，重置 thinking（不累加多轮）
          if (blockType === 'thinking') {
            assistantMessage.thinking = ''
            console.log('💭 新的 thinking 块开始，已重置')
          }
          
          // 如果是 tool_use 开始，记录状态
          if (blockType === 'tool_use') {
            const toolId = contentBlock?.id
            const toolName = contentBlock?.name
            console.log('🔧 工具调用开始:', toolName, toolId)
            if (toolId) {
              assistantMessage.toolStatuses[toolId] = { pending: true }
            }
          }
          
          // 🆕 如果是 tool_result，更新工具状态
          if (blockType === 'tool_result') {
            const toolUseId = contentBlock?.tool_use_id
            const isError = contentBlock?.is_error
            const resultContent = contentBlock?.content
            
            console.log('🔧 工具结果:', toolUseId, isError ? '❌' : '✅', resultContent)
            
            if (toolUseId) {
              assistantMessage.toolStatuses[toolUseId] = {
                pending: false,
                success: !isError,
                result: resultContent
              }
            }
          }
        }
        // 内容增量更新
        else if (event.type === 'content_delta') {
          const deltaType = event.data?.delta?.type
          const deltaText = event.data?.delta?.text
          const deltaThinking = event.data?.delta?.thinking  // 🔧 thinking_delta 用这个字段
          const blockIndex = event.data?.index
          
          if (deltaType === 'text_delta' && deltaText) {
            // 更新文本内容
            assistantMessage.content += deltaText
            // 更新对应的 content block
            if (blockIndex !== undefined && assistantMessage.contentBlocks[blockIndex]) {
              const block = assistantMessage.contentBlocks[blockIndex]
              block.text = (block.text || '') + deltaText
            }
            scrollToBottom()
          } else if (deltaType === 'thinking_delta' && deltaThinking) {
            // 🔧 更新 thinking 内容（注意：用 delta.thinking 不是 delta.text）
            assistantMessage.thinking += deltaThinking
            // 更新对应的 content block
            if (blockIndex !== undefined && assistantMessage.contentBlocks[blockIndex]) {
              const block = assistantMessage.contentBlocks[blockIndex]
              block.thinking = (block.thinking || '') + deltaThinking
            }
            scrollToBottom()
          } else if (deltaType === 'input_json_delta') {
            // 工具调用参数增量
            const partialJson = event.data?.delta?.partial_json
            console.log('🔧 工具参数增量:', partialJson)
            // 更新对应的 content block
            if (blockIndex !== undefined && assistantMessage.contentBlocks[blockIndex]) {
              const block = assistantMessage.contentBlocks[blockIndex]
              block.partialInput = (block.partialInput || '') + (partialJson || '')
            }
          }
        }
        // 内容块停止
        else if (event.type === 'content_stop') {
          const blockIndex = event.data?.index
          console.log('✅ 内容块停止:', blockIndex, event.data)
          
          // 如果有 partialInput，尝试解析为完整的 input
          if (blockIndex !== undefined && assistantMessage.contentBlocks[blockIndex]) {
            const block = assistantMessage.contentBlocks[blockIndex]
            if (block.partialInput) {
              try {
                block.input = JSON.parse(block.partialInput)
                delete block.partialInput
              } catch {
                // 解析失败，保留原始字符串
              }
            }
          }
        }
        // 🆕 工具结果事件（兼容旧格式，新版本通过 content_start + type=tool_result 发送）
        else if (event.type === 'tool_result') {
          const toolUseId = event.data?.tool_use_id
          const result = event.data?.result
          const isError = event.data?.is_error
          
          console.log('🔧 工具结果（旧格式）:', toolUseId, isError ? '❌' : '✅', result)
          
          // 更新工具状态
          if (toolUseId) {
            assistantMessage.toolStatuses[toolUseId] = {
              pending: false,
              success: !isError,
              result: result
            }
          }
        }
        
        // ==================== Plan 事件 ====================
        
        // 🆕 计划更新事件
        else if (event.type === 'plan_update') {
          console.log('📋 计划更新:', event.data?.plan)
          // 可以在这里更新 UI 显示执行计划
        }
        
        // ==================== 其他事件 ====================
        
        // 状态更新
        else if (event.type === 'status') {
          const statusMsg = event.data?.message
          console.log('📊 状态更新:', statusMsg)
        }
        // 完成
        else if (event.type === 'complete') {
          console.log('✅ 执行完成:', event.data)
          const finalResult = event.data?.final_result
          if (finalResult && !assistantMessage.content) {
            assistantMessage.content = finalResult
          }
        }
        // 错误事件
        else if (event.type === 'error') {
          console.error('❌ 错误事件:', event.data)
          assistantMessage.content += `\n\n❌ 错误: ${event.data?.message || '未知错误'}`
      }
      },
      // 🆕 启用后台任务
      { backgroundTasks: ['title_generation'] }
    )
    
    // 🆕 消息发送完成后刷新对话列表
    await loadConversationList()
  } catch (error) {
    console.error('❌ 发送消息失败:', error)
    
    // 添加错误消息
    messages.value.push({
      id: Date.now() + 2,
      role: 'assistant',
      content: '抱歉，处理您的消息时出错了。请稍后再试。\n\n错误信息: ' + error.message,
      timestamp: new Date()
    })
  } finally {
    isLoading.value = false
    currentSessionId.value = null
    await nextTick()
    scrollToBottom()
  }
}

// 🆕 停止生成
async function stopGeneration() {
  if (!currentSessionId.value) {
    console.warn('⚠️ 没有正在运行的 session')
    return
  }

  try {
    isStopping.value = true
    console.log('🛑 请求停止 session:', currentSessionId.value)
    
    // 调用停止接口
    await chatStore.stopSession(currentSessionId.value)
    
    console.log('✅ 停止请求已发送，等待确认...')
    // 注意：实际停止会通过 SSE 的 session_stopped 事件通知
  } catch (error) {
    console.error('❌ 停止失败:', error)
    
    // 失败时手动重置状态
    isLoading.value = false
    isStopping.value = false
    currentSessionId.value = null
    
    // 显示错误提示
    const lastMessage = messages.value[messages.value.length - 1]
    if (lastMessage && lastMessage.role === 'assistant') {
      lastMessage.content += '\n\n_[停止失败: ' + error.message + ']_'
    }
  }
}

function scrollToBottom() {
  if (messagesContainer.value) {
    setTimeout(() => {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }, 50)
  }
}

function formatTime(date) {
  return new Date(date).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 🆕 短时间格式化（用于对话列表）
function formatShortTime(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return '刚刚'
  if (diffMins < 60) return `${diffMins}分钟前`
  if (diffHours < 24) return `${diffHours}小时前`
  if (diffDays < 7) return `${diffDays}天前`
  
  return date.toLocaleDateString('zh-CN', {
    month: '2-digit',
    day: '2-digit'
  })
}

// 🆕 工作区相关处理函数
function handleFileSelect(file) {
  console.log('📄 选中文件:', file)
  // 打开文件预览
  previewFile.value = file
}

function closePreview() {
  previewFile.value = null
}

function handleProjectClick(project) {
  console.log('📦 点击项目:', project)
  // 找到入口文件并预览
  if (project.entry_file) {
    previewFile.value = {
      path: `${project.path}/${project.entry_file}`,
      type: 'file'
    }
  }
}

function handleRunProject(project) {
  console.log('▶️ 运行项目:', project)
  // 对于静态 HTML 项目，直接在新标签页打开
  if (project.type === 'static' && project.entry_file) {
    // 打开 HTML 预览
    previewFile.value = {
      path: `${project.path}/${project.entry_file}`,
      type: 'file'
    }
  } else {
    // 其他项目类型需要后端环境
    alert(`项目 "${project.name}" 需要运行环境\n类型: ${project.type}\n\n后续将支持沙箱运行功能！`)
  }
}
</script>

<style scoped>
.chat-layout {
  display: flex;
  height: 100vh;
  background: #f5f7fa;
}

/* 侧边栏 */
.sidebar {
  width: 280px;
  background: white;
  border-right: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  transition: all 0.3s ease;
}

.sidebar.collapsed {
  width: 60px;
}

.sidebar-header {
  padding: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #e5e7eb;
}

.sidebar-header h2 {
  margin: 0;
  font-size: 20px;
  white-space: nowrap;
}

.sidebar.collapsed .sidebar-header h2 {
  display: none;
}

.collapse-btn {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  padding: 5px;
}

.sidebar-content {
  flex: 1;
  padding: 15px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
}

.sidebar-button {
  padding: 12px;
  background: #f7fafc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}

.sidebar-button:hover {
  background: #edf2f7;
  border-color: #667eea;
}

.sidebar-button.primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  font-weight: 600;
}

.sidebar-button.primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

/* 🆕 对话列表样式 */
.conversations-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  margin-top: 10px;
  overflow: hidden;
}

.section-title {
  margin: 0 0 10px 0;
  font-size: 13px;
  color: #718096;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.conversation-item {
  padding: 12px;
  background: #f7fafc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 8px;
}

.conversation-item:hover {
  background: #edf2f7;
  border-color: #667eea;
}

.conversation-item.active {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-color: #667eea;
  color: white;
}

.conversation-content {
  flex: 1;
  min-width: 0;
}

.conversation-title {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-info {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  opacity: 0.7;
}

.conversation-item.active .conversation-info {
  opacity: 0.9;
}

/* 🆕 删除按钮样式 */
.delete-btn {
  opacity: 0;
  padding: 4px 6px;
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
  flex-shrink: 0;
}

.conversation-item:hover .delete-btn {
  opacity: 0.6;
}

.delete-btn:hover {
  opacity: 1 !important;
  background: rgba(229, 62, 62, 0.1);
}

.conversation-item.active .delete-btn {
  color: white;
}

.conversation-item.active .delete-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}

.loading-text, .empty-text {
  padding: 20px;
  text-align: center;
  font-size: 13px;
  color: #a0aec0;
}

.user-info {
  margin-top: auto;
  padding: 15px;
  background: #f7fafc;
  border-radius: 8px;
  font-size: 12px;
  color: #718096;
}

/* 主要内容 */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: row;
  overflow: hidden;
}

.main-content.with-workspace .chat-container {
  flex: 1;
  min-width: 0;
}

/* 🆕 工作区面板 */
.workspace-panel {
  width: 600px;
  min-width: 400px;
  max-width: 800px;
  border-left: 1px solid #2d2d44;
  background: #1e1e2e;
  display: flex;
  flex-direction: row;
  overflow: hidden;
}

/* 文件浏览器 */
.workspace-explorer {
  width: 100%;
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
}

.workspace-explorer.with-preview {
  width: 280px;
  min-width: 280px;
  border-right: 1px solid #3d3d5c;
}

/* 文件预览区域 */
.workspace-preview {
  flex: 1;
  min-width: 0;
  height: 100%;
  overflow: hidden;
}

.knowledge-panel {
  background: white;
  border-bottom: 1px solid #e5e7eb;
  max-height: 50vh;
  overflow-y: auto;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e5e7eb;
}

.panel-header h3 {
  margin: 0;
  font-size: 18px;
}

.close-btn {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  padding: 5px 10px;
}

.panel-body {
  padding: 20px;
}

/* 聊天区域 */
.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: white;
  overflow: hidden;
}

.chat-header {
  padding: 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-content h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

/* 🆕 工作区切换按钮 */
.workspace-toggle-btn {
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 8px;
  color: white;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.workspace-toggle-btn:hover {
  background: rgba(255, 255, 255, 0.3);
  transform: translateY(-1px);
}

.workspace-toggle-btn.active {
  background: rgba(255, 255, 255, 0.35);
  border-color: rgba(255, 255, 255, 0.5);
}

.subtitle {
  margin: 5px 0 0 0;
  font-size: 13px;
  opacity: 0.9;
  display: flex;
  align-items: center;
  gap: 10px;
}

.conversation-badge {
  display: inline-block;
  padding: 3px 8px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 12px;
  font-size: 11px;
  font-family: monospace;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: #f9fafb;
}

/* 欢迎卡片 */
.welcome-card {
  max-width: 600px;
  margin: 40px auto;
}

.welcome-content {
  text-align: center;
}

.welcome-icon {
  font-size: 64px;
  margin-bottom: 20px;
}

.welcome-content h2 {
  margin: 0 0 15px 0;
  font-size: 24px;
  color: #2c3e50;
}

.welcome-content p {
  color: #718096;
  margin: 10px 0;
}

.welcome-content ul {
  text-align: left;
  display: inline-block;
  margin: 20px 0;
}

.welcome-content li {
  margin: 8px 0;
  color: #4a5568;
}

.hint {
  font-style: italic;
  color: #667eea !important;
  font-weight: 500;
}

/* 消息样式 */
.message {
  display: flex;
  margin-bottom: 20px;
  animation: fadeIn 0.3s ease-in;
  align-items: flex-start;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.user-message {
  flex-direction: row-reverse;
}

.message-avatar {
  font-size: 32px;
  margin: 0 10px;
  flex-shrink: 0;
}

.message-card {
  max-width: 70%;
}

.user-message .message-card :deep(.card-body) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.message-text {
  line-height: 1.6;
  word-wrap: break-word;
  white-space: pre-wrap;
}

.message-time {
  font-size: 11px;
  margin-top: 8px;
  opacity: 0.6;
}

/* 思考过程样式 */
.thinking-section {
  margin-bottom: 15px;
  padding: 12px;
  background: rgba(102, 126, 234, 0.1);
  border-left: 3px solid #667eea;
  border-radius: 6px;
}

.thinking-header {
  font-size: 12px;
  font-weight: 600;
  color: #667eea;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 5px;
}

.thinking-content {
  font-size: 13px;
  color: #4a5568;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-style: italic;
  opacity: 0.9;
}

.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 8px 0;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  background: #667eea;
  border-radius: 50%;
  animation: typing 1.4s infinite;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  30% {
    transform: translateY(-10px);
    opacity: 1;
  }
}

/* 输入区域 */
.chat-input-container {
  padding: 20px;
  background: white;
  border-top: 1px solid #e5e7eb;
}

.chat-input-wrapper {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.chat-input {
  flex: 1;
  padding: 12px 16px;
  border: 2px solid #e5e7eb;
  border-radius: 12px;
  font-size: 14px;
  font-family: inherit;
  resize: none;
  outline: none;
  transition: border-color 0.3s;
  max-height: 120px;
  line-height: 1.5;
}

.chat-input:focus {
  border-color: #667eea;
}

.send-button {
  padding: 12px 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.2s, opacity 0.2s;
  white-space: nowrap;
  height: fit-content;
}

.send-button:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.send-button:active:not(:disabled) {
  transform: translateY(0);
}

.send-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 🆕 停止按钮样式 */
.stop-button {
  padding: 12px 24px;
  background: linear-gradient(135deg, #e53e3e 0%, #c53030 100%);
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.2s, opacity 0.2s;
  white-space: nowrap;
  height: fit-content;
}

.stop-button:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(229, 62, 62, 0.4);
}

.stop-button:active:not(:disabled) {
  transform: translateY(0);
}

.stop-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.chat-input:disabled {
  opacity: 0.7;
  background-color: #f7fafc;
  cursor: not-allowed;
}

/* ==================== 特殊工具结果 UI ==================== */

.special-result {
  margin-top: 16px;
  padding: 12px 16px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-weight: 600;
  color: #2d3748;
}

.result-icon {
  font-size: 18px;
}

.result-title {
  font-size: 14px;
}

/* Plan 结果 */
.plan-result {
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
  border-color: #7dd3fc;
}

.plan-goal {
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 8px;
  margin-bottom: 12px;
  font-size: 14px;
  color: #0369a1;
}

.plan-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.plan-step {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 8px;
  font-size: 13px;
  transition: all 0.2s;
}

.plan-step.completed {
  background: rgba(16, 185, 129, 0.1);
  border-left: 3px solid #10b981;
}

.plan-step.in-progress {
  background: rgba(245, 158, 11, 0.1);
  border-left: 3px solid #f59e0b;
}

.step-number {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0284c7;
  color: white;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.plan-step.completed .step-number {
  background: #10b981;
}

.plan-step.in-progress .step-number {
  background: #f59e0b;
}

.step-action {
  flex: 1;
  color: #334155;
}

.step-status {
  font-size: 16px;
}

/* 搜索结果 */
.search-result {
  background: linear-gradient(135deg, #fefce8 0%, #fef9c3 100%);
  border-color: #fde047;
}

.search-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.search-item {
  display: block;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 8px;
  text-decoration: none;
  transition: all 0.2s;
}

.search-item:hover {
  background: rgba(255, 255, 255, 1);
  transform: translateX(4px);
}

.search-item .item-title {
  display: block;
  font-weight: 600;
  color: #1e40af;
  font-size: 13px;
  margin-bottom: 4px;
}

.search-item .item-snippet {
  display: block;
  font-size: 12px;
  color: #64748b;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
}

/* 知识库结果 */
.knowledge-result {
  background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
  border-color: #86efac;
}

.knowledge-items {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.knowledge-item {
  padding: 12px;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 8px;
}

.knowledge-item .item-source {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  color: #16a34a;
  margin-bottom: 8px;
}

.knowledge-item .item-score {
  padding: 2px 6px;
  background: rgba(22, 163, 74, 0.1);
  border-radius: 4px;
  font-size: 11px;
}

.knowledge-item .item-content {
  font-size: 13px;
  color: #334155;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
}

/* 原始内容回退 */
.raw-content {
  margin: 0;
  padding: 12px;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 8px;
  font-size: 12px;
  font-family: 'Consolas', 'Monaco', monospace;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  color: #475569;
}

/* ==================== 推荐问题 ==================== */

.recommended-questions {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
}

.recommended-header {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 10px;
  font-weight: 500;
}

.recommended-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.recommended-btn {
  padding: 8px 14px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border: 1px solid #e2e8f0;
  border-radius: 20px;
  font-size: 13px;
  color: #475569;
  cursor: pointer;
  transition: all 0.2s;
}

.recommended-btn:hover {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-color: #667eea;
  color: white;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.recommended-btn:active {
  transform: translateY(0);
}
</style>

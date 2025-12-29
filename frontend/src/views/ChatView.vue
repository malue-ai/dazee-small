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
        <button @click="showKnowledgePanel = !showKnowledgePanel" class="sidebar-button">
          📚 知识库管理
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
              <div class="conversation-title">{{ conv.title }}</div>
              <div class="conversation-info">
                <span class="message-count">{{ conv.message_count }} 条</span>
                <span class="last-time">{{ formatShortTime(conv.updated_at) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="user-info">
          <div class="user-id">用户: {{ userId }}</div>
        </div>
      </div>
    </div>

    <!-- 主要内容区域 -->
    <div class="main-content">
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
              <!-- 显示 thinking 过程 -->
              <div v-if="message.role === 'assistant' && message.thinking" class="thinking-section">
                <div class="thinking-header">💭 思考过程</div>
                <div class="thinking-content">{{ message.thinking }}</div>
              </div>
              
              <!-- 显示主要内容 -->
              <MarkdownRenderer
                v-if="message.role === 'assistant'"
                :content="message.content"
              />
              <div v-else class="message-text">{{ message.content }}</div>
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
              @keydown.enter.exact.prevent="sendMessage"
              placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
              class="chat-input"
              rows="1"
              ref="inputTextarea"
            ></textarea>
            <button
              @click="sendMessage"
              :disabled="!inputMessage.trim() || isLoading"
              class="send-button"
            >
              <span v-if="!isLoading">发送 📤</span>
              <span v-else>发送中...</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, watch } from 'vue'
import { useChatStore } from '@/stores/chat'
import Card from '@/components/Card.vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import KnowledgeUpload from '@/components/KnowledgeUpload.vue'

const chatStore = useChatStore()
const messages = ref([])
const inputMessage = ref('')
const isLoading = ref(false)
const messagesContainer = ref(null)
const inputTextarea = ref(null)
const sidebarCollapsed = ref(false)
const showKnowledgePanel = ref(false)
const userId = ref('')

// 🆕 对话列表相关状态
const conversations = ref([])
const loadingConversations = ref(false)

onMounted(async () => {
  // 初始化用户ID
  userId.value = chatStore.initUserId()
  
  // 🆕 加载对话列表
  await loadConversationList()
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
    
    // 清空当前消息
    messages.value = []
    
    // 设置当前对话ID
    chatStore.conversationId = conversationId
    
    // 获取历史消息
    const result = await chatStore.getConversationMessages(conversationId, 100, 0, 'asc')
    
    // 转换为消息格式
    messages.value = result.messages.map(msg => ({
      id: msg.id,
      role: msg.role,
      content: msg.content,
      timestamp: new Date(msg.created_at),
      thinking: msg.metadata?.thinking || ''
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
    
    // 刷新对话列表
    await loadConversationList()
  } catch (error) {
    console.error('❌ 创建对话失败:', error)
  }
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
  
  try {
    let assistantMessage = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
      thinking: '',
      timestamp: new Date()
    }
    messages.value.push(assistantMessage)

    // 使用流式发送
    await chatStore.sendMessageStream(
      content,
      chatStore.conversationId,
      (event) => {
        // 处理流式事件
        console.log('收到事件:', event.type)
        
        if (event.type === 'conversation_start' && event.data?.conversation_id) {
          chatStore.conversationId = event.data.conversation_id
          // 🆕 刷新对话列表
          loadConversationList()
        } else if (event.type === 'content_delta') {
          if (event.data?.delta?.type === 'text' && event.data?.delta?.text) {
            assistantMessage.content += event.data.delta.text
            scrollToBottom()
          } else if (event.data?.delta?.type === 'thinking' && event.data?.delta?.text) {
            assistantMessage.thinking += event.data.delta.text
            scrollToBottom()
          }
        }
      }
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
    await nextTick()
    scrollToBottom()
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
  flex-direction: column;
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
}

.header-content h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
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
</style>

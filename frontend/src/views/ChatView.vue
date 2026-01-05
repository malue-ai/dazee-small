<template>
  <div class="app-container light-theme">
    <!-- 左侧侧边栏：历史对话 -->
    <div class="sidebar left-sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <div class="logo-area" v-if="!sidebarCollapsed">
          <span class="logo-icon">✨</span>
          <span class="logo-text">ZenFlux</span>
        </div>
        <button @click="sidebarCollapsed = !sidebarCollapsed" class="icon-btn collapse-btn">
          <span class="icon">{{ sidebarCollapsed ? '→' : '←' }}</span>
        </button>
      </div>

      <div v-show="!sidebarCollapsed" class="sidebar-content">
        <!-- 操作按钮 -->
        <div class="action-buttons">
          <button @click="createNewConversation" class="new-chat-btn">
            <span class="icon">＋</span> 新建对话
          </button>
          <button @click="$router.push('/knowledge')" class="nav-btn">
            <span class="icon">📚</span> 知识库
          </button>
        </div>

        <!-- 对话列表 -->
        <div class="conversations-section">
          <div class="section-header">最近对话</div>
          <div v-if="loadingConversations" class="loading-text">加载中...</div>
          <div v-else-if="conversations.length === 0" class="empty-text">暂无记录</div>
          <div v-else class="conversation-list">
            <div
              v-for="conv in conversations"
              :key="conv.id"
              class="conversation-item"
              :class="{ active: conv.id === chatStore.conversationId }"
              @click="loadConversation(conv.id)"
            >
              <div class="conv-title">{{ conv.title || '未命名对话' }}</div>
              <div class="conv-meta">
                <span class="conv-time">{{ formatShortTime(conv.updated_at) }}</span>
                <button class="delete-icon" @click.stop="confirmDeleteConversation(conv)">🗑️</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 用户信息 -->
        <div class="user-profile">
          <div class="avatar">U</div>
          <div class="user-details">
            <div class="user-name">User</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 中间主区域：对话流 -->
    <div class="main-column">
      <!-- 顶部导航栏 (极简) -->
      <div class="top-bar">
        <div class="current-chat-info">
          <h2>{{ currentConversationTitle }}</h2>
        </div>
        
        <div class="top-actions">
           <button 
            v-if="chatStore.conversationId"
            @click="toggleWorkspace" 
            class="action-btn"
            :class="{ active: showWorkspacePanel }"
            title="文件列表"
          >
            <span class="icon">📂</span>
          </button>
          <button 
            @click="toggleRightSidebar" 
            class="action-btn" 
            :class="{ active: showRightSidebar }"
            title="任务看板"
          >
            <span class="icon">📋</span>
          </button>
        </div>
      </div>

      <!-- 消息列表区域 -->
      <div class="chat-viewport" ref="messagesContainer">
        <!-- 欢迎页 -->
        <div v-if="messages.length === 0" class="welcome-screen">
          <div class="welcome-icon">✨</div>
          <h1>有什么我可以帮你的？</h1>
          <div class="suggestion-grid">
            <div class="suggestion-card" @click="setInput('帮我生成一个贪吃蛇游戏')">
              <span class="text">🎮 生成贪吃蛇游戏</span>
            </div>
            <div class="suggestion-card" @click="setInput('分析一下 requirements.txt')">
              <span class="text">📊 分析项目依赖</span>
            </div>
            <div class="suggestion-card" @click="setInput('查询关于 RAG 的最新论文')">
              <span class="text">🔍 搜索 RAG 论文</span>
            </div>
          </div>
        </div>

        <!-- 消息流 -->
        <div v-else class="message-list">
          <div
            v-for="message in messages"
            :key="message.id"
            class="message-row"
            :class="message.role"
          >
            <div class="message-avatar">
              {{ message.role === 'user' ? '👤' : '🤖' }}
            </div>
            
            <div class="message-bubble">
              <!-- 用户消息 -->
              <div v-if="message.role === 'user'" class="user-content">
                {{ message.content }}
              </div>
              
              <!-- 助手消息 -->
              <div v-else class="assistant-content">
                <MessageContent 
                  v-if="message.contentBlocks && message.contentBlocks.length > 0"
                  :content="message.contentBlocks"
                  :tool-statuses="message.toolStatuses || {}"
                />
                <template v-else>
                   <div v-if="message.thinking" class="thinking-box">
                     {{ message.thinking }}
                   </div>
                   <MarkdownRenderer :content="message.content" />
                </template>

                <!-- 推荐问题 -->
                <div v-if="message.recommendedQuestions?.length" class="recommended-section">
                  <div class="rec-chips">
                    <button 
                      v-for="(q, idx) in message.recommendedQuestions" 
                      :key="idx" 
                      class="rec-chip"
                      @click="askRecommendedQuestion(q)"
                    >
                      {{ q }}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Loading -->
          <div v-if="isLoading && !isGenerating" class="message-row assistant">
             <div class="message-avatar">🤖</div>
             <div class="message-bubble">
               <div class="typing-dots"><span>.</span><span>.</span><span>.</span></div>
             </div>
          </div>
        </div>
      </div>

      <!-- 输入框区域 -->
      <div class="input-area">
        <div class="input-box-wrapper">
          <textarea
            v-model="inputMessage"
            @keydown.enter.exact="handleEnter"
            @compositionstart="isComposing = true"
            @compositionend="isComposing = false"
            placeholder="输入消息..."
            ref="inputTextarea"
            :disabled="isLoading"
            rows="1"
          ></textarea>
          
          <div class="input-actions">
            <button 
              v-if="isLoading" 
              class="send-btn stop-btn" 
              @click="stopGeneration"
              :disabled="isStopping"
            >
              ⏹
            </button>
            <button 
              v-else 
              class="send-btn" 
              @click="sendMessage"
              :disabled="!inputMessage.trim()"
            >
              ↑
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧侧边栏：Plan & Context -->
    <div class="sidebar right-sidebar" v-show="showRightSidebar">
      <div class="sidebar-header">
        <h3>任务看板</h3>
        <button @click="showRightSidebar = false" class="icon-btn close-btn">✕</button>
      </div>
      
      <div class="sidebar-content right-content">
        <PlanWidget :plan="currentPlan" />
      </div>
    </div>

    <!-- 工作区面板 -->
    <div v-if="showWorkspacePanel && chatStore.conversationId" class="workspace-drawer">
       <div class="drawer-header">
         <h3>项目文件</h3>
         <button @click="showWorkspacePanel = false" class="icon-btn">✕</button>
       </div>
       <div class="drawer-body">
          <div class="workspace-explorer">
             <FileExplorer 
                :conversation-id="chatStore.conversationId"
                @file-select="handleFileSelect"
             />
          </div>
          <div v-if="previewFile" class="workspace-preview-pane">
             <div class="preview-header">
               <span>{{ previewFile.name }}</span>
               <button @click="previewFile = null">✕</button>
             </div>
             <FilePreview
                :conversation-id="chatStore.conversationId"
                :file-path="previewFile.path"
                @close="previewFile = null"
             />
          </div>
       </div>
    </div>

  </div>
</template>

<script setup>
// (Script 部分保持不变，逻辑完全通用)
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import MessageContent from '@/components/MessageContent.vue'
import PlanWidget from '@/components/PlanWidget.vue'
import FileExplorer from '@/components/FileExplorer.vue'
import FilePreview from '@/components/FilePreview.vue'

// --- 基础状态 ---
const router = useRouter()
const route = useRoute()
const chatStore = useChatStore()
const messagesContainer = ref(null)
const inputTextarea = ref(null)

// --- 数据状态 ---
const userId = ref('')
const messages = ref([])
const inputMessage = ref('')
const conversations = ref([])
const loadingConversations = ref(false)

// --- 交互状态 ---
const isLoading = ref(false)
const isGenerating = ref(false) 
const isComposing = ref(false)
const isStopping = ref(false)
const currentSessionId = ref(null)

// --- 重连状态 ---
const activeSessions = ref([])        // 活跃的 Session 列表
const showReconnectModal = ref(false) // 是否显示重连提示
const reconnectingSession = ref(null) // 正在重连的 Session

// --- 布局状态 ---
const sidebarCollapsed = ref(false)
const showRightSidebar = ref(true)
const showWorkspacePanel = ref(false)
const previewFile = ref(null)

// --- Computed ---
const currentConversationTitle = computed(() => {
  const conv = conversations.value.find(c => c.id === chatStore.conversationId)
  return conv ? conv.title : '新对话'
})

const currentPlan = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    if (messages.value[i].planResult) {
      return messages.value[i].planResult
    }
  }
  return null
})

// --- Lifecycle ---
onMounted(async () => {
  userId.value = chatStore.initUserId()
  await loadConversationList()
  
  // 🆕 检查是否有活跃的 Session（用于页面刷新重连）
  await checkActiveSessions()
  
  const conversationId = route.params.conversationId
  if (conversationId) await loadConversation(conversationId)
})

watch(() => route.params.conversationId, async (newId) => {
  if (newId) await loadConversation(newId)
})

watch(inputMessage, () => {
  nextTick(() => {
    if (inputTextarea.value) {
      inputTextarea.value.style.height = 'auto'
      inputTextarea.value.style.height = Math.min(inputTextarea.value.scrollHeight, 150) + 'px'
    }
  })
})

// --- Methods ---
async function loadConversationList() {
  loadingConversations.value = true
  try {
    const result = await chatStore.getConversationList(20, 0)
    conversations.value = result.conversations
  } finally {
    loadingConversations.value = false
  }
}

async function createNewConversation() {
  messages.value = []
  chatStore.conversationId = null
  router.push({ name: 'chat' })
  await loadConversationList()
  if (window.innerWidth < 768) sidebarCollapsed.value = true
}

async function loadConversation(conversationId) {
  if (chatStore.isConnected) chatStore.disconnectSSE()
  isLoading.value = false
  messages.value = []
  chatStore.conversationId = conversationId
  if (route.params.conversationId !== conversationId) {
    router.push({ name: 'conversation', params: { conversationId } })
  }
  try {
    const result = await chatStore.getConversationMessages(conversationId, 100, 0, 'asc')
    messages.value = result.messages.map(processHistoryMessage)
    await nextTick()
    scrollToBottom()
  } catch (e) { console.error(e) }
}

function processHistoryMessage(msg) {
  // 🔧 Plan 数据可能在 metadata.plan.plan 中（嵌套结构）
  let planData = null
  if (msg.metadata?.plan) {
    // 检查是否是嵌套结构（plan.plan）
    if (msg.metadata.plan.plan) {
      planData = msg.metadata.plan.plan
    } else if (msg.metadata.plan.goal || msg.metadata.plan.steps) {
      // 或者直接就是 plan 对象
      planData = msg.metadata.plan
    }
  }
  
  return {
    id: msg.id,
    role: msg.role,
    content: extractText(msg.content),
    thinking: extractThinking(msg.content),
    contentBlocks: parseContentBlocks(msg.content),
    toolStatuses: {},
    recommendedQuestions: msg.metadata?.recommended || [],
    planResult: planData,
    timestamp: new Date(msg.created_at)
  }
}

function extractText(content) {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) return content.filter(b => b.type === 'text').map(b => b.text).join('\n')
  return String(content)
}
function extractThinking(content) {
  if (Array.isArray(content)) {
    const block = content.find(b => b.type === 'thinking')
    return block?.thinking || ''
  }
  return ''
}
function parseContentBlocks(content) {
  if (Array.isArray(content)) return content
  if (typeof content === 'string') {
    try {
      const parsed = JSON.parse(content)
      if (Array.isArray(parsed)) return parsed
    } catch {}
  }
  return []
}

async function sendMessage() {
  const content = inputMessage.value.trim()
  if (!content || isLoading.value) return
  
  messages.value.push({
    id: Date.now(),
    role: 'user',
    content: content,
    timestamp: new Date()
  })
  inputMessage.value = ''
  if (inputTextarea.value) inputTextarea.value.style.height = 'auto'
  scrollToBottom()
  
  isLoading.value = true
  isGenerating.value = true
  
  const assistantMsg = {
    id: Date.now() + 1,
    role: 'assistant',
    content: '',
    thinking: '',
    contentBlocks: [],
    toolStatuses: {},
    planResult: null,
    recommendedQuestions: [],
    timestamp: new Date()
  }
  messages.value.push(assistantMsg)
  
  try {
    await chatStore.sendMessageStream(
      content,
      chatStore.conversationId,
      (event) => handleStreamEvent(event, assistantMsg)
    )
    await loadConversationList()
  } catch (e) {
    assistantMsg.content += `\n❌ 发送失败: ${e.message}`
  } finally {
    isLoading.value = false
    isGenerating.value = false
    scrollToBottom()
  }
}

function handleStreamEvent(event, msg) {
  const { type, data } = event
  if (data?.session_id) currentSessionId.value = data.session_id
  
  if (type === 'conversation_start' && data.conversation_id && !chatStore.conversationId) {
    chatStore.conversationId = data.conversation_id
    loadConversationList()
  }
  
  if (type === 'message_delta') {
    const delta = data.delta
    if (delta?.type === 'plan') {
      try {
        // 解析 plan 数据
        let planData = typeof delta.content === 'string' ? JSON.parse(delta.content) : delta.content
        
        // 🔧 处理嵌套结构：plan_todo 工具返回 { status, message, plan: {...} }
        if (planData && planData.plan) {
          // 如果是工具返回格式，提取 plan 字段
          msg.planResult = planData.plan
        } else if (planData && (planData.goal || planData.steps)) {
          // 如果直接就是 plan 对象
          msg.planResult = planData
        }
        
        // 自动展开右侧栏显示 Plan
        if (msg.planResult && !showRightSidebar.value) {
          showRightSidebar.value = true
        }
        
        console.log('📋 Plan 已更新:', msg.planResult)
      } catch (e) {
        console.warn('解析 Plan 失败:', e)
      }
    }
    if (delta?.type === 'recommended') {
       try {
        const rec = typeof delta.content === 'string' ? JSON.parse(delta.content) : delta.content
        msg.recommendedQuestions = rec.questions || []
      } catch {}
    }
  }
  
  if (type === 'content_start') {
    const { index, content_block } = data
    while (msg.contentBlocks.length <= index) msg.contentBlocks.push(null)
    msg.contentBlocks[index] = { ...content_block }
    if (content_block.type === 'thinking') msg.thinking = ''
    if (content_block.type === 'tool_use') msg.toolStatuses[content_block.id] = { pending: true }
    if (content_block.type === 'tool_result') {
      const toolId = content_block.tool_use_id
      if (toolId) {
        msg.toolStatuses[toolId] = {
          pending: false,
          success: !content_block.is_error,
          result: content_block.content
        }
        
        // 🔧 如果是 plan_todo 工具的结果，提取 Plan 数据
        try {
          const resultContent = typeof content_block.content === 'string' 
            ? JSON.parse(content_block.content) 
            : content_block.content
          
          if (resultContent && resultContent.plan) {
            msg.planResult = resultContent.plan
            // 自动展开右侧栏
            if (!showRightSidebar.value) showRightSidebar.value = true
            console.log('📋 从工具结果中提取 Plan:', msg.planResult)
          }
        } catch (e) {
          // 解析失败，忽略
        }
      }
    }
  }
  
  if (type === 'content_delta') {
    const { index, delta } = data
    const block = msg.contentBlocks[index]
    if (delta.type === 'text_delta') {
      msg.content += delta.text || ''
      if (block) block.text = (block.text || '') + (delta.text || '')
      scrollToBottom()
    }
    if (delta.type === 'thinking_delta') {
      msg.thinking += delta.thinking || ''
      if (block) block.thinking = (block.thinking || '') + (delta.thinking || '')
      scrollToBottom()
    }
    if (delta.type === 'input_json_delta' && block) {
      block.partialInput = (block.partialInput || '') + (delta.partial_json || '')
    }
  }
  
  if (type === 'content_stop') {
    const index = data.index
    const block = msg.contentBlocks[index]
    if (block?.partialInput) {
      try {
        block.input = JSON.parse(block.partialInput)
        delete block.partialInput
      } catch {}
    }
  }
}

function stopGeneration() {
  if (currentSessionId.value) {
    isStopping.value = true
    chatStore.stopSession(currentSessionId.value).finally(() => {
      isStopping.value = false; isLoading.value = false; isGenerating.value = false
    })
  }
}

// ==================== 重连相关方法 ====================

/**
 * 检查是否有活跃的 Session（页面刷新后自动重连）
 */
async function checkActiveSessions() {
  try {
    const sessions = await chatStore.getUserSessions()
    if (sessions && sessions.length > 0) {
      console.log(`🔄 发现 ${sessions.length} 个活跃 Session，自动重连...`)
      // 自动重连第一个（最新的）活跃 Session
      await reconnectToSession(sessions[0])
    }
  } catch (error) {
    // 静默失败，不影响正常使用
    console.log('ℹ️ 无活跃 Session 或检查失败')
  }
}

/**
 * 重连到指定 Session（使用 SSE）
 */
async function reconnectToSession(session) {
  try {
    reconnectingSession.value = session
    showReconnectModal.value = false
    
    console.log(`🔗 开始 SSE 重连 Session: ${session.session_id}`)
    
    // 1. 设置状态
    currentSessionId.value = session.session_id
    isLoading.value = true
    isGenerating.value = true
    
    // 2. 找到或创建 assistant 消息（先创建占位）
    let assistantMsg = messages.value.find(m => m.role === 'assistant' && m.id === session.message_id)
    if (!assistantMsg) {
      assistantMsg = {
        id: session.message_id || Date.now(),
        role: 'assistant',
        content: '',
        thinking: '',
        contentBlocks: [],
        toolStatuses: {},
        planResult: null,
        recommendedQuestions: [],
        timestamp: new Date()
      }
      messages.value.push(assistantMsg)
    }
    
    // 3. 使用 SSE 重连端点（GET /api/v1/chat/{session_id}）
    const afterSeq = 0  // 从头开始获取所有事件
    const url = `/api/v1/chat/${session.session_id}?after_seq=${afterSeq}`
    
    console.log(`📡 建立 SSE 重连: ${url}`)
    
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'text/event-stream'
      }
    })
    
    if (!response.ok) {
      if (response.status === 410) {
        // Session 已结束，从数据库加载
        console.log('ℹ️ Session 已结束，从数据库加载历史')
        if (session.conversation_id) {
          await loadConversation(session.conversation_id)
        }
        isLoading.value = false
        isGenerating.value = false
        return
      }
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }
    
    // 4. 读取 SSE 流
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    
    while (true) {
      const { done, value } = await reader.read()
      
      if (done) {
        console.log('✅ SSE 重连流结束')
        break
      }
      
      buffer += decoder.decode(value, { stream: true })
      
      // 解析 SSE 事件
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''  // 保留不完整的行
      
      let currentEventType = null
      let currentEventData = null
      
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEventType = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          currentEventData = line.slice(6)
        } else if (line === '' && currentEventData) {
          // 空行表示事件结束
          try {
            const event = JSON.parse(currentEventData)
            
            // 处理 reconnect_info 事件（包含上下文）
            if (currentEventType === 'reconnect_info') {
              const info = event.data
              console.log(`📋 重连上下文: conversation_id=${info.conversation_id}, message_id=${info.message_id}`)
              
              // 如果还没跳转到对应对话，现在跳转
              if (info.conversation_id && chatStore.conversationId !== info.conversation_id) {
                chatStore.conversationId = info.conversation_id
                router.push({ name: 'conversation', params: { conversationId: info.conversation_id } })
              }
            }
            // 处理 done 事件
            else if (currentEventType === 'done') {
              console.log('✅ SSE 重连完成')
              isLoading.value = false
              isGenerating.value = false
              // 重新加载对话以获取最终保存的消息
              if (session.conversation_id) {
                await loadConversation(session.conversation_id)
              }
              return
            }
            // 处理其他事件
            else {
              handleStreamEvent(event, assistantMsg)
              scrollToBottom()
            }
          } catch (e) {
            console.warn('解析事件失败:', e, currentEventData)
          }
          
          currentEventType = null
          currentEventData = null
        }
      }
    }
    
    isLoading.value = false
    isGenerating.value = false
    
  } catch (error) {
    console.error('❌ SSE 重连失败:', error)
    isLoading.value = false
    isGenerating.value = false
  } finally {
    reconnectingSession.value = null
  }
}

/**
 * 忽略活跃 Session（不重连）
 */
function dismissReconnect() {
  showReconnectModal.value = false
  activeSessions.value = []
}

function handleEnter(e) {
  if (isComposing.value) return
  e.preventDefault()
  sendMessage()
}

function scrollToBottom() {
  if (messagesContainer.value) setTimeout(() => {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }, 50)
}

function confirmDeleteConversation(conv) {
  if (confirm(`删除 "${conv.title}"?`)) {
    chatStore.deleteConversation(conv.id).then(() => {
      if (chatStore.conversationId === conv.id) createNewConversation()
      else loadConversationList()
    })
  }
}

function setInput(text) {
  inputMessage.value = text
  if (inputTextarea.value) inputTextarea.value.focus()
}

function askRecommendedQuestion(q) {
  setInput(q)
  sendMessage()
}

function toggleRightSidebar() { showRightSidebar.value = !showRightSidebar.value }
function toggleWorkspace() { showWorkspacePanel.value = !showWorkspacePanel.value }
function handleFileSelect(file) { previewFile.value = file }

function formatShortTime(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now - date
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return Math.floor(diff / 60000) + 'm'
  if (diff < 86400000) return Math.floor(diff / 3600000) + 'h'
  return date.getMonth() + 1 + '/' + date.getDate()
}
</script>

<style scoped>
/* --- 浅色极简主题 --- */
.app-container {
  display: flex;
  height: 100vh;
  width: 100vw;
  background-color: #ffffff;
  color: #1f2937;
  font-family: 'Inter', -apple-system, sans-serif;
  overflow: hidden;
}

/* --- 左侧边栏 --- */
.left-sidebar {
  width: 260px;
  background-color: #f9fafb; /* 极淡灰 */
  border-right: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
  flex-shrink: 0;
}

.left-sidebar.collapsed {
  width: 60px;
}

.sidebar-header {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  /* border-bottom: 1px solid #f3f4f6; 可选，让头部更一体化 */
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 16px;
  color: #111827;
}

.icon-btn {
  background: none;
  border: none;
  color: #6b7280;
  cursor: pointer;
  padding: 6px;
  border-radius: 4px;
  transition: background 0.2s;
}

.icon-btn:hover {
  background: #e5e7eb;
  color: #111827;
}

.sidebar-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px;
  overflow-y: auto;
}

.new-chat-btn {
  width: 100%;
  padding: 10px;
  background: #ffffff;
  color: #374151;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-weight: 500;
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 12px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
  transition: all 0.2s;
}

.new-chat-btn:hover {
  background: #f3f4f6;
  border-color: #d1d5db;
}

.nav-btn {
  width: 100%;
  padding: 8px 12px;
  background: transparent;
  color: #4b5563;
  border: none;
  border-radius: 6px;
  text-align: left;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.nav-btn:hover {
  background: #e5e7eb;
}

.section-header {
  font-size: 12px;
  color: #9ca3af;
  margin: 24px 0 8px 0;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.conversation-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.conversation-item {
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
  color: #4b5563;
  font-size: 14px;
}

.conversation-item:hover {
  background: #e5e7eb;
  color: #111827;
}

.conversation-item.active {
  background: #e5e7eb;
  color: #111827;
  font-weight: 500;
}

.conv-title {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 2px;
}

.conv-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #9ca3af;
}

.delete-icon {
  background: none;
  border: none;
  opacity: 0;
  cursor: pointer;
  font-size: 12px;
}

.conversation-item:hover .delete-icon {
  opacity: 1;
}

.user-profile {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  padding-top: 16px;
  border-top: 1px solid #e5e7eb;
}

.avatar {
  width: 28px;
  height: 28px;
  background: #e5e7eb;
  color: #4b5563;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
}

.user-name {
  font-size: 13px;
  font-weight: 500;
  color: #374151;
}

/* --- 中间主区域 --- */
.main-column {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
  background: #ffffff;
}

.top-bar {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  /* border-bottom: 1px solid #f3f4f6;  去掉边框更通透 */
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(8px);
  position: sticky;
  top: 0;
  z-index: 10;
}

.current-chat-info h2 {
  font-size: 15px;
  margin: 0;
  color: #111827;
  font-weight: 500;
}

.top-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  background: transparent;
  border: none;
  color: #6b7280;
  padding: 6px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #f3f4f6;
  color: #111827;
}

.action-btn.active {
  color: #2563eb;
  background: #eff6ff;
}

.chat-viewport {
  flex: 1;
  overflow-y: auto;
  padding: 20px 0;
  scroll-behavior: smooth;
}

.message-list {
  max-width: 768px; /* 限制宽度，提升阅读体验 */
  margin: 0 auto;
  padding: 0 24px;
}

.message-row {
  display: flex;
  gap: 16px;
  margin-bottom: 32px;
}

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  background: transparent; /* 去掉背景块 */
  flex-shrink: 0;
  margin-top: 2px;
}

.message-row.assistant .message-avatar {
  color: #2563eb;
}

.message-bubble {
  flex: 1;
  min-width: 0;
}

.user-content {
  background: #f3f4f6; /* 浅灰背景 */
  padding: 10px 16px;
  border-radius: 12px;
  display: inline-block;
  color: #111827;
  line-height: 1.6;
  font-size: 15px;
}

.assistant-content {
  line-height: 1.6;
  font-size: 15px;
  color: #374151;
}

/* 思考框 (浅色) */
.thinking-box {
  margin-bottom: 12px;
  padding: 12px;
  background: #f9fafb;
  border-left: 3px solid #e5e7eb;
  font-size: 13px;
  color: #6b7280;
  border-radius: 4px;
  font-style: italic;
}

/* 欢迎页 */
.welcome-screen {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #4b5563;
  margin-top: -60px; /* 视觉修正 */
}

.welcome-icon {
  font-size: 48px;
  margin-bottom: 24px;
}

.welcome-screen h1 {
  font-size: 24px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 40px;
}

.suggestion-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  width: 100%;
  max-width: 700px;
  padding: 0 20px;
}

.suggestion-card {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  padding: 16px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
  color: #4b5563;
  font-size: 14px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.suggestion-card:hover {
  border-color: #d1d5db;
  transform: translateY(-2px);
  box-shadow: 0 4px 6px rgba(0,0,0,0.05);
}

/* 输入区域 */
.input-area {
  padding: 24px;
  background: transparent;
  pointer-events: none; /* 让点击穿透空白区域 */
  position: sticky;
  bottom: 0;
}

.input-box-wrapper {
  pointer-events: auto;
  max-width: 768px;
  margin: 0 auto;
  background: #ffffff;
  border: 1px solid #e5e7eb; /* 极细边框 */
  border-radius: 16px;
  padding: 12px 16px;
  transition: all 0.2s;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08); /* 柔和阴影 */
  display: flex;
  align-items: flex-end;
  gap: 12px;
}

.input-box-wrapper:focus-within {
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.12);
  border-color: #d1d5db;
}

textarea {
  flex: 1;
  background: transparent;
  border: none;
  color: #111827;
  font-size: 16px;
  resize: none;
  outline: none;
  max-height: 200px;
  line-height: 1.5;
  padding: 4px 0;
}

textarea::placeholder {
  color: #9ca3af;
}

.input-actions {
  padding-bottom: 2px;
}

.send-btn {
  background: #111827; /* 黑色按钮 */
  color: white;
  border: none;
  width: 32px;
  height: 32px;
  border-radius: 50%; /* 圆形按钮 */
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.2s;
  font-size: 16px;
}

.send-btn:disabled {
  background: #e5e7eb;
  color: #9ca3af;
  cursor: default;
}

.stop-btn {
  background: #ef4444;
  border-radius: 16px; /* 停止按钮圆角矩形 */
  width: auto;
  padding: 0 16px;
  font-size: 14px;
  font-weight: 500;
}

/* --- 右侧边栏 --- */
.right-sidebar {
  width: 300px;
  background-color: #ffffff;
  border-left: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
}

.right-content {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
  background: #f9fafb; /* 浅灰底，凸显卡片 */
}

/* --- 悬浮面板 --- */
.workspace-drawer {
  position: absolute;
  top: 0;
  bottom: 0;
  right: 0;
  width: 600px;
  background: #ffffff;
  border-left: 1px solid #e5e7eb;
  z-index: 20;
  display: flex;
  flex-direction: column;
  box-shadow: -4px 0 24px rgba(0,0,0,0.1);
}

.drawer-header {
  height: 50px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  border-bottom: 1px solid #f3f4f6;
  font-weight: 500;
  color: #111827;
}

.drawer-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.workspace-explorer {
  width: 240px;
  border-right: 1px solid #f3f4f6;
  overflow-y: auto;
  background: #fafafa;
}

.workspace-preview-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: white;
}

.preview-header {
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  border-bottom: 1px solid #f3f4f6;
  background: #fff;
}

/* 推荐问题 */
.rec-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.rec-chip {
  padding: 6px 12px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  color: #4b5563;
  border-radius: 16px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}
.rec-chip:hover {
  border-color: #d1d5db;
  background: #f9fafb;
}

/* Loading Dots */
.typing-dots span {
  animation: blink 1.4s infinite both;
  margin: 0 2px;
  font-size: 20px;
  color: #9ca3af;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink {
  0% { opacity: 0.2; }
  20% { opacity: 1; }
  100% { opacity: 0.2; }
}

@media (max-width: 1024px) {
  .right-sidebar {
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    z-index: 30;
    box-shadow: -4px 0 24px rgba(0,0,0,0.15);
  }
}

/* ==================== 重连 Modal 样式 ==================== */
.reconnect-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.reconnect-modal {
  background: white;
  border-radius: 16px;
  width: 90%;
  max-width: 420px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
  animation: modalSlideIn 0.3s ease;
}

@keyframes modalSlideIn {
  from {
    opacity: 0;
    transform: translateY(-20px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.reconnect-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 24px;
  border-bottom: 1px solid #f3f4f6;
}

.reconnect-icon {
  font-size: 24px;
}

.reconnect-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}

.reconnect-body {
  padding: 20px 24px;
}

.reconnect-body p {
  margin: 0 0 16px;
  color: #6b7280;
  font-size: 14px;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.session-item {
  padding: 12px 16px;
  background: #f9fafb;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.session-item:hover {
  background: #f3f4f6;
  border-color: #6366f1;
}

.session-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.session-status {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
}

.session-status.running {
  background: #dcfce7;
  color: #16a34a;
}

.session-preview {
  color: #374151;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.session-progress {
  margin-top: 8px;
  height: 4px;
  background: #e5e7eb;
  border-radius: 2px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #6366f1, #8b5cf6);
  border-radius: 2px;
  transition: width 0.3s;
}

.reconnect-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid #f3f4f6;
}

.btn-secondary {
  padding: 8px 16px;
  background: #f3f4f6;
  color: #374151;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-secondary:hover {
  background: #e5e7eb;
}

.btn-primary {
  padding: 8px 20px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.btn-primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}
</style>

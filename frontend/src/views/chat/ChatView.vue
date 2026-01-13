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
          <div class="nav-buttons">
            <button @click="$router.push('/knowledge')" class="nav-btn">
              <span class="icon">📚</span> 知识库
            </button>
            <button @click="$router.push('/agents')" class="nav-btn">
              <span class="icon">🤖</span> 智能体
            </button>
          </div>
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
                <!-- 📎 显示附件（可点击预览） -->
                <div v-if="message.files && message.files.length > 0" class="message-files">
                  <div 
                    v-for="(file, idx) in message.files" 
                    :key="idx" 
                    class="message-file-item clickable"
                    @click="openAttachmentPreview(file)"
                    title="点击预览"
                  >
                    <span class="file-type-icon">{{ getFileTypeIcon(file) }}</span>
                    <span class="file-info">
                      <span class="file-title">{{ file.filename || file.name || '文件' }}</span>
                      <span class="file-type">{{ getFileTypeLabel(file) }}</span>
                    </span>
                    <span class="preview-hint">👁️</span>
                  </div>
                </div>
                <!-- 文字内容 -->
                <div v-if="message.content" class="user-text">{{ message.content }}</div>
              </div>
              
              <!-- 助手消息 -->
              <div v-else class="assistant-content">
                <MessageContent 
                  v-if="message.contentBlocks && message.contentBlocks.length > 0"
                  :content="message.contentBlocks"
                  :tool-statuses="message.toolStatuses || {}"
                  @mermaid-detected="handleMermaidDetected"
                />
                <template v-else>
                   <div v-if="message.thinking" class="thinking-box">
                     {{ message.thinking }}
                   </div>
                   <MarkdownRenderer :content="message.content" @mermaid-detected="handleMermaidDetected" />
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
          <!-- 📎 已选文件预览 -->
          <div v-if="selectedFiles.length > 0" class="selected-files">
            <div 
              v-for="(file, index) in selectedFiles" 
              :key="index" 
              class="file-chip"
            >
              <span class="file-icon">{{ getFileIcon(file) }}</span>
              <span class="file-name">{{ file.name }}</span>
              <button class="remove-file" @click="removeFile(index)">×</button>
            </div>
          </div>
          
          <div class="input-row">
            <!-- 文件上传按钮 -->
            <button 
              class="attach-btn" 
              @click="triggerFileUpload"
              :disabled="isLoading || isUploading"
              title="上传文件"
            >
              <span v-if="isUploading" class="uploading-icon">⏳</span>
              <span v-else>📎</span>
            </button>
            <input 
              type="file" 
              ref="fileInput" 
              @change="handleFileSelect" 
              multiple 
              accept="image/*,.pdf,.txt,.md,.csv,.json"
              style="display: none"
            />
            
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
                :disabled="!inputMessage.trim() && selectedFiles.length === 0"
              >
                ↑
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧侧边栏：Plan & Mind -->
    <div class="sidebar right-sidebar" v-show="showRightSidebar">
      <div class="sidebar-header">
        <div class="sidebar-tabs">
          <button 
            class="tab-btn" 
            :class="{ active: rightSidebarTab === 'plan' }"
            @click="rightSidebarTab = 'plan'"
          >
            📋 任务
          </button>
          <button 
            class="tab-btn" 
            :class="{ active: rightSidebarTab === 'mind' }"
            @click="rightSidebarTab = 'mind'"
          >
            🧠 Mind
            <span v-if="mermaidCharts.length" class="badge">{{ mermaidCharts.length }}</span>
          </button>
        </div>
        <button @click="showRightSidebar = false" class="icon-btn close-btn">✕</button>
      </div>
      
      <div class="sidebar-content right-content">
        <!-- 任务看板 -->
        <PlanWidget v-if="rightSidebarTab === 'plan'" :plan="currentPlan" />
        
        <!-- Mind / Mermaid 图表 -->
        <MermaidPanel v-else-if="rightSidebarTab === 'mind'" :charts="mermaidCharts" />
      </div>
    </div>

    <!-- 工作区面板 -->
    <div v-if="showWorkspacePanel && chatStore.conversationId" class="workspace-drawer">
       <div class="drawer-header">
         <h3>📁 项目文件</h3>
         <button @click="showWorkspacePanel = false" class="drawer-close-btn">✕</button>
       </div>
       <div class="drawer-body">
          <div class="workspace-explorer">
             <FileExplorer 
                :conversation-id="chatStore.conversationId"
                @file-select="handleFilePreviewSelect"
                @run-project="handleRunProjectFromExplorer"
             />
          </div>
          <div v-if="previewFile" class="workspace-preview-pane">
             <FilePreview
                :conversation-id="chatStore.conversationId"
                :file-path="previewFile.path"
                @close="previewFile = null"
             />
          </div>
          <div v-else class="workspace-empty-preview">
             <div class="empty-preview-icon">📄</div>
             <p>选择文件查看内容</p>
          </div>
       </div>
    </div>

    <!-- 附件预览模态框 -->
    <div v-if="previewingAttachment" class="file-preview-modal" @click.self="closeAttachmentPreview">
      <div class="preview-modal-content">
        <div class="preview-modal-header">
          <span class="preview-filename">{{ previewingAttachment.filename || previewingAttachment.name }}</span>
          <button class="close-preview-btn" @click="closeAttachmentPreview">✕</button>
        </div>
        <div class="preview-modal-body">
          <!-- 图片预览 -->
          <img 
            v-if="isImageFile(previewingAttachment)" 
            :src="previewingAttachment.preview_url || getFilePreviewUrl(previewingAttachment)"
            :alt="previewingAttachment.filename"
            class="preview-image"
            @error="handlePreviewError"
          />
          <!-- 其他文件 -->
          <div v-else class="preview-other">
            <div class="file-icon-large">{{ getFileTypeIcon(previewingAttachment) }}</div>
            <p class="file-name-large">{{ previewingAttachment.filename || previewingAttachment.name }}</p>
            <p class="file-meta">{{ getFileTypeLabel(previewingAttachment) }} · {{ formatFileSize(previewingAttachment.file_size) }}</p>
            <a 
              :href="getFilePreviewUrl(previewingAttachment)" 
              target="_blank" 
              class="download-btn"
            >
              📥 下载 / 打开
            </a>
          </div>
        </div>
      </div>
    </div>

    <!-- HITL 人类确认模态框 -->
    <div v-if="showConfirmModal" class="hitl-modal-overlay" @click.self="cancelHumanConfirmation">
      <div class="hitl-modal">
        <div class="hitl-modal-header">
          <span class="hitl-title">🤝 需要您的确认</span>
          <button class="hitl-close-btn" @click="cancelHumanConfirmation">✕</button>
        </div>
        
        <div class="hitl-modal-body">
          <!-- 问题内容 -->
          <div class="hitl-question">{{ confirmRequest?.question }}</div>
          
          <!-- 描述（如果有） -->
          <div v-if="confirmRequest?.description" class="hitl-description">
            {{ confirmRequest.description }}
          </div>
          
          <!-- yes_no / single_choice 类型 -->
          <div v-if="['yes_no', 'single_choice'].includes(confirmRequest?.confirmation_type)" class="hitl-options">
            <label 
              v-for="option in confirmRequest?.options" 
              :key="option" 
              class="hitl-option"
              :class="{ selected: confirmResponse === option }"
            >
              <input 
                type="radio" 
                :value="option" 
                v-model="confirmResponse"
                name="hitl-option"
              />
              <span class="option-label">{{ option === 'confirm' ? '✅ 确认' : option === 'cancel' ? '❌ 取消' : option }}</span>
            </label>
          </div>
          
          <!-- multiple_choice 类型 -->
          <div v-if="confirmRequest?.confirmation_type === 'multiple_choice'" class="hitl-options">
            <label 
              v-for="option in confirmRequest?.options" 
              :key="option" 
              class="hitl-option"
              :class="{ selected: confirmResponse?.includes(option) }"
            >
              <input 
                type="checkbox" 
                :value="option" 
                v-model="confirmResponse"
              />
              <span class="option-label">{{ option }}</span>
            </label>
          </div>
          
          <!-- text_input 类型 -->
          <div v-if="confirmRequest?.confirmation_type === 'text_input'" class="hitl-text-input">
            <textarea 
              v-model="confirmResponse" 
              placeholder="请输入您的回复..."
              rows="3"
            ></textarea>
          </div>
        </div>
        
        <div class="hitl-modal-footer">
          <button class="hitl-btn cancel" @click="cancelHumanConfirmation" :disabled="confirmSubmitting">
            取消
          </button>
          <button class="hitl-btn confirm" @click="submitHumanConfirmation" :disabled="confirmSubmitting">
            {{ confirmSubmitting ? '提交中...' : '提交' }}
          </button>
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
import { useWorkspaceStore } from '@/stores/workspace'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import MessageContent from '@/components/chat/MessageContent.vue'
import PlanWidget from '@/components/sidebar/PlanWidget.vue'
import FileExplorer from '@/components/workspace/FileExplorer.vue'
import FilePreview from '@/components/workspace/FilePreview.vue'
import MermaidPanel from '@/components/sidebar/MermaidPanel.vue'

// --- 基础状态 ---
const router = useRouter()
const route = useRoute()
const chatStore = useChatStore()
const workspaceStore = useWorkspaceStore()
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

// --- 文件上传状态 ---
const fileInput = ref(null)
const selectedFiles = ref([])  // 已选择的文件 { file, file_id, name, mime_type }
const isUploading = ref(false)

// --- 附件预览状态 ---
const previewingAttachment = ref(null)  // 正在预览的附件

// --- 重连状态 ---
const activeSessions = ref([])        // 活跃的 Session 列表
const showReconnectModal = ref(false) // 是否显示重连提示
const reconnectingSession = ref(null) // 正在重连的 Session

// --- 布局状态 ---
const sidebarCollapsed = ref(false)
const showRightSidebar = ref(true)
const showWorkspacePanel = ref(false)
const previewFile = ref(null)
const rightSidebarTab = ref('plan')  // 'plan' | 'mind'
const mermaidCharts = ref([])        // 存储检测到的 Mermaid 图表代码

// --- HITL 人类确认状态 ---
const showConfirmModal = ref(false)        // 是否显示确认对话框
const confirmRequest = ref(null)           // 当前确认请求数据
const confirmResponse = ref(null)          // 用户的响应
const confirmSubmitting = ref(false)       // 是否正在提交

// --- Computed ---
const currentConversationTitle = computed(() => {
  const conv = conversations.value.find(c => c.id === chatStore.conversationId)
  return conv ? conv.title : '新对话'
})

const currentPlan = computed(() => {
  // 从后往前查找最后一个有效的 plan
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const plan = messages.value[i].planResult
    // 确保 plan 是有效的对象（有 goal 或 steps）
    if (plan && typeof plan === 'object' && (plan.goal || plan.steps)) {
      return plan
    }
  }
  return null
})

// --- Lifecycle ---
onMounted(async () => {
  userId.value = chatStore.initUserId()
  await loadConversationList()
  
  // 🆕 检查是否有活跃的 Session（用于页面刷新重连）
  // 如果重连成功，会在内部调用 loadConversation，无需重复调用
  const sessionReconnected = await checkActiveSessions()
  
  // 只有没有重连 Session 时才根据路由参数加载对话
  const conversationId = route.params.conversationId
  if (conversationId && !sessionReconnected) {
    await loadConversation(conversationId)
  }
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
  mermaidCharts.value = []  // 清除 Mermaid 图表
  chatStore.conversationId = null
  router.push({ name: 'chat' })
  await loadConversationList()
  if (window.innerWidth < 768) sidebarCollapsed.value = true
}

async function loadConversation(conversationId) {
  if (chatStore.isConnected) chatStore.disconnectSSE()
  isLoading.value = false
  messages.value = []
  mermaidCharts.value = []  // 清除 Mermaid 图表
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
  // 🔧 Plan 数据解析（支持多种格式）
  let planData = null
  if (msg.metadata?.plan) {
    let rawPlan = msg.metadata.plan
    
    // 如果是 JSON 字符串，先解析
    if (typeof rawPlan === 'string') {
      try {
        rawPlan = JSON.parse(rawPlan)
      } catch (e) {
        console.warn('解析 metadata.plan JSON 失败:', e)
        rawPlan = null
      }
    }
    
    if (rawPlan && typeof rawPlan === 'object') {
      // 检查是否是嵌套结构（plan.plan）
      if (rawPlan.plan) {
        planData = rawPlan.plan
      } else if (rawPlan.goal || rawPlan.steps) {
        // 直接就是 plan 对象
        planData = rawPlan
      }
    }
  }
  
  // 🆕 提取文件信息
  let filesData = null
  if (msg.metadata?.files && msg.metadata.files.length > 0) {
    filesData = msg.metadata.files
  }
  
  return {
    id: msg.id,
    role: msg.role,
    content: extractText(msg.content),
    thinking: extractThinking(msg.content),
    contentBlocks: parseContentBlocks(msg.content),
    toolStatuses: {},
    files: filesData,  // 🆕 文件信息
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
  const hasFiles = selectedFiles.value.length > 0
  
  if ((!content && !hasFiles) || isLoading.value) return
  
  // 构建用户消息（包含文件）
  const userMsg = {
    id: Date.now(),
    role: 'user',
    content: content,
    files: hasFiles ? selectedFiles.value.map(f => ({
      file_id: f.file_id,
      filename: f.name,
      mime_type: f.mime_type
    })) : null,
    timestamp: new Date()
  }
  messages.value.push(userMsg)
  
  // 构建 files 参数（发送给后端）
  const filesParam = hasFiles ? selectedFiles.value.map(f => ({
    file_id: f.file_id
  })) : null
  
  // 清空输入
  inputMessage.value = ''
  selectedFiles.value = []
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
  
  // ✅ 获取响应式代理（Vue 会将 push 的对象转换为响应式）
  const reactiveMsg = messages.value[messages.value.length - 1]
  
  try {
    await chatStore.sendMessageStream(
      content,
      chatStore.conversationId,
      (event) => handleStreamEvent(event, reactiveMsg),
      { 
        files: filesParam,
        backgroundTasks: ['title_generation', 'recommended_questions'],
        // 🆕 前端上下文变量，直接注入到 Agent 的 System Prompt
        variables: {
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          locale: navigator.language,
          timestamp: new Date().toISOString()
        }
      }
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
    // 🆕 HITL 确认请求（通过 message_delta 发送）
    if (delta?.type === 'confirmation_request') {
      try {
        const hitlData = typeof delta.content === 'string' ? JSON.parse(delta.content) : delta.content
        console.log('🤝 收到 HITL 请求:', hitlData)
        showHumanConfirmation(hitlData)
      } catch (e) {
        console.warn('解析 HITL 请求失败:', e)
      }
    }
  }
  
  if (type === 'content_start') {
    const { index, content_block } = data
    while (msg.contentBlocks.length <= index) msg.contentBlocks.push(null)
    // 🆕 记录 block 类型到 contentBlocks，用于 content_delta 时判断
    msg.contentBlocks[index] = { ...content_block, _blockType: content_block.type }
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
    
    // 🆕 简化格式：delta 直接是字符串，类型由 content_block._blockType 决定
    const blockType = block?._blockType || ''
    const deltaText = typeof delta === 'string' ? delta : (delta.text || delta.thinking || delta.partial_json || '')
    
    if (blockType === 'text') {
      msg.content += deltaText
      if (block) block.text = (block.text || '') + deltaText
      scrollToBottom()
    } else if (blockType === 'thinking') {
      msg.thinking += deltaText
      if (block) block.thinking = (block.thinking || '') + deltaText
      scrollToBottom()
    } else if ((blockType === 'tool_use' || blockType === 'server_tool_use') && block) {
      // 工具参数增量（JSON 片段）
      block.partialInput = (block.partialInput || '') + deltaText
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

// ==================== HITL 人类确认相关方法 ====================

/**
 * 显示人类确认对话框
 */
function showHumanConfirmation(data) {
  confirmRequest.value = data
  confirmResponse.value = null
  showConfirmModal.value = true
  
  // 如果是 yes_no 类型，默认选中第一个选项
  if (data.confirmation_type === 'yes_no' && data.options?.length > 0) {
    confirmResponse.value = data.options[0]
  }
}

/**
 * 提交人类确认响应
 */
async function submitHumanConfirmation() {
  if (!confirmRequest.value || confirmSubmitting.value) return
  
  const requestId = confirmRequest.value.request_id
  const response = confirmResponse.value
  
  if (!response && confirmRequest.value.confirmation_type !== 'text_input') {
    alert('请选择一个选项')
    return
  }
  
  confirmSubmitting.value = true
  
  try {
    const res = await fetch(`/api/v1/human-confirmation/${requestId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ response })
    })
    
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }
    
    console.log('✅ HITL 响应已提交:', response)
    showConfirmModal.value = false
    confirmRequest.value = null
    confirmResponse.value = null
  } catch (error) {
    console.error('❌ 提交 HITL 响应失败:', error)
    alert('提交失败，请重试')
  } finally {
    confirmSubmitting.value = false
  }
}

/**
 * 取消/关闭确认对话框（等同于取消）
 */
function cancelHumanConfirmation() {
  if (confirmRequest.value) {
    // 发送取消响应
    confirmResponse.value = 'cancel'
    submitHumanConfirmation()
  } else {
    showConfirmModal.value = false
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
      return true  // 表示已处理对话加载
    }
    return false
  } catch (error) {
    // 静默失败，不影响正常使用
    console.log('ℹ️ 无活跃 Session 或检查失败')
    return false
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
      const newMsg = {
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
      messages.value.push(newMsg)
      // ✅ 获取响应式代理
      assistantMsg = messages.value[messages.value.length - 1]
    }
    
    // 3. 使用 SSE 重连端点（GET /api/v1/chat/{session_id}）
    const afterSeq = 0  // 从头开始获取所有事件
    const url = `/api/v1/chat/${session.session_id}?after_seq=${afterSeq}&format=zenflux`
    
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

// 🔧 防抖 scrollToBottom，避免重连时大量历史事件导致频繁滚动
let scrollTimer = null
function scrollToBottom() {
  if (!messagesContainer.value) return
  // 清除之前的定时器，只保留最后一次滚动
  if (scrollTimer) clearTimeout(scrollTimer)
  scrollTimer = setTimeout(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
    scrollTimer = null
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
function handleFilePreviewSelect(file) { previewFile.value = file }

// 处理从文件浏览器运行项目
async function handleRunProjectFromExplorer(project) {
  console.log('🚀 开始运行项目:', project)
  
  try {
    const result = await workspaceStore.runProject(
      chatStore.conversationId,
      project.name,
      project.type
    )
    
    console.log('📦 运行结果:', result)
    console.log('📍 preview_url:', result.preview_url)
    console.log('📍 success:', result.success)
    
    if (result.success && result.preview_url) {
      console.log('✅ 打开预览:', result.preview_url)
      
      // 尝试打开新窗口
      const newWindow = window.open(result.preview_url, '_blank')
      
      // 检测是否被浏览器拦截
      if (!newWindow || newWindow.closed || typeof newWindow.closed === 'undefined') {
        console.warn('⚠️ 弹窗被浏览器拦截，显示提示')
        // 如果被拦截，显示可点击的链接
        const shouldOpen = confirm(
          `项目已启动！\n\n预览地址：${result.preview_url}\n\n点击"确定"在新窗口打开预览`
        )
        if (shouldOpen) {
          window.open(result.preview_url, '_blank')
        }
      } else {
        console.log('✅ 新窗口已打开')
      }
    } else if (!result.success) {
      alert('启动项目失败: ' + (result.error || result.message))
    }
  } catch (error) {
    console.error('❌ 运行项目失败:', error)
    alert('运行项目失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 处理 Mermaid 图表检测
function handleMermaidDetected(charts) {
  if (!charts || charts.length === 0) return
  
  // 将新检测到的图表添加到列表中（去重）
  charts.forEach(chart => {
    if (!mermaidCharts.value.includes(chart)) {
      mermaidCharts.value.push(chart)
    }
  })
  
  // 如果检测到图表，自动切换到 Mind 标签并打开侧边栏
  if (mermaidCharts.value.length > 0) {
    rightSidebarTab.value = 'mind'
    if (!showRightSidebar.value) {
      showRightSidebar.value = true
    }
  }
}

// ==================== 文件上传相关方法 ====================

function triggerFileUpload() {
  if (fileInput.value) {
    fileInput.value.click()
  }
}

async function handleFileSelect(event) {
  const files = event.target.files
  if (!files || files.length === 0) return
  
  isUploading.value = true
  
  try {
    for (const file of files) {
      // 上传文件到后端
      const result = await uploadFile(file)
      if (result) {
        selectedFiles.value.push({
          file_id: result.file_id,
          name: result.filename || file.name,
          mime_type: result.mime_type || file.type,
          file_size: result.file_size || file.size
        })
      }
    }
  } catch (error) {
    console.error('文件上传失败:', error)
    alert('文件上传失败，请重试')
  } finally {
    isUploading.value = false
    // 清空 input，允许重复选择同一文件
    if (fileInput.value) {
      fileInput.value.value = ''
    }
  }
}

async function uploadFile(file) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('user_id', chatStore.initUserId())
  
  try {
    const response = await fetch('/api/v1/files/upload', {
      method: 'POST',
      body: formData
    })
    
    if (!response.ok) {
      throw new Error(`上传失败: ${response.status}`)
    }
    
    const result = await response.json()
    console.log('✅ 文件上传成功:', result.data)
    return result.data
  } catch (error) {
    console.error('❌ 文件上传失败:', error)
    throw error
  }
}

function removeFile(index) {
  selectedFiles.value.splice(index, 1)
}

function getFileIcon(file) {
  const mimeType = file.mime_type || ''
  if (mimeType.startsWith('image/')) return '🖼️'
  if (mimeType === 'application/pdf') return '📄'
  if (mimeType.includes('text/')) return '📝'
  if (mimeType.includes('json')) return '📋'
  return '📎'
}

function getFileTypeIcon(file) {
  const mimeType = file.mime_type || ''
  if (mimeType.startsWith('image/')) return '🖼️'
  if (mimeType === 'application/pdf') return '📕'
  if (mimeType.includes('text/')) return '📄'
  return '📎'
}

function getFileTypeLabel(file) {
  const mimeType = file.mime_type || ''
  if (mimeType.startsWith('image/')) return 'Image'
  if (mimeType === 'application/pdf') return 'PDF'
  if (mimeType === 'text/plain') return 'Text'
  if (mimeType === 'text/markdown') return 'Markdown'
  if (mimeType === 'text/csv') return 'CSV'
  if (mimeType.includes('json')) return 'JSON'
  return 'File'
}

// ==================== 附件预览相关方法 ====================

function openAttachmentPreview(file) {
  console.log('📄 预览附件:', file)
  // 直接使用 /preview 端点，无需提前获取 URL
  previewingAttachment.value = { ...file }
}

async function getFileUrl(fileId) {
  try {
    const response = await fetch(`/api/v1/files/${fileId}/url`)
    if (!response.ok) throw new Error('获取失败')
    const result = await response.json()
    console.log('📎 获取文件 URL:', result.data)
    return result.data.file_url  // API 返回的是 file_url
  } catch (error) {
    console.error('获取文件 URL 失败:', error)
    return null
  }
}

function getFilePreviewUrl(file) {
  // 优先使用代理预览端点（绕过 CORS）
  if (file.file_id) return `/api/v1/files/${file.file_id}/preview`
  if (file.preview_url) return file.preview_url
  if (file.file_url) return file.file_url
  return ''
}

function closeAttachmentPreview() {
  previewingAttachment.value = null
}

function isImageFile(file) {
  const mimeType = file.mime_type || ''
  return mimeType.startsWith('image/')
}

function formatFileSize(bytes) {
  if (!bytes) return '未知大小'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function handlePreviewError(event) {
  const src = event.target.src
  console.error('图片加载失败:', src)
  // 不清空 src，让用户看到尝试加载的 URL
  event.target.style.display = 'none'
  // 在图片位置显示错误信息
  const errorDiv = document.createElement('div')
  errorDiv.className = 'preview-error'
  errorDiv.innerHTML = `
    <p>⚠️ 图片加载失败</p>
    <p style="font-size: 12px; color: #6b7280; word-break: break-all; max-width: 400px;">
      ${src ? src.substring(0, 100) + '...' : '无 URL'}
    </p>
    <a href="${src}" target="_blank" style="color: #2563eb; font-size: 14px;">尝试直接打开</a>
  `
  event.target.parentNode.appendChild(errorDiv)
}

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

.action-buttons {
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
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
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
  transition: all 0.2s;
}

.new-chat-btn:hover {
  background: #f3f4f6;
  border-color: #d1d5db;
}

.nav-buttons {
  display: flex;
  gap: 8px;
}

.nav-btn {
  flex: 1;
  padding: 8px;
  background: transparent;
  color: #4b5563;
  border: 1px solid transparent;
  border-radius: 6px;
  text-align: center;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font-size: 13px;
  transition: all 0.2s;
}

.nav-btn:hover {
  background: #e5e7eb;
  color: #111827;
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
  max-width: 100%;
}

.user-text {
  word-break: break-word;
}

/* 用户消息中的文件列表 */
.message-files {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 8px;
}

.message-file-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: white;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
}

.file-type-icon {
  font-size: 20px;
}

.file-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.file-title {
  font-size: 14px;
  font-weight: 500;
  color: #111827;
}

.file-type {
  font-size: 12px;
  color: #6b7280;
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
  flex-direction: column;
  gap: 8px;
}

.input-row {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  width: 100%;
}

/* 已选文件预览 */
.selected-files {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f3f4f6;
}

.file-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: #f3f4f6;
  border-radius: 8px;
  font-size: 13px;
  color: #374151;
}

.file-icon {
  font-size: 14px;
}

.file-name {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.remove-file {
  background: none;
  border: none;
  color: #9ca3af;
  cursor: pointer;
  font-size: 16px;
  padding: 0 2px;
  line-height: 1;
}

.remove-file:hover {
  color: #ef4444;
}

/* 文件上传按钮 */
.attach-btn {
  background: none;
  border: none;
  color: #6b7280;
  cursor: pointer;
  font-size: 18px;
  padding: 6px;
  border-radius: 6px;
  transition: all 0.2s;
  flex-shrink: 0;
}

.attach-btn:hover {
  background: #f3f4f6;
  color: #111827;
}

.attach-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.uploading-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
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
  width: 340px;
  background-color: #ffffff;
  border-left: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
}

.right-sidebar .sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid #f3f4f6;
}

.sidebar-tabs {
  display: flex;
  gap: 4px;
}

.tab-btn {
  padding: 6px 12px;
  border: none;
  background: transparent;
  color: #6b7280;
  font-size: 13px;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 4px;
}

.tab-btn:hover {
  background: #f3f4f6;
  color: #374151;
}

.tab-btn.active {
  background: #fef3c7;
  color: #92400e;
}

.tab-btn .badge {
  background: #fbbf24;
  color: #78350f;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 10px;
  font-weight: 600;
}

.right-content {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
  background: #f9fafb;
}

/* --- 工作区悬浮面板（暗色主题） --- */
.workspace-drawer {
  position: absolute;
  top: 0;
  bottom: 0;
  right: 0;
  width: 700px;
  background: #0f0f1a;
  border-left: 1px solid #2d2d44;
  z-index: 20;
  display: flex;
  flex-direction: column;
  box-shadow: -8px 0 32px rgba(0, 0, 0, 0.4);
}

.drawer-header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: linear-gradient(135deg, #1a1a2e 0%, #13131f 100%);
  border-bottom: 1px solid #2d2d44;
}

.drawer-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #e5e5e5;
  letter-spacing: 0.3px;
}

.drawer-close-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  color: #a0a0b0;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.drawer-close-btn:hover {
  background: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.3);
  color: #ef4444;
}

.drawer-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.workspace-explorer {
  width: 280px;
  min-width: 280px;
  border-right: 1px solid #2d2d44;
  overflow: hidden;
  background: #13131f;
}

.workspace-preview-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #0f0f1a;
  overflow: hidden;
}

.workspace-empty-preview {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #666;
  text-align: center;
  background: #0f0f1a;
}

.empty-preview-icon {
  font-size: 48px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.workspace-empty-preview p {
  margin: 0;
  font-size: 14px;
  color: #666;
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

/* ==================== 文件预览模态框 ==================== */
.file-preview-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  backdrop-filter: blur(4px);
}

.preview-modal-content {
  background: white;
  border-radius: 16px;
  max-width: 90vw;
  max-height: 90vh;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  animation: modalFadeIn 0.2s ease;
}

@keyframes modalFadeIn {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.preview-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
  background: #f9fafb;
}

.preview-filename {
  font-weight: 500;
  color: #111827;
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.close-preview-btn {
  background: none;
  border: none;
  font-size: 20px;
  color: #6b7280;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: all 0.2s;
}

.close-preview-btn:hover {
  background: #e5e7eb;
  color: #111827;
}

.preview-modal-body {
  padding: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 300px;
  min-height: 200px;
}

.preview-image {
  max-width: 80vw;
  max-height: 75vh;
  object-fit: contain;
  border-radius: 8px;
}

.preview-other {
  text-align: center;
  padding: 40px;
}

.file-icon-large {
  font-size: 64px;
  margin-bottom: 16px;
}

.file-name-large {
  font-size: 18px;
  font-weight: 500;
  color: #111827;
  margin-bottom: 8px;
}

.file-meta {
  font-size: 14px;
  color: #6b7280;
  margin-bottom: 24px;
}

.download-btn {
  display: inline-block;
  padding: 10px 24px;
  background: #111827;
  color: white;
  border-radius: 8px;
  text-decoration: none;
  font-size: 14px;
  transition: all 0.2s;
}

.download-btn:hover {
  background: #374151;
  transform: translateY(-1px);
}

/* 文件卡片可点击样式 */
.message-file-item.clickable {
  cursor: pointer;
  transition: all 0.2s;
}

.message-file-item.clickable:hover {
  background: #f3f4f6;
  transform: translateX(2px);
}

.preview-hint {
  margin-left: auto;
  opacity: 0;
  transition: opacity 0.2s;
  font-size: 14px;
}

.message-file-item.clickable:hover .preview-hint {
  opacity: 1;
}

.preview-error {
  text-align: center;
  padding: 40px;
  color: #374151;
}

.preview-error p {
  margin: 8px 0;
}

/* ==================== HITL 人类确认模态框 ==================== */
.hitl-modal-overlay {
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

.hitl-modal {
  background: white;
  border-radius: 16px;
  width: 90%;
  max-width: 480px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
  animation: hitlModalSlideIn 0.3s ease;
}

@keyframes hitlModalSlideIn {
  from {
    opacity: 0;
    transform: translateY(-20px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.hitl-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid #e5e7eb;
}

.hitl-title {
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}

.hitl-close-btn {
  background: none;
  border: none;
  font-size: 20px;
  color: #6b7280;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: all 0.2s;
}

.hitl-close-btn:hover {
  background: #e5e7eb;
  color: #111827;
}

.hitl-modal-body {
  padding: 24px;
}

.hitl-question {
  font-size: 16px;
  color: #111827;
  line-height: 1.6;
  margin-bottom: 16px;
  white-space: pre-wrap;
}

.hitl-description {
  font-size: 14px;
  color: #6b7280;
  margin-bottom: 20px;
  padding: 12px;
  background: #f9fafb;
  border-radius: 8px;
}

.hitl-options {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hitl-option {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  background: #f9fafb;
  border: 2px solid transparent;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.hitl-option:hover {
  background: #f3f4f6;
  border-color: #d1d5db;
}

.hitl-option.selected {
  background: #eff6ff;
  border-color: #3b82f6;
}

.hitl-option input {
  margin-right: 12px;
  accent-color: #3b82f6;
}

.option-label {
  font-size: 15px;
  color: #111827;
}

.hitl-text-input textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 15px;
  resize: vertical;
  font-family: inherit;
}

.hitl-text-input textarea:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.hitl-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid #e5e7eb;
  background: #f9fafb;
  border-radius: 0 0 16px 16px;
}

.hitl-btn {
  padding: 10px 24px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.hitl-btn.cancel {
  background: #e5e7eb;
  color: #374151;
}

.hitl-btn.cancel:hover {
  background: #d1d5db;
}

.hitl-btn.confirm {
  background: #3b82f6;
  color: white;
}

.hitl-btn.confirm:hover {
  background: #2563eb;
}

.hitl-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>

<template>
  <div class="h-screen w-full flex bg-white relative overflow-hidden text-gray-900 font-sans">
    <!-- 左侧侧边栏：历史对话 -->
    <ConversationSidebar
      :conversations="conversationStore.conversations"
      :current-id="conversationStore.currentId"
      :collapsed="sidebarCollapsed"
      :loading="conversationStore.loading"
      :is-running="sessionStore.isConversationRunning"
      :username="authStore.username"
      :is-authenticated="authStore.isAuthenticated"
      @select="handleSelectConversation"
      @create="handleCreateConversation"
      @delete="handleDeleteConversation"
      @toggle-collapse="sidebarCollapsed = !sidebarCollapsed"
      @navigate="handleNavigate"
      @logout="handleLogout"
    />

    <!-- 右侧主区域 -->
    <div class="flex-1 flex min-w-0 relative z-10 overflow-hidden">
      <!-- 聊天内容区域 -->
      <div 
        class="flex flex-col min-w-0 overflow-hidden transition-all duration-300"
        :class="showRightSidebar ? 'w-1/2' : 'flex-1'"
      >
        <!-- 顶部导航栏 -->
        <ChatHeader
          :title="conversationStore.currentTitle"
          :agents="agents"
          :selected-agent-id="selectedAgentId"
          :disabled="chat.isLoading.value"
          :loading-agents="loadingAgents"
          :show-workspace-button="!!conversationStore.currentId"
          :sidebar-active="showRightSidebar"
          @select-agent="handleSelectAgent"
          @toggle-sidebar="showRightSidebar = !showRightSidebar"
        />

        <!-- 消息列表区域 -->
        <MessageList
          ref="messageListRef"
          :messages="conversationStore.messages"
          :loading="chat.isLoading.value"
          :generating="chat.isGenerating.value"
          :loading-more="conversationStore.loadingMore"
          :has-more="conversationStore.hasMore"
          @suggestion-click="handleSuggestionClick"
          @file-preview="handleFilePreview"
          @load-more="handleLoadMore"
        />

        <!-- 输入框区域 -->
        <ChatInputArea
          ref="inputAreaRef"
          v-model="inputMessage"
          :selected-files="fileUpload.selectedFiles.value"
          :loading="isCurrentLoading"
          :stopping="chat.isStopping.value"
          :uploading="fileUpload.isUploading.value"
          :disabled="isCurrentLoading"
          @send="handleSendMessage"
          @stop="handleStopGeneration"
          @upload-click="handleUploadClick"
          @remove-file="handleRemoveFile"
        />
      </div>

      <!-- 统一的右侧面板（任务/工作区） -->
      <Transition name="slide-right">
        <div 
          v-if="showRightSidebar"
          class="w-1/2 flex-shrink-0 bg-white flex flex-col overflow-hidden my-4 mr-4 ml-3 rounded-2xl shadow-xl border border-gray-100"
        >
            <!-- 顶部 Tab 栏 -->
            <div class="h-14 flex items-center justify-between px-4 border-b border-gray-100 flex-shrink-0">
              <div class="flex gap-1 p-1 bg-gray-100 rounded-lg">
          <button 
                  class="px-3 py-1.5 rounded-md text-xs font-medium transition-all flex items-center gap-1.5" 
                  :class="rightSidebarTab === 'plan' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-900'"
            @click="rightSidebarTab = 'plan'"
          >
                  <ClipboardList class="w-3.5 h-3.5" />
                  任务
          </button>
          <button 
                  v-if="conversationStore.currentId"
                  class="px-3 py-1.5 rounded-md text-xs font-medium transition-all flex items-center gap-1.5" 
                  :class="rightSidebarTab === 'workspace' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-900'"
                  @click="rightSidebarTab = 'workspace'"
                >
                  <FileText class="w-3.5 h-3.5" />
                  工作区
          </button>
        </div>
              <button 
                @click="showRightSidebar = false" 
                class="w-7 h-7 flex items-center justify-center rounded-full bg-gray-100 hover:bg-gray-200 text-gray-500 transition-colors"
              >
                <X class="w-4 h-4" />
              </button>
      </div>
      
        <!-- 任务看板 -->
            <div v-if="rightSidebarTab === 'plan'" class="flex-1 overflow-y-auto p-4 scrollbar-thin">
          <PlanWidget v-if="currentPlan" :plan="currentPlan" />
          <div v-else class="h-full flex flex-col items-center justify-center text-gray-400 opacity-60">
                  <div class="w-16 h-16 bg-gray-50 rounded-2xl flex items-center justify-center mb-4 border border-gray-100">
                    <ClipboardList class="w-8 h-8 text-gray-400" />
            </div>
            <p class="text-sm font-medium">暂无任务计划</p>
            <p class="text-xs mt-1">AI 生成计划后将显示在这里</p>
      </div>
    </div>

            <!-- 工作区 -->
            <div v-else-if="rightSidebarTab === 'workspace'" class="flex-1 flex overflow-hidden">
              <!-- 文件浏览器 -->
              <div class="w-[220px] min-w-[220px] border-r border-gray-100 bg-gray-50 overflow-y-auto">
             <FileExplorer 
                  v-if="conversationStore.currentId"
                  :conversation-id="conversationStore.currentId"
                @file-select="handleFilePreviewSelect"
                  @run-project="handleRunProject"
             />
          </div>
              <!-- 文件预览 -->
              <div class="flex-1 flex flex-col overflow-hidden">
             <FilePreview
                  v-if="previewFile && conversationStore.currentId"
                  :conversation-id="conversationStore.currentId"
                :file-path="previewFile.path"
                @close="previewFile = null"
             />
                <div v-else class="h-full flex flex-col items-center justify-center text-gray-400 bg-gray-50/50">
                  <div class="w-16 h-16 bg-white rounded-2xl flex items-center justify-center mb-4 border border-gray-100">
                    <FileText class="w-8 h-8 text-gray-400" />
             </div>
             <p class="text-sm font-medium">选择文件查看内容</p>
          </div>
       </div>
    </div>
            </div>
      </Transition>
    </div>
          
    <!-- 文件上传 input -->
              <input 
      type="file" 
      ref="fileInputRef" 
      @change="handleFileSelect" 
      multiple 
      accept="image/*,.pdf,.txt,.md,.csv,.json"
      style="display: none"
    />

    <!-- 附件预览模态框 -->
    <AttachmentPreview
      :show="!!previewingAttachment"
      :file="previewingAttachment"
      @close="previewingAttachment = null"
    />

    <!-- HITL 人类确认模态框 -->
    <ConfirmModal
      :show="hitl.showModal.value"
      :request="hitl.request.value"
      :submitting="hitl.isSubmitting.value"
      @submit="handleHITLSubmit"
      @cancel="handleHITLCancel"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'

// Stores
import { useConversationStore } from '@/stores/conversation'
import { useSessionStore } from '@/stores/session'
import { useWorkspaceStore } from '@/stores/workspace'
import { useAuthStore } from '@/stores/auth'

// Composables
import { useChat } from '@/composables/useChat'
import { useFileUpload } from '@/composables/useFileUpload'
import { ClipboardList, FileText, X } from 'lucide-vue-next'

// Components
import ConversationSidebar from '@/components/chat/ConversationSidebar.vue'
import ChatHeader from '@/components/chat/ChatHeader.vue'
import MessageList from '@/components/chat/MessageList.vue'
import ChatInputArea from '@/components/chat/ChatInputArea.vue'
import PlanWidget from '@/components/sidebar/PlanWidget.vue'
import FileExplorer from '@/components/workspace/FileExplorer.vue'
import FilePreview from '@/components/workspace/FilePreview.vue'
import AttachmentPreview from '@/components/modals/AttachmentPreview.vue'
import ConfirmModal from '@/components/modals/ConfirmModal.vue'

// Types
import type { Conversation, Agent, AttachedFile, PlanData, HITLResponse, FileItem } from '@/types'

// ==================== Stores & Composables ====================

const router = useRouter()
const route = useRoute()
const conversationStore = useConversationStore()
const sessionStore = useSessionStore()
const workspaceStore = useWorkspaceStore()
const authStore = useAuthStore()

const chat = useChat()
const fileUpload = useFileUpload()
const hitl = chat.hitl

// ==================== State ====================

// UI 状态
const sidebarCollapsed = ref(false)
const showRightSidebar = ref(true)
const rightSidebarTab = ref<'plan' | 'workspace'>('plan')

// 输入
const inputMessage = ref('')

// Agent
const agents = ref<Agent[]>([])
const loadingAgents = ref(false)
const selectedAgentId = ref<string | null>(null)

// 预览
const previewFile = ref<FileItem | null>(null)
const previewingAttachment = ref<AttachedFile | null>(null)

// Refs
const messageListRef = ref<InstanceType<typeof MessageList> | null>(null)
const inputAreaRef = ref<InstanceType<typeof ChatInputArea> | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

// ==================== Computed ====================

/** 当前 Plan（优先从 conversation_metadata 获取，否则从消息中查找） */
const currentPlan = computed<PlanData | null>(() => {
  // 优先使用从 conversation_metadata 加载的 plan
  if (conversationStore.conversationPlan) {
    return conversationStore.conversationPlan
  }
  
  // 否则从消息列表中查找最新的 plan
  const messages = conversationStore.messages
  for (let i = messages.length - 1; i >= 0; i--) {
    const plan = messages[i].planResult
    if (plan && typeof plan === 'object' && plan.todos) {
      return plan
    }
  }
  return null
})

/** 当前会话是否正在加载 */
const isCurrentLoading = computed(() => {
  if (chat.isLoading.value) return true
  const convId = conversationStore.currentId
  if (convId && sessionStore.isConversationRunning(convId)) return true
  return false
})

// ==================== Lifecycle ====================

onMounted(async () => {
  // 初始化
  conversationStore.initUserId()
  
    // 并行加载（获取最近 50 个对话，不含具体消息）
  await Promise.all([
    conversationStore.fetchList(),
    loadAgentList()
  ])
  
  // 启动活跃会话轮询
  sessionStore.startPolling(conversationStore.userId)
  
  // 根据路由加载会话（只在 onMounted 中加载一次）
  const conversationId = route.params.conversationId
  if (conversationId && typeof conversationId === 'string') {
    await conversationStore.load(conversationId)
  }
  
  // 设置文件输入引用
  fileUpload.setFileInputRef(fileInputRef.value)
})

onUnmounted(() => {
  sessionStore.stopPolling()
})


// ==================== Methods ====================

/** 加载 Agent 列表 */
async function loadAgentList(): Promise<void> {
  loadingAgents.value = true
  try {
    const response = await fetch('/api/v1/agents')
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    
    const result = await response.json()
    const agentsList = result.agents || []
    
    // 添加默认 Agent
    agents.value = [
      {
        agent_id: null,
        name: '默认智能体',
        description: '通用对话助手 (base_agent)',
        is_active: true
      },
      ...agentsList
    ]
    
    // 默认选择 dazee_agent
    if (!selectedAgentId.value) {
      const dazeeAgent = agents.value.find(a => a.agent_id === 'dazee_agent')
      selectedAgentId.value = dazeeAgent?.agent_id || null
    }
  } catch (error) {
    console.error('❌ 加载 Agent 列表失败:', error)
    agents.value = [{ agent_id: null, name: '默认智能体', description: '通用对话助手' }]
  } finally {
    loadingAgents.value = false
  }
}

/** 选择 Agent */
function handleSelectAgent(agent: Agent): void {
  selectedAgentId.value = agent.agent_id
}

/** 选择会话 */
async function handleSelectConversation(id: string): Promise<void> {
  // 只更新路由，由 useChat 的 watch 统一处理加载
  router.push({ name: 'conversation', params: { conversationId: id } })
}

/** 创建新会话 */
async function handleCreateConversation(): Promise<void> {
  conversationStore.reset()
  router.push({ name: 'chat' })
  await conversationStore.fetchList(50)
}

/** 删除会话 */
async function handleDeleteConversation(conv: Conversation): Promise<void> {
  if (confirm(`删除 "${conv.title}"?`)) {
    await conversationStore.remove(conv.id)
    if (conversationStore.currentId === conv.id) {
      await handleCreateConversation()
    }
  }
}

/** 导航 */
function handleNavigate(path: string): void {
  router.push(path)
}

/** 登出 */
function handleLogout(): void {
  if (confirm('确定要退出登录吗？')) {
    authStore.logout()
    router.push('/login')
  }
}

/** 点击建议 */
function handleSuggestionClick(text: string): void {
  inputMessage.value = text
  inputAreaRef.value?.focus()
}

/** 发送消息 */
async function handleSendMessage(): Promise<void> {
  const content = inputMessage.value.trim()
  const files = fileUpload.selectedFiles.value.length > 0 
    ? [...fileUpload.selectedFiles.value] 
    : undefined

  if (!content && !files?.length) return
  
  // 清空输入
  inputMessage.value = ''
  fileUpload.clearFiles()

  // 发送
  await chat.sendMessage(content, files, {
    agentId: selectedAgentId.value
  })

  // 刷新会话列表（保持 50 条，失败不影响用户体验）
  try {
    await conversationStore.fetchList(50)
  } catch (e) {
    console.warn('⚠️ 刷新会话列表失败:', e)
  }

  // 滚动到底部
  messageListRef.value?.scrollToBottom()
}

/** 停止生成 */
async function handleStopGeneration(): Promise<void> {
  await chat.stopGeneration()
}

/** 点击上传按钮 */
function handleUploadClick(): void {
  fileInputRef.value?.click()
}

/** 处理文件选择 */
async function handleFileSelect(event: Event): Promise<void> {
  try {
    await fileUpload.handleFileSelect(event)
  } catch {
    alert('文件上传失败，请重试')
  }
}

/** 移除文件 */
function handleRemoveFile(index: number): void {
  fileUpload.removeFile(index)
}

/** 文件预览（消息中的附件） */
function handleFilePreview(file: AttachedFile): void {
  previewingAttachment.value = file
}

/** 文件预览（工作区） */
function handleFilePreviewSelect(file: FileItem): void {
  previewFile.value = file
}

/** 加载更多历史消息 */
async function handleLoadMore(): Promise<void> {
  // 记录当前滚动高度
  const previousHeight = messageListRef.value?.getScrollHeight() || 0
  
  // 加载更多
  const loaded = await conversationStore.loadMore()
  
  // 保持滚动位置
  if (loaded && messageListRef.value) {
    messageListRef.value.maintainScrollPosition(previousHeight)
  }
}

/** 运行项目 */
async function handleRunProject(project: { name: string; type: string }): Promise<void> {
  if (!conversationStore.currentId) return
  
  try {
    const result = await workspaceStore.runProject(
      conversationStore.currentId,
      project.name,
      project.type
    )
    
    if (result.success && result.preview_url) {
      const newWindow = window.open(result.preview_url, '_blank')
      if (!newWindow) {
        const shouldOpen = confirm(`项目已启动！\n\n预览地址：${result.preview_url}\n\n点击"确定"在新窗口打开预览`)
        if (shouldOpen) {
          window.open(result.preview_url, '_blank')
        }
      }
    } else if (!result.success) {
      alert('启动项目失败: ' + (result.error || result.message))
    }
  } catch (error) {
    console.error('❌ 运行项目失败:', error)
    alert('运行项目失败')
  }
}

/** HITL 提交 */
async function handleHITLSubmit(response: HITLResponse): Promise<void> {
  hitl.updateResponse(response)
  await hitl.submit()
}

/** HITL 取消 */
async function handleHITLCancel(): Promise<void> {
  await hitl.cancel()
}
</script>

<style scoped>
/* 滚动条美化 - 默认透明，hover 时显示 */
.scrollbar-thin::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-thin::-webkit-scrollbar-thumb {
  background-color: transparent;
  border-radius: 3px;
}
/* 鼠标悬停在容器上时显示滚动条 */
.scrollbar-thin:hover::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.3);
}
.scrollbar-thin::-webkit-scrollbar-thumb:hover {
  background-color: rgba(156, 163, 175, 0.5);
}

/* 右侧面板过渡动画 - 使用 width 和 margin 实现平滑推开效果 */
.slide-right-enter-active,
.slide-right-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.slide-right-enter-from,
.slide-right-leave-to {
  width: 0 !important;
  margin-left: 0 !important;
  margin-right: 0 !important;
  opacity: 0;
  overflow: hidden;
}

</style>

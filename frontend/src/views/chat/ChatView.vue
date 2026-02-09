<template>
  <div class="h-screen w-full flex bg-background relative overflow-hidden text-foreground font-sans">
    <!-- 左侧侧边栏：历史对话 -->
    <ConversationSidebar
      :conversations="filteredConversations"
      :current-id="conversationStore.currentId"
      :collapsed="sidebarCollapsed"
      :loading="conversationStore.loading"
      :user-id="conversationStore.userId"
      :is-running="sessionStore.isConversationRunning"
      :agents="agentStore.agents"
      :current-agent-id="agentStore.currentAgentId"
      @select="handleSelectConversation"
      @create="handleCreateConversation"
      @delete="handleDeleteConversation"
      @toggle-collapse="sidebarCollapsed = !sidebarCollapsed"
      @navigate="handleNavigate"
      @select-agent="handleSelectAgent"
      @edit-agent="handleEditAgent"
      @delete-agent="handleDeleteAgent"
    />

    <!-- 右侧主区域 -->
    <div class="flex-1 flex min-w-0 relative z-10 overflow-hidden">

      <!-- 无项目空状态：引导用户创建第一个项目 -->
      <div v-if="showEmptyProjectState" class="flex-1 flex flex-col items-center justify-center text-center px-8">
        <div class="w-20 h-20 bg-card rounded-3xl shadow-lg border border-border flex items-center justify-center mb-8 transform hover:scale-105 transition-transform duration-300">
          <Rocket class="w-10 h-10 text-primary" />
        </div>
        <h1 class="text-2xl font-bold mb-3 text-foreground">创建你的第一个项目</h1>
        <p class="text-muted-foreground mb-8 max-w-md text-sm leading-relaxed">项目是你和 AI 协作的空间。创建一个项目，开始智能对话吧。</p>
        <button
          @click="router.push('/create-project')"
          class="inline-flex items-center gap-2 px-6 py-3 bg-primary text-primary-foreground rounded-xl font-medium text-sm hover:bg-primary/90 transition-colors shadow-md hover:shadow-lg"
        >
          <Plus class="w-4 h-4" />
          新建项目
        </button>
      </div>

      <!-- 聊天内容区域 -->
      <div 
        v-else
        class="flex flex-col min-w-0 overflow-hidden transition-all duration-300"
        :class="showRightSidebar ? 'w-1/2' : 'flex-1'"
      >
        <!-- Agent 项目顶部导航栏 -->
        <div v-if="isAgentMode && agentStore.currentAgent" class="flex-shrink-0 h-12 flex items-center gap-3 px-4 border-b border-border bg-background/80 backdrop-blur-sm relative z-20">
          <!-- 项目名称 -->
          <div class="flex items-center gap-2 text-sm font-medium text-foreground mr-2">
            <Bot class="w-4 h-4 text-primary" />
            <span class="truncate max-w-[120px]">{{ agentStore.currentAgent.name }}</span>
          </div>

          <!-- 分隔线 -->
          <div class="w-px h-5 bg-border"></div>

          <!-- 对话标签页（仅显示打开的标签） -->
          <div class="flex items-center gap-1 flex-1 min-w-0 overflow-x-auto scrollbar-none">
            <div
              v-for="convId in agentStore.currentOpenTabIds"
              :key="convId"
              class="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer"
              :class="conversationStore.currentId === convId 
                ? 'bg-accent text-accent-foreground' 
                : 'text-muted-foreground hover:bg-muted hover:text-foreground'"
              @click="handleSelectConversation(convId)"
            >
              <MessageSquare class="w-3 h-3" />
              <span class="truncate max-w-[100px]">{{ getConversationTitle(convId) }}</span>
              <!-- 关闭标签（不删除对话，仅从标签栏移除） -->
              <button
                class="ml-1 p-0.5 rounded hover:bg-muted-foreground/10 hover:text-foreground transition-colors"
                title="关闭标签"
                @click.stop="handleCloseTab(convId)"
              >
                <X class="w-3 h-3" />
              </button>
            </div>
          </div>

          <!-- 新建对话按钮 -->
          <button 
            @click="handleCreateConversation"
            class="flex-shrink-0 p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors"
            title="新建对话"
          >
            <Plus class="w-4 h-4" />
          </button>

          <!-- 历史记录按钮 -->
          <div ref="historyDropdownRef" class="relative flex-shrink-0">
            <button 
              @click="showHistoryDropdown = !showHistoryDropdown"
              class="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors"
              :class="showHistoryDropdown ? 'bg-muted text-foreground' : ''"
              title="历史记录"
            >
              <History class="w-4 h-4" />
            </button>

            <!-- 历史记录下拉面板 -->
            <Transition name="fade">
              <div 
                v-if="showHistoryDropdown" 
                class="absolute right-0 top-full mt-1 w-72 bg-card border border-border rounded-xl shadow-lg z-50 overflow-hidden"
              >
                <div class="px-3 py-2 border-b border-border">
                  <span class="text-xs font-medium text-muted-foreground">历史对话</span>
                </div>
                <div class="max-h-64 overflow-y-auto scrollbar-thin">
                  <!-- 无历史记录 -->
                  <div v-if="agentStore.currentConversationIds.length === 0" class="px-4 py-6 text-center">
                    <p class="text-xs text-muted-foreground/50">暂无对话记录</p>
                  </div>
                  <!-- 历史列表 -->
                  <div
                    v-for="convId in agentStore.currentConversationIds"
                    :key="convId"
                    class="group flex items-center gap-2 px-3 py-2.5 hover:bg-muted cursor-pointer transition-colors"
                    @click="handleOpenFromHistory(convId)"
                  >
                    <MessageSquare class="w-3.5 h-3.5 flex-shrink-0 text-muted-foreground/50" />
                    <div class="flex-1 min-w-0">
                      <div class="flex items-center gap-2">
                        <span class="text-sm truncate" :class="conversationStore.currentId === convId ? 'text-foreground font-medium' : 'text-muted-foreground'">
                          {{ getConversationTitle(convId) }}
                        </span>
                        <span v-if="conversationStore.currentId === convId" class="text-[10px] text-primary font-medium flex-shrink-0">当前</span>
                      </div>
                    </div>
                    <!-- 删除按钮（hover 时显示，真正删除对话记录） -->
                    <button
                      class="opacity-0 group-hover:opacity-100 p-1 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 rounded transition-all flex-shrink-0"
                      title="删除对话"
                      @click.stop="handleDeleteFromHistory(convId)"
                    >
                      <Trash2 class="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            </Transition>
          </div>
        </div>

        <!-- 顶部导航栏 (已移除) -->
        <!-- <ChatHeader
          :title="conversationStore.currentTitle"
          :show-workspace-button="!!conversationStore.currentId"
          :sidebar-active="showRightSidebar"
          @toggle-sidebar="showRightSidebar = !showRightSidebar"
        /> -->

        <!-- 消息列表区域 -->
        <MessageList
          ref="messageListRef"
          :messages="conversationStore.messages"
          :loading="chat.isLoading.value"
          :generating="chat.isGenerating.value"
          :loading-more="conversationStore.loadingMore"
          :has-more="conversationStore.hasMore"
          :agent-info="isAgentMode ? agentStore.currentAgent : null"
          @suggestion-click="handleSuggestionClick"
          @file-preview="handleFilePreview"
          @load-more="handleLoadMore"
        />

        <!-- WebSocket 连接状态提示 -->
        <Transition name="fade">
          <div
            v-if="chat.connectionStatus.value === 'reconnecting'"
            class="flex items-center justify-center gap-2 py-1.5 text-xs text-muted-foreground bg-muted/50"
          >
            <Loader2 class="w-3 h-3 animate-spin" />
            <span>连接已断开，正在重连...</span>
          </div>
          <div
            v-else-if="chat.connectionStatus.value === 'connecting'"
            class="flex items-center justify-center gap-2 py-1.5 text-xs text-muted-foreground bg-muted/50"
          >
            <Loader2 class="w-3 h-3 animate-spin" />
            <span>正在连接...</span>
          </div>
        </Transition>

        <!-- 输入框区域 -->
        <ChatInputArea
          ref="inputAreaRef"
          v-model="inputMessage"
          :selected-files="fileUpload.selectedFiles.value"
          :loading="isCurrentLoading"
          :stopping="chat.isStopping.value"
          :uploading="fileUpload.isUploading.value"
          @send="handleSendMessage"
          @stop="handleStopGeneration"
          @upload-click="handleUploadClick"
          @remove-file="handleRemoveFile"
        />
      </div>

      <!-- [隐藏] 右侧面板（任务/工作区）- 暂时不需要，后续恢复时取消注释并将 showRightSidebar 改回 ref(true) -->
      <!-- <Transition name="slide-right">
        <div 
          v-if="showRightSidebar"
          class="w-1/2 flex-shrink-0 bg-white flex flex-col overflow-hidden my-4 mr-4 ml-3 rounded-2xl shadow-xl border border-border"
        >
            <div class="h-14 flex items-center justify-between px-4 border-b border-border flex-shrink-0">
              <div class="flex gap-1 p-1 bg-muted rounded-lg">
                <button 
                  class="px-3 py-1.5 rounded-md text-xs font-medium transition-all flex items-center gap-1.5" 
                  :class="rightSidebarTab === 'plan' ? 'bg-white text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'"
                  @click="rightSidebarTab = 'plan'"
                >
                  <ClipboardList class="w-3.5 h-3.5" />
                  任务
                </button>
                <button 
                  v-if="conversationStore.currentId"
                  class="px-3 py-1.5 rounded-md text-xs font-medium transition-all flex items-center gap-1.5" 
                  :class="rightSidebarTab === 'workspace' ? 'bg-white text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'"
                  @click="rightSidebarTab = 'workspace'"
                >
                  <FileText class="w-3.5 h-3.5" />
                  工作区
                </button>
              </div>
              <button 
                @click="showRightSidebar = false" 
                class="w-7 h-7 flex items-center justify-center rounded-full bg-muted hover:bg-muted/80 text-muted-foreground transition-colors"
              >
                <X class="w-4 h-4" />
              </button>
            </div>
            <div v-if="rightSidebarTab === 'plan'" class="flex-1 overflow-y-auto p-4 scrollbar-thin">
              <PlanWidget v-if="currentPlan" :plan="currentPlan" />
              <div v-else class="h-full flex flex-col items-center justify-center text-muted-foreground/40 opacity-60">
                <div class="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mb-4 border border-border">
                  <ClipboardList class="w-8 h-8 text-muted-foreground/50" />
                </div>
                <p class="text-sm font-medium">暂无任务计划</p>
                <p class="text-xs mt-1">AI 生成计划后将显示在这里</p>
              </div>
            </div>
            <div v-else-if="rightSidebarTab === 'workspace'" class="flex-1 flex overflow-hidden">
              <div class="w-[220px] min-w-[220px] border-r border-border bg-muted overflow-y-auto">
                <FileExplorer 
                  v-if="conversationStore.currentId"
                  :conversation-id="conversationStore.currentId"
                  @file-select="handleFilePreviewSelect"
                  @run-project="handleRunProject"
                />
              </div>
              <div class="flex-1 flex flex-col overflow-hidden">
                <FilePreview
                  v-if="previewFile && conversationStore.currentId"
                  :conversation-id="conversationStore.currentId"
                  :file-path="previewFile.path"
                  @close="previewFile = null"
                />
                <div v-else class="h-full flex flex-col items-center justify-center text-muted-foreground/60 bg-muted/50">
                  <div class="w-16 h-16 bg-white rounded-2xl flex items-center justify-center mb-4 border border-border">
                    <FileText class="w-8 h-8 text-muted-foreground/60" />
                  </div>
                  <p class="text-sm font-medium">选择文件查看内容</p>
                </div>
              </div>
            </div>
        </div>
      </Transition> -->
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

    <!-- V11: 回滚选项模态框 -->
    <RollbackOptionsModal
      :show="chat.showRollbackModal.value"
      :options="chat.rollbackData.value?.options"
      :error="chat.rollbackData.value?.error"
      :loading="chat.rollbackLoading.value"
      @confirm="chat.confirmRollback"
      @dismiss="chat.dismissRollback"
    />

    <!-- V11.1: HITL 危险操作确认模态框 -->
    <HITLConfirmModal
      :show="chat.showHITLConfirmModal.value"
      :data="chat.hitlConfirmData.value"
      :loading="chat.hitlConfirmLoading.value"
      @approve="chat.approveHITLConfirm"
      @reject="chat.rejectHITLConfirm"
    />

    <!-- V11: 长任务确认模态框 -->
    <LongRunConfirmModal
      :show="chat.showLongRunConfirmModal.value"
      :data="chat.longRunConfirmData.value"
      @confirm="chat.confirmLongRunContinue"
      @dismiss="chat.dismissLongRunConfirm"
    />

    <!-- 通用确认/提示弹窗 -->
    <SimpleConfirmModal
      :show="simpleModal.show"
      :title="simpleModal.title"
      :message="simpleModal.message"
      :type="simpleModal.type"
      :confirm-text="simpleModal.confirmText"
      :show-cancel="simpleModal.showCancel"
      @confirm="simpleModal.onConfirm"
      @cancel="handleSimpleModalCancel"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'

// Stores
import { useConversationStore } from '@/stores/conversation'
import { useSessionStore } from '@/stores/session'
import { useWorkspaceStore } from '@/stores/workspace'
import { useAgentStore } from '@/stores/agent'
import { useGuideStore } from '@/stores/guide'

// Composables
import { useChat } from '@/composables/useChat'
import { useFileUpload } from '@/composables/useFileUpload'
import { ClipboardList, FileText, Loader2, X, Bot, MessageSquare, Plus, History, Trash2, Rocket } from 'lucide-vue-next'

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
import SimpleConfirmModal from '@/components/modals/SimpleConfirmModal.vue'
import RollbackOptionsModal from '@/components/modals/RollbackOptionsModal.vue'
import LongRunConfirmModal from '@/components/modals/LongRunConfirmModal.vue'
import HITLConfirmModal from '@/components/modals/HITLConfirmModal.vue'

// Types
import type { Conversation, AttachedFile, PlanData, HITLResponse, FileItem } from '@/types'

// ==================== Stores & Composables ====================

const router = useRouter()
const route = useRoute()
const conversationStore = useConversationStore()
const sessionStore = useSessionStore()
const workspaceStore = useWorkspaceStore()
const agentStore = useAgentStore()
const guideStore = useGuideStore()
const chat = useChat()
const fileUpload = useFileUpload()
const hitl = chat.hitl

// ==================== State ====================

// UI 状态
const sidebarCollapsed = ref(false)
const showRightSidebar = ref(false)
const rightSidebarTab = ref<'plan' | 'workspace'>('plan')
const showHistoryDropdown = ref(false)
const historyDropdownRef = ref<HTMLElement | null>(null)

// 输入
const inputMessage = ref('')

// 预览
const previewFile = ref<FileItem | null>(null)
const previewingAttachment = ref<AttachedFile | null>(null)

// 通用确认弹窗
const simpleModal = ref({
  show: false,
  title: '确认操作',
  message: '',
  type: 'confirm' as 'confirm' | 'warning' | 'info' | 'error',
  confirmText: '确定',
  showCancel: true,
  onConfirm: () => {},
})

function showConfirm(options: {
  title?: string
  message: string
  type?: 'confirm' | 'warning' | 'info' | 'error'
  confirmText?: string
  showCancel?: boolean
}): Promise<boolean> {
  return new Promise((resolve) => {
    simpleModal.value = {
      show: true,
      title: options.title || '确认操作',
      message: options.message,
      type: options.type || 'confirm',
      confirmText: options.confirmText || '确定',
      showCancel: options.showCancel !== false,
      onConfirm: () => {
        simpleModal.value.show = false
        resolve(true)
      },
    }
    // cancel 回调在模板里直接处理
    const origOnConfirm = simpleModal.value.onConfirm
    simpleModal.value.onConfirm = () => {
      origOnConfirm()
    }
    // 监听 cancel（通过 watch show 变化实现）
    const cancelHandler = () => {
      simpleModal.value.show = false
      resolve(false)
    }
    // 存到一个临时变量供模板使用
    ;(simpleModal.value as any)._cancelHandler = cancelHandler
  })
}

function handleSimpleModalCancel() {
  const handler = (simpleModal.value as any)._cancelHandler
  if (handler) handler()
  else simpleModal.value.show = false
}

// Refs
const messageListRef = ref<InstanceType<typeof MessageList> | null>(null)
const inputAreaRef = ref<InstanceType<typeof ChatInputArea> | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

// ==================== Computed ====================

/** 是否处于 Agent（项目）模式 */
const isAgentMode = computed(() => {
  return !!route.params.agentId
})

/** 当前 Agent ID（从路由获取） */
const agentId = computed(() => {
  return (route.params.agentId as string) || null
})

/** 过滤后的对话列表（Agent 模式下只显示关联的对话） */
const filteredConversations = computed(() => {
  if (!isAgentMode.value || !agentId.value) {
    return conversationStore.conversations
  }
  const linkedIds = agentStore.getConversationIds(agentId.value)
  return conversationStore.conversations.filter(c => linkedIds.includes(c.id))
})

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

/** 是否显示"无项目"空状态（无 Agent 且未在 Agent 路由中） */
const showEmptyProjectState = computed(() => {
  return !isAgentMode.value && agentStore.agents.length === 0
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
  
  // 并行加载对话列表和 Agent 列表
  await Promise.all([
    conversationStore.fetchList(),
    agentStore.fetchList()
  ])
  
  // 如果路由中有 agentId，加载对应 Agent；否则默认选中第一个项目
  let routeAgentId = route.params.agentId as string | undefined
  if (routeAgentId) {
    await agentStore.selectAgent(routeAgentId)
  } else if (agentStore.agents.length > 0) {
    const firstAgent = agentStore.agents[0]
    routeAgentId = firstAgent.agent_id
    await agentStore.selectAgent(firstAgent.agent_id)
    router.replace({ name: 'agent', params: { agentId: firstAgent.agent_id } })
  }

  // 根据路由加载会话
  const conversationId = route.params.conversationId
  if (conversationId && typeof conversationId === 'string') {
    await conversationStore.load(conversationId)
    // Agent 模式下，确保该会话在标签页中显示
    if (routeAgentId) {
      agentStore.openTab(routeAgentId, conversationId)
    }
  }
  
  // 设置文件输入引用
  fileUpload.setFileInputRef(fileInputRef.value)

  // 首次引导：未完成过引导时启动交互式引导
  if (!guideStore.isCompleted && !guideStore.isActive) {
    sidebarCollapsed.value = false
    guideStore.canSkip = false // 首次用户没有 Key，不允许跳过设置阶段
    guideStore.startGuide()
  }

  // 从设置页返回时，Step 已在 SettingsView 推进到 5，确保侧边栏展开
  if (guideStore.isActive && guideStore.currentStep === 5) {
    sidebarCollapsed.value = false
  }
})

onUnmounted(() => {
  document.removeEventListener('click', handleHistoryClickOutside)
})

// ==================== 历史下拉框：点击外部关闭 ====================

function handleHistoryClickOutside(e: MouseEvent) {
  if (historyDropdownRef.value && !historyDropdownRef.value.contains(e.target as Node)) {
    showHistoryDropdown.value = false
  }
}

watch(showHistoryDropdown, (isOpen) => {
  if (isOpen) {
    // nextTick 避免当前点击事件立即触发关闭
    nextTick(() => {
      document.addEventListener('click', handleHistoryClickOutside)
    })
  } else {
    document.removeEventListener('click', handleHistoryClickOutside)
  }
})

// 监听路由中的 agentId 变化
watch(() => route.params.agentId, async (newAgentId) => {
  if (newAgentId && typeof newAgentId === 'string') {
    if (agentStore.currentAgentId !== newAgentId) {
      await agentStore.selectAgent(newAgentId)
    }
  } else {
    agentStore.reset()
  }
})


// ==================== Methods ====================

/** 选择会话 */
async function handleSelectConversation(id: string): Promise<void> {
  if (isAgentMode.value && agentId.value) {
    router.push({ name: 'agent-conversation', params: { agentId: agentId.value, conversationId: id } })
  } else {
    router.push({ name: 'conversation', params: { conversationId: id } })
  }
}

/** 创建新会话 */
async function handleCreateConversation(): Promise<void> {
  conversationStore.reset()
  if (isAgentMode.value && agentId.value) {
    router.push({ name: 'agent', params: { agentId: agentId.value } })
  } else {
    router.push({ name: 'chat' })
  }
  await conversationStore.fetchList(50)
}

/** 删除会话 */
async function handleDeleteConversation(conv: Conversation): Promise<void> {
  const confirmed = await showConfirm({
    title: '删除会话',
    message: `确定要删除 "${conv.title}" 吗？`,
    type: 'warning',
    confirmText: '删除',
  })
  if (confirmed) {
    const isDeletingCurrent = conversationStore.currentId === conv.id

    // 1. 同步：从标签页 & 历史映射中移除
    if (isAgentMode.value && agentId.value) {
      agentStore.unlinkConversation(agentId.value, conv.id)
    }

    // 2. 同步：如果删除的是当前对话，立即切走（参考 handleCloseTab）
    if (isDeletingCurrent) {
      conversationStore.reset()
      if (isAgentMode.value && agentId.value) {
        router.push({ name: 'agent', params: { agentId: agentId.value } })
      } else {
        router.push({ name: 'chat' })
      }
    }

    // 3. 异步：清理本地数据 + 调后端接口（不阻塞 UI）
    conversationStore.remove(conv.id)
  }
}

/** 通过 ID 删除对话（顶部导航栏中使用） */
async function handleDeleteConversationById(convId: string): Promise<void> {
  const conv = conversationMap.value.get(convId)
  if (conv) {
    await handleDeleteConversation(conv)
  }
}

/** 对话 ID → 对话对象的快速索引（用于顶部导航栏 O(1) 查找） */
const conversationMap = computed(() => {
  const map = new Map<string, Conversation>()
  for (const conv of conversationStore.conversations) {
    map.set(conv.id, conv)
  }
  return map
})

/** 获取对话标题（O(1) 查找） */
function getConversationTitle(convId: string): string {
  return conversationMap.value.get(convId)?.title || '新对话'
}

/** 关闭标签页（不删除对话，仅从标签栏移除） */
function handleCloseTab(convId: string): void {
  if (!agentId.value) return
  agentStore.closeTab(agentId.value, convId)
  // 如果关闭的是当前对话，切换到其他标签或空状态
  if (conversationStore.currentId === convId) {
    const remaining = agentStore.getOpenTabIds(agentId.value)
    if (remaining.length > 0) {
      handleSelectConversation(remaining[remaining.length - 1])
    } else {
      conversationStore.reset()
      router.push({ name: 'agent', params: { agentId: agentId.value } })
    }
  }
}

/** 从历史记录中打开对话（添加到标签页并切换过去） */
function handleOpenFromHistory(convId: string): void {
  if (!agentId.value) return
  agentStore.openTab(agentId.value, convId)
  handleSelectConversation(convId)
  showHistoryDropdown.value = false
}

/** 从历史记录中删除对话（真正删除） */
async function handleDeleteFromHistory(convId: string): Promise<void> {
  const conv = conversationMap.value.get(convId)
  const title = conv?.title || '此对话'
  const confirmed = await showConfirm({
    title: '删除对话',
    message: `确定要删除 "${title}" 吗？`,
    type: 'warning',
    confirmText: '删除',
  })
  if (confirmed) {
    const isDeletingCurrent = conversationStore.currentId === convId

    // 1. 同步：从标签页 & 历史映射中移除
    if (agentId.value) {
      agentStore.unlinkConversation(agentId.value, convId)
    }

    // 2. 同步：如果删除的是当前对话，立即切走（参考 handleCloseTab）
    if (isDeletingCurrent) {
      const remaining = agentId.value ? agentStore.getOpenTabIds(agentId.value) : []
      if (remaining.length > 0) {
        handleSelectConversation(remaining[remaining.length - 1])
      } else {
        conversationStore.reset()
        if (agentId.value) {
          router.push({ name: 'agent', params: { agentId: agentId.value } })
        } else {
          router.push({ name: 'chat' })
        }
      }
    }

    // 3. 异步：清理本地数据 + 调后端接口（不阻塞 UI）
    conversationStore.remove(convId)
  }
}

/** 导航 */
function handleNavigate(path: string): void {
  if (guideStore.isActive) {
    // Step 1 → 2：点击设置按钮，进入设置页
    if (guideStore.currentStep === 1 && path === '/settings') {
      guideStore.nextStep()
    }
    // Step 5 → 6：点击"新建项目"，进入创建页
    if (guideStore.currentStep === 5 && path === '/create-project') {
      guideStore.nextStep()
    }
  }
  router.push(path)
}

/** 选择 Agent（项目） */
async function handleSelectAgent(selectedAgentId: string): Promise<void> {
  try {
    await agentStore.selectAgent(selectedAgentId)

    // 重置加载状态
    chat.isLoading.value = false
    chat.isStopping.value = false

    // 尝试恢复最近使用的会话：优先打开的标签页 > 历史记录
    const openTabs = agentStore.getOpenTabIds(selectedAgentId)
    const historyIds = agentStore.getConversationIds(selectedAgentId)
    const lastConvId = openTabs.length > 0
      ? openTabs[openTabs.length - 1]
      : historyIds.length > 0
        ? historyIds[historyIds.length - 1]
        : null

    if (lastConvId) {
      // 确保在标签页中显示
      agentStore.openTab(selectedAgentId, lastConvId)
      await conversationStore.load(lastConvId)
      router.push({ name: 'agent-conversation', params: { agentId: selectedAgentId, conversationId: lastConvId } })
    } else {
      conversationStore.reset()
      router.push({ name: 'agent', params: { agentId: selectedAgentId } })
    }
  } catch (error) {
    console.warn('⚠️ 加载项目失败:', error)
    await agentStore.fetchList()
  }
}

/** 编辑 Agent（项目） */
function handleEditAgent(targetAgentId: string): void {
  router.push({ name: 'edit-project', params: { agentId: targetAgentId } })
}

/** 删除 Agent（项目） */
async function handleDeleteAgent(targetAgentId: string): Promise<void> {
  const agent = agentStore.agents.find(a => a.agent_id === targetAgentId)
  const agentName = agent?.name || targetAgentId
  const confirmed = await showConfirm({
    title: '删除项目',
    message: `确定要删除项目 "${agentName}" 吗？`,
    type: 'warning',
    confirmText: '删除',
  })
  if (confirmed) {
    try {
      const wasCurrentAgent = agentStore.currentAgentId === targetAgentId
      await agentStore.removeAgent(targetAgentId)
      if (wasCurrentAgent) {
        conversationStore.reset()
        // 自动选中第一个剩余项目，若无则回到首页
        if (agentStore.agents.length > 0) {
          const firstAgent = agentStore.agents[0]
          await agentStore.selectAgent(firstAgent.agent_id)
          router.push({ name: 'agent', params: { agentId: firstAgent.agent_id } })
        } else {
          agentStore.reset()
          router.push({ name: 'chat' })
        }
      }
    } catch (error) {
      console.error('❌ 删除项目失败:', error)
      showConfirm({ title: '操作失败', message: '删除失败，请重试', type: 'error', showCancel: false })
    }
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

  // 如果智能体正在回复，先停止当前回复
  if (isCurrentLoading.value) {
    await handleStopGeneration()
  }
  
  // 清空输入
  inputMessage.value = ''
  fileUpload.clearFiles()

  // 记录发送前的上下文
  const hadConversation = !!conversationStore.currentId
  const sendAgentId = agentId.value
  const sendIsAgentMode = isAgentMode.value

  // Agent 模式下，如果是新对话，先创建并立即绑定到项目（不等流式完成）
  if (sendIsAgentMode && sendAgentId && !hadConversation) {
    await conversationStore.create(content.slice(0, 20) || '新对话')
    if (conversationStore.currentId) {
      agentStore.linkConversation(sendAgentId, conversationStore.currentId)
      router.replace({
        name: 'agent-conversation',
        params: { agentId: sendAgentId, conversationId: conversationStore.currentId }
      })
    }
  }

  // 发送（Agent 模式下传 agentId）
  const sendOptions = sendIsAgentMode && sendAgentId
    ? { agentId: sendAgentId }
    : {}
  await chat.sendMessage(content, files, sendOptions)

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
    showConfirm({ title: '上传失败', message: '文件上传失败，请重试', type: 'error', showCancel: false })
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
        const shouldOpen = await showConfirm({
          title: '项目已启动',
          message: `预览地址：${result.preview_url}\n\n点击"打开"在新窗口中查看`,
          type: 'info',
          confirmText: '打开',
        })
        if (shouldOpen) {
          window.open(result.preview_url, '_blank')
        }
      }
    } else if (!result.success) {
      showConfirm({ title: '启动失败', message: '启动项目失败: ' + (result.error || result.message), type: 'error', showCancel: false })
    }
  } catch (error) {
    console.error('❌ 运行项目失败:', error)
    showConfirm({ title: '运行失败', message: '运行项目失败，请重试', type: 'error', showCancel: false })
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

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>

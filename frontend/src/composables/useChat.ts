/**
 * 聊天核心 Composable
 * 负责发送消息、处理流式事件、更新消息
 */

import { ref, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useConversationStore } from '@/stores/conversation'
import { useSessionStore } from '@/stores/session'
import { useWorkspaceStore } from '@/stores/workspace'
import { useConnectionStore } from '@/stores/connection'
import { useAgentStore } from '@/stores/agent'
import { useNotificationStore } from '@/stores/notification'
import { useHITL } from './useHITL'
import type {
  UIMessage,
  AttachedFile,
  SendMessageOptions,
  ContentBlock,
  PlanData,
  HITLConfirmRequest,
  PlaybookSuggestion
} from '@/types'
import { FILE_WRITE_TOOLS, TERMINAL_TOOLS, BACKGROUND_TASKS } from '@/utils'
import * as sessionApi from '@/api/session'
import * as playbookApi from '@/api/playbook'

/**
 * 聊天核心 Composable
 */
export function useChat() {
  const router = useRouter()
  const route = useRoute()
  const conversationStore = useConversationStore()
  const sessionStore = useSessionStore()
  const workspaceStore = useWorkspaceStore()
  const connectionStore = useConnectionStore()
  const hitl = useHITL()

  // ==================== 状态 ====================

  /** 是否正在加载 (请求发起但未收到响应) */
  const isLoading = ref(false)

  /** 是否正在停止 */
  const isStopping = ref(false)

  /** 当前内容块类型（用于 delta 处理） */
  let currentBlockType: string | null = null

  /** 待处理的工具调用 */
  const pendingToolCalls = ref<Record<string, { name: string; input: string; id: string }>>({})

  /** V11: 回滚选项弹窗 */
  const showRollbackModal = ref(false)
  const rollbackData = ref<{
    task_id: string
    options: { id: string; action: string; target: string }[]
    error?: string
    reason?: string
    /** V11.2: Diff 预览数据 */
    preview?: sessionApi.RollbackPreview | null
    previewLoading?: boolean
  } | null>(null)
  const rollbackLoading = ref(false)

  /** V11.1: HITL 危险操作确认弹窗 */
  const showHITLConfirmModal = ref(false)
  const hitlConfirmData = ref<{
    reason: string
    tools: string[]
    message: string
  } | null>(null)
  const hitlConfirmLoading = ref(false)

  /** V11: 长任务确认弹窗 */
  const showLongRunConfirmModal = ref(false)
  const longRunConfirmData = ref<{ turn: number; message: string } | null>(null)

  // ==================== 计算属性 ====================

  /** 消息列表（从 store 获取） */
  const messages = computed(() => conversationStore.messages)

  /** 当前会话 ID */
  const conversationId = computed(() => conversationStore.currentId)

  /** 当前会话标题 */
  const currentTitle = computed(() => conversationStore.currentTitle)

  /** 会话列表 */
  const conversations = computed(() => conversationStore.conversations)

  /** 是否正在生成 (根据 Session 状态) */
  const isGenerating = computed(() => {
    return conversationId.value ? sessionStore.isConversationRunning(conversationId.value) : false
  })

  /** 是否当前会话正在加载/生成 */
  const isCurrentConversationLoading = computed(() => {
    return isLoading.value || isGenerating.value
  })

  /** 当前连接状态 */
  const connectionStatus = computed(() => {
    if (!conversationId.value) return 'disconnected'
    return connectionStore.getConnection(conversationId.value).connectionStatus.value
  })

  // ==================== 路由监听 ====================

  // 监听路由参数变化
  watch(
    () => route.params.conversationId,
    async (newId) => {
      if (newId && typeof newId === 'string') {
        // Skip if already on this conversation (e.g. router.replace after creating
        // a new conversation in handleSendMessage). Without this guard, the
        // loadConversation() call resets isLoading=false and kills the loading dots.
        if (conversationId.value === newId) return
        await loadConversation(newId)
      }
    }
  )

  // ==================== 初始化 ====================
  
  // 🆕 设置 HITL 的 SSE 事件处理器（在定义 handleStreamEvent 函数之后会被调用）
  // 注意：这个设置需要在 handleStreamEvent 定义之后才能生效
  // 所以我们在文件末尾再次设置

  // ==================== 方法 ====================

  /**
   * 初始化
   */
  async function initialize(): Promise<boolean> {
    conversationStore.initUserId()

    // Register playbook suggestion handler on the global WebSocket notification channel.
    // When playbook_extraction finishes (after SSE stream closed), the backend pushes
    // via WebSocket → this handler injects the suggestion into the last assistant message.
    connectionStore.registerPlaybookHandler(injectPlaybookSuggestion)

    // 加载会话列表
    await conversationStore.fetchList()

    // 根据路由加载会话
    const routeConvId = route.params.conversationId
    if (routeConvId && typeof routeConvId === 'string') {
      await loadConversation(routeConvId)
    }

    return false
  }

  /**
   * 清理
   */
  function cleanup(): void {
    // 不再主动关闭连接，交给 ConnectionStore 管理或在会话结束时关闭
  }

  /**
   * 创建新会话
   */
  async function createNewConversation(): Promise<void> {
    // 重置所有加载状态
    isLoading.value = false
    isStopping.value = false
    
    conversationStore.reset()
    router.push({ name: 'chat' })
    await conversationStore.fetchList()
  }

  /**
   * 加载会话
   */
  async function loadConversation(convId: string): Promise<void> {
    // 重置局部加载状态
    isLoading.value = false
    isStopping.value = false
    
    // 如果该会话正在运行，load 方法会优先使用缓存
    await conversationStore.load(convId)

    // 更新路由
    if (route.params.conversationId !== convId) {
      router.push({ name: 'conversation', params: { conversationId: convId } })
    }
  }

  /**
   * 发送消息
   */
  async function sendMessage(
    content: string,
    files?: AttachedFile[],
    options: Partial<SendMessageOptions> = {}
  ): Promise<string> {
    const hasContent = content.trim().length > 0
    const hasFiles = files && files.length > 0

    if ((!hasContent && !hasFiles) || isLoading.value) {
      return ''
    }

    const currentConvId = conversationStore.currentId
    // 如果没有会话 ID (新会话)，conversationStore.addUserMessage 会报错
    // 应该先创建会话吗？通常 conversationStore.create() 会被调用
    // 这里假设 conversationStore 已经处理好了 currentId，或者在第一次回复时创建
    // 实际逻辑：如果 currentId 为空，addUserMessage 需要处理?
    // conversationStore.addUserMessage 抛出错误 if no ID.
    // 所以如果是新会话，MessageList 组件应该触发 create? 
    // 不，通常 ChatView 会在 mount 时处理，或者 sendMessage 自动创建。
    // 这里我们假设 conversationStore.currentId 已经由 create() 设置好了（在 ChatView 初始化时）
    // 如果是 'chat' 路由，create() 会在 ChatView onMounted 中并未调用，而是等待?
    // ChatView: onMounted -> if route has id -> load.
    // handleCreateConversation -> create -> push router.
    // HandleSendMessage -> if no currentId -> create? 
    // 原逻辑：sendMessage 直接调用 conversationStore.addUserMessage
    
    if (!currentConvId) {
       // 自动创建会话
       const newConv = await conversationStore.create(content.slice(0, 20) || '新对话')
       // create 会设置 currentId
    }

    const targetConvId = conversationStore.currentId!

    // 添加用户消息
    conversationStore.addUserMessage(content, files, targetConvId)

    // 添加空的助手消息
    const assistantMsg = conversationStore.addAssistantMessage(targetConvId)

    isLoading.value = true
    // isGenerating 是 computed，依赖 sessionStore 状态

    try {
      // 构建请求体
      const requestBody = {
        message: content,
        user_id: conversationStore.userId,
        conversation_id: targetConvId,
        stream: true,
        agent_id: options.agentId || undefined,
        background_tasks: options.backgroundTasks || [
          BACKGROUND_TASKS.TITLE_GENERATION,
          BACKGROUND_TASKS.RECOMMENDED_QUESTIONS
        ],
        files: files?.map(f => ({
          file_url: f.file_url,
          local_path: f.local_path,
          file_name: f.file_name,
          file_type: f.file_type,
          file_size: f.file_size
        })),
        variables: options.variables || {
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          locale: navigator.language,
          local_time: new Date().toLocaleString('sv-SE', { timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone }).replace(' ', 'T')
        }
      }

      // 获取当前会话的 WebSocket 连接
      const ws = connectionStore.getConnection(targetConvId)

      // Capture agentId at send time (route may change if user navigates away)
      const sendAgentId = options.agentId || (route.params.agentId as string) || ''

      // 通过 WebSocket 发送消息
      const result = await ws.connect(requestBody, {
        onEvent: (event) => handleStreamEvent(event, assistantMsg, targetConvId, sendAgentId),
        onConnected: () => {
          console.log(`✅ WebSocket 流开始 (${targetConvId})`)
        },
        onDisconnected: () => {
          console.log(`✅ WebSocket 流结束 (${targetConvId})`)
          // 重置停止状态 (如果是当前会话)
          if (conversationStore.currentId === targetConvId) {
            isStopping.value = false
          }
        },
        onError: (error) => {
          console.error(`❌ WebSocket 错误 (${targetConvId}):`, error)
          assistantMsg.content += `\n❌ 发送失败: ${error.message}`
          sessionStore.markCompleted(targetConvId)
        }
      })

      // 刷新会话列表
      try {
        await conversationStore.fetchList()
      } catch (e) {
        console.warn('⚠️ 发送后刷新会话列表失败:', e)
      }

      return result
    } catch (error) {
      assistantMsg.content += `\n❌ 发送失败: ${(error as Error).message}`
      sessionStore.markCompleted(targetConvId)
      throw error
    } finally {
      isLoading.value = false
    }
  }

  /**
   * 停止生成
   */
  async function stopGeneration(): Promise<void> {
    const currentConvId = conversationStore.currentId
    const sessionId = sessionStore.currentSessionId ||
      sessionStore.getSessionIdByConversation(currentConvId)

    if (!sessionId) {
      console.warn('⚠️ 无法停止：session_id 不存在')
      return
    }

    isStopping.value = true

    try {
      // 发送停止请求
      await sessionStore.stop(sessionId)

      // 停止成功后，强制终止前端流并清理状态
      // 避免后端已停止但 WebSocket 未收到 session_stopped 导致 UI 卡在生成中
      if (currentConvId) {
        const ws = connectionStore.getConnection(currentConvId)
        ws.disconnect()
        sessionStore.markCompleted(currentConvId)
      }
      isStopping.value = false
      isLoading.value = false
    } catch (error) {
      console.error('❌ 停止请求失败:', error)
      // 如果请求失败，强制断开连接
      if (currentConvId) {
        const ws = connectionStore.getConnection(currentConvId)
        ws.disconnect()
        sessionStore.markCompleted(currentConvId)
      }
      isStopping.value = false
      isLoading.value = false
    }
  }

  /**
   * V11.2: 加载回滚 Diff 预览
   */
  async function loadRollbackPreview(): Promise<void> {
    const sessionId =
      sessionStore.currentSessionId ||
      sessionStore.getSessionIdByConversation(conversationStore.currentId) ||
      rollbackData.value?.task_id
    if (!sessionId || !rollbackData.value) return

    rollbackData.value.previewLoading = true
    rollbackData.value.preview = null
    try {
      const preview = await sessionApi.previewRollback(sessionId)
      if (rollbackData.value) {
        rollbackData.value.preview = preview
      }
    } catch (e) {
      console.error('预览加载失败:', e)
      // 预览失败不影响回滚功能，仅 log
    } finally {
      if (rollbackData.value) {
        rollbackData.value.previewLoading = false
      }
    }
  }

  /**
   * V11: 确认回滚（V11.2: 支持选择性回滚）
   */
  async function confirmRollback(selectedFiles?: string[]): Promise<void> {
    const sessionId =
      sessionStore.currentSessionId ||
      sessionStore.getSessionIdByConversation(conversationStore.currentId) ||
      rollbackData.value?.task_id
    if (!sessionId) return

    rollbackLoading.value = true
    try {
      await sessionApi.rollbackSession(sessionId, selectedFiles)
      showRollbackModal.value = false
      rollbackData.value = null
    } catch (e) {
      console.error('❌ 回滚失败:', e)
      if (rollbackData.value) {
        rollbackData.value.error = (e as Error).message || '回滚请求失败'
      }
    } finally {
      rollbackLoading.value = false
    }
  }

  /**
   * V11: 关闭回滚弹窗
   */
  function dismissRollback(): void {
    showRollbackModal.value = false
    rollbackData.value = null
  }

  /**
   * V11.1: 批准 HITL 危险操作
   */
  async function approveHITLConfirm(): Promise<void> {
    const sessionId =
      sessionStore.currentSessionId ||
      sessionStore.getSessionIdByConversation(conversationStore.currentId)
    if (!sessionId) return

    hitlConfirmLoading.value = true
    try {
      await sessionApi.submitHITLConfirm(sessionId, true)
      showHITLConfirmModal.value = false
      hitlConfirmData.value = null
    } catch (e) {
      console.error('HITL 批准失败:', e)
    } finally {
      hitlConfirmLoading.value = false
    }
  }

  /**
   * V11.1: 拒绝 HITL 危险操作（触发回退策略）
   */
  async function rejectHITLConfirm(): Promise<void> {
    const sessionId =
      sessionStore.currentSessionId ||
      sessionStore.getSessionIdByConversation(conversationStore.currentId)
    if (!sessionId) return

    hitlConfirmLoading.value = true
    try {
      await sessionApi.submitHITLConfirm(sessionId, false)
      showHITLConfirmModal.value = false
      hitlConfirmData.value = null
    } catch (e) {
      console.error('HITL 拒绝失败:', e)
    } finally {
      hitlConfirmLoading.value = false
    }
  }

  /**
   * V11: 确认继续长任务
   */
  async function confirmLongRunContinue(): Promise<void> {
    const sessionId =
      sessionStore.currentSessionId ||
      sessionStore.getSessionIdByConversation(conversationStore.currentId)
    if (!sessionId) return
    try {
      await sessionApi.confirmContinueSession(sessionId)
      showLongRunConfirmModal.value = false
      longRunConfirmData.value = null
    } catch (e) {
      console.error('❌ 确认继续失败:', e)
    }
  }

  /**
   * V11: 关闭长任务确认弹窗
   */
  async function dismissLongRunConfirm(): Promise<void> {
    showLongRunConfirmModal.value = false
    longRunConfirmData.value = null
    const sessionId =
      sessionStore.currentSessionId ||
      sessionStore.getSessionIdByConversation(conversationStore.currentId)
    if (sessionId) {
      try {
        await sessionApi.stopSession(sessionId)
      } catch {
        // ignore
      }
    }
  }

  /**
   * Playbook: 接受策略建议
   */
  async function acceptPlaybookSuggestion(msg: UIMessage): Promise<void> {
    const suggestion = msg.playbookSuggestion
    if (!suggestion || suggestion.user_action) return

    try {
      await playbookApi.playbookAction(suggestion.playbook_id, 'approve')
      suggestion.user_action = 'accepted'
    } catch (e) {
      console.error('Playbook approve 失败:', e)
    }
  }

  /**
   * Playbook: 忽略策略建议
   */
  async function dismissPlaybookSuggestion(msg: UIMessage): Promise<void> {
    const suggestion = msg.playbookSuggestion
    if (!suggestion || suggestion.user_action) return

    try {
      await playbookApi.playbookAction(suggestion.playbook_id, 'dismiss')
      suggestion.user_action = 'dismissed'
    } catch (e) {
      console.error('Playbook dismiss 失败:', e)
    }
  }

  /**
   * 处理流事件
   *
   * @param agentId - 发送消息时捕获的 agentId（用于离开会话后推送通知）
   */
  function handleStreamEvent(event: { type: string; data: any; [key: string]: any }, msg: UIMessage, convId?: string, agentId?: string): void {
    // Skip broadcast events targeting a different conversation
    // (WebSocket ConnectionManager broadcasts to ALL connections)
    const eventConvId = event.conversation_id
    if (eventConvId && convId && eventConvId !== convId) return

    const { type, data } = event

    // 处理 session 开始事件
    if (type === 'session_start') {
      console.log('🚀 Session 开始:', data.session_id)
      if (data.session_id && convId) {
        sessionStore.setCurrentSessionId(data.session_id)
        sessionStore.markRunning(convId, data.session_id)
      }
    }

    // 处理会话开始事件
    if (type === 'conversation_start' && data.conversation_id) {
      // 只有在新会话且 ID 匹配时才更新?
      // 实际上 createNewConversation 时 conversationStore.currentId 已经有了
      // 这里主要是确认 ID
      if (conversationStore.currentId === data.conversation_id) {
         // ok
      }
    }

    // 处理消息开始事件 - 更新占位消息的 ID
    if (type === 'message_start') {
      const messageId = data.message_id || data.message?.id
      if (messageId) {
        msg.id = messageId
      }
      // 确保标记为运行中
      if (data.session_id && convId) {
         sessionStore.markRunning(convId, data.session_id)
      }
    }

    // 处理消息增量事件
    if (type === 'message_delta') {
      handleMessageDelta(data.delta, msg)
    }

    // 处理内容块开始事件
    if (type === 'content_start') {
      handleContentStart(data, msg)
    }

    // 处理内容增量事件
    if (type === 'content_delta') {
      handleContentDelta(data, msg)
    }

    // 处理内容块停止事件
    if (type === 'content_stop') {
      handleContentStop(data, msg)
    }
    // 兼容 ZenO 格式（message.assistant.*）
    if (type === 'message.assistant.delta') {
      const delta = (event as any).delta
      if (delta?.type === 'thinking') {
        msg.thinking = (msg.thinking || '') + (delta.content || '')
      } else if (delta?.type === 'response') {
        msg.content += (delta.content || '')
      } else if (delta?.type === 'clue') {
        try {
          const raw = typeof delta.content === 'string' ? JSON.parse(delta.content) : delta.content
          const request = normalizeHITLRequest(raw)
          if (request && !hitl.showModal.value) {
            hitl.show(request)
          }
        } catch {
          // 忽略解析错误
        }
      } else if (delta?.type === 'hitl_data') {
        // 处理 hitl_data delta（HITL 异步模式）
        try {
          const hitlData = typeof delta.content === 'string' ? JSON.parse(delta.content) : delta.content
          
          if (hitlData && hitlData.status === 'pending') {
            console.log('🤝 收到 HITL pending 状态:', hitlData)
            const request = normalizeHITLRequestFromHitlData(hitlData)
            if (request && !hitl.showModal.value) {
              hitl.show(request)
            }
          } else if (hitlData && (hitlData.timed_out || hitlData.status === 'timed_out')) {
            console.log('⏱️ HITL 超时，关闭弹窗')
            hitl.hide()
          } else if (hitlData && hitlData.status === 'completed' && hitlData.success) {
            console.log('✅ HITL 已完成:', hitlData.response)
          }
        } catch (e) {
          console.warn('⚠️ 解析 hitl_data 失败:', e)
        }
      }
    }

    // 处理对话增量事件（标题更新等）
    if (type === 'conversation_delta') {
      if (data?.title) {
        // 后端已更新数据库，这里只更新本地列表
        const conv = conversationStore.conversations.find(c => c.id === (data.conversation_id || convId))
        if (conv) {
          conv.title = data.title
          console.log(`🏷️ 对话标题已更新: ${data.title}`)
        }
      }
    }

    // 处理流结束/消息结束
    if ((type === 'message_stop' || type === 'session_stopped' || type === 'error') && convId) {
       sessionStore.markCompleted(convId)

       // 错误事件：将错误信息写入助手消息，让用户看到具体原因
       if (type === 'error' && data?.error) {
         const errorMsg = data.error.message || data.error.type || '请求处理失败'
         msg.content = `⚠️ ${errorMsg}`
       }

       // Safety net: 消息结束时如果 HITL 弹窗仍在显示则关闭
       if (hitl.showModal.value) {
         console.log('🔒 消息结束，关闭残留 HITL 弹窗')
         hitl.hide()
       }

       // 用户不在当前会话时，推送全局通知
       if (convId !== conversationStore.currentId && type !== 'error') {
         const notifStore = useNotificationStore()
         const agentStore = useAgentStore()
         const agent = agentId ? agentStore.agents.find(a => a.agent_id === agentId) : null
         const title = agent?.name || '新消息'
         const preview = msg.content?.slice(0, 80) || '回复已完成'
         const routeTarget = agentId
           ? { name: 'agent-conversation', params: { agentId, conversationId: convId } }
           : { name: 'conversation', params: { conversationId: convId } }
         
         // 判断是否为定时任务提醒（内容以 ⏰ **定时提醒** 开头）
         const isReminder = msg.content?.trim().startsWith('⏰ **定时提醒**')
         
         if (isReminder) {
           // 提取提醒标题和内容
           const lines = msg.content.split('\n').filter(l => l.trim())
           const reminderTitle = lines[1]?.replace(/\*\*/g, '').trim() || '定时提醒'
           const reminderContent = lines.slice(3).join('\n').trim().slice(0, 80)
           notifStore.reminder(reminderTitle, reminderContent, routeTarget)
         } else {
           notifStore.chatMessage(title, preview, routeTarget)
         }
       }
    }

    // V11: 回滚选项（V11.2: 初始化 preview 状态以触发 Diff 预览加载）
    if (type === 'rollback_options') {
      const taskId = data?.task_id || sessionStore.currentSessionId
      const options = Array.isArray(data?.options) ? data.options : []
      rollbackData.value = {
        task_id: taskId || '',
        options,
        error: data?.error,
        reason: data?.reason,
        preview: null,
        previewLoading: false,
      }
      showRollbackModal.value = true
    }

    // V11: 回滚已完成
    if (type === 'rollback_completed') {
      showRollbackModal.value = false
      rollbackData.value = null
    }

    // V11.1: HITL 危险操作确认
    if (type === 'hitl_confirm') {
      hitlConfirmData.value = {
        reason: data?.reason ?? '',
        tools: Array.isArray(data?.tools) ? data.tools : [],
        message: data?.message ?? '危险操作需用户确认'
      }
      showHITLConfirmModal.value = true
    }

    // V11: 长任务确认
    if (type === 'long_running_confirm') {
      longRunConfirmData.value = {
        turn: data?.turn ?? 0,
        message: data?.message ?? '任务已执行较多轮次，是否继续？'
      }
      showLongRunConfirmModal.value = true
    }

    // Playbook 策略建议（内联卡片，非弹窗）
    if (type === 'playbook_suggestion') {
      _attachPlaybookSuggestion(data, msg)
    }
  }

  /**
   * Attach a playbook suggestion to a message.
   * Used by both SSE stream handler and WebSocket push handler.
   */
  function _attachPlaybookSuggestion(data: any, msg: UIMessage): void {
    const suggestion: PlaybookSuggestion = {
      playbook_id: data?.playbook_id ?? '',
      name: data?.name ?? '',
      description: data?.description ?? '',
      strategy_summary: data?.strategy_summary ?? '',
      user_action: null,
    }
    if (suggestion.playbook_id) {
      msg.playbookSuggestion = suggestion
    }
  }

  /**
   * Inject a playbook suggestion from WebSocket push (after SSE stream closed).
   * Finds the last assistant message in the current conversation and attaches the suggestion.
   */
  function injectPlaybookSuggestion(data: any): void {
    const msgs = conversationStore.messages
    // Find the last assistant message to attach the suggestion to
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'assistant') {
        _attachPlaybookSuggestion(data, msgs[i])
        return
      }
    }
  }

  /**
   * 处理消息增量
   */
  function handleMessageDelta(delta: { type: string; content: string | object }, msg: UIMessage): void {
    if (!delta) return

    if (delta.type === 'recommended') {
      try {
        const rec = typeof delta.content === 'string'
          ? JSON.parse(delta.content)
          : delta.content
        msg.recommendedQuestions = (rec as { questions?: string[] }).questions || []
      } catch {
        // 忽略解析错误
      }
    }

    if (delta.type === 'preface') {
      const text = typeof delta.content === 'string' ? delta.content : JSON.stringify(delta.content)
      msg.content += text || ''
    }

    if (delta.type === 'confirmation_request') {
      try {
        const raw = typeof delta.content === 'string'
          ? JSON.parse(delta.content)
          : delta.content
        const request = normalizeHITLRequest(raw)
        if (request && !hitl.showModal.value) {
          hitl.show(request)
        }
      } catch (e) {
        console.warn('解析 HITL 请求失败:', e)
      }
    }

    // HITL 超时/关闭事件：后端 HITL 工具超时后发送，前端关闭弹窗
    if (delta.type === 'hitl') {
      try {
        const hitlData = typeof delta.content === 'string' ? JSON.parse(delta.content) : delta.content
        if (hitlData && (hitlData.timed_out || hitlData.status === 'timed_out')) {
          console.log('⏱️ HITL 超时，关闭弹窗')
          hitl.hide()
        }
      } catch {
        // 忽略解析错误
      }
    }
  }

  /**
   * 尝试从内容中解析并更新 Plan
   */
  function tryUpdatePlanFromContent(content: string, msg: UIMessage): void {
    if (!content) return
    
    const syncPlanUpdate = (planData: PlanData) => {
      msg.planResult = planData
      conversationStore.updatePlan(planData)
    }
    
    try {
      const resultContent = JSON.parse(content)
      if (resultContent?.plan) {
        syncPlanUpdate(resultContent.plan as PlanData)
      }
    } catch {
      const planMatch = content.match(/"plan"\s*:\s*(\{[\s\S]*)/)?.[1]
      if (planMatch) {
        try {
          let planJson = planMatch
          let depth = 0
          let endIndex = 0
          for (let i = 0; i < planJson.length; i++) {
            if (planJson[i] === '{') depth++
            else if (planJson[i] === '}') {
              depth--
              if (depth === 0) {
                endIndex = i + 1
                break
              }
            }
          }
          if (endIndex > 0) {
            const planData = JSON.parse(planJson.substring(0, endIndex))
            if (planData?.name || planData?.todos) {
              syncPlanUpdate(planData as PlanData)
            }
          }
        } catch {
          // ignore
        }
      }
    }
  }

  /**
   * 初始化内容块
   */
  function initContentBlock(contentBlock: ContentBlock): ContentBlock {
    const block = { ...contentBlock, _blockType: contentBlock.type }
    
    switch (contentBlock.type) {
      case 'text':
        if (!('text' in block)) (block as any).text = ''
        break
      case 'thinking':
        if (!('thinking' in block)) (block as any).thinking = ''
        break
      case 'tool_use':
      case 'server_tool_use':
        if (!('partialInput' in block)) (block as any).partialInput = ''
        break
      case 'tool_result':
        if (!('content' in block)) (block as any).content = ''
        break
    }
    
    return block as ContentBlock
  }

  /**
   * 更新内容块
   */
  function updateContentBlock(msg: UIMessage, index: number, deltaText: string): void {
    const block = msg.contentBlocks[index]
    if (!block) {
      const fallbackBlock = initContentBlock({ type: 'text', text: '' } as ContentBlock)
      msg.contentBlocks[index] = fallbackBlock
    }

    const current = msg.contentBlocks[index]
    if (!current) return

    const blockType = (current as any)._blockType || currentBlockType || ''

    switch (blockType) {
      case 'text':
        msg.content += deltaText
        ;(current as any).text = ((current as any).text || '') + deltaText
        break
        
      case 'thinking':
        msg.thinking = (msg.thinking || '') + deltaText
        ;(current as any).thinking = ((current as any).thinking || '') + deltaText
        break
        
      case 'tool_use':
      case 'server_tool_use':
        ;(current as any).partialInput = ((current as any).partialInput || '') + deltaText
        
        const toolIds = Object.keys(pendingToolCalls.value)
        if (toolIds.length > 0) {
          const lastId = toolIds[toolIds.length - 1]
          pendingToolCalls.value[lastId].input += deltaText
        }

        if (workspaceStore.isLivePreviewing && deltaText) {
          workspaceStore.updateLivePreview(deltaText)
        }
        break
        
      case 'tool_result':
        ;(current as any).content = ((current as any).content || '') + deltaText
        
        const toolUseId = (current as any).tool_use_id
        if (toolUseId && msg.toolStatuses[toolUseId]) {
          msg.toolStatuses[toolUseId].result = (current as any).content
        }

        if (toolUseId) {
          const toolCall = pendingToolCalls.value[toolUseId]
          if (toolCall?.name === 'plan_todo') {
            tryUpdatePlanFromContent((current as any).content, msg)
          }
        }
        break
    }
  }

  /**
   * 处理内容块开始
   */
  function handleContentStart(data: { index: number; content_block: ContentBlock }, msg: UIMessage): void {
    if (!data || typeof data.index !== 'number' || !data.content_block) return
    let { index, content_block } = data

    // Safety net: Agent 生成新内容块时，如果 HITL 弹窗仍在显示则关闭
    // 说明 HITL 工具已返回（超时或其他原因），Agent 继续执行
    if (hitl.showModal.value) {
      console.log('🔄 Agent 继续执行，关闭残留 HITL 弹窗')
      hitl.hide()
    }

    if (index === -1) {
      index = msg.contentBlocks.length
    }

    while (msg.contentBlocks.length <= index) {
      msg.contentBlocks.push(null as unknown as ContentBlock)
    }

    const initializedBlock = initContentBlock(content_block)
    msg.contentBlocks[index] = initializedBlock
    currentBlockType = content_block.type

    if (content_block.type === 'thinking') {
      msg.thinking = ''
    }

    if (content_block.type === 'tool_use' && 'id' in content_block) {
      const toolId = content_block.id as string
      const toolName = (content_block as any).name as string

      msg.toolStatuses[toolId] = { pending: true }

      pendingToolCalls.value[toolId] = {
        name: toolName,
        input: '',
        id: toolId
      }

      if (FILE_WRITE_TOOLS.includes(toolName as any)) {
        const inputObj = (content_block as any).input
        const initialPath = inputObj?.path || inputObj?.file_path || null
        workspaceStore.startLivePreview(toolName, toolId, initialPath)
      }

      if (TERMINAL_TOOLS.includes(toolName as any)) {
        workspaceStore.setTerminalRunning(true)
      }
    }

    if (content_block.type === 'tool_result' && 'tool_use_id' in content_block) {
      const toolUseId = content_block.tool_use_id as string
      const content = (content_block as any).content
      const isError = (content_block as any).is_error

      msg.toolStatuses[toolUseId] = {
        pending: false,
        success: !isError,
        result: content
      }

      const toolCall = pendingToolCalls.value[toolUseId]

      if (toolCall && TERMINAL_TOOLS.includes(toolCall.name as any)) {
        let outputText = content
        try {
          const jsonContent = JSON.parse(content)
          if (jsonContent.stdout !== undefined) {
            outputText = jsonContent.stdout
            if (jsonContent.stderr) {
              outputText += '\n[STDERR]\n' + jsonContent.stderr
            }
          } else if (jsonContent.message) {
            outputText = jsonContent.message
          }
        } catch {
          // ignore
        }

        workspaceStore.addTerminalLog(isError ? 'error' : 'output', outputText)
        workspaceStore.setTerminalRunning(false)
        delete pendingToolCalls.value[toolUseId]
      }

      if (toolCall?.name === 'plan_todo' && content) {
        tryUpdatePlanFromContent(content, msg)
      }
    }
  }

  /**
   * 处理内容增量
   */
  function handleContentDelta(data: { index: number; delta: string | object }, msg: UIMessage): void {
    if (!data || typeof data.index !== 'number') return
    const { index, delta } = data

    const deltaText = typeof delta === 'string'
      ? delta
      : ((delta as any).text || (delta as any).thinking || (delta as any).partial_json || '')

    if (!deltaText) return

    updateContentBlock(msg, index, deltaText)
  }

  /**
   * 处理内容块停止
   */
  function handleContentStop(data: { index: number }, msg: UIMessage): void {
    if (!data || typeof data.index !== 'number') return
    const { index } = data
    const block = msg.contentBlocks[index]

    if (block && (block as any).partialInput) {
      try {
        (block as any).input = JSON.parse((block as any).partialInput)
        delete (block as any).partialInput
      } catch {
        // ignore
      }
    }

    if (block && (block as any).type === 'tool_use') {
      const toolName = (block as any).name as string
      if (toolName === 'hitl' || toolName === 'request_human_confirmation') {
        const rawInput = (block as any).input || {}
        const request = normalizeHITLRequest(rawInput)
        if (request && !hitl.showModal.value) {
          hitl.show(request)
        }
      }
    }

    if (currentBlockType === 'tool_use' && workspaceStore.isLivePreviewing) {
      workspaceStore.finishLivePreview()

      const toolIds = Object.keys(pendingToolCalls.value)
      if (toolIds.length > 0) {
        const lastId = toolIds[toolIds.length - 1]
        const toolCall = pendingToolCalls.value[lastId]

        if (TERMINAL_TOOLS.includes(toolCall.name as any)) {
          try {
            const inputObj = JSON.parse(toolCall.input)
            const command = inputObj.command || inputObj.project_path
            if (command) {
              workspaceStore.addTerminalLog('command', command)
            }
          } catch {
            // ignore
          }
        }
      }
    }

    if (block && block.type === 'tool_result') {
      const toolUseId = (block as any).tool_use_id
      const toolCall = toolUseId ? pendingToolCalls.value[toolUseId] : null
      
      if (toolCall?.name === 'plan_todo') {
        const content = (block as any).content
        if (content) {
          tryUpdatePlanFromContent(content, msg)
        }
        delete pendingToolCalls.value[toolUseId]
      }
    }
  }

  /**
   * 检查活跃会话（页面刷新重连）
   */
  async function checkActiveSessions(): Promise<boolean> {
    try {
      const userId = conversationStore.userId
      if (!userId) return false

      if (sessionStore.hasActiveSessions) {
        console.log('🔄 发现活跃 Session')
        return false // 暂时返回 false，不自动重连
      }

      return false
    } catch (error) {
      console.log('ℹ️ 无活跃 Session 或检查失败')
      return false
    }
  }

  return {
    // 状态
    isLoading,
    isGenerating,
    isStopping,
    hitl,

    // V11: 回滚（V11.2: Diff 预览 + 选择性回滚）
    showRollbackModal,
    rollbackData,
    rollbackLoading,
    loadRollbackPreview,
    confirmRollback,
    dismissRollback,

    // V11.1: HITL 危险操作确认
    showHITLConfirmModal,
    hitlConfirmData,
    hitlConfirmLoading,
    approveHITLConfirm,
    rejectHITLConfirm,

    // V11: 长任务确认
    showLongRunConfirmModal,
    longRunConfirmData,
    confirmLongRunContinue,
    dismissLongRunConfirm,

    // 连接状态
    connectionStatus,

    // 计算属性
    messages,
    conversationId,
    currentTitle,
    conversations,
    isCurrentConversationLoading,

    // Playbook
    acceptPlaybookSuggestion,
    dismissPlaybookSuggestion,
    injectPlaybookSuggestion,

    // 方法
    initialize,
    cleanup,
    createNewConversation,
    loadConversation,
    sendMessage,
    stopGeneration
  }
}

/**
 * 规范化 HITL 请求
 */
function normalizeHITLRequest(raw: any): HITLConfirmRequest | null {
  if (!raw) return null
  if (typeof raw === 'string') {
    try {
      return normalizeHITLRequest(JSON.parse(raw))
    } catch {
      return null
    }
  }
  if (typeof raw !== 'object') return null

  const question = raw.question || raw.title || ''
  if (!question) return null

  const confirmationType = raw.confirmation_type || raw.input_type ||
    (raw.questions ? 'form' : 'yes_no')

  return {
    question,
    options: raw.options,
    confirmation_type: confirmationType,
    timeout: raw.timeout,
    description: raw.description || raw.metadata?.description,
    questions: raw.questions || raw.metadata?.questions,
    default_value: raw.default_value,
    metadata: raw.metadata
  } as HITLConfirmRequest
}

/**
 * 🆕 从 hitl_data 构造 HITL 请求（用于 ZenO 格式的 hitl_data delta）
 */
function normalizeHITLRequestFromHitlData(hitlData: any): HITLConfirmRequest | null {
  if (!hitlData || !hitlData.questions) return null

  // 从 hitl_data 格式转换为 HITLConfirmRequest 格式
  return {
    question: hitlData.title || '请选择',
    confirmation_type: 'form',
    description: hitlData.description,
    questions: hitlData.questions,
    metadata: hitlData
  } as HITLConfirmRequest
}

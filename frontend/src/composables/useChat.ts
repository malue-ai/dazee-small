/**
 * 聊天核心 Composable
 * 负责发送消息、处理 SSE 事件、更新消息
 */

import { ref, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useConversationStore } from '@/stores/conversation'
import { useSessionStore } from '@/stores/session'
import { useWorkspaceStore } from '@/stores/workspace'
import { useSSE, type SSEEventHandler } from './useSSE'
import { useHITL } from './useHITL'
import type {
  UIMessage,
  AttachedFile,
  SendMessageOptions,
  ContentBlock,
  PlanData,
  HITLConfirmRequest
} from '@/types'
import { FILE_WRITE_TOOLS, TERMINAL_TOOLS, BACKGROUND_TASKS } from '@/utils'
import * as sessionApi from '@/api/session'

/**
 * 聊天核心 Composable
 */
export function useChat() {
  const router = useRouter()
  const route = useRoute()
  const conversationStore = useConversationStore()
  const sessionStore = useSessionStore()
  const workspaceStore = useWorkspaceStore()
  const hitl = useHITL()
  const sse = useSSE()

  // ==================== 状态 ====================

  /** 是否正在加载 */
  const isLoading = ref(false)

  /** 是否正在生成 */
  const isGenerating = ref(false)

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
  } | null>(null)
  const rollbackLoading = ref(false)

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

  /** 是否当前会话正在加载 */
  const isCurrentConversationLoading = computed(() => {
    if (isLoading.value) return true
    const convId = conversationStore.currentId
    if (convId && sessionStore.isConversationRunning(convId)) return true
    return false
  })

  // ==================== 路由监听 ====================

  // 监听路由参数变化
  watch(
    () => route.params.conversationId,
    async (newId) => {
      if (newId && typeof newId === 'string') {
        await loadConversation(newId)
      }
    }
  )

  // ==================== 方法 ====================

  /**
   * 初始化
   */
  async function initialize(): Promise<boolean> {
    conversationStore.initUserId()

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
    sse.disconnect()
  }

  /**
   * 创建新会话
   */
  async function createNewConversation(): Promise<void> {
    // 断开现有 SSE 连接
    if (sse.isConnected.value) {
      sse.disconnect()
    }
    
    // 重置所有加载状态
    isLoading.value = false
    isGenerating.value = false
    isStopping.value = false
    
    conversationStore.reset()
    router.push({ name: 'chat' })
    await conversationStore.fetchList()
  }

  /**
   * 加载会话
   */
  async function loadConversation(convId: string): Promise<void> {
    if (sse.isConnected.value) {
      sse.disconnect()
    }

    // 重置所有加载状态（确保切换会话时状态正确）
    isLoading.value = false
    isGenerating.value = false
    isStopping.value = false
    
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

    // 添加用户消息
    conversationStore.addUserMessage(content, files)

    // 添加空的助手消息
    const assistantMsg = conversationStore.addAssistantMessage()

    isLoading.value = true
    isGenerating.value = false

    try {
      // 构建请求体
      const requestBody = {
        message: content,
        user_id: conversationStore.userId,
        conversation_id: conversationStore.currentId || undefined,
        stream: true,
        agent_id: options.agentId || undefined,
        background_tasks: options.backgroundTasks || [
          BACKGROUND_TASKS.TITLE_GENERATION,
          BACKGROUND_TASKS.RECOMMENDED_QUESTIONS
        ],
        files: files?.map(f => ({
          file_url: f.file_url,
          file_name: f.file_name,
          file_type: f.file_type,
          file_size: f.file_size
        })),
        variables: options.variables || {
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          locale: navigator.language,
          timestamp: new Date().toISOString()
        }
      }

      // 连接 SSE
      const result = await sse.connect(requestBody, {
        onEvent: (event) => handleStreamEvent(event, assistantMsg),
        onConnected: () => {
          console.log('✅ SSE 已连接')
        },
        onDisconnected: () => {
          console.log('✅ SSE 已断开')
          // 🔧 重置停止状态（用户主动停止时，SSE 会在收到 done 后断开）
          isStopping.value = false
        },
        onError: (error) => {
          console.error('❌ SSE 错误:', error)
          assistantMsg.content += `\n❌ 发送失败: ${error.message}`
        }
      })

      // 刷新会话列表（失败不应中断发送流程）
      try {
        await conversationStore.fetchList()
      } catch (e) {
        console.warn('⚠️ 发送后刷新会话列表失败:', e)
      }

      return result
    } catch (error) {
      assistantMsg.content += `\n❌ 发送失败: ${(error as Error).message}`
      throw error
    } finally {
      isLoading.value = false
      isGenerating.value = false
    }
  }

  /**
   * 停止生成
   * 
   * 注意：不立即断开 SSE，等待后端发送 done 事件后由事件处理器断开
   * 事件顺序：billing → message_stop (done) → session_stopped
   */
  async function stopGeneration(): Promise<void> {
    const sessionId = sessionStore.currentSessionId ||
      sessionStore.getSessionIdByConversation(conversationStore.currentId)

    if (!sessionId) {
      console.warn('⚠️ 无法停止：session_id 不存在')
      return
    }

    isStopping.value = true

    try {
      // 只发送停止请求，不立即断开 SSE
      // SSE 会在收到 message_stop 或 session_stopped 事件后由事件处理器断开
      await sessionStore.stop(sessionId)
      // 🔧 修复：不在这里 disconnect，让事件处理器在收到 done 后断开
      // sse.disconnect()
    } catch (error) {
      // 停止请求失败时才强制断开
      console.error('❌ 停止请求失败:', error)
      sse.disconnect()
      isStopping.value = false
      isLoading.value = false
      isGenerating.value = false
    }
    // 注意：isStopping、isLoading、isGenerating 状态会在收到 done 事件时由事件处理器重置
  }

  /**
   * V11: 确认回滚（调用后端回滚 API）
   */
  async function confirmRollback(): Promise<void> {
    const sessionId =
      sessionStore.currentSessionId ||
      sessionStore.getSessionIdByConversation(conversationStore.currentId) ||
      rollbackData.value?.task_id
    if (!sessionId) {
      console.warn('⚠️ 无法回滚：session_id 不存在')
      return
    }
    rollbackLoading.value = true
    try {
      await sessionApi.rollbackSession(sessionId)
      showRollbackModal.value = false
      rollbackData.value = null
    } catch (e) {
      console.error('❌ 回滚失败:', e)
      if (rollbackData.value) {
        rollbackData.value = {
          ...rollbackData.value,
          error: (e as Error).message || '回滚请求失败'
        }
      }
    } finally {
      rollbackLoading.value = false
    }
  }

  /**
   * V11: 关闭回滚弹窗（保持当前状态）
   */
  function dismissRollback(): void {
    showRollbackModal.value = false
    rollbackData.value = null
  }

  /**
   * V11: 用户确认继续长任务（调用后端后关闭弹窗，执行器会继续）
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
   * V11: 关闭长任务确认弹窗（用户选择停止则停止会话）
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
   * 处理流事件
   */
  function handleStreamEvent(event: { type: string; data: any }, msg: UIMessage): void {
    const { type, data } = event

    // 保存 session_id
    if (data?.session_id) {
      sessionStore.setCurrentSessionId(data.session_id)
    }

    // 处理 session 开始事件
    if (type === 'session_start') {
      console.log('🚀 Session 开始:', data.session_id)
      // session_start 主要用于保存 session_id，已在上面处理
    }

    // 处理会话开始事件
    if (type === 'conversation_start' && data.conversation_id) {
      if (!conversationStore.currentId) {
        conversationStore.currentId = data.conversation_id
        conversationStore.fetchList().catch(e => {
          console.warn('⚠️ conversation_start 后刷新会话列表失败:', e)
        })
      }
    }

    // 处理消息开始事件 - 更新占位消息的 ID
    if (type === 'message_start') {
      const messageId = data.message_id || data.message?.id
      if (messageId) {
        // 将占位消息的临时 ID 更新为后端返回的 message_id
        msg.id = messageId
        console.log('📝 Message 开始，ID 已更新:', messageId)
      }
    }

    // 处理消息增量事件（plan、recommended 等）
    if (type === 'message_delta') {
      handleMessageDelta(data.delta, msg)
    }

    // 处理内容块开始事件
    if (type === 'content_start') {
      if (!isGenerating.value) {
        isGenerating.value = true
      }
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

    // V11: 回滚选项（异常或终止策略触发）
    if (type === 'rollback_options') {
      const taskId = data?.task_id || sessionStore.currentSessionId
      const options = Array.isArray(data?.options) ? data.options : []
      rollbackData.value = {
        task_id: taskId || '',
        options,
        error: data?.error,
        reason: data?.reason
      }
      showRollbackModal.value = true
    }

    // V11: 回滚已完成（自动回滚或用户确认回滚后）
    if (type === 'rollback_completed') {
      showRollbackModal.value = false
      rollbackData.value = null
    }

    // V11: 长任务确认（是否继续执行）
    if (type === 'long_running_confirm') {
      longRunConfirmData.value = {
        turn: data?.turn ?? 0,
        message: data?.message ?? '任务已执行较多轮次，是否继续？'
      }
      showLongRunConfirmModal.value = true
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
  }

  /**
   * 尝试从内容中解析并更新 Plan（支持流式解析）
   * @param content - 工具返回的内容（可能是不完整的 JSON）
   * @param msg - 当前消息
   */
  function tryUpdatePlanFromContent(content: string, msg: UIMessage): void {
    if (!content) return
    
    /**
     * 同步更新消息级别和会话级别的 Plan
     * 确保右侧任务进度面板实时更新
     */
    const syncPlanUpdate = (planData: PlanData) => {
      msg.planResult = planData
      // 🔧 同步更新会话级别的 conversationPlan，确保 PlanWidget 实时刷新
      conversationStore.updatePlan(planData)
      console.log('📋 Plan 已同步更新:', planData?.name, `(${planData.todos?.filter(t => t.status === 'completed').length || 0}/${planData.todos?.length || 0} 完成)`)
    }
    
    try {
      // 尝试解析完整 JSON
      const resultContent = JSON.parse(content)
      if (resultContent?.plan) {
        syncPlanUpdate(resultContent.plan as PlanData)
      }
    } catch {
      // JSON 不完整，尝试提取部分 plan 数据（用于流式显示）
      // 只在能找到 "plan": { 时尝试解析
      const planMatch = content.match(/"plan"\s*:\s*(\{[\s\S]*)/)?.[1]
      if (planMatch) {
        try {
          // 尝试补全 JSON（简单处理）
          let planJson = planMatch
          // 计算大括号平衡
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
          // 忽略解析错误
        }
      }
    }
  }

  /**
   * 初始化内容块（统一处理所有类型）
   * 确保每种类型的内容块都有正确的初始结构
   */
  function initContentBlock(contentBlock: ContentBlock): ContentBlock {
    const block = { ...contentBlock, _blockType: contentBlock.type }
    
    // 根据类型初始化字段
    switch (contentBlock.type) {
      case 'text':
        if (!('text' in block)) {
          (block as any).text = ''
        }
        break
      case 'thinking':
        if (!('thinking' in block)) {
          (block as any).thinking = ''
        }
        break
      case 'tool_use':
      case 'server_tool_use':
        if (!('partialInput' in block)) {
          (block as any).partialInput = ''
        }
        break
      case 'tool_result':
        // tool_result 的 content 可能在 content_start 时就完整发送
        // 也可能通过 delta 流式发送
        if (!('content' in block)) {
          (block as any).content = ''
        }
        break
    }
    
    return block as ContentBlock
  }

  /**
   * 更新内容块（统一处理流式增量）
   * 通过替换数组元素来确保响应式更新
   */
  function updateContentBlock(msg: UIMessage, index: number, deltaText: string): void {
    const block = msg.contentBlocks[index]
    if (!block) {
      // 容错：如果缺少 content_start，按文本块补齐
      const fallbackBlock = initContentBlock({ type: 'text', text: '' } as ContentBlock)
      msg.contentBlocks[index] = fallbackBlock
    }

    const current = msg.contentBlocks[index]
    if (!current) return

    const blockType = (current as any)._blockType || currentBlockType || ''

    switch (blockType) {
      case 'text':
        msg.content += deltaText
        // 直接修改现有对象属性（Vue 3 Proxy 会追踪）
        ;(current as any).text = ((current as any).text || '') + deltaText
        break
        
      case 'thinking':
        msg.thinking = (msg.thinking || '') + deltaText
        // 直接修改现有对象属性
        ;(current as any).thinking = ((current as any).thinking || '') + deltaText
        break
        
      case 'tool_use':
      case 'server_tool_use':
        ;(current as any).partialInput = ((current as any).partialInput || '') + deltaText
        
        // 更新 pending tool input
        const toolIds = Object.keys(pendingToolCalls.value)
        if (toolIds.length > 0) {
          const lastId = toolIds[toolIds.length - 1]
          pendingToolCalls.value[lastId].input += deltaText
        }

        // 更新实时预览
        if (workspaceStore.isLivePreviewing && deltaText) {
          workspaceStore.updateLivePreview(deltaText)
        }
        break
        
      case 'tool_result':
        // 流式累加工具结果内容
        ;(current as any).content = ((current as any).content || '') + deltaText
        
        // 同步更新 toolStatuses 中的结果
        const toolUseId = (current as any).tool_use_id
        if (toolUseId && msg.toolStatuses[toolUseId]) {
          msg.toolStatuses[toolUseId].result = (current as any).content
        }

        // plan_todo 工具：流式更新 Plan
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

    // 支持 index=-1 (自动追加到末尾)
    if (index === -1) {
      index = msg.contentBlocks.length
    }

    // 扩展 contentBlocks 数组
    while (msg.contentBlocks.length <= index) {
      msg.contentBlocks.push(null as unknown as ContentBlock)
    }

    // 初始化并存储内容块
    const initializedBlock = initContentBlock(content_block)
    msg.contentBlocks[index] = initializedBlock
    currentBlockType = content_block.type

    // 类型特定处理
    if (content_block.type === 'thinking') {
      msg.thinking = ''
    }

    if (content_block.type === 'tool_use' && 'id' in content_block) {
      const toolId = content_block.id as string
      const toolName = (content_block as any).name as string

      msg.toolStatuses[toolId] = { pending: true }

      // 初始化 pending tool call
      pendingToolCalls.value[toolId] = {
        name: toolName,
        input: '',
        id: toolId
      }

      // 文件写入工具 -> 启动实时预览
      if (FILE_WRITE_TOOLS.includes(toolName as any)) {
        const inputObj = (content_block as any).input
        const initialPath = inputObj?.path || inputObj?.file_path || null
        workspaceStore.startLivePreview(toolName, toolId, initialPath)
      }

      // 终端命令工具 -> 标记终端运行中
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

      // 获取对应的工具调用信息
      const toolCall = pendingToolCalls.value[toolUseId]

      // 处理终端输出
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
          // 不是 JSON，直接显示
        }

        workspaceStore.addTerminalLog(isError ? 'error' : 'output', outputText)
        workspaceStore.setTerminalRunning(false)
        delete pendingToolCalls.value[toolUseId]
      }

      // plan_todo 工具：提取 Plan 数据（非流式情况，content_start 时已有完整数据）
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

    // 提取 delta 文本
    const deltaText = typeof delta === 'string'
      ? delta
      : ((delta as any).text || (delta as any).thinking || (delta as any).partial_json || '')

    if (!deltaText) return

    // 统一更新内容块
    updateContentBlock(msg, index, deltaText)
  }

  /**
   * 处理内容块停止
   */
  function handleContentStop(data: { index: number }, msg: UIMessage): void {
    if (!data || typeof data.index !== 'number') return
    const { index } = data
    const block = msg.contentBlocks[index]

    // 解析完整的工具输入
    if (block && (block as any).partialInput) {
      try {
        (block as any).input = JSON.parse((block as any).partialInput)
        delete (block as any).partialInput
      } catch {
        // 忽略解析错误
      }
    }

    // HITL：工具输入完整后弹窗
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

    // 结束实时预览
    if (currentBlockType === 'tool_use' && workspaceStore.isLivePreviewing) {
      workspaceStore.finishLivePreview()

      // 处理终端命令输入完成
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
            // 忽略解析错误
          }
        }
      }
    }

    // plan_todo 工具：tool_result 完整后最终确认 Plan 数据
    if (block && block.type === 'tool_result') {
      const toolUseId = (block as any).tool_use_id
      const toolCall = toolUseId ? pendingToolCalls.value[toolUseId] : null
      
      if (toolCall?.name === 'plan_todo') {
        const content = (block as any).content
        if (content) {
          tryUpdatePlanFromContent(content, msg)
          console.log('📋 Plan 数据已确认:', msg.planResult?.name)
        }
        // 清理 pendingToolCalls
        delete pendingToolCalls.value[toolUseId]
      }
    }
  }

  return {
    // 状态
    isLoading,
    isGenerating,
    isStopping,
    hitl,

    // V11: 回滚
    showRollbackModal,
    rollbackData,
    rollbackLoading,
    confirmRollback,
    dismissRollback,

    // V11: 长任务确认
    showLongRunConfirmModal,
    longRunConfirmData,
    confirmLongRunContinue,
    dismissLongRunConfirm,

    // 计算属性
    messages,
    conversationId,
    currentTitle,
    conversations,
    isCurrentConversationLoading,

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
 * 规范化 HITL 请求（兼容不同字段命名）
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

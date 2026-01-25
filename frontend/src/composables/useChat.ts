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
import type {
  UIMessage,
  AttachedFile,
  SendMessageOptions,
  ContentBlock,
  PlanData,
  Agent
} from '@/types'
import { FILE_WRITE_TOOLS, TERMINAL_TOOLS, BACKGROUND_TASKS } from '@/utils'

/**
 * 聊天核心 Composable
 */
export function useChat() {
  const router = useRouter()
  const route = useRoute()
  const conversationStore = useConversationStore()
  const sessionStore = useSessionStore()
  const workspaceStore = useWorkspaceStore()
  const sse = useSSE()

  // ==================== 状态 ====================

  /** 是否正在加载 */
  const isLoading = ref(false)

  /** 是否正在生成 */
  const isGenerating = ref(false)

  /** 是否正在停止 */
  const isStopping = ref(false)

  /** 当前选择的 Agent */
  const selectedAgent = ref<Agent | null>(null)

  /** 当前内容块类型（用于 delta 处理） */
  let currentBlockType: string | null = null

  /** 待处理的工具调用 */
  const pendingToolCalls = ref<Record<string, { name: string; input: string; id: string }>>({})

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

    // 启动活跃会话轮询
    const userId = conversationStore.userId
    if (userId) {
      sessionStore.startPolling(userId)
    }

    // 检查活跃会话（页面刷新重连）
    const reconnected = await checkActiveSessions()

    // 如果没有重连，根据路由加载会话
    const routeConvId = route.params.conversationId
    if (!reconnected && routeConvId && typeof routeConvId === 'string') {
      await loadConversation(routeConvId)
    }

    return reconnected
  }

  /**
   * 清理
   */
  function cleanup(): void {
    sessionStore.stopPolling()
    sse.disconnect()
  }

  /**
   * 设置选中的 Agent
   */
  function setSelectedAgent(agent: Agent | null): void {
    selectedAgent.value = agent
    console.log('🤖 已选择 Agent:', agent?.name || '默认')
  }

  /**
   * 创建新会话
   */
  async function createNewConversation(): Promise<void> {
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

    isLoading.value = false
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
        agent_id: selectedAgent.value?.agent_id || options.agentId || undefined,
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
        },
        onError: (error) => {
          console.error('❌ SSE 错误:', error)
          assistantMsg.content += `\n❌ 发送失败: ${error.message}`
        }
      })

      // 刷新会话列表
      await conversationStore.fetchList()

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
      await sessionStore.stop(sessionId)
      sse.disconnect()
    } finally {
      isStopping.value = false
      isLoading.value = false
      isGenerating.value = false
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

    // 处理会话开始事件
    if (type === 'conversation_start' && data.conversation_id) {
      if (!conversationStore.currentId) {
        conversationStore.currentId = data.conversation_id
        conversationStore.fetchList()
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
  }

  /**
   * 处理消息增量
   */
  function handleMessageDelta(delta: { type: string; content: string | object }, msg: UIMessage): void {
    if (!delta) return

    if (delta.type === 'plan') {
      try {
        let planData = typeof delta.content === 'string'
          ? JSON.parse(delta.content)
          : delta.content

        // 处理嵌套结构
        if (planData?.plan) {
          msg.planResult = planData.plan as PlanData
        } else if (planData?.goal || planData?.steps) {
          msg.planResult = planData as PlanData
        }

        console.log('📋 Plan 已更新:', msg.planResult)
      } catch (e) {
        console.warn('解析 Plan 失败:', e)
      }
    }

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
  }

  /**
   * 处理内容块开始
   */
  function handleContentStart(data: { index: number; content_block: ContentBlock }, msg: UIMessage): void {
    const { index, content_block } = data

    // 扩展 contentBlocks 数组
    while (msg.contentBlocks.length <= index) {
      msg.contentBlocks.push(null as unknown as ContentBlock)
    }

    // 记录 block 类型
    msg.contentBlocks[index] = { ...content_block, _blockType: content_block.type } as ContentBlock
    currentBlockType = content_block.type

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

      // 处理终端输出
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
          // 不是 JSON，直接显示
        }

        workspaceStore.addTerminalLog(isError ? 'error' : 'output', outputText)
        workspaceStore.setTerminalRunning(false)
        delete pendingToolCalls.value[toolUseId]
      }

      // 提取 Plan 数据
      try {
        const resultContent = typeof content === 'string'
          ? JSON.parse(content)
          : content

        if (resultContent?.plan) {
          msg.planResult = resultContent.plan as PlanData
          console.log('📋 从工具结果中提取 Plan:', msg.planResult)
        }
      } catch {
        // 忽略解析错误
      }
    }
  }

  /**
   * 处理内容增量
   */
  function handleContentDelta(data: { index: number; delta: string | object }, msg: UIMessage): void {
    const { index, delta } = data
    const block = msg.contentBlocks[index]
    const blockType = (block as any)?._blockType || currentBlockType || ''

    const deltaText = typeof delta === 'string'
      ? delta
      : ((delta as any).text || (delta as any).thinking || (delta as any).partial_json || '')

    if (blockType === 'text') {
      msg.content += deltaText
      if (block && 'text' in block) {
        (block as any).text = ((block as any).text || '') + deltaText
      }
    } else if (blockType === 'thinking') {
      msg.thinking = (msg.thinking || '') + deltaText
      if (block && 'thinking' in block) {
        (block as any).thinking = ((block as any).thinking || '') + deltaText
      }
    } else if (blockType === 'tool_use' || blockType === 'server_tool_use') {
      if (block) {
        (block as any).partialInput = ((block as any).partialInput || '') + deltaText
      }

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
    }
  }

  /**
   * 处理内容块停止
   */
  function handleContentStop(data: { index: number }, msg: UIMessage): void {
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
  }

  /**
   * 检查活跃会话（页面刷新重连）
   */
  async function checkActiveSessions(): Promise<boolean> {
    try {
      const userId = conversationStore.userId
      if (!userId) return false

      const sessions = await sessionStore.getActiveSessions(userId)

      if (sessions && sessions.length > 0) {
        console.log(`🔄 发现 ${sessions.length} 个活跃 Session`)
        // TODO: 实现重连逻辑
        // await reconnectToSession(sessions[0])
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
    selectedAgent,

    // 计算属性
    messages,
    conversationId,
    currentTitle,
    conversations,
    isCurrentConversationLoading,

    // 方法
    initialize,
    cleanup,
    setSelectedAgent,
    createNewConversation,
    loadConversation,
    sendMessage,
    stopGeneration
  }
}

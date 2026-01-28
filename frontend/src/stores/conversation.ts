/**
 * 会话管理 Store
 * 负责管理对话的 CRUD、列表、消息历史
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as chatApi from '@/api/chat'
import type { Conversation, Message, UIMessage, ContentBlock, ToolStatusMap, PlanData, AttachedFile } from '@/types'

export const useConversationStore = defineStore('conversation', () => {
  // ==================== 状态 ====================

  /** 会话列表 */
  const conversations = ref<Conversation[]>([])

  /** 当前会话 ID */
  const currentId = ref<string | null>(null)

  /** 当前会话的消息列表 */
  const messages = ref<UIMessage[]>([])

  /** 当前会话的 Plan（从 conversation_metadata 加载） */
  const conversationPlan = ref<PlanData | null>(null)

  /** 用户 ID */
  const userId = ref<string>('')

  /** 加载状态 */
  const loading = ref(false)

  /** 消息加载状态 */
  const loadingMessages = ref(false)

  // ==================== 计算属性 ====================

  /** 当前会话信息 */
  const currentConversation = computed(() => {
    if (!currentId.value) return null
    return conversations.value.find(c => c.id === currentId.value) || null
  })

  /** 当前会话标题 */
  const currentTitle = computed(() => {
    return currentConversation.value?.title || '新对话'
  })

  /** 是否有消息 */
  const hasMessages = computed(() => messages.value.length > 0)

  // ==================== 方法 ====================

  /**
   * 初始化用户 ID
   */
  function initUserId(): string {
    if (!userId.value) {
      userId.value = localStorage.getItem('userId') || 'user_' + Date.now()
      localStorage.setItem('userId', userId.value)
    }
    return userId.value
  }

  /**
   * 获取会话列表
   * @param limit - 数量限制
   * @param offset - 偏移量
   */
  async function fetchList(limit = 20, offset = 0): Promise<Conversation[]> {
    const uid = initUserId()
    loading.value = true

    try {
      const result = await chatApi.getConversationList(uid, limit, offset)
      conversations.value = result.conversations
      return result.conversations
    } catch (error) {
      console.error('❌ 获取会话列表失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  /**
   * 创建新会话
   * @param title - 会话标题
   */
  async function create(title = '新对话'): Promise<Conversation> {
    const uid = initUserId()

    try {
      const conversation = await chatApi.createConversation(uid, title)
      currentId.value = conversation.id
      messages.value = []
      
      // 刷新列表
      await fetchList()
      
      console.log('✅ 会话创建成功:', conversation.id)
      return conversation
    } catch (error) {
      console.error('❌ 创建会话失败:', error)
      throw error
    }
  }

  /**
   * 加载会话及其消息
   * @param conversationId - 会话 ID
   */
  async function load(conversationId: string): Promise<void> {
    currentId.value = conversationId
    loadingMessages.value = true
    conversationPlan.value = null  // 重置 plan

    try {
      const result = await chatApi.getConversationMessages(conversationId, 100, 0, 'asc')
      messages.value = result.messages.map(processHistoryMessage)
      
      // 从 conversation_metadata 中提取 plan
      if (result.conversation_metadata?.plan) {
        conversationPlan.value = result.conversation_metadata.plan as PlanData
        console.log('📋 从会话元数据加载 Plan:', conversationPlan.value?.name)
      }
      
      console.log('✅ 历史消息已加载:', messages.value.length, '条')
    } catch (error) {
      console.error('❌ 加载消息失败:', error)
      throw error
    } finally {
      loadingMessages.value = false
    }
  }

  /**
   * 更新会话标题
   * @param conversationId - 会话 ID
   * @param title - 新标题
   */
  async function updateTitle(conversationId: string, title: string): Promise<void> {
    try {
      await chatApi.updateConversation(conversationId, title)
      
      // 更新本地列表
      const conv = conversations.value.find(c => c.id === conversationId)
      if (conv) {
        conv.title = title
      }
      
      console.log('✅ 会话标题已更新')
    } catch (error) {
      console.error('❌ 更新会话失败:', error)
      throw error
    }
  }

  /**
   * 删除会话
   * @param conversationId - 会话 ID
   */
  async function remove(conversationId: string): Promise<void> {
    try {
      await chatApi.deleteConversation(conversationId)
      
      // 从列表中移除
      conversations.value = conversations.value.filter(c => c.id !== conversationId)
      
      // 如果删除的是当前会话，清空状态
      if (currentId.value === conversationId) {
        currentId.value = null
        messages.value = []
      }
      
      console.log('✅ 会话已删除')
    } catch (error) {
      console.error('❌ 删除会话失败:', error)
      throw error
    }
  }

  /**
   * 添加用户消息
   * @param content - 消息内容
   * @param files - 附件文件
   */
  function addUserMessage(content: string, files?: AttachedFile[]): UIMessage {
    const msg: UIMessage = {
      id: Date.now(),
      role: 'user',
      content,
      contentBlocks: [],
      toolStatuses: {},
      files: files || undefined,
      timestamp: new Date()
    }
    messages.value.push(msg)
    return msg
  }

  /**
   * 添加助手消息（空消息，用于流式填充）
   * 注意：返回的是数组中的响应式对象，而不是原始对象
   */
  function addAssistantMessage(): UIMessage {
    const msg: UIMessage = {
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
    messages.value.push(msg)
    // 返回数组中的最后一个元素（被 Vue Proxy 包装的响应式对象）
    return messages.value[messages.value.length - 1]
  }

  /**
   * 获取最后一条助手消息（响应式引用）
   */
  function getLastAssistantMessage(): UIMessage | null {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].role === 'assistant') {
        return messages.value[i]
      }
    }
    return null
  }

  /**
   * 重置当前会话
   */
  function reset(): void {
    currentId.value = null
    messages.value = []
    conversationPlan.value = null
  }

  /**
   * 处理历史消息，转换为 UIMessage 格式
   */
  function processHistoryMessage(msg: Message): UIMessage {
    // 解析 Plan 数据
    let planData: PlanData | null = null
    if (msg.metadata?.plan) {
      let rawPlan: string | object | null = msg.metadata.plan
      
      if (typeof rawPlan === 'string') {
        try {
          rawPlan = JSON.parse(rawPlan)
        } catch {
          rawPlan = null
        }
      }
      
      if (rawPlan && typeof rawPlan === 'object') {
        const plan = rawPlan as Record<string, unknown>
        if (plan.plan) {
          planData = plan.plan as PlanData
        } else if (plan.goal || plan.steps) {
          planData = plan as PlanData
        }
      }
    }

    // 提取文件信息
    const filesData = msg.metadata?.files as AttachedFile[] | undefined

    // 解析内容块
    const contentBlocks = parseContentBlocks(msg.content)
    const toolStatuses = extractToolStatuses(contentBlocks)

    return {
      id: msg.id,
      role: msg.role,
      content: extractText(msg.content),
      thinking: extractThinking(msg.content),
      contentBlocks,
      toolStatuses,
      files: filesData,
      recommendedQuestions: (msg.metadata?.recommended as string[]) || [],
      planResult: planData,
      timestamp: new Date(msg.created_at)
    }
  }

  /**
   * 内容块基础类型
   */
  interface ContentBlockBase {
    type: string
    [key: string]: unknown
  }

  /**
   * 从内容中提取文本
   */
  function extractText(content: string | object[]): string {
    if (typeof content === 'string') return content
    if (Array.isArray(content)) {
      return (content as ContentBlockBase[])
        .filter((b): b is ContentBlockBase & { type: 'text'; text: string } => b.type === 'text')
        .map(b => b.text)
        .join('\n')
    }
    return String(content)
  }

  /**
   * 从内容中提取思考过程
   */
  function extractThinking(content: string | object[]): string {
    if (Array.isArray(content)) {
      const block = (content as ContentBlockBase[]).find(
        (b): b is ContentBlockBase & { type: 'thinking'; thinking: string } => 
          b.type === 'thinking'
      )
      return block?.thinking || ''
    }
    return ''
  }

  /**
   * 解析内容块
   */
  function parseContentBlocks(content: string | object[]): ContentBlock[] {
    if (Array.isArray(content)) return content as ContentBlock[]
    if (typeof content === 'string') {
      try {
        const parsed = JSON.parse(content)
        if (Array.isArray(parsed)) return parsed as ContentBlock[]
      } catch {
        // 不是 JSON，返回空数组
      }
    }
    return []
  }

  /**
   * 从内容块中提取工具状态
   */
  function extractToolStatuses(contentBlocks: ContentBlock[]): ToolStatusMap {
    const statuses: ToolStatusMap = {}

    if (!Array.isArray(contentBlocks)) return statuses

    // 首先标记所有 tool_use 为 pending
    for (const block of contentBlocks) {
      if (block.type === 'tool_use' && 'id' in block && block.id) {
        statuses[block.id] = { pending: true }
      }
    }

    // 从 tool_result 更新状态
    for (const block of contentBlocks) {
      if (block.type === 'tool_result' && 'tool_use_id' in block && block.tool_use_id) {
        let isError = block.is_error === true

        // 额外检查 content 中是否包含错误
        if (!isError && block.content) {
          const contentStr = typeof block.content === 'string'
            ? block.content
            : JSON.stringify(block.content)
          if (
            contentStr.includes('"error"') ||
            contentStr.includes('"Error"') ||
            contentStr.includes('HTTP 4') ||
            contentStr.includes('HTTP 5')
          ) {
            isError = true
          }
        }

        statuses[block.tool_use_id] = {
          pending: false,
          success: !isError,
          result: block.content as string | object
        }
      }
    }

    return statuses
  }

  return {
    // 状态
    conversations,
    currentId,
    messages,
    conversationPlan,
    userId,
    loading,
    loadingMessages,
    
    // 计算属性
    currentConversation,
    currentTitle,
    hasMessages,
    
    // 方法
    initUserId,
    fetchList,
    create,
    load,
    updateTitle,
    remove,
    addUserMessage,
    addAssistantMessage,
    getLastAssistantMessage,
    reset
  }
})

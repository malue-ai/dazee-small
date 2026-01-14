import { defineStore } from 'pinia'
import axios from '@/api/index'
import { useWorkspaceStore } from './workspace'

// 文件写入工具列表（用于实时预览）
const FILE_WRITE_TOOLS = [
  'write_file',
  'sandbox_write_file', 
  'str_replace_editor',
  'create_file'
]

export const useChatStore = defineStore('chat', {
  state: () => ({
    sessionId: null,
    conversationId: null,
    userId: null,
    messages: [],
    isConnected: false,
    // SSE 断线重连状态
    sseConnection: null,
    lastEventId: 0,
    reconnectAttempts: 0,
    maxReconnectAttempts: 3,
    // 🆕 当前内容块类型（用于简化 delta 格式）
    _currentBlockType: null,
    // 🆕 待处理的工具调用（用于终端日志关联）
    _pendingToolCalls: {},
  }),

  actions: {
    /**
     * 初始化用户ID
     */
    initUserId() {
      if (!this.userId) {
        // 从 localStorage 获取或创建新的
        this.userId = localStorage.getItem('userId') || 'user_' + Date.now()
        localStorage.setItem('userId', this.userId)
      }
      return this.userId
    },

    // ==================== Conversation 管理 ====================

    /**
     * 创建新对话
     */
    async createConversation(title = '新对话') {
      const userId = this.initUserId()

      try {
        const response = await axios.post('/v1/conversations', null, {
          params: { user_id: userId, title }
        })

        this.conversationId = response.data.data.id
        console.log('✅ 对话创建成功:', this.conversationId)
        return response.data.data
      } catch (error) {
        console.error('❌ 创建对话失败:', error)
        throw error
      }
    },

    /**
     * 获取对话列表
     */
    async getConversationList(limit = 20, offset = 0) {
      const userId = this.initUserId()

      try {
        const response = await axios.get('/v1/conversations', {
          params: { user_id: userId, limit, offset }
        })

        console.log('✅ 对话列表:', response.data.data)
        return response.data.data
      } catch (error) {
        console.error('❌ 获取对话列表失败:', error)
        throw error
      }
    },

    /**
     * 获取对话详情
     */
    async getConversation(conversationId) {
      try {
        const response = await axios.get(`/v1/conversations/${conversationId}`)
        return response.data.data
      } catch (error) {
        console.error('❌ 获取对话详情失败:', error)
        throw error
      }
    },

    /**
     * 更新对话标题
     */
    async updateConversation(conversationId, title) {
      try {
        const response = await axios.put(`/v1/conversations/${conversationId}`, null, {
          params: { title }
        })

        console.log('✅ 对话更新成功')
        return response.data.data
      } catch (error) {
        console.error('❌ 更新对话失败:', error)
        throw error
      }
    },

    /**
     * 删除对话
     */
    async deleteConversation(conversationId) {
      try {
        const response = await axios.delete(`/v1/conversations/${conversationId}`)
        console.log('✅ 对话删除成功')
        return response.data.data
      } catch (error) {
        console.error('❌ 删除对话失败:', error)
        throw error
      }
    },

    /**
     * 获取对话历史消息
     */
    async getConversationMessages(conversationId, limit = 50, offset = 0, order = 'asc') {
      try {
        const response = await axios.get(`/v1/conversations/${conversationId}/messages`, {
          params: { limit, offset, order }
        })

        console.log('✅ 历史消息:', response.data.data)
        return response.data.data
      } catch (error) {
        console.error('❌ 获取历史消息失败:', error)
        throw error
      }
    },

    /**
     * 获取对话摘要
     */
    async getConversationSummary(conversationId) {
      try {
        const response = await axios.get(`/v1/conversations/${conversationId}/summary`)
        return response.data.data
      } catch (error) {
        console.error('❌ 获取对话摘要失败:', error)
        throw error
      }
    },

    // ==================== Session 管理 ====================

    /**
     * 获取会话状态（用于断线重连判断）
     */
    async getSessionStatus(sessionId) {
      try {
        const response = await axios.get(`/v1/session/${sessionId}/status`)
        return response.data.data
      } catch (error) {
        console.error('❌ 获取会话状态失败:', error)
        throw error
      }
    },

    /**
     * 获取会话事件（用于断线重连）
     */
    async getSessionEvents(sessionId, afterId = null, limit = 100) {
      try {
        const params = { limit }
        if (afterId !== null) {
          params.after_id = afterId
        }

        const response = await axios.get(`/v1/session/${sessionId}/events`, {
          params
        })
        return response.data.data
      } catch (error) {
        console.error('❌ 获取会话事件失败:', error)
        throw error
      }
    },

    /**
     * 获取用户的所有活跃会话
     */
    async getUserSessions() {
      const userId = this.initUserId()

      try {
        const response = await axios.get(`/v1/user/${userId}/sessions`)
        return response.data.data.sessions
      } catch (error) {
        console.error('❌ 获取用户会话失败:', error)
        throw error
      }
    },

    /**
     * 停止正在运行的会话（用户主动中断）
     */
    async stopSession(sessionId) {
      try {
        console.log('🛑 停止会话:', sessionId)
        const response = await axios.post(`/v1/session/${sessionId}/stop`)
        console.log('✅ 会话已停止:', response.data)
        return response.data.data
      } catch (error) {
        console.error('❌ 停止会话失败:', error)
        throw error
      }
    },

    // ==================== 消息发送（同步模式）====================

    /**
     * 发送消息（同步模式）
     */
    async sendMessage(content, conversationId = null) {
      const userId = this.initUserId()

      try {
        const response = await axios.post('/v1/chat', {
          message: content,
          user_id: userId,
          conversation_id: conversationId,
          stream: false
        })

        // 保存 task_id 和 conversation_id
        this.sessionId = response.data.data.task_id
        this.conversationId = response.data.data.conversation_id

        return response.data.data
      } catch (error) {
        console.error('❌ 发送消息失败:', error)
        throw error
      }
    },

    // ==================== SSE 流式消息（带断线重连）====================

    /**
     * 使用 SSE 流式发送消息（支持断线重连）
     * 
     * @param {string} content - 消息内容
     * @param {string|null} conversationId - 对话ID
     * @param {Function} onEvent - 事件回调
     * @param {Object} options - 可选配置
     * @param {string[]} options.backgroundTasks - 后台任务列表，如 ['title_generation']
     * @param {Array} options.files - 文件引用列表，如 [{file_id: "xxx"}]
     * @param {string} options.agentId - Agent ID，如 'test_agent'
     * @param {Object} options.variables - 前端上下文变量
     */
    async sendMessageStream(content, conversationId = null, onEvent, options = {}) {
      const userId = this.initUserId()

      return new Promise((resolve, reject) => {
        // 构建请求 body
        const requestBody = {
          message: content,
          user_id: userId,
          stream: true
        }
        
        if (conversationId) {
          requestBody.conversation_id = conversationId
        }
        
        // 🆕 添加 Agent ID 参数
        if (options.agentId) {
          requestBody.agent_id = options.agentId
          console.log('🤖 使用 Agent:', options.agentId)
        }
        
        // 🆕 添加后台任务参数
        if (options.backgroundTasks && options.backgroundTasks.length > 0) {
          requestBody.background_tasks = options.backgroundTasks
        }
        
        // 🆕 添加文件参数
        if (options.files && options.files.length > 0) {
          requestBody.files = options.files
          console.log('📎 发送文件:', options.files)
        }
        
        // 🆕 添加前端上下文变量（位置、时区等）
        if (options.variables && Object.keys(options.variables).length > 0) {
          requestBody.variables = options.variables
          console.log('📍 发送上下文变量:', options.variables)
        }

        // 使用 fetch 创建 SSE 连接
        this._createSSEConnection(requestBody, onEvent, resolve, reject)
      })
    },

    /**
     * 创建 SSE 连接（内部方法）
     */
    async _createSSEConnection(requestBody, onEvent, resolve, reject) {
      try {
        console.log('🔌 创建 SSE 连接...', requestBody)
        
        const response = await fetch('/api/v1/chat?format=zenflux', {
          method: 'POST',
          headers: {
            'Accept': 'text/event-stream',
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(requestBody)
        })

        console.log('📡 SSE 响应状态:', response.status, response.statusText)
        console.log('📡 响应头:', Object.fromEntries(response.headers.entries()))

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()

        let fullResponse = ''
        this.isConnected = true
        this.reconnectAttempts = 0

        // 读取流
        const readStream = async () => {
          try {
            let buffer = '' // 缓冲区，用于处理不完整的 SSE 消息
            let currentEvent = {
              id: null,
              event: null,
              data: null
            }

            while (true) {
              const { done, value } = await reader.read()
              
              if (done) {
                console.log('✅ SSE 连接正常关闭')
                this.isConnected = false
                break
              }

              // 将新数据添加到缓冲区
              buffer += decoder.decode(value, { stream: true })
              
              console.log('📥 收到数据块:', buffer.length, '字节')
              
              // 按行分割（保留完整的消息）
              const lines = buffer.split('\n')
              
              // 如果最后一行不完整（没有换行符结尾），保留到下次处理
              if (!buffer.endsWith('\n')) {
                buffer = lines.pop() || ''
              } else {
                buffer = ''
              }

              for (const line of lines) {
                // 空行表示一个完整的 SSE 消息结束
                if (line === '') {
                  if (currentEvent.data) {
                    try {
                      const data = JSON.parse(currentEvent.data)
                      
                      // 获取事件类型（优先使用 data.type，否则使用 SSE event 字段）
                      const eventType = data.type || currentEvent.event
                      
                      // 确保 data 包含 type 字段
                      if (!data.type && eventType) {
                        data.type = eventType
                      }
                      
                      console.log('✉️ SSE 事件:', {
                        id: currentEvent.id,
                        event: currentEvent.event,
                        type: eventType,
                        data: data
                      })
                      
                      // 记录事件ID（用于断线重连）
                      if (currentEvent.id) {
                        this.lastEventId = currentEvent.id
                      }
                      
                      // 回调处理事件（传递包含 type 的完整数据）
                      if (onEvent) {
                        onEvent(data)
                      }

                      // 🆕 简化格式：delta 直接是字符串
                      // 需要跟踪当前 block 类型来判断是否是文本内容
                      if (eventType === 'content_start') {
                        const blockType = data.data?.content_block?.type
                        this._currentBlockType = blockType
                        
                        // 🎬 检测工具调用
                        if (blockType === 'tool_use') {
                          const toolName = data.data?.content_block?.name
                          const toolId = data.data?.content_block?.id
                          
                          // 初始化 pending tool call
                          this._pendingToolCalls[toolId] = {
                            name: toolName,
                            input: '',
                            id: toolId
                          }
                          
                          // 文件写入工具 -> 启动实时预览
                          if (FILE_WRITE_TOOLS.includes(toolName)) {
                            const workspaceStore = useWorkspaceStore()
                            // 尝试从 input 中提取文件路径 (如果是非流式直接有 input)
                            const inputObj = data.data?.content_block?.input
                            const initialPath = inputObj?.path || inputObj?.file_path || null
                            workspaceStore.startLivePreview(toolName, toolId, initialPath)
                          }
                          
                          // 终端命令工具 -> 标记终端运行中
                          if (['sandbox_run_command', 'run_project', 'sandbox_run_project'].includes(toolName)) {
                            const workspaceStore = useWorkspaceStore()
                            workspaceStore.setTerminalRunning(true)
                          }
                        }
                        
                        // 🎬 检测工具结果 -> 终端输出
                        if (blockType === 'tool_result') {
                          const toolUseId = data.data?.content_block?.tool_use_id
                          const content = data.data?.content_block?.content
                          const isError = data.data?.content_block?.is_error
                          
                          // 查找对应的工具调用
                          const toolCall = this._pendingToolCalls[toolUseId]
                          if (toolCall && ['sandbox_run_command', 'run_project', 'sandbox_run_project'].includes(toolCall.name)) {
                            const workspaceStore = useWorkspaceStore()
                            
                            // 尝试解析 JSON 结果
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
                            } catch (e) {
                              // 不是 JSON，直接显示文本
                            }
                            
                            workspaceStore.addTerminalLog(
                              isError ? 'error' : 'output',
                              outputText
                            )
                            workspaceStore.setTerminalRunning(false)
                            
                            // 清理
                            delete this._pendingToolCalls[toolUseId]
                          }
                        }
                      }
                      
                      if (eventType === 'content_delta') {
                        const delta = data.data?.delta
                        // 简化格式：delta 是字符串，类型由 _currentBlockType 决定
                        if (this._currentBlockType === 'text') {
                          const deltaText = typeof delta === 'string' ? delta : (delta?.text || '')
                          fullResponse += deltaText
                        }
                        
                        // 🎬 更新工具输入（流式参数）
                        if (this._currentBlockType === 'tool_use') {
                          const workspaceStore = useWorkspaceStore()
                          const deltaText = typeof delta === 'string' ? delta : (delta?.partial_json || '')
                          
                          // 更新 pending tool input
                          // 注意：这里我们只知道当前 block，不知道 id，但通常只有一个 active block
                          // 我们遍历找到最后一个 pending 的 tool call（简化处理）
                          const toolIds = Object.keys(this._pendingToolCalls)
                          if (toolIds.length > 0) {
                            const lastId = toolIds[toolIds.length - 1]
                            this._pendingToolCalls[lastId].input += deltaText
                          }
                          
                          if (workspaceStore.isLivePreviewing) {
                            if (deltaText) {
                              workspaceStore.updateLivePreview(deltaText)
                            }
                          }
                        }
                      } else if (eventType === 'content' && data.data?.text) {
                        fullResponse += data.data.text
                      }
                      
                      // 🎬 工具执行完成
                      if (eventType === 'content_stop') {
                        if (this._currentBlockType === 'tool_use') {
                          const workspaceStore = useWorkspaceStore()
                          
                          // 结束实时预览
                          if (workspaceStore.isLivePreviewing) {
                            workspaceStore.finishLivePreview()
                          }
                          
                          // 处理终端命令输入完成
                          const toolIds = Object.keys(this._pendingToolCalls)
                          if (toolIds.length > 0) {
                            const lastId = toolIds[toolIds.length - 1]
                            const toolCall = this._pendingToolCalls[lastId]
                            
                            if (['sandbox_run_command', 'run_project', 'sandbox_run_project'].includes(toolCall.name)) {
                              // 尝试解析完整的 input JSON
                              try {
                                const inputObj = JSON.parse(toolCall.input)
                                const command = inputObj.command || inputObj.project_path // run_project use project_path
                                
                                if (command) {
                                  workspaceStore.addTerminalLog('command', command)
                                }
                              } catch (e) {
                                // JSON 可能不完整，忽略
                              }
                            }
                          }
                        }
                      }
                      
                      // 保存 session_id 和 conversation_id
                      if (data.session_id) {
                        this.sessionId = data.session_id
                      }
                      if (eventType === 'conversation_start' && data.data?.conversation_id) {
                        this.conversationId = data.data.conversation_id
                      }

                      // 处理 complete 事件 (只收集数据，不终止流)
                      if (eventType === 'complete') {
                        console.log('✅ Agent 执行完成 (complete 事件)')
                        // 如果 complete 事件包含 final_result，使用它
                        if (data.data?.final_result && !fullResponse) {
                          fullResponse = data.data.final_result
                        }
                        // 注意：不要在这里 return，还需要等待 done 事件
                      }

                      // 流结束：只在 done 或 session_end 时终止
                      if (eventType === 'done' || eventType === 'session_end') {
                        console.log('✅ 流结束:', eventType)
                        this.isConnected = false
                        resolve(fullResponse)
                        return
                      }
                    } catch (e) {
                      console.error('❌ 解析 SSE 数据失败:', e, currentEvent.data)
                    }
                  }
                  
                  // 重置当前事件
                  currentEvent = { id: null, event: null, data: null }
                  
                } else if (line.startsWith('id: ')) {
                  currentEvent.id = line.slice(4).trim()
                } else if (line.startsWith('event: ')) {
                  currentEvent.event = line.slice(7).trim()
                } else if (line.startsWith('data: ')) {
                  // data 可能跨多行，需要累积
                  if (currentEvent.data) {
                    currentEvent.data += '\n' + line.slice(6)
                  } else {
                    currentEvent.data = line.slice(6)
                  }
                }
              }
            }
          } catch (error) {
            console.error('❌ SSE 读取错误:', error)
            this.isConnected = false
            
            // 尝试断线重连
            await this._handleSSEReconnect(onEvent, resolve, reject)
          }
        }

        // 开始读取
        await readStream()

      } catch (error) {
        console.error('❌ SSE 连接错误:', error)
        this.isConnected = false
        
        // 尝试断线重连
        await this._handleSSEReconnect(onEvent, resolve, reject)
      }
    },

    /**
     * 处理 SSE 断线重连
     */
    async _handleSSEReconnect(onEvent, resolve, reject) {
      // 检查是否有 session_id（没有就无法重连）
      if (!this.sessionId) {
        console.error('❌ 无法重连：缺少 session_id')
        reject(new Error('SSE 连接断开，无法重连'))
        return
      }

      // 检查重连次数
      if (this.reconnectAttempts >= this.maxReconnectAttempts) {
        console.error('❌ 达到最大重连次数，停止重连')
        reject(new Error('SSE 连接断开，重连失败'))
        return
      }

      this.reconnectAttempts++
      console.log(`🔄 尝试断线重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`)

      try {
        // 1. 检查 Session 状态
        const sessionStatus = await this.getSessionStatus(this.sessionId)
        console.log('📊 Session 状态:', sessionStatus)

        // 如果已经完成，不需要重连
        if (sessionStatus.status === 'completed' || sessionStatus.status === 'failed') {
          console.log('✅ Session 已完成，不需要重连')
          resolve('')
          return
        }

        // 2. 获取丢失的事件
        console.log(`📥 获取丢失的事件 (after_id=${this.lastEventId})`)
        const eventsData = await this.getSessionEvents(this.sessionId, this.lastEventId)
        
        // 3. 重放丢失的事件
        if (eventsData.events && eventsData.events.length > 0) {
          console.log(`🔄 重放 ${eventsData.events.length} 个丢失的事件`)
          for (const event of eventsData.events) {
            if (onEvent) {
              onEvent(event)
            }
            this.lastEventId = event.id
          }
        }

        // 4. 重新建立 SSE 连接
        console.log('🔗 重新建立 SSE 连接...')
        // 注意：这里需要前端重新发送请求，或者使用 EventSource 的重连机制
        // 由于我们使用 fetch，这里简单地等待一段时间后完成
        setTimeout(() => {
          console.log('✅ 断线重连完成')
          resolve('')
        }, 1000)

      } catch (error) {
        console.error('❌ 断线重连失败:', error)
        
        // 等待后重试
        await new Promise(resolve => setTimeout(resolve, 1000 * this.reconnectAttempts))
        await this._handleSSEReconnect(onEvent, resolve, reject)
      }
    },

    /**
     * 手动断开 SSE 连接
     */
    disconnectSSE() {
      if (this.sseConnection) {
        this.sseConnection.close()
        this.sseConnection = null
      }
      this.isConnected = false
      console.log('🔌 SSE 连接已断开')
    },

    /**
     * 重置状态
     */
    reset() {
      this.sessionId = null
      this.conversationId = null
      this.messages = []
      this.lastEventId = 0
      this.reconnectAttempts = 0
      this.disconnectSSE()
    }
  }
})

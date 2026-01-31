<template>
  <div class="h-screen w-full flex bg-gray-50 relative overflow-hidden text-gray-900 font-sans">
    <!-- 背景装饰 (与登录页一致) -->
    <div class="absolute inset-0 z-0 opacity-20 pointer-events-none">
      <div class="absolute top-0 left-0 w-[500px] h-[500px] bg-blue-200 rounded-full mix-blend-multiply filter blur-3xl animate-blob"></div>
      <div class="absolute top-0 right-0 w-[500px] h-[500px] bg-purple-200 rounded-full mix-blend-multiply filter blur-3xl animate-blob animation-delay-2000"></div>
      <div class="absolute -bottom-8 left-20 w-[500px] h-[500px] bg-pink-200 rounded-full mix-blend-multiply filter blur-3xl animate-blob animation-delay-4000"></div>
    </div>

    <!-- 左侧侧边栏：历史对话 -->
    <div 
      class="relative z-10 flex flex-col border-r border-white/20 bg-white/60 backdrop-blur-xl transition-all duration-300 ease-in-out flex-shrink-0"
      :class="sidebarCollapsed ? 'w-[70px]' : 'w-[280px]'"
    >
      <div class="h-16 flex items-center justify-between px-5 border-b border-white/20">
        <div class="flex items-center gap-3 font-bold text-lg text-gray-800" v-if="!sidebarCollapsed">
          <div class="w-8 h-8 rounded-xl bg-gray-900 flex items-center justify-center text-white shadow-lg shadow-gray-900/20">
            ✨
          </div>
          <span>ZenFlux</span>
        </div>
        <button 
          @click="sidebarCollapsed = !sidebarCollapsed" 
          class="p-2 rounded-xl text-gray-500 hover:bg-white/80 hover:text-gray-900 transition-colors"
        >
          <span class="text-lg">{{ sidebarCollapsed ? '→' : '←' }}</span>
        </button>
      </div>

      <div v-show="!sidebarCollapsed" class="flex-1 flex flex-col p-4 overflow-y-auto scrollbar-thin">
        <!-- 操作按钮 -->
        <div class="flex flex-col gap-3 mb-6">
          <button 
            @click="createNewConversation" 
            class="w-full flex items-center justify-center gap-2 px-4 py-3 bg-gray-900 text-white rounded-xl text-sm font-medium shadow-lg shadow-gray-900/10 hover:bg-gray-800 hover:shadow-gray-900/20 transition-all transform active:scale-95"
          >
            <span>＋</span> 新建对话
          </button>
          <div class="flex gap-2">
            <button 
              @click="$router.push('/knowledge')" 
              class="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 bg-white/50 border border-white/40 rounded-xl text-xs font-medium text-gray-600 hover:bg-white hover:text-gray-900 hover:border-white/60 transition-all shadow-sm"
            >
              <span>📚</span> 知识库
            </button>
            <button 
              @click="$router.push('/agents')" 
              class="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 bg-white/50 border border-white/40 rounded-xl text-xs font-medium text-gray-600 hover:bg-white hover:text-gray-900 hover:border-white/60 transition-all shadow-sm"
            >
              <span>🤖</span> 智能体
            </button>
          </div>
        </div>

        <!-- 对话列表 -->
        <div class="flex flex-col gap-2">
          <div class="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2 px-2">最近对话</div>
          <div v-if="loadingConversations" class="text-sm text-gray-400 px-2 py-4 text-center">加载中...</div>
          <div v-else-if="conversations.length === 0" class="text-sm text-gray-400 px-2 py-4 text-center">暂无记录</div>
          <div v-else class="flex flex-col gap-1">
            <div
              v-for="conv in conversations"
              :key="conv.id"
              class="group relative flex flex-col px-4 py-3 rounded-xl cursor-pointer transition-all duration-200 border border-transparent"
              :class="conv.id === chatStore.conversationId ? 'bg-white shadow-md border-white/40 text-gray-900' : 'text-gray-600 hover:bg-white/50 hover:text-gray-900'"
              @click="loadConversation(conv.id)"
            >
              <div class="truncate font-medium text-sm mb-1">{{ conv.title || '未命名对话' }}</div>
              <div class="flex items-center justify-between text-xs text-gray-400">
                <span>{{ formatShortTime(conv.updated_at) }}</span>
                <button 
                  class="opacity-0 group-hover:opacity-100 p-1 -mr-1 hover:text-red-500 transition-opacity" 
                  @click.stop="confirmDeleteConversation(conv)"
                >
                  🗑️
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 用户信息 -->
        <div class="mt-auto pt-4 border-t border-gray-200/50 flex items-center gap-3 px-2">
          <div class="w-9 h-9 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-xs font-bold text-white shadow-md">U</div>
          <div class="flex flex-col">
            <span class="text-sm font-semibold text-gray-800">User</span>
            <span class="text-xs text-gray-400">Pro Plan</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 中间主区域：对话流 -->
    <div class="flex-1 flex flex-col min-w-0 relative z-10">
      <!-- 顶部导航栏 -->
      <div class="h-16 flex items-center justify-between px-8 border-b border-white/20 bg-white/40 backdrop-blur-md sticky top-0 z-20">
        <div class="flex items-center gap-3">
          <h2 class="text-base font-semibold text-gray-800">{{ currentConversationTitle }}</h2>
          <!-- Agent 选择器 -->
          <div class="relative group">
            <button 
              @click="showAgentSelector = !showAgentSelector"
              class="px-3 py-1 rounded-full bg-blue-100 text-blue-700 text-xs font-medium border border-blue-200 hover:bg-blue-200 transition-all flex items-center gap-1.5 cursor-pointer"
              :disabled="isLoading"
            >
              <span>{{ currentAgentName || 'Claude 3.5' }}</span>
              <span class="text-[10px]">{{ showAgentSelector ? '▲' : '▼' }}</span>
            </button>
            
            <!-- Agent 下拉列表 -->
            <div 
              v-if="showAgentSelector" 
              class="absolute top-full left-0 mt-2 w-64 bg-white rounded-xl shadow-2xl border border-gray-100 overflow-hidden z-50 animate-in fade-in slide-in-from-top-2 duration-200"
            >
              <div class="p-2 border-b border-gray-100 bg-gray-50">
                <p class="text-xs text-gray-500 px-2">选择智能体</p>
              </div>
              <div class="max-h-[300px] overflow-y-auto scrollbar-thin">
                <div v-if="loadingAgents" class="p-4 text-center text-sm text-gray-400">
                  加载中...
                </div>
                <div v-else-if="agents.length === 0" class="p-4 text-center text-sm text-gray-400">
                  暂无可用智能体
                </div>
                <button
                  v-for="agent in agents"
                  :key="agent.agent_id"
                  @click="selectAgent(agent)"
                  class="w-full text-left px-4 py-3 hover:bg-blue-50 transition-colors border-b border-gray-50 last:border-0"
                  :class="selectedAgentId === agent.agent_id ? 'bg-blue-50' : ''"
                >
                  <div class="flex items-center justify-between">
                    <div class="flex-1 min-w-0">
                      <p class="text-sm font-medium text-gray-900 truncate">
                        {{ agent.name || agent.agent_id }}
                      </p>
                      <p class="text-xs text-gray-500 truncate mt-0.5">
                        {{ agent.description || '无描述' }}
                      </p>
                    </div>
                    <span v-if="selectedAgentId === agent.agent_id" class="ml-2 text-blue-600 text-sm">✓</span>
                  </div>
                </button>
              </div>
            </div>
          </div>
        </div>
        
        <div class="flex items-center gap-2">
           <button 
            v-if="chatStore.conversationId"
            @click="toggleWorkspace" 
            class="p-2.5 rounded-xl transition-all duration-200"
            :class="showWorkspacePanel ? 'bg-white shadow-sm text-blue-600' : 'text-gray-500 hover:bg-white/50 hover:text-gray-900'"
            title="文件列表"
          >
            <span class="text-lg">📂</span>
          </button>
          <button 
            @click="toggleRightSidebar" 
            class="p-2.5 rounded-xl transition-all duration-200" 
            :class="showRightSidebar ? 'bg-white shadow-sm text-blue-600' : 'text-gray-500 hover:bg-white/50 hover:text-gray-900'"
            title="任务看板"
          >
            <span class="text-lg">📋</span>
          </button>
        </div>
      </div>

      <!-- 消息列表区域 -->
      <div class="flex-1 overflow-y-auto scroll-smooth p-6 md:p-8" ref="messagesContainer">
        <!-- 欢迎页 -->
        <div v-if="messages.length === 0" class="h-full flex flex-col items-center justify-center text-center -mt-10">
          <div class="w-20 h-20 bg-white rounded-3xl shadow-xl flex items-center justify-center mb-8 transform hover:scale-105 transition-transform duration-300">
            <span class="text-5xl">✨</span>
          </div>
          <h1 class="text-3xl font-bold mb-4 text-gray-900">有什么我可以帮你的？</h1>
          <p class="text-gray-500 mb-10 max-w-md">我是你的 AI 助手，可以协助你完成编码、写作、分析等各种任务。</p>
          
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4 w-full max-w-3xl px-4">
            <div 
              class="p-5 rounded-2xl bg-white border border-gray-100 hover:border-blue-200 hover:shadow-lg cursor-pointer transition-all duration-300 group" 
              @click="setInput('帮我生成一个贪吃蛇游戏')"
            >
              <div class="text-2xl mb-3 group-hover:scale-110 transition-transform">🎮</div>
              <h3 class="font-semibold text-gray-800 mb-1">生成贪吃蛇游戏</h3>
              <p class="text-xs text-gray-400">使用 Python 或 JavaScript</p>
            </div>
            <div 
              class="p-5 rounded-2xl bg-white border border-gray-100 hover:border-blue-200 hover:shadow-lg cursor-pointer transition-all duration-300 group" 
              @click="setInput('分析一下 requirements.txt')"
            >
              <div class="text-2xl mb-3 group-hover:scale-110 transition-transform">📊</div>
              <h3 class="font-semibold text-gray-800 mb-1">分析项目依赖</h3>
              <p class="text-xs text-gray-400">检查版本冲突和安全问题</p>
            </div>
            <div 
              class="p-5 rounded-2xl bg-white border border-gray-100 hover:border-blue-200 hover:shadow-lg cursor-pointer transition-all duration-300 group" 
              @click="setInput('查询关于 RAG 的最新论文')"
            >
              <div class="text-2xl mb-3 group-hover:scale-110 transition-transform">🔍</div>
              <h3 class="font-semibold text-gray-800 mb-1">搜索 RAG 论文</h3>
              <p class="text-xs text-gray-400">获取最新的研究进展</p>
            </div>
          </div>
        </div>

        <!-- 消息流 -->
        <div v-else class="max-w-4xl mx-auto flex flex-col gap-8 pb-4">
          <div
            v-for="message in messages"
            :key="message.id"
            class="flex gap-5 group"
            :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
          >
            <div 
              class="w-10 h-10 rounded-xl flex items-center justify-center text-lg flex-shrink-0 mt-1 shadow-sm"
              :class="message.role === 'assistant' ? 'bg-white border border-gray-100' : 'order-2 hidden'"
            >
              {{ message.role === 'user' ? '👤' : '🤖' }}
            </div>
            
            <div 
              class="flex-1 min-w-0 max-w-[80%]"
              :class="message.role === 'user' ? 'order-1 flex justify-end' : ''"
            >
              <!-- 用户消息 -->
              <div v-if="message.role === 'user'" class="flex flex-col items-end gap-2">
                <!-- 📎 显示附件 -->
                <div v-if="message.files && message.files.length > 0" class="flex flex-col gap-2 mb-1">
                  <div 
                    v-for="(file, idx) in message.files" 
                    :key="idx" 
                    class="flex items-center gap-3 p-3 bg-white/80 rounded-xl border border-white/40 cursor-pointer hover:bg-white transition-colors shadow-sm"
                    @click="openAttachmentPreview(file)"
                  >
                    <span class="text-xl">{{ getFileTypeIcon(file) }}</span>
                    <div class="flex flex-col text-left">
                      <span class="text-sm font-medium text-gray-800 truncate max-w-[12rem]">{{ file.filename || file.name || '文件' }}</span>
                      <span class="text-xs text-gray-500">{{ getFileTypeLabel(file) }}</span>
                    </div>
                  </div>
                </div>
                <!-- 文字内容 -->
                <div v-if="message.content" class="bg-gray-900 text-white px-5 py-3.5 rounded-2xl rounded-tr-sm text-sm leading-relaxed shadow-lg shadow-gray-900/10 whitespace-pre-wrap">
                  {{ message.content }}
                </div>
              </div>
              
              <!-- 助手消息 -->
              <div v-else class="flex flex-col gap-3">
                <div class="bg-white/60 backdrop-blur-sm border border-white/40 px-6 py-5 rounded-2xl rounded-tl-sm shadow-sm text-sm leading-relaxed text-gray-800">
                  <MessageContent 
                    v-if="message.contentBlocks && message.contentBlocks.length > 0"
                    :content="message.contentBlocks"
                    :tool-statuses="message.toolStatuses || {}"
                    @mermaid-detected="handleMermaidDetected"
                  />
                  <template v-else>
                     <div v-if="message.thinking" class="mb-4 p-4 bg-gray-50/80 border border-gray-100 rounded-xl text-sm text-gray-500 italic">
                       {{ message.thinking }}
                     </div>
                     <MarkdownRenderer :content="message.content" @mermaid-detected="handleMermaidDetected" />
                  </template>
                </div>

                <!-- 推荐问题 -->
                <div v-if="message.recommendedQuestions?.length" class="flex flex-wrap gap-2 ml-1">
                  <button 
                    v-for="(q, idx) in message.recommendedQuestions" 
                    :key="idx" 
                    class="px-4 py-2 bg-white/50 border border-white/60 rounded-full text-xs text-gray-600 hover:text-gray-900 hover:bg-white hover:border-gray-200 transition-all shadow-sm"
                    @click="askRecommendedQuestion(q)"
                  >
                    {{ q }}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Loading -->
          <div v-if="isLoading && !isGenerating" class="flex gap-5">
             <div class="w-10 h-10 bg-white border border-gray-100 rounded-xl flex items-center justify-center text-lg shadow-sm">🤖</div>
             <div class="flex items-center h-10">
               <div class="typing-dots flex gap-1.5 p-3 bg-white/40 rounded-xl">
                 <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></span>
                 <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100"></span>
                 <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200"></span>
               </div>
             </div>
          </div>
        </div>
      </div>

      <!-- 输入框区域 -->
      <div class="px-6 pb-6 pt-2 bg-transparent pointer-events-none sticky bottom-0 z-30">
        <div class="pointer-events-auto max-w-4xl mx-auto bg-white/80 backdrop-blur-xl border border-white/40 rounded-3xl p-3 shadow-xl shadow-gray-200/50 transition-all duration-300 focus-within:shadow-2xl focus-within:border-blue-200 focus-within:ring-4 focus-within:ring-blue-500/5">
          <!-- 📎 已选文件预览 -->
          <div v-if="selectedFiles.length > 0" class="flex flex-wrap gap-2 px-2 pb-3 border-b border-gray-100 mb-2">
            <div 
              v-for="(file, index) in selectedFiles" 
              :key="index" 
              class="flex items-center gap-2 pl-3 pr-2 py-1.5 bg-gray-50 rounded-lg text-xs font-medium text-gray-700 border border-gray-100 group"
            >
              <span class="text-base">{{ getFileIcon(file) }}</span>
              <span class="max-w-[150px] truncate">{{ file.name }}</span>
              <button class="p-0.5 rounded-md hover:bg-gray-200 text-gray-400 hover:text-red-500 transition-colors" @click="removeFile(index)">×</button>
            </div>
          </div>
          
          <div class="flex items-end gap-2">
            <!-- 文件上传按钮 -->
            <button 
              class="p-3 rounded-xl text-gray-400 hover:bg-gray-100 hover:text-gray-900 transition-colors flex-shrink-0" 
              @click="triggerFileUpload"
              :disabled="isLoading || isUploading"
              title="上传文件"
            >
              <span v-if="isUploading" class="animate-spin block">⏳</span>
              <span v-else class="text-xl">📎</span>
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
              class="flex-1 max-h-[200px] py-3 bg-transparent border-none outline-none text-base text-gray-800 placeholder:text-gray-400 resize-none leading-relaxed"
            ></textarea>
            
            <div class="pb-1">
              <button 
                v-if="isLoading" 
                class="p-3 rounded-xl bg-red-50 text-red-500 hover:bg-red-100 transition-all shadow-sm" 
                @click="stopGeneration"
                :disabled="isStopping"
              >
                ⏹
              </button>
              <button 
                v-else 
                class="p-3 rounded-xl transition-all shadow-sm flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none" 
                :class="inputMessage.trim() || selectedFiles.length > 0 ? 'bg-gray-900 text-white hover:bg-gray-800 hover:shadow-lg' : 'bg-gray-100 text-gray-400 cursor-not-allowed'"
                @click="sendMessage"
                :disabled="!inputMessage.trim() && selectedFiles.length === 0"
              >
                <span class="text-lg">↑</span>
              </button>
            </div>
          </div>
        </div>
        <div class="text-center mt-2">
          <p class="text-[10px] text-gray-400">AI 可能生成错误信息，请核对重要事实。</p>
        </div>
      </div>
    </div>

    <!-- 右侧侧边栏：Plan & Mind -->
    <div 
      v-show="showRightSidebar"
      class="w-[380px] relative z-10 flex flex-col border-l border-white/20 bg-white/60 backdrop-blur-xl transition-all duration-300 shadow-xl md:shadow-none"
    >
      <div class="h-16 flex items-center justify-between px-5 border-b border-white/20">
        <div class="flex gap-1 p-1.5 bg-white/50 rounded-xl border border-white/40 shadow-sm">
          <button 
            class="px-4 py-1.5 rounded-lg text-xs font-medium transition-all" 
            :class="rightSidebarTab === 'plan' ? 'bg-gray-900 text-white shadow-md' : 'text-gray-500 hover:text-gray-900'"
            @click="rightSidebarTab = 'plan'"
          >
            📋 任务
          </button>
          <button 
            class="px-4 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5" 
            :class="rightSidebarTab === 'mind' ? 'bg-gray-900 text-white shadow-md' : 'text-gray-500 hover:text-gray-900'"
            @click="rightSidebarTab = 'mind'"
          >
            🧠 Mind
            <span v-if="mermaidCharts.length" class="px-1.5 py-0.5 rounded-full bg-white/20 text-white text-[10px] leading-none font-bold">{{ mermaidCharts.length }}</span>
          </button>
        </div>
        <button @click="showRightSidebar = false" class="p-2 rounded-xl text-gray-400 hover:bg-white hover:text-gray-900 transition-colors md:hidden">✕</button>
      </div>
      
      <div class="flex-1 overflow-y-auto p-5 scrollbar-thin">
        <!-- 任务看板 -->
        <template v-if="rightSidebarTab === 'plan'">
          <PlanWidget v-if="currentPlan" :plan="currentPlan" />
          <div v-else class="h-full flex flex-col items-center justify-center text-gray-400 opacity-60">
            <div class="w-16 h-16 bg-white rounded-2xl flex items-center justify-center mb-4 shadow-sm border border-gray-100">
              <span class="text-3xl">📋</span>
            </div>
            <p class="text-sm font-medium">暂无任务计划</p>
            <p class="text-xs mt-1">AI 生成计划后将显示在这里</p>
          </div>
        </template>
        
        <!-- Mind / Mermaid 图表 -->
        <template v-else-if="rightSidebarTab === 'mind'">
          <MermaidPanel v-if="mermaidCharts.length > 0" :charts="mermaidCharts" />
          <div v-else class="h-full flex flex-col items-center justify-center text-gray-400 opacity-60">
            <div class="w-16 h-16 bg-white rounded-2xl flex items-center justify-center mb-4 shadow-sm border border-gray-100">
              <span class="text-3xl">🧠</span>
            </div>
            <p class="text-sm font-medium">暂无思维导图</p>
            <p class="text-xs mt-1">AI 生成图表后将显示在这里</p>
          </div>
        </template>
      </div>
    </div>

    <!-- 工作区面板 -->
    <div v-if="showWorkspacePanel && chatStore.conversationId" class="absolute top-0 bottom-0 right-0 w-[800px] bg-white/90 backdrop-blur-2xl border-l border-white/20 z-40 flex flex-col shadow-2xl animate-in slide-in-from-right duration-300">
       <div class="h-16 flex items-center justify-between px-6 border-b border-gray-100 bg-white/50">
         <h3 class="font-bold text-gray-800 flex items-center gap-2">
           <span class="text-xl">📂</span> 项目文件
         </h3>
         <button @click="showWorkspacePanel = false" class="p-2 rounded-xl text-gray-400 hover:bg-red-50 hover:text-red-500 transition-colors">✕</button>
       </div>
       <div class="flex-1 flex overflow-hidden">
          <div class="w-[300px] min-w-[300px] border-r border-gray-100 bg-gray-50/50 overflow-y-auto">
             <FileExplorer 
                :conversation-id="chatStore.conversationId"
                @file-select="handleFilePreviewSelect"
                @run-project="handleRunProjectFromExplorer"
             />
          </div>
          <div v-if="previewFile" class="flex-1 flex flex-col bg-white overflow-hidden">
             <FilePreview
                :conversation-id="chatStore.conversationId"
                :file-path="previewFile.path"
                @close="previewFile = null"
             />
          </div>
          <div v-else class="flex-1 flex flex-col items-center justify-center text-gray-400 bg-white/50">
             <div class="w-20 h-20 bg-gray-50 rounded-2xl flex items-center justify-center mb-4">
               <span class="text-4xl opacity-50">📄</span>
             </div>
             <p class="text-sm font-medium">选择文件查看内容</p>
          </div>
       </div>
    </div>

    <!-- 附件预览模态框 -->
    <div v-if="previewingAttachment" class="fixed inset-0 bg-gray-900/60 backdrop-blur-md z-50 flex items-center justify-center p-6 animate-in fade-in duration-300" @click.self="closeAttachmentPreview">
      <div class="bg-white rounded-3xl shadow-2xl max-w-[90vw] max-h-[90vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-300 ring-1 ring-white/20">
        <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gray-50/50">
          <span class="font-semibold text-gray-800 truncate max-w-md">{{ previewingAttachment.filename || previewingAttachment.name }}</span>
          <button class="p-2 rounded-full text-gray-400 hover:bg-gray-200 hover:text-gray-900 transition-colors" @click="closeAttachmentPreview">✕</button>
        </div>
        <div class="p-8 flex items-center justify-center min-w-[400px] min-h-[300px] overflow-auto bg-gray-50/30">
          <!-- 图片预览 -->
          <img 
            v-if="isImageFile(previewingAttachment)" 
            :src="previewingAttachment.preview_url || getFilePreviewUrl(previewingAttachment)"
            :alt="previewingAttachment.filename"
            class="max-w-full max-h-[75vh] object-contain rounded-xl shadow-lg border border-gray-100"
            @error="handlePreviewError"
          />
          <!-- 其他文件 -->
          <div v-else class="text-center py-12">
            <div class="w-24 h-24 bg-gray-100 rounded-3xl flex items-center justify-center mx-auto mb-6">
              <span class="text-6xl">{{ getFileTypeIcon(previewingAttachment) }}</span>
            </div>
            <p class="text-xl font-bold text-gray-900 mb-2">{{ previewingAttachment.filename || previewingAttachment.name }}</p>
            <p class="text-sm text-gray-500 mb-8">{{ getFileTypeLabel(previewingAttachment) }} · {{ formatFileSize(previewingAttachment.file_size) }}</p>
            <a 
              :href="getFilePreviewUrl(previewingAttachment)" 
              target="_blank" 
              class="inline-flex items-center justify-center px-8 py-3 bg-gray-900 text-white rounded-xl font-medium hover:bg-gray-800 transition-all shadow-lg hover:shadow-gray-900/20"
            >
              📥 下载 / 打开
            </a>
          </div>
        </div>
      </div>
    </div>

    <!-- HITL 人类确认模态框 -->
    <div v-if="showConfirmModal" class="fixed inset-0 bg-gray-900/60 backdrop-blur-md z-50 flex items-center justify-center p-6 animate-in fade-in duration-300" @click.self="cancelHumanConfirmation">
      <div class="bg-white rounded-3xl shadow-2xl w-full max-w-lg overflow-hidden animate-in slide-in-from-bottom-8 duration-300 ring-1 ring-white/20">
        <div class="flex items-center justify-between px-8 py-5 border-b border-gray-100 bg-gray-50/50">
          <span class="text-lg font-bold text-gray-900 flex items-center gap-2">
            <span class="text-2xl">🤝</span> 需要您的确认
          </span>
          <button class="p-2 rounded-full text-gray-400 hover:bg-gray-200 hover:text-gray-900 transition-colors" @click="cancelHumanConfirmation">✕</button>
        </div>
        
        <div class="p-8 space-y-6">
          <!-- 问题内容 -->
          <div class="text-lg text-gray-800 font-medium leading-relaxed whitespace-pre-wrap">{{ confirmRequest?.question }}</div>
          
          <!-- 描述（如果有） -->
          <div v-if="confirmRequest?.description" class="text-sm text-gray-600 bg-blue-50 p-4 rounded-xl border border-blue-100 leading-relaxed">
            {{ confirmRequest.description }}
          </div>
          
          <!-- yes_no / single_choice 类型 -->
          <div v-if="['yes_no', 'single_choice'].includes(confirmRequest?.confirmation_type)" class="flex flex-col gap-3">
            <label 
              v-for="option in confirmRequest?.options" 
              :key="option" 
              class="flex items-center p-4 rounded-xl border-2 cursor-pointer transition-all hover:bg-gray-50"
              :class="confirmResponse === option ? 'border-blue-500 bg-blue-50/50 ring-1 ring-blue-500/20' : 'border-gray-100'"
            >
              <input 
                type="radio" 
                :value="option" 
                v-model="confirmResponse"
                name="hitl-option"
                class="mr-4 accent-blue-600 w-5 h-5"
              />
              <span class="text-base font-medium text-gray-800">{{ option === 'confirm' ? '✅ 确认' : option === 'cancel' ? '❌ 取消' : option }}</span>
            </label>
          </div>
          
          <!-- multiple_choice 类型 -->
          <div v-if="confirmRequest?.confirmation_type === 'multiple_choice'" class="flex flex-col gap-3">
            <label 
              v-for="option in confirmRequest?.options" 
              :key="option" 
              class="flex items-center p-4 rounded-xl border-2 cursor-pointer transition-all hover:bg-gray-50"
              :class="confirmResponse?.includes(option) ? 'border-blue-500 bg-blue-50/50 ring-1 ring-blue-500/20' : 'border-gray-100'"
            >
              <input 
                type="checkbox" 
                :value="option" 
                v-model="confirmResponse"
                class="mr-4 accent-blue-600 w-5 h-5 rounded"
              />
              <span class="text-base font-medium text-gray-800">{{ option }}</span>
            </label>
          </div>
          
          <!-- text_input 类型 -->
          <div v-if="confirmRequest?.confirmation_type === 'text_input'" class="w-full">
            <textarea 
              v-model="confirmResponse" 
              placeholder="请输入您的回复..."
              rows="4"
              class="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all resize-none text-gray-800"
            ></textarea>
          </div>
          
          <!-- form 类型（复杂表单） -->
          <div v-if="confirmRequest?.confirmation_type === 'form'" class="space-y-5">
            <div v-for="question in confirmRequest?.questions" :key="question.id" class="space-y-2">
              <!-- 问题标签 -->
              <label class="block text-sm font-medium text-gray-700">
                {{ question.label }}
                <span v-if="question.required !== false" class="text-red-500">*</span>
              </label>
              
              <!-- 提示文字 -->
              <div v-if="question.hint" class="text-xs text-gray-500 mb-2">{{ question.hint }}</div>
              
              <!-- 单选题 -->
              <div v-if="question.type === 'single_choice'" class="flex flex-col gap-2">
                <label 
                  v-for="option in question.options" 
                  :key="option" 
                  class="flex items-center p-3 rounded-lg border cursor-pointer transition-all hover:bg-gray-50"
                  :class="confirmResponse[question.id] === option ? 'border-blue-500 bg-blue-50/50' : 'border-gray-200'"
                >
                  <input 
                    type="radio" 
                    :value="option" 
                    v-model="confirmResponse[question.id]"
                    :name="`form-${question.id}`"
                    class="mr-3 accent-blue-600"
                  />
                  <span class="text-sm text-gray-800">{{ option }}</span>
                </label>
              </div>
              
              <!-- 多选题 -->
              <div v-if="question.type === 'multiple_choice'" class="flex flex-col gap-2">
                <label 
                  v-for="option in question.options" 
                  :key="option" 
                  class="flex items-center p-3 rounded-lg border cursor-pointer transition-all hover:bg-gray-50"
                  :class="confirmResponse[question.id]?.includes(option) ? 'border-blue-500 bg-blue-50/50' : 'border-gray-200'"
                >
                  <input 
                    type="checkbox" 
                    :value="option" 
                    v-model="confirmResponse[question.id]"
                    class="mr-3 accent-blue-600 rounded"
                  />
                  <span class="text-sm text-gray-800">{{ option }}</span>
                </label>
              </div>
              
              <!-- 文本输入 -->
              <div v-if="question.type === 'text_input'">
                <input 
                  v-model="confirmResponse[question.id]" 
                  :placeholder="question.hint || '请输入...'"
                  class="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all text-sm text-gray-800"
                />
              </div>
            </div>
          </div>
        </div>
        
        <div class="flex items-center justify-end gap-4 px-8 py-5 bg-gray-50/50 border-t border-gray-100">
          <button class="px-6 py-2.5 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-200 transition-colors" @click="cancelHumanConfirmation" :disabled="confirmSubmitting">
            取消
          </button>
          <button class="px-6 py-2.5 rounded-xl text-sm font-medium bg-gray-900 text-white hover:bg-gray-800 transition-all shadow-lg shadow-gray-900/10 transform active:scale-95 disabled:opacity-50" @click="submitHumanConfirmation" :disabled="confirmSubmitting">
            {{ confirmSubmitting ? '提交中...' : '提交' }}
          </button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
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

// --- Agent 选择状态 ---
const agents = ref([])                  // Agent 列表
const loadingAgents = ref(false)        // 是否正在加载 Agent
const showAgentSelector = ref(false)    // 是否显示 Agent 选择器
const selectedAgentId = ref(null)       // 当前选择的 Agent ID
const currentAgentName = ref(null)      // 当前 Agent 名称

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
  await Promise.all([
    loadConversationList(),
    loadAgentList()  // 加载 Agent 列表
  ])
  
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

// 监听全局点击事件，关闭 Agent 选择器（点击外部时）
watch(showAgentSelector, (newVal) => {
  if (newVal) {
    // 延迟添加监听器，避免立即触发
    setTimeout(() => {
      const closeDropdown = (e) => {
        // 检查点击是否在下拉菜单或按钮外部
        const dropdown = document.querySelector('.absolute.top-full')
        const button = e.target.closest('button')
        
        if (dropdown && !dropdown.contains(e.target) && !button) {
          showAgentSelector.value = false
          document.removeEventListener('click', closeDropdown)
        }
      }
      document.addEventListener('click', closeDropdown)
    }, 100)
  }
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

// ==================== Agent 管理相关方法 ====================

/**
 * 加载 Agent 列表
 */
async function loadAgentList() {
  loadingAgents.value = true
  try {
    const response = await fetch('/api/v1/agents')
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    
    const result = await response.json()
    console.log('📦 Agent API 响应:', result)
    
    // 🔧 修复：后端返回格式是 { total, agents }，不是 { data: { agents } }
    const agentsList = result.agents || []
    
    // 🆕 添加默认 Agent (base_agent) 到列表开头
    agents.value = [
      {
        agent_id: null,  // null 表示使用后端默认的 base_agent
        name: '默认智能体',
        description: '通用对话助手 (base_agent)',
        is_active: true,
        version: '1.0.0'
      },
      ...agentsList
    ]
    
    // 默认选择第一个（默认 Agent）
    if (!selectedAgentId.value) {
      selectAgent(agents.value[0], false)  // 静默选择，不触发对话
    }
    
    console.log('✅ Agent 列表已加载:', agents.value.length, '个')
  } catch (error) {
    console.error('❌ 加载 Agent 列表失败:', error)
    // 失败时至少显示默认 Agent
    agents.value = [
      {
        agent_id: null,
        name: '默认智能体',
        description: '通用对话助手 (base_agent)',
        is_active: true,
        version: '1.0.0'
      }
    ]
    selectAgent(agents.value[0], false)
  } finally {
    loadingAgents.value = false
  }
}

/**
 * 选择 Agent
 */
function selectAgent(agent, closeDropdown = true) {
  // 🔧 agent_id 为 null 表示使用默认 base_agent（后端不传 agent_id）
  selectedAgentId.value = agent.agent_id
  currentAgentName.value = agent.name || agent.agent_id || '默认智能体'
  
  if (closeDropdown) {
    showAgentSelector.value = false
  }
  
  console.log('🤖 已选择 Agent:', {
    id: agent.agent_id || 'base_agent (默认)',
    name: agent.name,
    model: agent.model
  })
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
    // 构建请求选项
    const options = { 
      files: filesParam,
      backgroundTasks: ['title_generation', 'recommended_questions'],
      // 🆕 前端上下文变量，直接注入到 Agent 的 System Prompt
      variables: {
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        locale: navigator.language,
        timestamp: new Date().toISOString()
      }
    }
    
    // 🔧 只有选择了非默认 Agent（agent_id 不为 null）时才传递 agentId
    // null 表示使用后端默认的 base_agent
    if (selectedAgentId.value !== null) {
      options.agentId = selectedAgentId.value
    }
    
    await chatStore.sendMessageStream(
      content,
      chatStore.conversationId,
      (event) => handleStreamEvent(event, reactiveMsg),
      options
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
  showConfirmModal.value = true
  
  // 根据类型初始化 confirmResponse
  if (data.confirmation_type === 'yes_no' && data.options?.length > 0) {
    // yes_no 类型：默认选中第一个选项
    confirmResponse.value = data.options[0]
  } else if (data.confirmation_type === 'multiple_choice') {
    // multiple_choice 类型：初始化为数组（支持默认值）
    confirmResponse.value = data.metadata?.default_value || []
  } else if (data.confirmation_type === 'form') {
    // form 类型：初始化为对象，设置默认值
    const formData = {}
    if (data.questions) {
      data.questions.forEach(q => {
        formData[q.id] = q.default !== undefined ? q.default : (q.type === 'multiple_choice' ? [] : '')
      })
    }
    confirmResponse.value = formData
  } else {
    confirmResponse.value = null
  }
}

/**
 * 提交人类确认响应
 */
async function submitHumanConfirmation() {
  if (!confirmRequest.value || confirmSubmitting.value) return
  
  const requestId = confirmRequest.value.request_id
  let response = confirmResponse.value
  
  // 验证必填项
  if (!response && confirmRequest.value.confirmation_type !== 'text_input') {
    alert('请选择一个选项')
    return
  }
  
  // form 类型：将对象序列化为 JSON 字符串
  if (confirmRequest.value.confirmation_type === 'form' && typeof response === 'object') {
    response = JSON.stringify(response)
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
/* 滚动条美化 */
.scrollbar-thin::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-thin::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.3);
  border-radius: 3px;
}
.scrollbar-thin::-webkit-scrollbar-thumb:hover {
  background-color: rgba(156, 163, 175, 0.5);
}

/* Loading Dots 动画 */
.typing-dots span {
  animation: blink 1.4s infinite both;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes blink {
  0% { opacity: 0.2; }
  20% { opacity: 1; }
  100% { opacity: 0.2; }
}

@keyframes blob {
  0% { transform: translate(0px, 0px) scale(1); }
  33% { transform: translate(30px, -50px) scale(1.1); }
  66% { transform: translate(-20px, 20px) scale(0.9); }
  100% { transform: translate(0px, 0px) scale(1); }
}
.animate-blob {
  animation: blob 15s infinite;
}
.animation-delay-2000 {
  animation-delay: 2s;
}
.animation-delay-4000 {
  animation-delay: 4s;
}

/* 消息内容中的 Markdown 样式修正 */
:deep(.prose) {
  max-width: none;
}
:deep(.prose pre) {
  background-color: #f3f4f6;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
}
</style>
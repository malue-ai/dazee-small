<template>
  <div class="h-screen w-full flex bg-background text-foreground font-sans overflow-hidden">
    <!-- ==================== 左侧：聊天引导面板 ==================== -->
    <div class="w-1/2 flex flex-col border-r border-border">
      <!-- 顶部导航 -->
      <div class="h-14 flex items-center gap-3 px-5 border-b border-border flex-shrink-0">
        <button 
          @click="handleBack" 
          class="p-1.5 rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        >
          <ArrowLeft class="w-4 h-4" />
        </button>
        <span class="text-sm font-semibold text-foreground">{{ isEditMode ? '编辑项目' : '新建项目' }}</span>
      </div>

      <!-- 消息列表 -->
      <div ref="messageListRef" class="flex-1 overflow-y-auto scrollbar-thin px-6 py-6 space-y-4">
        <div
          v-for="(msg, index) in messages"
          :key="index"
          class="flex"
          :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
        >
          <!-- AI 消息 -->
          <div
            v-if="msg.role === 'assistant'"
            class="max-w-[85%] text-sm text-foreground leading-relaxed"
          >
            <p class="whitespace-pre-wrap">{{ msg.content }}</p>
          </div>

          <!-- 用户消息 -->
          <div
            v-else
            class="max-w-[85%] px-4 py-2.5 bg-accent text-accent-foreground rounded-2xl rounded-br-md text-sm leading-relaxed"
          >
            <p class="whitespace-pre-wrap">{{ msg.content }}</p>
          </div>
        </div>

        <!-- 加载指示器 -->
        <div v-if="isThinking" class="flex justify-start">
          <div class="flex items-center gap-1.5 text-muted-foreground">
            <span class="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce" style="animation-delay: 0ms"></span>
            <span class="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce" style="animation-delay: 150ms"></span>
            <span class="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce" style="animation-delay: 300ms"></span>
          </div>
        </div>
      </div>

      <!-- 底部输入框 -->
      <div class="px-5 pb-5 pt-2 flex-shrink-0">
        <div class="bg-card border border-border rounded-2xl p-3 shadow-sm transition-all duration-300 focus-within:shadow-lg focus-within:border-primary/30">
          <div class="flex items-end gap-2">
            <button 
              class="p-2.5 rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground transition-colors flex-shrink-0"
              title="上传文件"
            >
              <Paperclip class="w-5 h-5" />
            </button>

            <textarea
              ref="inputRef"
              v-model="inputText"
              @keydown.enter.exact="handleSendMessage"
              @compositionstart="isComposing = true"
              @compositionend="isComposing = false"
              @input="adjustInputHeight"
              placeholder="告诉我你需要什么项目"
              :disabled="isTypewriting"
              rows="1"
              class="flex-1 max-h-[120px] py-2.5 bg-transparent border-none outline-none text-sm text-foreground placeholder:text-muted-foreground/50 resize-none leading-relaxed"
            ></textarea>

            <button 
              ref="sendBtnRef"
              class="p-2.5 rounded-xl transition-all shadow-sm flex items-center justify-center"
              :class="canSend ? 'bg-primary text-white hover:bg-primary-hover shadow-primary/20' : 'bg-muted text-muted-foreground/40 cursor-not-allowed'"
              :disabled="!canSend"
              @click="handleSendMessage"
            >
              <Loader2 v-if="isGenerating" class="w-5 h-5 animate-spin" />
              <ArrowUp v-else class="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ==================== 右侧：项目配置面板 ==================== -->
    <div class="w-1/2 flex flex-col bg-muted/30">
      <!-- 顶部预览卡 + 操作按钮 -->
      <div class="h-14 flex items-center justify-between px-6 border-b border-border flex-shrink-0">
        <div class="flex items-center gap-3">
          <!-- 项目图标 -->
          <div class="w-9 h-9 rounded-xl bg-muted flex items-center justify-center text-base font-bold text-foreground border border-border overflow-hidden">
            <img v-if="iconPreviewUrl" :src="iconPreviewUrl" alt="" class="w-full h-full object-cover" />
            <span v-else>{{ projectIcon }}</span>
          </div>
          <div class="flex flex-col">
            <span class="text-sm font-semibold text-foreground leading-tight">{{ form.name || 'My project' }}</span>
            <span class="text-[11px] text-muted-foreground leading-tight">{{ isEditMode ? 'Editing' : 'Draft' }}</span>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <!-- 标签切换 -->
          <div class="flex gap-1 p-1 bg-muted rounded-lg">
            <button 
              class="px-3 py-1.5 rounded-md text-xs font-medium transition-all"
              :class="activeTab === 'preview' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'"
              @click="activeTab = 'preview'"
            >
              预览
            </button>
            <button 
              class="px-3 py-1.5 rounded-md text-xs font-medium transition-all"
              :class="activeTab === 'config' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'"
              @click="activeTab = 'config'"
            >
              配置
            </button>
          </div>

          <!-- 创建/保存按钮 -->
          <button 
            ref="createBtnRef"
            class="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium transition-all shadow-sm"
            :class="canCreate && !isCreating
              ? 'bg-primary text-white hover:bg-primary-hover shadow-primary/20' 
              : 'bg-muted text-muted-foreground cursor-not-allowed'"
            :disabled="!canCreate || isCreating"
            @click="isEditMode ? handleSave() : handleCreate()"
          >
            <Loader2 v-if="isCreating" class="w-4 h-4 animate-spin" />
            <Save v-else-if="isEditMode" class="w-4 h-4" />
            <Plus v-else class="w-4 h-4" />
            {{ isCreating ? (isEditMode ? '保存中...' : '创建中...') : (isEditMode ? '保存' : '创建') }}
          </button>
        </div>
      </div>

      <!-- 错误提示 -->
      <Transition name="toast">
        <div 
          v-if="errorMessage" 
          class="mx-6 mt-3 flex items-center gap-2.5 px-4 py-3 rounded-xl bg-destructive/10 border border-destructive/20 text-sm text-destructive"
        >
          <AlertCircle class="w-4 h-4 flex-shrink-0" />
          <span class="flex-1">{{ errorMessage }}</span>
          <button 
            @click="errorMessage = ''" 
            class="p-0.5 rounded hover:bg-destructive/10 transition-colors flex-shrink-0"
          >
            <X class="w-3.5 h-3.5" />
          </button>
        </div>
      </Transition>

      <!-- 配置内容区域 -->
      <div ref="configAreaRef" class="flex-1 overflow-y-auto scrollbar-thin p-6">
        <!-- 配置标签 -->
        <div v-if="activeTab === 'config'" class="max-w-lg mx-auto space-y-6">
          <!-- 图标 -->
          <div class="space-y-2">
            <label class="text-sm font-medium text-foreground">图标</label>
            <div class="flex items-end gap-3">
              <div 
                class="relative w-16 h-16 rounded-2xl bg-muted flex items-center justify-center border border-border cursor-pointer hover:border-primary/40 transition-colors group overflow-hidden"
                @click="triggerIconUpload"
              >
                <!-- 已上传图片 -->
                <img 
                  v-if="iconPreviewUrl" 
                  :src="iconPreviewUrl" 
                  alt="项目图标" 
                  class="w-full h-full object-cover"
                />
                <!-- 默认：名称首字母 -->
                <span v-else class="text-2xl font-bold text-foreground">{{ projectIcon }}</span>
                <!-- 悬浮遮罩 -->
                <div class="absolute inset-0 bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity rounded-2xl">
                  <Upload class="w-5 h-5 text-white" />
                </div>
              </div>
              <!-- 删除按钮 -->
              <button 
                v-if="iconPreviewUrl"
                @click="removeIcon"
                class="p-1.5 rounded-lg text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                title="移除图标"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
            <!-- 隐藏的文件选择器 -->
            <input 
              ref="iconInputRef"
              type="file"
              accept="image/*"
              class="hidden"
              @change="handleIconUpload"
            />
          </div>

          <!-- 名称 -->
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <label class="text-sm font-medium text-foreground">
                名称 <span class="text-destructive">*</span>
              </label>
              <span class="text-xs text-muted-foreground">{{ form.name.length }} / 50</span>
            </div>
            <input 
              v-model="form.name"
              type="text"
              maxlength="50"
              placeholder="为你的项目命名"
              class="w-full px-4 py-3 text-sm bg-card border border-border rounded-xl focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40 text-foreground placeholder:text-muted-foreground/50 transition-colors"
            />
          </div>

          <!-- 描述 -->
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <label class="text-sm font-medium text-foreground">
                描述 <span class="text-destructive">*</span>
              </label>
              <span class="text-xs text-muted-foreground">{{ form.description.length }} / 500</span>
            </div>
            <textarea
              v-model="form.description"
              maxlength="500"
              rows="4"
              placeholder="简单描述这个项目的用途"
              class="w-full px-4 py-3 text-sm bg-card border border-border rounded-xl focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40 text-foreground placeholder:text-muted-foreground/50 resize-none transition-colors"
            ></textarea>
          </div>

          <!-- 指令 -->
          <div class="space-y-2">
            <label class="text-sm font-medium text-foreground">指令</label>
            <textarea
              v-model="form.instructions"
              rows="6"
              placeholder="提供关于该项目行为方式的详细指令"
              class="w-full px-4 py-3 text-sm bg-card border border-border rounded-xl focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40 text-foreground placeholder:text-muted-foreground/50 resize-none transition-colors"
            ></textarea>
          </div>

          <!-- AI 模型 -->
          <div class="space-y-2">
            <label class="text-sm font-medium text-foreground">AI 模型</label>
            <div class="relative" ref="modelDropdownRef">
              <!-- 触发按钮 -->
              <button
                type="button"
                @click="toggleModelDropdown"
                :disabled="modelsLoading || availableModels.length === 0"
                class="w-full flex items-center justify-between px-4 py-3 text-sm bg-card border rounded-xl transition-colors text-left disabled:opacity-50 disabled:cursor-not-allowed"
                :class="modelDropdownOpen
                  ? 'border-primary/40 ring-1 ring-primary/40'
                  : 'border-border hover:border-muted-foreground/30'"
              >
                <span v-if="modelsLoading" class="text-muted-foreground/50 flex items-center gap-2">
                  <Loader2 class="w-3.5 h-3.5 animate-spin" />
                  加载中...
                </span>
                <span v-else-if="availableModels.length === 0" class="text-muted-foreground/50">无可用模型</span>
                <span v-else-if="selectedModelDisplay" class="text-foreground truncate">{{ selectedModelDisplay }}</span>
                <span v-else class="text-muted-foreground/50">选择模型</span>
                <ChevronDown
                  class="w-4 h-4 text-muted-foreground flex-shrink-0 transition-transform duration-200"
                  :class="{ 'rotate-180': modelDropdownOpen }"
                />
              </button>

              <!-- 下拉面板 -->
              <Transition
                enter-active-class="transition duration-150 ease-out"
                enter-from-class="opacity-0 -translate-y-1"
                enter-to-class="opacity-100 translate-y-0"
                leave-active-class="transition duration-100 ease-in"
                leave-from-class="opacity-100 translate-y-0"
                leave-to-class="opacity-0 -translate-y-1"
              >
                <div
                  v-if="modelDropdownOpen && availableModels.length > 0"
                  class="absolute z-50 mt-1.5 w-full bg-card border border-border rounded-xl shadow-lg overflow-hidden"
                >
                  <div class="max-h-[240px] overflow-y-auto scrollbar-thin py-1">
                    <button
                      v-for="m in availableModels"
                      :key="m.model_name"
                      type="button"
                      @click="selectModel(m.model_name)"
                      class="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left transition-colors"
                      :class="form.model === m.model_name
                        ? 'bg-primary/8 text-primary'
                        : 'text-foreground hover:bg-muted'"
                    >
                      <div class="flex-1 min-w-0">
                        <div class="truncate font-medium">{{ m.display_name }}</div>
                        <div class="text-xs text-muted-foreground truncate mt-0.5">{{ m.provider }}</div>
                      </div>
                      <svg v-if="form.model === m.model_name" class="w-4 h-4 text-primary flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    </button>
                  </div>
                </div>
              </Transition>
            </div>
            <p v-if="!modelsLoading && availableModels.length === 0" class="text-xs text-destructive">
              请先在设置页面配置 API Key 以激活模型
            </p>
          </div>

          <!-- 存储路径 -->
          <div class="space-y-2">
            <div class="flex items-center gap-2">
              <label class="text-sm font-medium text-foreground">存储路径</label>
              <span class="text-xs text-muted-foreground">（可选）</span>
            </div>
            <div class="flex items-center gap-2">
              <div
                class="relative flex-1 cursor-pointer"
                @click="openFolderPicker"
              >
                <FolderOpen class="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/50 pointer-events-none" />
                <input
                  :value="form.dataDir"
                  type="text"
                  readonly
                  placeholder="点击选择文件夹"
                  class="w-full pl-10 pr-4 py-3 text-sm bg-card border border-border rounded-xl cursor-pointer text-foreground placeholder:text-muted-foreground/50 transition-colors hover:border-primary/40 focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40"
                />
              </div>
              <button
                v-if="form.dataDir"
                type="button"
                @click="form.dataDir = ''"
                class="p-2.5 rounded-xl text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors flex-shrink-0"
                title="清除自定义路径"
              >
                <X class="w-4 h-4" />
              </button>
            </div>
            <p class="text-xs text-muted-foreground">
              自定义项目文件的存储位置。留空则自动存储到默认路径。
            </p>
          </div>
        </div>

        <!-- 预览标签 -->
        <div v-else class="max-w-lg mx-auto">
          <div class="bg-card rounded-2xl border border-border shadow-sm p-8 space-y-6">
            <!-- 图标 + 名称 -->
            <div class="flex flex-col items-center gap-4">
              <div class="w-20 h-20 rounded-2xl bg-muted flex items-center justify-center text-3xl font-bold text-foreground border border-border overflow-hidden">
                <img v-if="iconPreviewUrl" :src="iconPreviewUrl" alt="" class="w-full h-full object-cover" />
                <span v-else>{{ projectIcon }}</span>
              </div>
              <div class="text-center">
                <h2 class="text-lg font-semibold text-foreground">{{ form.name || '未命名项目' }}</h2>
                <span class="inline-block mt-1 px-2 py-0.5 rounded text-[10px] font-medium bg-muted text-muted-foreground">Draft</span>
              </div>
            </div>

            <!-- 描述 -->
            <div v-if="form.description" class="space-y-1.5">
              <h3 class="text-xs font-medium text-muted-foreground uppercase tracking-wider">描述</h3>
              <p class="text-sm text-foreground leading-relaxed whitespace-pre-wrap">{{ form.description }}</p>
            </div>
            <div v-else class="text-center py-4">
              <p class="text-sm text-muted-foreground/50">暂未填写描述</p>
            </div>

            <!-- 指令 -->
            <div v-if="form.instructions" class="space-y-1.5">
              <h3 class="text-xs font-medium text-muted-foreground uppercase tracking-wider">指令</h3>
              <div class="px-4 py-3 bg-muted/50 rounded-xl">
                <p class="text-sm text-foreground leading-relaxed whitespace-pre-wrap">{{ form.instructions }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 返回确认弹窗 -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition duration-150 ease-in"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div v-if="showBackConfirm" class="fixed inset-0 z-[9999] flex items-center justify-center">
          <!-- 背景遮罩 -->
          <div class="absolute inset-0 bg-black/40" @click="showBackConfirm = false" />
          <!-- 弹窗 -->
          <div class="relative bg-card rounded-2xl shadow-xl border border-border p-6 w-[360px] space-y-4">
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 rounded-xl flex items-center justify-center"
                :class="isCreating ? 'bg-primary/10' : 'bg-amber-500/10'"
              >
                <Loader2 v-if="isCreating" class="w-5 h-5 text-primary animate-spin" />
                <AlertCircle v-else class="w-5 h-5 text-amber-500" />
              </div>
              <h3 class="text-base font-semibold text-foreground">
                {{ isCreating ? '项目正在创建中' : '确认离开？' }}
              </h3>
            </div>
            <p class="text-sm text-muted-foreground leading-relaxed">
              {{ isCreating
                ? '项目仍在后台创建中，离开后创建不会中断。你可以稍后在项目列表中查看。'
                : (isEditMode ? '你有未保存的修改，离开后更改将丢失。' : '项目尚未创建，离开后当前内容将丢失。')
              }}
            </p>
            <div class="flex justify-end gap-2 pt-1">
              <button
                class="px-4 py-2 text-sm font-medium rounded-xl text-muted-foreground hover:bg-muted transition-colors"
                @click="showBackConfirm = false"
              >
                {{ isCreating ? '继续等待' : '继续编辑' }}
              </button>
              <button
                class="px-4 py-2 text-sm font-medium rounded-xl transition-colors"
                :class="isCreating
                  ? 'bg-primary/10 text-primary hover:bg-primary/20'
                  : 'bg-destructive/10 text-destructive hover:bg-destructive/20'"
                @click="doBack"
              >
                {{ isCreating ? '返回列表' : '确认离开' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ArrowLeft, ArrowUp, Paperclip, Plus, Loader2, AlertCircle, X, Upload, Trash2, ChevronDown, Save, FolderOpen } from 'lucide-vue-next'
import { useAgentStore } from '@/stores/agent'
import { useAgentCreationStore } from '@/stores/agentCreation'
import { useGuideStore } from '@/stores/guide'
import { useWebSocketChat } from '@/composables/useWebSocketChat'
import { modelApi, type ModelInfo } from '@/api/models'
import { getAgentDetail } from '@/api/agent'
import { runCommand, isTauriEnv } from '@/api/tauri'
import api from '@/api/index'
import type { ChatRequest } from '@/types'

// ==================== 路由 & Store & WebSocket ====================

const router = useRouter()
const route = useRoute()
const agentStore = useAgentStore()
const agentCreationStore = useAgentCreationStore()
const guideStore = useGuideStore()
const ws = useWebSocketChat()

// ==================== 编辑模式 ====================

/** 是否为编辑模式 */
const isEditMode = computed(() => route.name === 'edit-project')

/** 编辑的 Agent ID */
const editAgentId = computed(() => (route.params.agentId as string) || '')

/** 编辑模式数据加载中 */
const editLoading = ref(false)

// ==================== 常量 ====================

/** 引导 Prompt 前缀（仅首条消息拼接） */
const GUIDE_PROMPT = `[系统上下文] 用户正在创建一个新的 AI 项目（Agent）。请根据用户的描述，帮助他们完善以下信息：
1. 项目名称（简短有力）
2. 项目描述（一两句话说清用途）
3. 项目指令/提示词（详细的行为指导）

请用自然语言回复用户，在回复末尾用以下 JSON 格式输出建议（用 \`\`\`json 代码块包裹）：
\`\`\`json
{"name": "项目名称", "description": "项目描述", "instructions": "详细指令"}
\`\`\`

用户说：`

// ==================== 类型 ====================

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

// ==================== 聊天状态 ====================

const messages = ref<ChatMessage[]>([])

const inputText = ref('')
const inputRef = ref<HTMLTextAreaElement | null>(null)
const messageListRef = ref<HTMLDivElement | null>(null)
const isComposing = ref(false)
const isThinking = ref(false)

/** 是否正在流式生成中 */
const isGenerating = ref(false)

/** 当前会话 ID（由后端在第一条消息时创建） */
const conversationId = ref<string | null>(null)

/** 是否为第一条用户消息（用于拼接引导 prompt） */
const isFirstMessage = ref(true)

/** 当前正在生成的助手消息引用（用于流式追加） */
let currentAssistantMsg: ChatMessage | null = null

// ==================== 表单状态 ====================

const form = reactive({
  icon: '',
  name: '',
  description: '',
  instructions: '',
  model: '',
  dataDir: ''
})

// ==================== 文件夹选择 ====================

/** 调用系统原生文件夹选择对话框 */
async function openFolderPicker() {
  if (!isTauriEnv()) {
    // 非 Tauri 环境（浏览器开发时）回退为手动输入
    const path = prompt('请输入文件夹路径：')
    if (path) form.dataDir = path
    return
  }

  try {
    // 检测平台，调用对应的系统文件夹选择器
    const isWin = navigator.userAgent.includes('Windows') || navigator.platform.startsWith('Win')

    let result
    if (isWin) {
      // Windows：使用 PowerShell 弹出 FolderBrowserDialog
      result = await runCommand([
        'powershell', '-NoProfile', '-Command',
        `Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description = '选择项目存储路径'; $d.ShowNewFolderButton = $true; if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }`
      ], { timeout_ms: 120000 })
    } else {
      // macOS / Linux：使用 osascript / zenity
      const isMac = navigator.userAgent.includes('Mac')
      if (isMac) {
        result = await runCommand([
          'osascript', '-e',
          'set theFolder to choose folder with prompt "选择项目存储路径"\nreturn POSIX path of theFolder'
        ], { timeout_ms: 120000 })
      } else {
        result = await runCommand([
          'zenity', '--file-selection', '--directory', '--title=选择项目存储路径'
        ], { timeout_ms: 120000 })
      }
    }

    if (result.success && result.stdout.trim()) {
      form.dataDir = result.stdout.trim()
    }
  } catch (e) {
    console.error('打开文件夹选择器失败:', e)
  }
}

// ==================== 模型选择 ====================

/** 已激活的模型列表 */
const availableModels = ref<ModelInfo[]>([])

/** 模型加载中 */
const modelsLoading = ref(false)

/** 加载已激活模型 */
async function loadModels() {
  modelsLoading.value = true
  try {
    const { data } = await modelApi.listModels()
    availableModels.value = data
    // Default to first model if none selected
    if (!form.model && data.length > 0) {
      form.model = data[0].model_name
    }
  } catch (e) {
    console.error('加载模型列表失败:', e)
  } finally {
    modelsLoading.value = false
  }
}

// ==================== 模型下拉框 ====================

const modelDropdownRef = ref<HTMLElement | null>(null)
const modelDropdownOpen = ref(false)

/** 当前选中模型的显示名称 */
const selectedModelDisplay = computed(() => {
  if (!form.model) return ''
  const m = availableModels.value.find(item => item.model_name === form.model)
  return m ? `${m.display_name} (${m.provider})` : form.model
})

function toggleModelDropdown() {
  if (modelsLoading.value || availableModels.value.length === 0) return
  modelDropdownOpen.value = !modelDropdownOpen.value
}

function selectModel(modelName: string) {
  form.model = modelName
  modelDropdownOpen.value = false
}

/** 点击外部关闭下拉框 */
function handleClickOutside(e: MouseEvent) {
  if (modelDropdownRef.value && !modelDropdownRef.value.contains(e.target as Node)) {
    modelDropdownOpen.value = false
  }
}

const activeTab = ref<'preview' | 'config'>('config')

/** 图标上传相关 */
const iconInputRef = ref<HTMLInputElement | null>(null)
const iconPreviewUrl = ref<string | null>(null)
const iconFile = ref<File | null>(null)

// ==================== 引导相关 ====================

const sendBtnRef = ref<HTMLElement | null>(null)
const configAreaRef = ref<HTMLElement | null>(null)
const createBtnRef = ref<HTMLElement | null>(null)

/** 打字机动画进行中 */
const isTypewriting = ref(false)
let typewriterTimer: ReturnType<typeof setInterval> | null = null

/** 错误提示信息 */
const errorMessage = ref('')
let errorTimer: ReturnType<typeof setTimeout> | null = null

/** 显示错误提示（自动 5 秒后消失） */
function showError(msg: string) {
  errorMessage.value = msg
  if (errorTimer) clearTimeout(errorTimer)
  errorTimer = setTimeout(() => { errorMessage.value = '' }, 5000)
}

// ==================== 计算属性 ====================

/** 项目图标：优先使用自定义图标，否则取名称首字 */
const projectIcon = computed(() => {
  if (form.icon) return form.icon
  if (form.name) return form.name.charAt(0).toUpperCase()
  return 'M'
})

/** 是否可以发送消息（不在生成中、不在打字机动画中且有内容） */
const canSend = computed(() => inputText.value.trim().length > 0 && !isGenerating.value && !isTypewriting.value)

/** 是否可以创建项目（名称和描述都必填） */
const canCreate = computed(() => form.name.trim().length > 0 && form.description.trim().length > 0)

// ==================== 方法 ====================

/** 是否有未保存的内容（表单已填写或有用户对话） */
const hasUnsavedContent = computed(() => {
  const hasFormContent = form.name.trim() || form.description.trim() || form.instructions.trim()
  const hasUserMessages = messages.value.some(m => m.role === 'user')
  return !!(hasFormContent || hasUserMessages)
})

/** 返回确认弹窗 */
const showBackConfirm = ref(false)

/** 返回上一页（有内容时先确认） */
function handleBack() {
  if (isCreating.value) {
    // 创建中：弹出特殊提示
    showBackConfirm.value = true
    return
  }
  if (hasUnsavedContent.value) {
    showBackConfirm.value = true
    return
  }
  doBack()
}

/** 确认返回 */
function doBack() {
  showBackConfirm.value = false
  ws.close()
  router.back()
}

/** 发送消息 */
async function handleSendMessage(event?: KeyboardEvent | MouseEvent) {
  if (event instanceof KeyboardEvent) {
    if (isComposing.value) return
    event.preventDefault()
  }
  if (!canSend.value) return

  // 引导 Step 7：用户点击发送后，暂时隐藏遮罩（等 AI 回复）
  if (guideStore.isActive && guideStore.currentStep === 7) {
    guideStore.setTarget(null)
  }

  const text = inputText.value.trim()
  inputText.value = ''

  // 添加用户消息（显示给用户的是原始文本，不含系统 prompt）
  messages.value.push({ role: 'user', content: text })
  scrollToBottom()

  // 重置输入框高度
  nextTick(() => {
    if (inputRef.value) {
      inputRef.value.style.height = 'auto'
    }
  })

  // 构造发送给后端的消息内容（首条消息拼接引导 prompt，但不影响 UI 展示）
  const messageContent = isFirstMessage.value
    ? GUIDE_PROMPT + text
    : text

  // 添加空的助手消息（流式填充）
  const assistantMsg: ChatMessage = { role: 'assistant', content: '' }
  messages.value.push(assistantMsg)
  currentAssistantMsg = assistantMsg

  isThinking.value = true
  isGenerating.value = true

  try {
    // 构建 WebSocket 请求体（不传 agent_id，使用后端默认 agent）
    const requestBody: ChatRequest = {
      message: messageContent,
      user_id: 'local',
      stream: true,
      ...(conversationId.value ? { conversation_id: conversationId.value } : {})
    }

    // 通过 WebSocket 发送并等待流结束
    await ws.connect(requestBody, {
      onEvent: handleStreamEvent,
      onConnected: () => {
        console.log('✅ 创建项目引导对话已连接')
      },
      onDisconnected: () => {
        isGenerating.value = false
        isThinking.value = false
        // 流结束后解析 JSON 填充表单
        if (currentAssistantMsg) {
          parseAndFillForm(currentAssistantMsg.content)
          currentAssistantMsg = null
        }
        // 引导 Step 7 → Step 8：AI 回复完成后，高亮配置区域
        if (guideStore.isActive && guideStore.currentStep === 7) {
          setTimeout(() => {
            guideStore.nextStep() // → step 8
            nextTick(() => {
              if (configAreaRef.value) {
                guideStore.setTarget(configAreaRef.value)
              }
            })
          }, 800) // 短暂延迟，让用户看到表单填充效果
        }
      },
      onError: (error) => {
        console.error('❌ WebSocket 错误:', error)
        isGenerating.value = false
        isThinking.value = false
        if (currentAssistantMsg && !currentAssistantMsg.content) {
          currentAssistantMsg.content = '抱歉，连接出现问题，请重试。'
        }
        currentAssistantMsg = null
      }
    })

    // 首条消息发送成功后标记
    if (isFirstMessage.value) {
      isFirstMessage.value = false
    }
  } catch (error) {
    console.error('❌ 发送消息失败:', error)
    isGenerating.value = false
    isThinking.value = false
    if (currentAssistantMsg && !currentAssistantMsg.content) {
      currentAssistantMsg.content = '抱歉，发送失败，请检查网络后重试。'
    }
    currentAssistantMsg = null
  }
}

// ==================== 流式事件处理 ====================

/** 处理 WebSocket 流式事件 */
function handleStreamEvent(event: { type: string; data: any }): void {
  const { type, data } = event

  // 记录会话 ID（后端首次创建会话时返回）
  if (type === 'conversation_start' && data?.conversation_id) {
    conversationId.value = data.conversation_id
  }

  // 内容增量：追加文本到当前助手消息
  if (type === 'content_delta' && currentAssistantMsg) {
    // 首次收到内容时关闭 thinking 动画
    if (isThinking.value) {
      isThinking.value = false
    }

    const delta = data?.delta
    let deltaText = ''
    if (typeof delta === 'string') {
      deltaText = delta
    } else if (delta?.text) {
      deltaText = delta.text
    } else if (typeof data?.text === 'string') {
      deltaText = data.text
    }

    if (deltaText) {
      currentAssistantMsg.content += deltaText
      scrollToBottom()
    }
  }

  // 内容块开始：处理 text 类型的块
  if (type === 'content_start') {
    if (isThinking.value) {
      isThinking.value = false
    }
  }

  // 消息/流结束
  if (type === 'message_stop' || type === 'session_end' || type === 'session_stopped') {
    isGenerating.value = false
    isThinking.value = false
    if (currentAssistantMsg) {
      parseAndFillForm(currentAssistantMsg.content)
      currentAssistantMsg = null
    }
  }
}

// ==================== JSON 解析与表单填充 ====================

/**
 * 从 AI 回复中解析 JSON 代码块，自动填充表单
 * 支持格式：```json { "name": "...", "description": "...", "instructions": "..." } ```
 */
function parseAndFillForm(text: string): void {
  if (!text) return

  // 匹配 ```json ... ``` 代码块
  const jsonBlockRegex = /```json\s*\n?([\s\S]*?)```/g
  let match: RegExpExecArray | null = null
  let lastJson: Record<string, string> | null = null

  while ((match = jsonBlockRegex.exec(text)) !== null) {
    try {
      const parsed = JSON.parse(match[1].trim())
      if (typeof parsed === 'object' && parsed !== null) {
        lastJson = parsed
      }
    } catch {
      // JSON 解析失败，跳过
    }
  }

  if (!lastJson) return

  // 用 AI 建议更新表单（每次都覆盖，让多轮对话可以迭代完善）
  let filled = false
  if (lastJson.name) {
    form.name = lastJson.name.slice(0, 50)
    filled = true
  }
  if (lastJson.description) {
    form.description = lastJson.description.slice(0, 500)
    filled = true
  }
  if (lastJson.instructions) {
    form.instructions = lastJson.instructions
    filled = true
  }

  // 如果有填充，切到配置标签让用户看到
  if (filled) {
    activeTab.value = 'config'
  }
}

// ==================== 图标上传 ====================

/** 触发文件选择器 */
function triggerIconUpload() {
  iconInputRef.value?.click()
}

/** 处理图标文件上传 */
function handleIconUpload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  // 校验文件类型
  if (!file.type.startsWith('image/')) {
    showError('请选择图片文件')
    return
  }

  // 校验文件大小（最大 2MB）
  if (file.size > 2 * 1024 * 1024) {
    showError('图标文件大小不能超过 2MB')
    return
  }

  iconFile.value = file

  // 生成预览 URL
  if (iconPreviewUrl.value) {
    URL.revokeObjectURL(iconPreviewUrl.value)
  }
  iconPreviewUrl.value = URL.createObjectURL(file)

  // 重置 input 以便重复选同一文件
  input.value = ''
}

/** 移除图标 */
function removeIcon() {
  if (iconPreviewUrl.value) {
    URL.revokeObjectURL(iconPreviewUrl.value)
  }
  iconPreviewUrl.value = null
  iconFile.value = null
  form.icon = ''
}

// ==================== UI 辅助 ====================

/** 滚动到底部 */
function scrollToBottom() {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

/** 调整输入框高度 */
function adjustInputHeight() {
  if (inputRef.value) {
    inputRef.value.style.height = 'auto'
    inputRef.value.style.height = Math.min(inputRef.value.scrollHeight, 120) + 'px'
  }
}

// ==================== 打字机效果（引导 Step 2） ====================

/**
 * 启动打字机效果：逐字将文本写入输入框
 * 完成后自动推进到 Step 8（高亮发送按钮）
 */
function startTypewriter(text: string) {
  isTypewriting.value = true
  inputText.value = ''
  let i = 0
  typewriterTimer = setInterval(() => {
    if (i < text.length) {
      inputText.value += text[i]
      i++
    } else {
      clearInterval(typewriterTimer!)
      typewriterTimer = null
      isTypewriting.value = false
      // 打字完成 → Step 7：高亮发送按钮
      if (guideStore.isActive) {
        guideStore.nextStep() // → step 7
        nextTick(() => {
          if (sendBtnRef.value) {
            guideStore.setTarget(sendBtnRef.value)
          }
        })
      }
    }
  }, 80)
}

// ==================== 创建项目 ====================

/** 创建中状态 */
const isCreating = ref(false)

/** 创建项目（异步模式：POST 立即返回，WS 推送进度到全局通知卡片） */
async function handleCreate() {
  if (!canCreate.value || isCreating.value) return

  isCreating.value = true

  try {
    const { agent_id, name } = await agentStore.createAgent({
      name: form.name.trim(),
      description: form.description.trim(),
      prompt: form.instructions.trim() || `你是一个名为 ${form.name.trim()} 的 AI 助手。${form.description.trim()}`,
      ...(form.model ? { model: form.model } : {}),
      ...(form.dataDir.trim() ? { data_dir: form.dataDir.trim() } : {})
    })

    // Start tracking creation progress (global notification + WS)
    agentCreationStore.startCreation(agent_id, name)

    // 引导完成
    if (guideStore.isActive) {
      guideStore.completeGuide()
    }

    // 立即返回首页，通知卡片会在右上角显示创建进度
    router.replace({ name: 'chat' })
  } catch (error: any) {
    console.error('❌ 创建项目失败:', error)
    const msg = error?.response?.data?.detail?.message || error?.response?.data?.detail || error?.message || '未知错误'
    showError(`创建失败：${msg}`)
  } finally {
    isCreating.value = false
  }
}

// ==================== 保存项目（编辑模式） ====================

/** 保存项目（调用 Agent Update API） */
async function handleSave() {
  if (!canCreate.value || isCreating.value || !editAgentId.value) return

  isCreating.value = true
  try {
    await agentStore.updateAgent(editAgentId.value, {
      name: form.name.trim(),
      description: form.description.trim(),
      prompt: form.instructions.trim() || undefined,
      ...(form.model ? { model: form.model } : {}),
      ...(form.dataDir.trim() ? { data_dir: form.dataDir.trim() } : {})
    })

    // 保存成功，跳转到 Agent 对话页
    router.replace({ name: 'agent', params: { agentId: editAgentId.value } })
  } catch (error: any) {
    console.error('❌ 保存项目失败:', error)
    const msg = error?.response?.data?.detail || error?.message || '未知错误'
    showError(`保存失败：${msg}`)
  } finally {
    isCreating.value = false
  }
}

// ==================== 加载 Agent 数据（编辑模式） ====================

/** 加载已有 Agent 数据填充表单 */
async function loadAgentData() {
  if (!editAgentId.value) return

  editLoading.value = true
  try {
    const detail = await getAgentDetail(editAgentId.value)
    form.name = detail.name || ''
    form.description = detail.description || ''
    form.model = detail.model || ''
    form.dataDir = detail.data_dir || ''

    // 加载 prompt 作为 instructions
    try {
      const { data } = await api.get(`/v1/agents/${editAgentId.value}/prompt`)
      if (data?.prompt) {
        form.instructions = data.prompt
      }
    } catch {
      // prompt 接口可能不存在或失败，不影响主流程
    }

    // 编辑模式默认显示配置标签
    activeTab.value = 'config'
  } catch (error: any) {
    console.error('❌ 加载项目数据失败:', error)
    showError('加载项目数据失败，请返回重试')
  } finally {
    editLoading.value = false
  }
}

// ==================== 生命周期 ====================

onMounted(() => {
  // 注册点击外部关闭下拉框
  document.addEventListener('click', handleClickOutside)

  // Load available models
  loadModels()

  if (isEditMode.value) {
    // 编辑模式：加载已有数据，设置初始提示消息
    messages.value = [{
      role: 'assistant',
      content: '你正在编辑项目配置。可以直接在右侧修改表单，也可以在这里告诉我你想怎么调整，我会帮你更新配置。'
    }]
    loadAgentData()
  } else {
    // 创建模式：设置初始引导消息
    messages.value = [{
      role: 'assistant',
      content: '嗨！我会帮你创建一个新项目。你可以说，例如："创建一个帮助生成新产品视觉效果的AI"或是"创建一个帮助格式化代码的助手。"\n\n你想要做什么？'
    }]

    if (guideStore.isActive && guideStore.currentStep === 6) {
      // 引导模式：延迟启动打字机效果
      setTimeout(() => startTypewriter('创建一个会议纪要项目'), 600)
    } else {
      inputRef.value?.focus()
    }
  }
})

onUnmounted(() => {
  // 移除事件监听
  document.removeEventListener('click', handleClickOutside)
  // 页面离开时关闭 WebSocket 连接（聊天引导用的 WS）
  ws.close()
  if (errorTimer) clearTimeout(errorTimer)
  if (typewriterTimer) clearInterval(typewriterTimer)
  // 释放图标预览 URL
  if (iconPreviewUrl.value) {
    URL.revokeObjectURL(iconPreviewUrl.value)
  }
})

// ==================== 引导步骤监听 ====================

// 引导步骤切换时设置高亮目标
watch(() => guideStore.currentStep, (step) => {
  if (!guideStore.isActive) return
  if (step === 8) {
    // Step 8：高亮配置区域
    nextTick(() => {
      if (configAreaRef.value) {
        guideStore.setTarget(configAreaRef.value)
      }
    })
  } else if (step === 9) {
    // Step 9：高亮"创建"按钮
    nextTick(() => {
      if (createBtnRef.value) {
        guideStore.setTarget(createBtnRef.value)
      }
    })
  }
})
</script>

<style scoped>
.toast-enter-active {
  transition: all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
}
.toast-leave-active {
  transition: all 0.2s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>

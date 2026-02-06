<template>
  <div class="tool-card">
    <!-- 头部 -->
    <div class="tool-header" @click="toggle">
      <div class="tool-left">
        <component :is="toolIcon" class="tool-icon" />
        <div class="tool-info">
          <span class="tool-title">{{ friendlyDescription }}</span>
          <span class="tool-status" :class="status">{{ statusText }}</span>
        </div>
      </div>
      <div class="tool-right">
        <span v-if="result" class="result-badge" :class="{ 'is-error': isError }">
          {{ isError ? '失败' : '完成' }}
        </span>
        <span class="tool-toggle">{{ isExpanded ? '收起' : '详情' }}</span>
      </div>
    </div>
    
    <!-- 详情 -->
    <div v-show="isExpanded" class="tool-body">
      <!-- 工具输入 -->
      <div class="tool-section">
        <div class="tool-section-label">
          <ArrowDownToLine class="section-icon" /> 输入参数
        </div>
        <pre class="tool-code" :class="{ 'is-streaming': isStreaming }">{{ formatJson(sanitizedDisplayInput) }}</pre>
      </div>
      <!-- 工具输出 -->
      <div v-if="result || partialResult || intermediateContent" class="tool-section">
        <div class="tool-section-label">
          <ArrowUpFromLine class="section-icon" /> 执行结果
        </div>
        
        <!-- 中间内容展示 (如图片) -->
        <div v-if="intermediateContent && intermediateContent.type === 'image'" class="intermediate-image">
           <img :src="`data:image/png;base64,${intermediateContent.data}`" alt="Generated Image" />
        </div>
        
        <pre v-if="displayResult" class="tool-code" :class="{ 'is-error': isError, 'is-streaming': isResultStreaming }">{{ formatResult(displayResult) }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, type Component } from 'vue'
import {
  FileEdit,
  FileText,
  FolderOpen,
  Terminal,
  Code,
  Link,
  Upload,
  FilePlus,
  Search,
  Brain,
  BookOpen,
  ClipboardList,
  Presentation,
  Palette,
  FileOutput,
  Plug,
  Paperclip,
  BarChart3,
  GitBranch,
  Hand,
  FileSearch,
  Wrench,
  ArrowDownToLine,
  ArrowUpFromLine
} from 'lucide-vue-next'

// 工具配置：图标组件、名称、描述模板
const TOOL_CONFIG: Record<string, { icon: Component; name: string; descTemplate?: (input: any) => string }> = {
  // 沙盒文件操作
  'sandbox_write_file': {
    icon: FileEdit,
    name: '写入文件',
    descTemplate: (input) => input?.path ? `写入 ${getFileName(input.path)}` : '写入文件'
  },
  'sandbox_read_file': {
    icon: FileText,
    name: '读取文件',
    descTemplate: (input) => input?.path ? `读取 ${getFileName(input.path)}` : '读取文件'
  },
  'sandbox_list_files': {
    icon: FolderOpen,
    name: '列出目录',
    descTemplate: (input) => input?.path ? `浏览 ${input.path}` : '列出目录'
  },
  'sandbox_run_command': {
    icon: Terminal,
    name: '执行命令',
    descTemplate: (input) => input?.command ? `执行 ${truncate(input.command, 40)}` : '执行命令'
  },
  'sandbox_execute_python': {
    icon: Code,
    name: '执行 Python',
    descTemplate: () => '执行 Python 代码'
  },
  'sandbox_get_public_url': {
    icon: Link,
    name: '获取 URL',
    descTemplate: (input) => input?.port ? `获取端口 ${input.port} 的公开链接` : '获取公开链接'
  },
  'sandbox_upload_file': {
    icon: Upload,
    name: '上传文件',
    descTemplate: (input) => input?.path ? `上传 ${getFileName(input.path)}` : '上传文件'
  },
  
  // 其他文件操作
  'write_file': {
    icon: FileEdit,
    name: '写入文件',
    descTemplate: (input) => input?.path ? `写入 ${getFileName(input.path)}` : '写入文件'
  },
  'read_file': {
    icon: FileText,
    name: '读取文件',
    descTemplate: (input) => input?.path ? `读取 ${getFileName(input.path)}` : '读取文件'
  },
  'str_replace_editor': {
    icon: FileEdit,
    name: '编辑文件',
    descTemplate: (input) => input?.path ? `编辑 ${getFileName(input.path)}` : '编辑文件'
  },
  'create_file': {
    icon: FilePlus,
    name: '创建文件',
    descTemplate: (input) => input?.path ? `创建 ${getFileName(input.path)}` : '创建文件'
  },
  
  // 搜索工具
  'web_search': {
    icon: Search,
    name: '网络搜索',
    descTemplate: (input) => input?.query ? `搜索「${truncate(input.query, 30)}」` : '网络搜索'
  },
  'tavily_search': {
    icon: Search,
    name: '网络搜索',
    descTemplate: (input) => input?.query ? `搜索「${truncate(input.query, 30)}」` : '网络搜索'
  },
  'exa_search': {
    icon: Brain,
    name: '智能搜索',
    descTemplate: (input) => input?.query ? `语义搜索「${truncate(input.query, 30)}」` : '智能搜索'
  },
  
  // 知识库
  'knowledge_search': {
    icon: BookOpen,
    name: '知识检索',
    descTemplate: (input) => input?.query ? `检索「${truncate(input.query, 30)}」` : '知识库检索'
  },
  'ragie_retrieve': {
    icon: BookOpen,
    name: '知识检索',
    descTemplate: (input) => input?.query ? `检索「${truncate(input.query, 30)}」` : '知识库检索'
  },
  
  // 计划与任务
  'plan_todo': {
    icon: ClipboardList,
    name: '任务规划',
    descTemplate: (input) => {
      if (input?.operation === 'create') return '创建任务计划'
      if (input?.operation === 'update_todo') return '更新任务状态'
      if (input?.operation === 'add_todo') return '添加新步骤'
      return '任务规划'
    }
  },
  
  // 文档生成
  'ppt_generator': {
    icon: Presentation,
    name: 'PPT 生成',
    descTemplate: (input) => input?.topic ? `生成 PPT「${truncate(input.topic, 25)}」` : '生成 PPT'
  },
  'slidespeak_render': {
    icon: Palette,
    name: '幻灯片渲染',
    descTemplate: () => '渲染 PPT 文件'
  },
  'text2document': {
    icon: FileOutput,
    name: '文档生成',
    descTemplate: () => '生成文档'
  },
  
  // API 调用
  'api_calling': {
    icon: Plug,
    name: 'API 调用',
    descTemplate: (input) => input?.api_name ? `调用 ${input.api_name}` : 'API 调用'
  },
  
  // 文件发送
  'send_files': {
    icon: Paperclip,
    name: '发送文件',
    descTemplate: (input) => {
      const count = input?.files?.length
      return count ? `发送 ${count} 个文件` : '发送文件'
    }
  },
  
  // 数据分析
  'wenshu_analytics': {
    icon: BarChart3,
    name: '数据分析',
    descTemplate: () => '数据分析'
  },
  
  // 图表生成
  'Ontology_TextToChart_zen0': {
    icon: GitBranch,
    name: '流程图生成',
    descTemplate: () => '生成流程图'
  },
  
  // 人工确认
  'request_human_confirmation': {
    icon: Hand,
    name: '等待确认',
    descTemplate: (input) => input?.question ? `等待确认: ${truncate(input.question, 30)}` : '等待用户确认'
  },
  
  // 文档解析
  'document_partition_tool': {
    icon: FileSearch,
    name: '文档解析',
    descTemplate: (input) => input?.source ? `解析文档` : '解析文档'
  }
}

// 状态文案映射
const STATUS_TEXT_MAP: Record<string, string> = {
  'pending': '执行中...',
  'success': '',
  'error': ''
}

// 辅助函数：获取文件名
function getFileName(path: string): string {
  if (!path) return ''
  const parts = path.split('/')
  return parts[parts.length - 1] || path
}

// 辅助函数：截断字符串
function truncate(str: string, maxLen: number): string {
  if (!str) return ''
  return str.length > maxLen ? str.slice(0, maxLen) + '...' : str
}

const props = defineProps({
  name: String,
  input: [Object, String],
  partialInput: String, // 流式传输中的参数
  result: [Object, String],
  partialResult: String, // 流式传输中的结果
  status: {
    type: String, // 'pending', 'success', 'error'
    default: 'pending'
  },
  intermediateContent: Object // 中间内容
})

// 解析输入参数（支持字符串和对象）
const parsedInput = computed(() => {
  if (!props.input && !props.partialInput) return {}
  
  // 优先使用完整的 input
  if (props.input && typeof props.input === 'object') {
    return props.input
  }
  
  // 尝试解析 partialInput
  if (props.partialInput) {
    try {
      return JSON.parse(props.partialInput)
    } catch {
      return {}
    }
  }
  
  // 尝试解析 input 字符串
  if (typeof props.input === 'string') {
    try {
      return JSON.parse(props.input)
    } catch {
      return {}
    }
  }
  
  return {}
})

// 显示的输入：优先显示解析后的 input，否则显示流式的 partialInput
const displayInput = computed(() => {
  if (props.input && Object.keys(props.input).length > 0) {
    return props.input
  }
  if (props.partialInput) {
    return props.partialInput
  }
  return props.input || {}
})

function sanitizeToolInput(input: any): any {
  if (!input || typeof input !== 'object') return input
  if (Array.isArray(input)) return input

  const cloned = { ...(input as Record<string, any>) }
  delete cloned.session_id
  delete cloned.user_id
  delete cloned.conversation_id
  return cloned
}

const sanitizedDisplayInput = computed(() => {
  const raw = displayInput.value

  // 字符串：尝试解析为 JSON 后再过滤（用于历史消息/兼容形态）
  if (typeof raw === 'string') {
    try {
      return sanitizeToolInput(JSON.parse(raw))
    } catch {
      return raw
    }
  }

  // 对象：浅拷贝过滤，避免影响原始响应式数据
  return sanitizeToolInput(raw)
})

// 获取工具配置
const toolConfig = computed(() => {
  const name = props.name || ''
  
  // 精确匹配
  if (TOOL_CONFIG[name]) {
    return TOOL_CONFIG[name]
  }
  
  // 模糊匹配（处理带前缀的工具名）
  for (const [key, config] of Object.entries(TOOL_CONFIG)) {
    if (name.toLowerCase().includes(key.toLowerCase())) {
      return config
    }
  }
  
  // 默认配置
  return {
    icon: Wrench,
    name: name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
    descTemplate: undefined
  }
})

// 工具图标
const toolIcon = computed(() => toolConfig.value.icon)

// 友好描述（根据工具类型和输入生成）
const friendlyDescription = computed(() => {
  const config = toolConfig.value
  if (config.descTemplate) {
    return config.descTemplate(parsedInput.value)
  }
  return config.name
})

const isExpanded = ref(false)

const isLoading = computed(() => props.status === 'pending')
const isError = computed(() => props.status === 'error')
const isSuccess = computed(() => props.status === 'success')
const isStreaming = computed(() => props.partialInput && !props.input)
const isResultStreaming = computed(() => props.partialResult && !props.result)

// 显示的结果：优先显示完整的 result，否则显示流式的 partialResult
const displayResult = computed(() => {
  if (props.result) return props.result
  if (props.partialResult) return props.partialResult
  return null
})

// 状态显示文案
const statusText = computed(() => {
  return STATUS_TEXT_MAP[props.status] || ''
})

function toggle() {
  isExpanded.value = !isExpanded.value
}

function formatJson(data: any) {
  if (!data) return '{}'
  try {
    const obj = typeof data === 'string' ? JSON.parse(data) : data
    return JSON.stringify(obj, null, 2)
  } catch {
    return data
  }
}

function formatResult(data: any) {
  if (!data) return ''
  return formatJson(data)
}
</script>

<style scoped>
/* 工具卡片 - 简洁风格 */
.tool-card {
  margin: 8px 0;
  background: #f8f9fa;
  border-radius: 10px;
  overflow: hidden;
}

.tool-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s;
}

.tool-header:hover {
  background: #f1f3f4;
}

.tool-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.tool-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: #5f6368;
}

.tool-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.tool-title {
  font-size: 13px;
  font-weight: 500;
  color: #3c4043;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tool-status {
  font-size: 12px;
  color: #9aa0a6;
  flex-shrink: 0;
}

.tool-status.pending {
  color: #fbbc04;
}

.tool-status.success {
  color: #34a853;
}

.tool-status.error {
  color: #ea4335;
}

.tool-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.result-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: #e6f4ea;
  color: #137333;
}

.result-badge.is-error {
  background: #fce8e6;
  color: #c5221f;
}

.tool-toggle {
  font-size: 12px;
  color: #9aa0a6;
}

.tool-body {
  padding: 0 14px 12px;
}

.tool-section {
  margin-top: 12px;
}

.tool-section:first-child {
  margin-top: 0;
}

.intermediate-image img {
  max-width: 100%;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  margin-top: 4px;
}

.tool-section-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 500;
  color: #9aa0a6;
  margin-bottom: 6px;
}

.section-icon {
  width: 12px;
  height: 12px;
}

.tool-code {
  margin: 0;
  padding: 10px 12px;
  background: #ffffff;
  border-radius: 8px;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  font-size: 12px;
  color: #5f6368;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}

.tool-code.is-error {
  background: #fce8e6;
  color: #c5221f;
}

.tool-code.is-streaming {
  background: linear-gradient(90deg, #fff 0%, #e8f5e9 50%, #fff 100%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* 滚动条 */
.tool-code::-webkit-scrollbar {
  width: 4px;
}

.tool-code::-webkit-scrollbar-thumb {
  background: #dadce0;
  border-radius: 2px;
}
</style>

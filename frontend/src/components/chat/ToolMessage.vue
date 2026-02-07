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
  // 文件操作
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
  // tavily_search / exa_search 已迁移到 Skills-First 架构，由 web_search + api_calling 覆盖
  
  // 知识库
  'knowledge_search': {
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
  // ppt_generator / slidespeak_render 已迁移到 PPT Skill + api_calling
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
.tool-card {
  margin: 8px 0;
  background: var(--color-muted);
  border: 1px solid var(--color-border);
  border-radius: 12px;
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
  background: rgba(0, 0, 0, 0.03);
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
  color: var(--color-muted-foreground);
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
  color: var(--color-foreground);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tool-status {
  font-size: 12px;
  color: var(--color-muted-foreground);
  flex-shrink: 0;
}

.tool-status.pending {
  color: var(--color-primary);
}

.tool-status.success {
  color: var(--color-success);
}

.tool-status.error {
  color: var(--color-destructive);
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
  background: var(--color-accent);
  color: var(--color-accent-foreground);
}

.result-badge.is-error {
  background: rgba(239, 68, 68, 0.08);
  color: var(--color-destructive);
}

.tool-toggle {
  font-size: 12px;
  color: var(--color-muted-foreground);
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
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  margin-top: 4px;
}

.tool-section-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 500;
  color: var(--color-muted-foreground);
  margin-bottom: 6px;
}

.section-icon {
  width: 12px;
  height: 12px;
}

.tool-code {
  margin: 0;
  padding: 10px 12px;
  background: var(--color-background);
  border-radius: 8px;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  font-size: 12px;
  color: var(--color-muted-foreground);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}

.tool-code.is-error {
  background: rgba(239, 68, 68, 0.05);
  color: var(--color-destructive);
}

.tool-code.is-streaming {
  background: linear-gradient(90deg, var(--color-background) 0%, var(--color-accent) 50%, var(--color-background) 100%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>

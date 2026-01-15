<template>
  <div class="tool-message">
    <!-- 头部：折叠状态 -->
    <div class="tool-header" @click="toggle" :class="{ 'is-expanded': isExpanded, 'is-error': isError, 'is-success': isSuccess }">
      <div class="header-left">
        <span class="status-indicator" :class="status"></span>
        <span class="tool-name">{{ formatToolName(name) }}</span>
        <span class="status-text" :class="{ 'success-text': isSuccess, 'error-text': isError }">{{ statusText }}</span>
      </div>
      
      <div class="header-right">
        <span class="toggle-icon">{{ isExpanded ? '收起' : '详情' }}</span>
      </div>
    </div>
    
    <!-- 详情：展开状态 -->
    <div v-show="isExpanded" class="tool-body">
      <!-- 输入参数 -->
      <div class="section input-section">
        <div class="section-label">Input</div>
        <pre class="code-block" :class="{ 'streaming': isStreaming }">{{ formatJson(displayInput) }}</pre>
      </div>
      
      <!-- 执行结果 -->
      <div class="section output-section" v-if="result">
        <div class="section-label">Output</div>
        <pre class="code-block" :class="{ 'error-text': isError }">{{ formatResult(result) }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

// 工具名中文映射表
const TOOL_NAME_MAP = {
  // 沙盒/文件操作
  'sandbox_write_file': '写入文件',
  'sandbox_read_file': '读取文件',
  'sandbox_run_command': '执行命令',
  'sandbox_run_project': '运行项目',
  'sandbox_create_project': '创建项目',
  'write_file': '写入文件',
  'read_file': '读取文件',
  'str_replace_editor': '编辑文件',
  'create_file': '创建文件',
  
  // API 调用
  'api_calling': '调用服务',
  
  // 搜索
  'web_search': '网络搜索',
  'tavily_search': '网络搜索',
  'exa_search': '智能搜索',
  'perplxity': '联网搜索',
  
  // 知识库
  'ragie_retrieve': '知识检索',
  'knowledge_search': '知识检索',
  'chatDocuments': '文档问答',
  
  // 计划与任务
  'plan_todo': '任务规划',
  'scheduled_task': '定时任务',
  
  // 文档生成
  'ppt_generator': 'PPT 生成',
  'slidespeak_render': '幻灯片渲染',
  'text2document': '文档生成',
  
  // 数据分析
  'wenshu_analytics': '数据分析',
  'wenshu_api': '数据查询',
  
  // 流程图/图表
  'Ontology_TextToChart_zen0': '流程图生成',
  'nano_banana': '图表生成',
  
  // 人工确认
  'request_human_confirmation': '等待确认',
  
  // Dify/Coze 集成
  'dify_api': 'Dify 服务',
  'coze_api': 'Coze 服务',
}

// 状态文案映射
const STATUS_TEXT_MAP = {
  'pending': '执行中...',
  'success': '已完成',
  'error': '执行失败'
}

const props = defineProps({
  name: String,
  input: [Object, String],
  partialInput: String, // 流式传输中的参数
  result: [Object, String],
  status: {
    type: String, // 'pending', 'success', 'error'
    default: 'pending'
  }
})

// 显示的输入：优先显示解析后的 input，否则显示流式的 partialInput
const displayInput = computed(() => {
  // 如果有完整的 input 且不为空对象，优先使用
  if (props.input && Object.keys(props.input).length > 0) {
    return props.input
  }
  // 否则显示流式的 partialInput
  if (props.partialInput) {
    return props.partialInput
  }
  return props.input || {}
})

const isExpanded = ref(false)

const isLoading = computed(() => props.status === 'pending')
const isError = computed(() => props.status === 'error')
const isSuccess = computed(() => props.status === 'success')
const isStreaming = computed(() => props.partialInput && !props.input)

// 状态显示文案
const statusText = computed(() => {
  return STATUS_TEXT_MAP[props.status] || ''
})

function toggle() {
  isExpanded.value = !isExpanded.value
}

function formatToolName(name) {
  if (!name) return '工具调用'
  
  // 优先使用中文映射
  if (TOOL_NAME_MAP[name]) {
    return TOOL_NAME_MAP[name]
  }
  
  // 尝试模糊匹配（处理带前缀的工具名，如 "dify_Ontology_TextToChart_zen0"）
  for (const [key, value] of Object.entries(TOOL_NAME_MAP)) {
    if (name.toLowerCase().includes(key.toLowerCase())) {
      return value
    }
  }
  
  // 降级：将下划线替换为空格，首字母大写
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function formatJson(data) {
  if (!data) return '{}'
  try {
    const obj = typeof data === 'string' ? JSON.parse(data) : data
    return JSON.stringify(obj, null, 2)
  } catch {
    return data
  }
}

function formatResult(data) {
  if (!data) return ''
  return formatJson(data)
}
</script>

<style scoped>
.tool-message {
  margin: 12px 0;
  border-radius: 8px;
  overflow: hidden;
  font-family: 'Inter', system-ui, sans-serif;
  border: 1px solid #e5e7eb;
  background: #ffffff;
}

.tool-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: #f9fafb;
  cursor: pointer;
  transition: background 0.2s;
  user-select: none;
}

.tool-header:hover {
  background: #f3f4f6;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: #374151;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #d1d5db;
}

.status-indicator.pending {
  background: #fbbf24;
  animation: pulse 1.5s infinite;
}

.status-indicator.success {
  background: #10b981;
}

.status-indicator.error {
  background: #ef4444;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.tool-name {
  font-weight: 500;
  color: #111827;
}

.status-text {
  color: #9ca3af;
  font-size: 12px;
}

.status-text.success-text {
  color: #10b981;
}

.status-text.error-text {
  color: #ef4444;
}

.header-right {
  font-size: 12px;
  color: #9ca3af;
}

.tool-body {
  padding: 12px;
  background: #ffffff;
  border-top: 1px solid #e5e7eb;
}

.section {
  margin-bottom: 12px;
}

.section:last-child {
  margin-bottom: 0;
}

.section-label {
  font-size: 11px;
  color: #9ca3af;
  margin-bottom: 6px;
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.05em;
}

.code-block {
  margin: 0;
  padding: 10px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  color: #4b5563;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
}

.error-text {
  color: #ef4444;
  background: #fef2f2;
  border-color: #fee2e2;
}

.streaming {
  background: linear-gradient(90deg, #f9fafb 0%, #f0fdf4 50%, #f9fafb 100%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>

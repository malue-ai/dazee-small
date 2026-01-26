<template>
  <div class="tool-card">
    <!-- 头部 -->
    <div class="tool-header" @click="toggle">
      <div class="tool-left">
        <span class="tool-dot" :class="status"></span>
        <span class="tool-name">{{ formatToolName(name) }}</span>
        <span class="tool-status" :class="status">{{ statusText }}</span>
      </div>
      <span class="tool-toggle">{{ isExpanded ? '收起' : '详情' }}</span>
    </div>
    
    <!-- 详情 -->
    <div v-show="isExpanded" class="tool-body">
      <div class="tool-section">
        <div class="tool-section-label">输入</div>
        <pre class="tool-code" :class="{ 'is-streaming': isStreaming }">{{ formatJson(displayInput) }}</pre>
      </div>
      <div v-if="result" class="tool-section">
        <div class="tool-section-label">输出</div>
        <pre class="tool-code" :class="{ 'is-error': isError }">{{ formatResult(result) }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

// 工具名中文映射表
const TOOL_NAME_MAP = {
  // 沙盒工具（E2B）
  'sandbox_write_file': '写入文件',
  'sandbox_read_file': '读取文件',
  'sandbox_list_files': '列出目录',
  'sandbox_run_command': '执行命令',
  'sandbox_execute_python': '执行代码',
  'sandbox_get_public_url': '获取URL',
  // 其他文件操作
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
}

.tool-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #9aa0a6;
}

.tool-dot.pending {
  background: #fbbc04;
  animation: pulse 1.2s infinite;
}

.tool-dot.success {
  background: #34a853;
}

.tool-dot.error {
  background: #ea4335;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.tool-name {
  font-size: 13px;
  font-weight: 500;
  color: #3c4043;
}

.tool-status {
  font-size: 12px;
  color: #9aa0a6;
}

.tool-status.success {
  color: #34a853;
}

.tool-status.error {
  color: #ea4335;
}

.tool-toggle {
  font-size: 12px;
  color: #9aa0a6;
}

.tool-body {
  padding: 0 14px 12px;
}

.tool-section {
  margin-top: 10px;
}

.tool-section:first-child {
  margin-top: 0;
}

.tool-section-label {
  font-size: 11px;
  font-weight: 500;
  color: #9aa0a6;
  margin-bottom: 6px;
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

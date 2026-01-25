<template>
  <div class="tool-card">
    <!-- 头部 -->
    <div class="tool-header" @click="toggle">
      <div class="tool-left">
        <!-- 状态图标 -->
        <div class="status-dot" :class="status">
          <svg v-if="isLoading" class="spinner" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" opacity="0.25"/>
            <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          <svg v-else-if="isSuccess" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          <svg v-else-if="isError" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </div>
        <!-- 工具名 + 状态 -->
        <div class="tool-info">
          <span class="tool-name">{{ formatToolName(name) }}</span>
          <span class="tool-status" :class="status">{{ statusText }}</span>
        </div>
      </div>
      <!-- 展开箭头 -->
      <svg 
        class="chevron" 
        :class="{ 'is-expanded': isExpanded }"
        viewBox="0 0 24 24" 
        fill="none" 
        stroke="currentColor" 
        stroke-width="2"
      >
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </div>
    
    <!-- 详情（可折叠） -->
    <Transition name="slide">
      <div v-show="isExpanded" class="tool-body">
        <!-- 输入 -->
        <div class="tool-section">
          <div class="section-label">输入参数</div>
          <pre class="code-block" :class="{ 'is-streaming': isStreaming }">{{ formatJson(displayInput) }}</pre>
        </div>
        <!-- 输出 -->
        <div v-if="result" class="tool-section">
          <div class="section-label">执行结果</div>
          <pre class="code-block" :class="{ 'is-error': isError }">{{ formatResult(result) }}</pre>
        </div>
      </div>
    </Transition>
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
/* Apple 风格工具卡片 */
.tool-card {
  margin: 8px 0;
  background: #f9fafb;
  border-radius: 12px;
  overflow: hidden;
}

.tool-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.tool-header:hover {
  background: #f3f4f6;
}

.tool-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 状态圆点/图标 */
.status-dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.status-dot.pending {
  background: #fef3c7;
  color: #d97706;
}

.status-dot.success {
  background: #d1fae5;
  color: #059669;
}

.status-dot.error {
  background: #fee2e2;
  color: #dc2626;
}

.status-dot svg {
  width: 12px;
  height: 12px;
}

.status-dot .spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 工具信息 */
.tool-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tool-name {
  font-size: 13px;
  font-weight: 500;
  color: #374151;
}

.tool-status {
  font-size: 12px;
  color: #9ca3af;
}

.tool-status.success {
  color: #059669;
}

.tool-status.error {
  color: #dc2626;
}

/* 展开箭头 */
.chevron {
  width: 16px;
  height: 16px;
  color: #9ca3af;
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.chevron.is-expanded {
  transform: rotate(180deg);
}

/* 详情区域 */
.tool-body {
  padding: 0 14px 14px;
}

.tool-section {
  margin-top: 12px;
}

.tool-section:first-child {
  margin-top: 0;
}

.section-label {
  font-size: 11px;
  font-weight: 500;
  color: #9ca3af;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.code-block {
  margin: 0;
  padding: 10px 12px;
  background: #ffffff;
  border-radius: 8px;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  font-size: 12px;
  color: #4b5563;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}

.code-block.is-error {
  background: #fef2f2;
  color: #b91c1c;
}

.code-block.is-streaming {
  background: linear-gradient(90deg, #ffffff 0%, #f0fdf4 50%, #ffffff 100%);
  background-size: 200% 100%;
  animation: shimmer 2s ease-in-out infinite;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* 滚动条 */
.code-block::-webkit-scrollbar {
  width: 4px;
}

.code-block::-webkit-scrollbar-track {
  background: transparent;
}

.code-block::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 2px;
}

/* 展开动画 */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
}

.slide-enter-to,
.slide-leave-from {
  opacity: 1;
  max-height: 500px;
}
</style>

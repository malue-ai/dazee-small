<template>
  <div v-if="hasMessages" class="flex flex-col gap-3">
    <!-- 错误信息 -->
    <div 
      v-for="error in errors" 
      :key="`error-${error.field}`"
      class="flex items-start gap-3 p-3 bg-red-50 border border-red-200 rounded-lg animate-in fade-in slide-in-from-top-1"
    >
      <AlertCircle class="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
      <div class="flex-1 min-w-0">
        <div class="text-sm font-medium text-red-800">{{ error.message }}</div>
        <div class="text-xs text-red-600 mt-0.5">字段: {{ formatFieldName(error.field) }}</div>
      </div>
    </div>

    <!-- 警告信息 -->
    <div 
      v-for="warning in warnings" 
      :key="`warning-${warning.field}`"
      class="flex items-start gap-3 p-3 bg-amber-50 border border-amber-200 rounded-lg animate-in fade-in slide-in-from-top-1"
    >
      <AlertTriangle class="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
      <div class="flex-1 min-w-0">
        <div class="text-sm font-medium text-amber-800">{{ warning.message }}</div>
        <div class="text-xs text-amber-600 mt-0.5">字段: {{ formatFieldName(warning.field) }}</div>
      </div>
    </div>

    <!-- 验证通过 -->
    <div 
      v-if="isValid && !loading"
      class="flex items-center gap-3 p-3 bg-green-50 border border-green-200 rounded-lg animate-in fade-in slide-in-from-top-1"
    >
      <CheckCircle class="w-5 h-5 text-green-500" />
      <div class="text-sm font-medium text-green-800">配置校验通过</div>
    </div>
  </div>

  <!-- 加载状态 -->
  <div v-if="loading" class="flex items-center gap-2 text-gray-500 text-sm">
    <Loader2 class="w-4 h-4 animate-spin" />
    <span>正在校验配置...</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { AlertCircle, AlertTriangle, CheckCircle, Loader2 } from 'lucide-vue-next'

interface ValidationError {
  field: string
  message: string
  code?: string
}

interface ValidationWarning {
  field: string
  message: string
}

const props = defineProps<{
  errors: ValidationError[]
  warnings: ValidationWarning[]
  loading?: boolean
  isValid?: boolean
}>()

const hasMessages = computed(() => {
  return props.errors.length > 0 || props.warnings.length > 0 || (props.isValid && !props.loading)
})

const formatFieldName = (field: string): string => {
  const fieldMap: Record<string, string> = {
    'agent_id': 'Agent ID',
    'prompt': '系统提示词',
    'model': '模型',
    'max_turns': '最大对话轮数',
    'llm.thinking_budget': 'LLM 思考预算',
    'llm.max_tokens': 'LLM 最大输出 Token',
    'memory.retention_policy': '记忆保留策略',
  }
  
  // 处理数组字段 (如 mcp_tools[0].name)
  const arrayMatch = field.match(/^(\w+)\[(\d+)\]\.(\w+)$/)
  if (arrayMatch) {
    const [, arrayName, index, fieldName] = arrayMatch
    const arrayNameMap: Record<string, string> = {
      'mcp_tools': 'MCP 工具',
      'apis': 'REST API',
    }
    return `${arrayNameMap[arrayName] || arrayName} #${parseInt(index) + 1} - ${fieldName}`
  }
  
  return fieldMap[field] || field
}
</script>

<template>
  <!--
    工具块渲染器
    后续可按 block.name 切换专用组件（如 PPT 预览、代码执行面板等）
    当前统一使用默认的 ToolMessage
  -->
  <ToolMessage 
    :name="block.name"
    :input="block.input"
    :partial-input="block.partialInput"
    :result="toolResultContent"
    :partial-result="toolPartialResult"
    :status="toolStatus"
    :intermediate-content="toolIntermediateContent"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ToolMessage from './ToolMessage.vue'

const props = defineProps({
  /** 原始 content block（tool_use / server_tool_use） */
  block: {
    type: Object,
    required: true
  },
  /** 工具执行状态映射 { [toolId]: { pending, success, result } } */
  toolStatuses: {
    type: Object,
    default: () => ({})
  },
  /** 全部内容块（用于查找配对的 tool_result 流式数据） */
  contentBlocks: {
    type: Array,
    default: () => []
  }
})

/** 解析工具执行状态 */
const toolStatus = computed(() => {
  const status = props.toolStatuses[props.block.id]
  if (!status) return 'pending'
  if (status.pending) return 'pending'
  return status.success ? 'success' : 'error'
})

/** 完整的工具执行结果（仅在执行完毕后返回） */
const toolResultContent = computed(() => {
  const status = props.toolStatuses[props.block.id]
  if (!status?.result || status.pending) return null
  return status.result
})

/** 流式传输中的部分结果 */
const toolPartialResult = computed(() => {
  for (const b of props.contentBlocks as any[]) {
    if (b?.type === 'tool_result' && b.tool_use_id === props.block.id) {
      return b.content || null
    }
  }
  return null
})

/** 从流式结果中提取中间内容（如图片预览） */
const toolIntermediateContent = computed(() => {
  const partial = toolPartialResult.value
  if (!partial) return undefined

  const match = partial.match(/"preview"\s*:\s*"([^"]+)"/)
  if (match?.[1]) {
    return { type: 'image', data: match[1] }
  }
  return undefined
})
</script>

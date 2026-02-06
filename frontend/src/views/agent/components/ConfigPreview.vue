<template>
  <div class="flex flex-col gap-4">
    <!-- 标签切换 -->
    <div class="flex items-center gap-2 border-b border-gray-200 pb-2">
      <button
        @click="activeTab = 'config'"
        class="px-4 py-2 text-sm font-medium rounded-lg transition-colors"
        :class="activeTab === 'config' ? 'bg-gray-900 text-white' : 'text-gray-600 hover:bg-gray-100'"
      >
        config.yaml
      </button>
      <button
        @click="activeTab = 'prompt'"
        class="px-4 py-2 text-sm font-medium rounded-lg transition-colors"
        :class="activeTab === 'prompt' ? 'bg-gray-900 text-white' : 'text-gray-600 hover:bg-gray-100'"
      >
        prompt.md
      </button>
    </div>

    <!-- 预览内容 -->
    <div class="relative">
      <!-- 加载状态 -->
      <div v-if="loading" class="absolute inset-0 bg-gray-900/50 rounded-lg flex items-center justify-center z-10">
        <Loader2 class="w-6 h-6 animate-spin text-white" />
      </div>

      <!-- 代码预览 -->
      <div class="bg-gray-900 rounded-lg overflow-hidden">
        <div class="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
          <span class="text-xs text-gray-400 font-mono">
            {{ activeTab === 'config' ? 'config.yaml' : 'prompt.md' }}
          </span>
          <button
            @click="copyToClipboard"
            class="flex items-center gap-1.5 px-2 py-1 text-xs text-gray-400 hover:text-white transition-colors rounded hover:bg-gray-700"
          >
            <component :is="copied ? Check : Copy" class="w-3.5 h-3.5" />
            {{ copied ? '已复制' : '复制' }}
          </button>
        </div>
        <pre class="p-4 overflow-x-auto text-sm font-mono leading-relaxed max-h-96 overflow-y-auto">
          <code :class="activeTab === 'config' ? 'text-green-400' : 'text-blue-300'">{{ displayContent }}</code>
        </pre>
      </div>

      <!-- 空状态 -->
      <div v-if="!loading && !displayContent" class="bg-gray-100 rounded-lg p-8 text-center">
        <FileCode class="w-8 h-8 text-gray-400 mx-auto mb-2" />
        <p class="text-sm text-gray-500">填写配置后将显示预览</p>
      </div>
    </div>

    <!-- 提示信息 -->
    <div class="flex items-start gap-2 text-xs text-gray-500 bg-gray-50 rounded-lg p-3">
      <Info class="w-4 h-4 flex-shrink-0 mt-0.5" />
      <div>
        <p>这是根据您的配置生成的文件预览。</p>
        <p class="mt-1">创建 Agent 后，这些文件将保存在 <code class="bg-gray-200 px-1 rounded">instances/&lt;auto-generated-uuid&gt;/</code> 目录下。</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Copy, Check, Loader2, FileCode, Info } from 'lucide-vue-next'
import api from '@/api/index'

interface PreviewData {
  config_yaml: string
  prompt_md: string
}

const props = defineProps<{
  formData: Record<string, any>
  agentName?: string
}>()

const activeTab = ref<'config' | 'prompt'>('config')
const loading = ref(false)
const previewData = ref<PreviewData | null>(null)
const copied = ref(false)

const displayContent = computed(() => {
  if (!previewData.value) return ''
  return activeTab.value === 'config' 
    ? previewData.value.config_yaml 
    : previewData.value.prompt_md
})

const fetchPreview = async () => {
  if (!props.formData.name || !props.formData.prompt) {
    previewData.value = null
    return
  }

  try {
    loading.value = true
    const response = await api.post('/v1/agents/preview', props.formData)
    previewData.value = response.data
  } catch (error) {
    console.error('获取配置预览失败:', error)
    previewData.value = null
  } finally {
    loading.value = false
  }
}

const copyToClipboard = async () => {
  if (!displayContent.value) return
  
  try {
    await navigator.clipboard.writeText(displayContent.value)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch (error) {
    console.error('复制失败:', error)
  }
}

// 监听表单数据变化，使用防抖获取预览
let debounceTimer: ReturnType<typeof setTimeout> | null = null
watch(
  () => props.formData,
  () => {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(fetchPreview, 800)
  },
  { deep: true, immediate: true }
)
</script>

<style scoped>
pre {
  white-space: pre-wrap;
  word-break: break-all;
}
</style>

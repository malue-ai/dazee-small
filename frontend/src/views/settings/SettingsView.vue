<template>
  <div class="min-h-screen bg-muted p-8">
    <div class="max-w-2xl mx-auto">
      <!-- 页面标题 -->
      <div class="mb-8">
        <h1 class="text-2xl font-semibold text-foreground">Settings</h1>
        <p class="mt-1 text-sm text-muted-foreground">Configure API keys and application preferences</p>
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="flex items-center justify-center py-20">
        <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
        <span class="ml-3 text-sm text-muted-foreground">Loading settings...</span>
      </div>

      <!-- 配置表单 -->
      <div v-else class="space-y-6">
        <!-- 状态提示 -->
        <div 
          v-if="!status?.configured" 
          class="bg-accent border border-primary/30 rounded-lg p-4"
        >
          <div class="flex items-start gap-3">
            <AlertTriangle class="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
            <div>
              <p class="text-sm font-medium text-accent-foreground">Required configuration missing</p>
              <p class="text-sm text-accent-foreground mt-1">
                Please configure at least one LLM API Key to start using the application.
              </p>
            </div>
          </div>
        </div>

        <div 
          v-if="saveSuccess" 
          class="bg-success/10 border border-success/30 rounded-lg p-4"
        >
          <div class="flex items-center gap-2">
            <Check class="w-4 h-4 text-success" />
            <p class="text-sm text-success">Settings saved successfully</p>
          </div>
        </div>

        <!-- 分组配置 -->
        <div
          v-for="(groupSchema, groupKey) in schema"
          :key="groupKey"
          class="bg-white rounded-2xl border border-border overflow-hidden"
        >
          <!-- 分组标题 -->
          <div class="px-6 py-4 border-b border-border bg-muted/50">
            <h2 class="text-sm font-semibold text-foreground uppercase tracking-wide">
              {{ groupLabels[groupKey] || groupKey }}
            </h2>
            <p class="text-xs text-muted-foreground mt-0.5" v-if="groupDescriptions[groupKey]">
              {{ groupDescriptions[groupKey] }}
            </p>
          </div>

          <!-- Knowledge 分组：特殊渲染 -->
          <div v-if="groupKey === 'knowledge'" class="p-6 space-y-5">
            <!-- 语义搜索开关 -->
            <div class="flex items-start justify-between gap-4">
              <div>
                <p class="text-sm font-medium text-foreground">语义搜索</p>
                <p class="text-xs text-muted-foreground mt-1">
                  开启后搜索能理解意思，如搜"天气"也能匹配"气候"相关文档
                </p>
              </div>
              <button
                @click="toggleSemanticSearch"
                class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200"
                :class="isSemanticEnabled ? 'bg-primary' : 'bg-muted-foreground/20'"
              >
                <span
                  class="inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform duration-200"
                  :class="isSemanticEnabled ? 'translate-x-5' : 'translate-x-0'"
                />
              </button>
            </div>

            <!-- 语义搜索详细配置（展开） -->
            <template v-if="isSemanticEnabled">
              <!-- 向量模型选择 -->
              <div>
                <p class="text-sm font-medium text-foreground mb-2">向量模型</p>
                <div class="space-y-2">
                  <label
                    v-for="opt in providerOptions"
                    :key="opt.value"
                    class="flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all"
                    :class="selectedProvider === opt.value
                      ? 'border-primary bg-accent'
                      : 'border-border hover:border-muted-foreground/30'"
                    @click="selectedProvider = opt.value"
                  >
                    <span
                      class="mt-0.5 flex-shrink-0 w-4 h-4 rounded-full border-2 transition-colors"
                      :class="selectedProvider === opt.value
                        ? 'border-primary bg-primary'
                        : 'border-muted-foreground/30'"
                    >
                      <span
                        v-if="selectedProvider === opt.value"
                        class="block w-full h-full rounded-full"
                      />
                    </span>
                    <div class="flex-1 min-w-0">
                      <span class="text-sm font-medium text-foreground">{{ opt.label }}</span>
                      <span
                        v-if="opt.value === 'local' && embeddingStatus?.local_available"
                        class="ml-2 inline-flex items-center gap-1 text-xs text-success"
                      >
                        <Check class="w-3 h-3" /> 已安装
                      </span>
                      <span
                        v-if="opt.value === 'openai' && embeddingStatus?.openai_available"
                        class="ml-2 inline-flex items-center gap-1 text-xs text-success"
                      >
                        <Check class="w-3 h-3" /> 已配置
                      </span>
                      <p class="text-xs text-muted-foreground mt-0.5">{{ opt.description }}</p>
                    </div>
                  </label>
                </div>
              </div>

              <!-- 本地模型安装提示 -->
              <div
                v-if="selectedProvider !== 'openai' && !embeddingStatus?.local_available"
                class="bg-accent border border-primary/20 rounded-xl p-4"
              >
                <div class="flex items-start gap-3">
                  <Download class="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
                  <div>
                    <p class="text-sm font-medium text-accent-foreground">需要安装本地模型</p>
                    <p class="text-xs text-accent-foreground/80 mt-1">
                      在终端运行以下命令。首次使用时自动下载 BGE-M3 Q4 模型（424MB，中英文双语）到 ~/.xiaodazi/models/
                    </p>
                    <div class="mt-2 flex items-center gap-2">
                      <code class="flex-1 px-3 py-1.5 bg-white rounded-lg text-xs font-mono text-foreground border border-border">
                        pip install llama-cpp-python
                      </code>
                      <button
                        @click="copyInstallCommand"
                        class="px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 rounded-lg transition-colors"
                      >
                        {{ copied ? '已复制' : '复制' }}
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 当前状态摘要 -->
              <div
                v-if="embeddingStatus"
                class="flex items-center gap-2 text-xs text-muted-foreground bg-muted rounded-lg px-3 py-2"
              >
                <span
                  class="w-2 h-2 rounded-full"
                  :class="embeddingStatus.current_provider ? 'bg-success' : 'bg-muted-foreground/30'"
                />
                {{ embeddingStatus.recommendation }}
              </div>
            </template>
          </div>

          <!-- 通用分组：默认渲染 -->
          <div v-else class="divide-y divide-border/50">
            <div
              v-for="(fieldMeta, fieldKey) in groupSchema"
              :key="fieldKey"
              class="px-6 py-4"
            >
              <label class="flex items-center gap-2 text-sm font-medium text-foreground mb-2">
                {{ fieldMeta.label }}
                <span v-if="fieldMeta.required" class="text-destructive text-xs">required</span>
                <Lock v-if="fieldMeta.secret" class="w-3 h-3 text-muted-foreground/50" />
              </label>
              <div class="relative">
                <input
                  :type="fieldMeta.secret && !showSecrets[fieldKey] ? 'password' : 'text'"
                  :placeholder="fieldMeta.default || `Enter ${fieldMeta.label}`"
                  v-model="formData[groupKey][fieldKey]"
                  class="w-full px-3 py-2 text-sm border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/20 transition-shadow font-mono"
                  :class="{ 'pr-10': fieldMeta.secret }"
                />
                <button
                  v-if="fieldMeta.secret"
                  @click="toggleSecret(fieldKey)"
                  class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
                >
                  <Eye v-if="!showSecrets[fieldKey]" class="w-4 h-4" />
                  <EyeOff v-else class="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="flex items-center justify-between pt-2">
          <router-link
            to="/"
            class="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Back to Chat
          </router-link>
          <button
            @click="saveSettings"
            :disabled="saving"
            class="px-6 py-2 bg-primary text-white text-sm font-medium rounded-xl hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-lg shadow-primary/20"
          >
            <span v-if="saving" class="flex items-center gap-2">
              <Loader2 class="w-3 h-3 animate-spin" />
              Saving...
            </span>
            <span v-else>Save Settings</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { AlertTriangle, Check, Lock, Eye, EyeOff, Loader2, Download } from 'lucide-vue-next'
import {
  getSettings,
  getSettingsSchema,
  getSettingsStatus,
  getEmbeddingStatus,
  updateSettings,
  type SettingsSchema,
  type SettingsData,
  type SettingsStatus,
  type EmbeddingStatus,
} from '@/api/settings'

// ==================== 常量 ====================

const groupLabels: Record<string, string> = {
  api_keys: 'API Keys',
  llm: 'LLM Configuration',
  knowledge: 'Knowledge Base',
  app: 'Application',
}

const groupDescriptions: Record<string, string> = {
  knowledge: 'Enable semantic search to find documents by meaning, not just keywords',
}

const providerOptions = [
  { value: 'auto', label: 'Auto (Recommended)', description: 'Use local model if available, otherwise OpenAI' },
  { value: 'local', label: 'Local Model (Offline)', description: 'BGE-M3, Chinese + English, ~1GB disk' },
  { value: 'openai', label: 'OpenAI Cloud', description: 'Requires API Key and internet connection' },
]

// ==================== 状态 ====================

const loading = ref(true)
const saving = ref(false)
const saveSuccess = ref(false)
const copied = ref(false)
const schema = ref<SettingsSchema>({})
const status = ref<SettingsStatus | null>(null)
const embeddingStatus = ref<EmbeddingStatus | null>(null)
const formData = reactive<SettingsData>({})
const showSecrets = reactive<Record<string, boolean>>({})

// Knowledge-specific computed state
const selectedProvider = ref('auto')

const isSemanticEnabled = computed(() => {
  const val = formData.knowledge?.SEMANTIC_SEARCH_ENABLED
  return val === 'true' || val === '1' || val === 'yes'
})

// ==================== 方法 ====================

function toggleSecret(key: string) {
  showSecrets[key] = !showSecrets[key]
}

function toggleSemanticSearch() {
  if (!formData.knowledge) formData.knowledge = {}
  formData.knowledge.SEMANTIC_SEARCH_ENABLED = isSemanticEnabled.value ? 'false' : 'true'
}

async function copyInstallCommand() {
  try {
    await navigator.clipboard.writeText('pip install llama-cpp-python')
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    // Fallback: do nothing
  }
}

async function loadAll() {
  loading.value = true
  try {
    const [schemaData, settingsData, statusData, embedStatus] = await Promise.all([
      getSettingsSchema(),
      getSettings(),
      getSettingsStatus(),
      getEmbeddingStatus().catch(() => null),
    ])

    schema.value = schemaData
    status.value = statusData
    embeddingStatus.value = embedStatus

    // Initialize formData from schema
    for (const [groupKey, groupSchema] of Object.entries(schemaData)) {
      formData[groupKey] = {}
      for (const fieldKey of Object.keys(groupSchema)) {
        formData[groupKey][fieldKey] = settingsData?.[groupKey]?.[fieldKey] || ''
      }
    }

    // Sync knowledge-specific state
    if (embedStatus) {
      selectedProvider.value = formData.knowledge?.EMBEDDING_PROVIDER || embedStatus.provider_setting || 'auto'
    }
  } catch (e) {
    console.error('Failed to load settings:', e)
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  saving.value = true
  saveSuccess.value = false

  /** 验证失败时回退引导到 Step 2，并显示对应错误提示 */
  function rollbackGuideToStep2(reason: string) {
    if (guideStore.isActive && guideStore.currentStep === 3) {
      guideStore.goToStep(2, reason)
    }
  }

  // 校验 1：必须展开选中一个 Provider
  if (!expandedProvider.value) {
    saveError.value = '请先展开并选中一个 Provider'
    rollbackGuideToStep2('请先选择一个 Provider 并填写 API Key')
    return
  }

  const selectedName = expandedProvider.value
  const selectedProvider = providers.value.find(p => p.name === selectedName)
  if (!selectedProvider) {
    saveError.value = '未找到选中的 Provider'
    rollbackGuideToStep2('请重新选择一个 Provider')
    return
  }

  // 校验 2：选中的 Provider 必须填写了 API Key
  const selectedKey = providerKeys[selectedName]?.trim()
  if (!selectedKey) {
    saveError.value = `请填写 ${selectedProvider.display_name} 的 API Key`
    rollbackGuideToStep2(`请填写 ${selectedProvider.display_name} 的 API Key 后再点击下一步`)
    return
  }

  saving.value = true

  try {
    // 校验 3：验证选中 Provider 的 API Key（如果已验证通过则跳过）
    if (!validateResults[selectedName]?.valid) {
      validating[selectedName] = true
      try {
        const customBaseUrl = providerBaseUrls[selectedName]?.trim() || undefined
        const result = await modelApi.validateKey(selectedName, selectedKey, customBaseUrl)
        validateResults[selectedName] = result
        if (!result.valid) {
          saveError.value = `${selectedProvider.display_name} 的 API Key 验证失败：${result.message || '请检查后重试'}`
          saving.value = false
          rollbackGuideToStep2(`API Key 验证失败，请检查 ${selectedProvider.display_name} 的 Key 后重试`)
          return
        }
      } catch (e: any) {
        saveError.value = `${selectedProvider.display_name} 的 API Key 验证失败，请检查后重试`
        saving.value = false
        rollbackGuideToStep2(`API Key 验证失败，请检查 ${selectedProvider.display_name} 的 Key 后重试`)
        return
      } finally {
        validating[selectedName] = false
      }
    }

    // 校验 4：验证通过后必须有可用模型
    const validResult = validateResults[selectedName]
    if (!validResult?.models?.length) {
      saveError.value = `${selectedProvider.display_name} 验证通过但未返回可用模型`
      saving.value = false
      rollbackGuideToStep2(`${selectedProvider.display_name} 未返回可用模型，请更换 Provider 或检查 Key`)
      return
    }

    // 构建 Settings API 格式
    const updates: SettingsData = { api_keys: {}, llm: {}, app: {} }

    // 保存选中 Provider 的 Key
    updates['api_keys'][selectedProvider.api_key_env] = selectedKey

    // 保存自定义 Base URL（如有）
    const baseUrl = providerBaseUrls[selectedName]?.trim()
    if (baseUrl) {
      const baseUrlEnv = selectedProvider.api_key_env.replace(/_API_KEY$/, '_BASE_URL')
      updates['api_keys'][baseUrlEnv] = baseUrl
    }

    // 同时保存其他已配置的 Provider（不丢失已有配置）
    for (const p of providers.value) {
      if (p.name === selectedName) continue
      const key = providerKeys[p.name]?.trim()
      if (key) {
        updates['api_keys'][p.api_key_env] = key
        const otherBaseUrl = providerBaseUrls[p.name]?.trim()
        if (otherBaseUrl) {
          const baseUrlEnv = p.api_key_env.replace(/_API_KEY$/, '_BASE_URL')
          updates['api_keys'][baseUrlEnv] = otherBaseUrl
        }
      }
    }

    await updateSettings(updates)

    // Refresh status
    const [statusData, embedStatus] = await Promise.all([
      getSettingsStatus(),
      getEmbeddingStatus().catch(() => null),
    ])
    status.value = statusData
    embeddingStatus.value = embedStatus

    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 3000)
  } catch (e) {
    console.error('Failed to save settings:', e)
  } finally {
    saving.value = false
  }
}

// ==================== 生命周期 ====================

onMounted(loadAll)
</script>

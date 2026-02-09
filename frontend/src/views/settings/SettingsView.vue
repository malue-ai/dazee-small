<template>
  <div class="min-h-screen bg-muted p-8">
    <div class="max-w-2xl mx-auto">
      <!-- 页面标题 -->
      <div class="mb-8">
        <h1 class="text-2xl font-semibold text-foreground">Settings</h1>
        <p class="mt-1 text-sm text-muted-foreground">配置 API Key</p>
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="flex items-center justify-center py-20">
        <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
        <span class="ml-3 text-sm text-muted-foreground">Loading...</span>
      </div>

      <!-- 配置表单 -->
      <div v-else class="space-y-6">
        <!-- 保存成功提示 -->
        <div v-if="saveSuccess" class="bg-success/10 border border-success/30 rounded-lg p-4">
          <div class="flex items-center gap-2">
            <Check class="w-4 h-4 text-success" />
            <p class="text-sm text-success">配置已保存成功</p>
          </div>
        </div>

        <!-- 保存失败 / 校验错误提示 -->
        <div v-if="saveError" class="bg-destructive/10 border border-destructive/30 rounded-lg p-4">
          <div class="flex items-center gap-2">
            <AlertTriangle class="w-4 h-4 text-destructive" />
            <p class="text-sm text-destructive">{{ saveError }}</p>
          </div>
        </div>

        <!-- ==================== Provider 卡片区域 ==================== -->
        <div ref="providerSectionRef">
          <h2 class="text-sm font-semibold text-foreground uppercase tracking-wide mb-3">
            API Providers
          </h2>

          <div class="space-y-3">
            <div
              v-for="p in providers"
              :key="p.name"
              :ref="el => setProviderCardRef(p.name, el)"
              class="bg-card rounded-lg border border-border overflow-hidden transition-shadow"
              :class="{ 'ring-2 ring-primary/30': expandedProvider === p.name }"
            >
              <!-- Provider 头部（点击展开/收起） -->
              <button
                class="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-muted/50 transition-colors"
                @click="toggleProvider(p.name)"
              >
                <span class="text-xl flex-shrink-0">{{ p.icon }}</span>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-medium text-foreground">{{ p.display_name }}</span>
                    <span
                      v-if="providerKeyState[p.name]?.configured"
                      class="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-success/10 text-success"
                    >
                      已配置
                    </span>
                    <span
                      v-else
                      class="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground"
                    >
                      未配置
                    </span>
                  </div>
                  <p class="text-xs text-muted-foreground truncate mt-0.5">{{ p.description }}</p>
                </div>
                <ChevronDown
                  class="w-4 h-4 text-muted-foreground flex-shrink-0 transition-transform duration-200"
                  :class="{ 'rotate-180': expandedProvider === p.name }"
                />
              </button>

              <!-- 展开内容 -->
              <div v-if="expandedProvider === p.name" class="border-t border-border px-4 py-4 space-y-4 bg-muted/30">
                <!-- API Key 输入框 -->
                <div>
                  <label class="flex items-center gap-1.5 text-xs font-medium text-foreground mb-1.5">
                    <Lock class="w-3 h-3 text-muted-foreground/50" />
                    API Key
                    <span class="text-muted-foreground/40 font-normal">{{ p.api_key_env }}</span>
                  </label>
                  <div class="flex gap-2">
                    <div class="relative flex-1">
                      <input
                        :type="showSecrets[p.name] ? 'text' : 'password'"
                        v-model="providerKeys[p.name]"
                        :placeholder="`Enter ${p.display_name} API Key`"
                        class="w-full px-3 py-2 text-sm border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20 transition-shadow font-mono pr-9"
                      />
                      <button
                        @click="showSecrets[p.name] = !showSecrets[p.name]"
                        class="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-muted-foreground hover:text-foreground"
                      >
                        <Eye v-if="!showSecrets[p.name]" class="w-3.5 h-3.5" />
                        <EyeOff v-else class="w-3.5 h-3.5" />
                      </button>
                    </div>
                    <button
                      @click="validateProviderKey(p.name)"
                      :disabled="!providerKeys[p.name]?.trim() || validating[p.name]"
                      class="px-3 py-2 text-xs font-medium rounded-lg border border-border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5 flex-shrink-0"
                    >
                      <Loader2 v-if="validating[p.name]" class="w-3 h-3 animate-spin" />
                      <ShieldCheck v-else class="w-3 h-3" />
                      验证
                    </button>
                  </div>
                </div>

                <!-- Base URL（可选） -->
                <div>
                  <label class="text-xs font-medium text-foreground mb-1.5 block">
                    Base URL
                    <span class="text-muted-foreground/40 font-normal ml-1">可选</span>
                  </label>
                  <input
                    type="text"
                    v-model="providerBaseUrls[p.name]"
                    :placeholder="p.base_url"
                    class="w-full px-3 py-2 text-sm border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20 transition-shadow font-mono text-muted-foreground"
                  />
                </div>

                <!-- 验证结果 -->
                <div
                  v-if="validateResults[p.name]"
                  class="rounded-lg px-3 py-2 text-xs"
                  :class="validateResults[p.name].valid
                    ? 'bg-success/10 text-success border border-success/20'
                    : 'bg-destructive/10 text-destructive border border-destructive/20'"
                >
                  <div class="flex items-center gap-1.5">
                    <CircleCheck v-if="validateResults[p.name].valid" class="w-3.5 h-3.5 flex-shrink-0" />
                    <AlertTriangle v-else class="w-3.5 h-3.5 flex-shrink-0" />
                    <span>{{ validateResults[p.name].message }}</span>
                  </div>
                  <!-- 验证通过：显示全部模型列表 -->
                  <div
                    v-if="validateResults[p.name].valid && validateResults[p.name].model_details?.length"
                    class="mt-2.5"
                  >
                    <div class="text-[10px] text-success/70 mb-1.5">
                      共 {{ validateResults[p.name].model_details.length }} 个可用模型
                    </div>
                    <div class="space-y-1 max-h-[240px] overflow-y-auto scrollbar-thin pr-1">
                      <div
                        v-for="m in validateResults[p.name].model_details"
                        :key="m.model_name"
                        class="flex items-center gap-2 rounded-lg px-2.5 py-1.5 border"
                        :class="m.in_catalog
                          ? 'bg-white/60 border-success/10'
                          : 'bg-white/30 border-border/50'"
                      >
                        <span
                          class="text-[11px] truncate min-w-0 flex-shrink"
                          :class="m.in_catalog ? 'font-medium text-foreground' : 'text-muted-foreground'"
                        >
                          {{ m.display_name }}
                        </span>
                        <div class="flex items-center gap-1 flex-shrink-0 ml-auto">
                          <span v-if="m.context_window" class="px-1.5 py-0.5 bg-muted rounded text-[9px] text-muted-foreground">
                            {{ formatContextWindow(m.context_window) }}
                          </span>
                          <span v-if="m.max_output_tokens && m.in_catalog" class="px-1.5 py-0.5 bg-muted rounded text-[9px] text-muted-foreground">
                            {{ formatContextWindow(m.max_output_tokens) }} out
                          </span>
                          <span v-if="m.supports_thinking" class="px-1.5 py-0.5 bg-primary/10 rounded text-[9px] text-primary">
                            Thinking
                          </span>
                          <span v-if="m.supports_vision" class="px-1.5 py-0.5 bg-primary/10 rounded text-[9px] text-primary">
                            Vision
                          </span>
                          <span v-if="m.supports_tools && m.in_catalog" class="px-1.5 py-0.5 bg-muted rounded text-[9px] text-muted-foreground">
                            Tools
                          </span>
                          <span v-if="!m.in_catalog" class="px-1.5 py-0.5 bg-muted/50 rounded text-[9px] text-muted-foreground/60 italic">
                            未收录
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                  <!-- Fallback: 没有 model_details 时显示纯名字 -->
                  <div
                    v-else-if="validateResults[p.name].valid && validateResults[p.name].models.length"
                    class="mt-2 flex flex-wrap gap-1"
                  >
                    <span
                      v-for="m in validateResults[p.name].models.slice(0, 8)"
                      :key="m"
                      class="px-1.5 py-0.5 bg-success/10 rounded text-[10px]"
                    >
                      {{ m }}
                    </span>
                    <span v-if="validateResults[p.name].models.length > 8" class="text-[10px] text-success/60">
                      +{{ validateResults[p.name].models.length - 8 }} more
                    </span>
                  </div>
                </div>

                <!-- Provider 支持的模型 -->
                <div v-if="p.models?.length" class="text-xs text-muted-foreground">
                  <span class="font-medium">支持模型：</span>
                  <span>{{ p.models.map(m => m.display_name).join('、') }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ==================== 操作按钮 ==================== -->
        <div class="flex items-center justify-between pt-2">
          <a
            ref="backToChatRef"
            @click="handleBackToChat"
            class="text-sm text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            ← 返回聊天
          </a>
          <button
            ref="saveBtnRef"
            @click="saveSettings"
            :disabled="saving"
            class="px-6 py-2 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <span v-if="saving" class="flex items-center gap-2">
              <Loader2 class="w-3 h-3 animate-spin" />
              验证保存中...
            </span>
            <span v-else>验证并保存</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import {
  Check, Lock, Eye, EyeOff, Loader2,
  CircleCheck, AlertTriangle, ChevronDown, ShieldCheck,
} from 'lucide-vue-next'
import {
  getSettings,
  getSettingsStatus,
  updateSettings,
  type SettingsData,
  type SettingsStatus,
} from '@/api/settings'
import { modelApi, type ProviderDetail, type ValidateKeyResult } from '@/api/models'
import { useGuideStore } from '@/stores/guide'

const router = useRouter()
const guideStore = useGuideStore()

// ==================== 状态 ====================

const loading = ref(true)
const saving = ref(false)
const saveSuccess = ref(false)
const saveError = ref('')
const status = ref<SettingsStatus | null>(null)

// Provider 相关状态
const providers = ref<ProviderDetail[]>([])
const expandedProvider = ref<string | null>(null)
const providerKeys = reactive<Record<string, string>>({})
const providerBaseUrls = reactive<Record<string, string>>({})
const showSecrets = reactive<Record<string, boolean>>({})
const validating = reactive<Record<string, boolean>>({})
const validateResults = reactive<Record<string, ValidateKeyResult>>({})

// Provider Key 配置状态（用于显示已配置/未配置标签）
const providerKeyState = computed(() => {
  const result: Record<string, { configured: boolean }> = {}
  for (const p of providers.value) {
    result[p.name] = {
      configured: p.api_key_configured || !!(providerKeys[p.name]?.trim()),
    }
  }
  return result
})

/** 判断是否为后端返回的脱敏 Key（如 "sk-xxxx...yyyy" 或 "***"） */
function isMaskedKey(key: string): boolean {
  if (!key) return false
  if (key === '***') return true
  // 后端脱敏格式：前6位 + ... + 后4位，总长度 < 20
  return key.includes('...') && key.length < 20
}

// ==================== 引导系统 Refs ====================

const saveBtnRef = ref<HTMLElement | null>(null)
const backToChatRef = ref<HTMLElement | null>(null)
const providerSectionRef = ref<HTMLElement | null>(null)
const providerCardRefs = reactive<Record<string, HTMLElement | null>>({})

function setProviderCardRef(name: string, el: any) {
  if (el) providerCardRefs[name] = (el.$el || el) as HTMLElement
}

// ==================== 方法 ====================

/** Format context window size for display (e.g. 200000 → "200K") */
function formatContextWindow(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(tokens % 1_000_000 === 0 ? 0 : 1)}M`
  if (tokens >= 1_000) return `${Math.round(tokens / 1_000)}K`
  return `${tokens}`
}

function toggleProvider(name: string) {
  expandedProvider.value = expandedProvider.value === name ? null : name
}

async function validateProviderKey(providerName: string) {
  const key = providerKeys[providerName]?.trim()
  if (!key) return

  validating[providerName] = true
  delete validateResults[providerName]

  try {
    const customBaseUrl = providerBaseUrls[providerName]?.trim() || undefined
    const result = await modelApi.validateKey(providerName, key, customBaseUrl)
    validateResults[providerName] = result
  } catch (e: any) {
    validateResults[providerName] = {
      valid: false,
      provider: providerName,
      message: e?.response?.data?.detail?.message || e?.message || '验证过程发生错误',
      models: [],
      model_details: [],
    }
  } finally {
    validating[providerName] = false
  }
}

// ==================== 数据加载 ====================

async function loadAll() {
  loading.value = true
  try {
    const [providerData, settingsData, statusData] = await Promise.all([
      modelApi.getSupportedProviders(),
      getSettings(),
      getSettingsStatus(),
    ])

    providers.value = providerData
    status.value = statusData

    // 初始化 Provider Key 输入框（从已有 settings 读取脱敏值）
    for (const p of providerData) {
      const existingKey = settingsData?.['api_keys']?.[p.api_key_env] || ''
      providerKeys[p.name] = existingKey
    }

    // 引导系统：如果有已配置的 Key，允许跳过
    if (guideStore.isActive) {
      const hasConfiguredKey = providerData.some(p => p.api_key_configured)
      guideStore.canSkip = hasConfiguredKey
    }
  } catch (e) {
    console.error('Failed to load settings:', e)
  } finally {
    loading.value = false
  }
}

// ==================== 保存设置 ====================

async function saveSettings() {
  saveError.value = ''
  saveSuccess.value = false

  /** 验证失败时回退引导到 Step 2 */
  function rollbackGuideToStep2(reason?: string) {
    if (guideStore.isActive && guideStore.currentStep === 3) {
      guideStore.goToStep(2, reason)
    }
  }

  // ==================== 收集所有需要处理的 Provider ====================
  interface ProviderToSave {
    detail: ProviderDetail
    key: string
    baseUrl?: string
    masked: boolean  // Key 是脱敏值（已配置且未修改）
  }

  const toSave: ProviderToSave[] = []

  for (const p of providers.value) {
    const key = providerKeys[p.name]?.trim()
    if (!key && !p.api_key_configured) continue // 没填 Key 且未配置过 → 跳过
    if (!key) continue // 没填 Key → 跳过

    toSave.push({
      detail: p,
      key,
      baseUrl: providerBaseUrls[p.name]?.trim() || undefined,
      masked: p.api_key_configured && isMaskedKey(key),
    })
  }

  // 校验：至少有一个 Provider 填写了 Key
  if (toSave.length === 0) {
    saveError.value = '请至少为一个 Provider 填写 API Key'
    rollbackGuideToStep2('请先选择一个 Provider 并填写 API Key')
    return
  }

  saving.value = true

  try {
    // ==================== 验证所有新填写的 Key ====================
    const failedProviders: string[] = []

    for (const item of toSave) {
      if (item.masked) continue // 脱敏值 → 跳过验证
      if (validateResults[item.detail.name]?.valid) continue // 已验证通过 → 跳过

      validating[item.detail.name] = true
      try {
        const result = await modelApi.validateKey(item.detail.name, item.key, item.baseUrl)
        validateResults[item.detail.name] = result
        if (!result.valid) {
          failedProviders.push(`${item.detail.display_name}: ${result.message || '验证失败'}`)
        }
      } catch (e: any) {
        failedProviders.push(`${item.detail.display_name}: ${e?.response?.data?.detail?.message || e?.message || '验证失败'}`)
        validateResults[item.detail.name] = {
          valid: false,
          provider: item.detail.name,
          message: e?.response?.data?.detail?.message || e?.message || '验证过程发生错误',
          models: [],
          model_details: [],
        }
      } finally {
        validating[item.detail.name] = false
      }
    }

    if (failedProviders.length > 0) {
      saveError.value = `以下 Provider 验证失败：\n${failedProviders.join('；')}`
      saving.value = false
      rollbackGuideToStep2('API Key 验证失败，请检查后重试')
      return
    }

    // ==================== 构建更新对象 ====================
    const updates: SettingsData = { api_keys: {} }
    let firstValidModels: string[] = []

    for (const item of toSave) {
      // 保存 API Key（脱敏值不发送，后端会忽略）
      if (!item.masked) {
        updates['api_keys'][item.detail.api_key_env] = item.key
      }

      // 保存自定义 Base URL（如有）
      if (item.baseUrl) {
        const baseUrlEnv = item.detail.api_key_env.replace(/_API_KEY$/, '_BASE_URL')
        updates['api_keys'][baseUrlEnv] = item.baseUrl
      }

      // 记录第一个有验证结果的模型列表（用于默认模型）
      if (!firstValidModels.length) {
        const vr = validateResults[item.detail.name]
        if (vr?.models?.length) firstValidModels = vr.models
      }
    }

    // 默认模型：取第一个验证通过的 Provider 的首个模型
    if (firstValidModels.length) {
      updates.llm = {}
      updates.llm.COT_AGENT_MODEL = firstValidModels[0]
    }

    await updateSettings(updates)

    // ==================== 激活所有新填写 Key 的 Provider 模型 ====================
    for (const item of toSave) {
      if (item.masked) continue // 脱敏值不需要重新激活
      try {
        await modelApi.activateProvider(item.detail.name, item.key, item.baseUrl)
      } catch (e: any) {
        console.warn(`模型激活失败 [${item.detail.name}]（不影响 Key 保存）:`, e?.message)
      }
    }

    // Refresh status
    const statusData = await getSettingsStatus()
    status.value = statusData

    saveSuccess.value = true

    // 引导系统：保存成功后允许跳过 + 推进步骤
    if (guideStore.isActive) {
      guideStore.canSkip = true
    }
    if (guideStore.isActive && guideStore.currentStep === 3) {
      guideStore.nextStep() // → step 4
      nextTick(() => {
        if (backToChatRef.value) {
          guideStore.setTarget(backToChatRef.value)
        }
      })
    }

    setTimeout(() => { saveSuccess.value = false }, 3000)
  } catch (e: any) {
    console.error('Failed to save settings:', e)
    saveError.value = e?.response?.data?.detail?.message || e?.message || '保存失败，请重试'
  } finally {
    saving.value = false
  }
}

/** 返回聊天 */
function handleBackToChat() {
  if (guideStore.isActive && guideStore.currentStep === 4) {
    guideStore.nextStep() // → step 5
  }
  router.push('/')
}

// ==================== 引导系统交互协调 ====================

/** 当 Step 2 时，注册"下一步"前置校验 */
function registerGuideValidation(step: number) {
  if (step === 2) {
    guideStore.setBeforeNextStep(() => {
      // 检查是否有任何 Provider 填写了 Key 或已配置
      const hasAnyKey = providers.value.some(p =>
        providerKeys[p.name]?.trim() || p.api_key_configured
      )
      if (!hasAnyKey) {
        return '请至少为一个 Provider 填写 API Key'
      }
      return true
    })
  } else {
    guideStore.setBeforeNextStep(null)
  }
}

/** 根据当前步骤设置高亮目标元素 */
function applyGuideTarget(step: number) {
  registerGuideValidation(step)
  switch (step) {
    case 2: {
      if (providerSectionRef.value) {
        guideStore.setTarget(providerSectionRef.value)
      }
      break
    }
    case 3:
      if (saveBtnRef.value) guideStore.setTarget(saveBtnRef.value)
      break
    case 4:
      if (backToChatRef.value) guideStore.setTarget(backToChatRef.value)
      break
  }
}

// ==================== 生命周期 ====================

onMounted(async () => {
  await loadAll()

  if (guideStore.isActive) {
    nextTick(() => {
      applyGuideTarget(guideStore.currentStep)
    })
  }
})

watch(() => guideStore.currentStep, (step) => {
  if (!guideStore.isActive) return
  nextTick(() => applyGuideTarget(step))
})

onUnmounted(() => {
  if (guideStore.isActive) {
    guideStore.setBeforeNextStep(null)
  }
})
</script>

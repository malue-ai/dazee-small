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
          class="bg-white rounded-lg border border-border overflow-hidden"
        >
          <!-- 分组标题 -->
          <div class="px-6 py-4 border-b border-border bg-muted/50">
            <h2 class="text-sm font-semibold text-foreground uppercase tracking-wide">
              {{ groupLabels[groupKey] || groupKey }}
            </h2>
            <p class="text-xs text-muted-foreground/50 mt-0.5" v-if="status?.summary?.[groupKey]">
              {{ status.summary[groupKey].configured }} / {{ status.summary[groupKey].total }} configured
            </p>
          </div>

          <!-- 配置项 -->
          <div class="divide-y divide-gray-100">
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
                  class="w-full px-3 py-2 text-sm border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20 transition-shadow font-mono"
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
            class="px-6 py-2 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
import { ref, reactive, onMounted } from 'vue'
import { AlertTriangle, Check, Lock, Eye, EyeOff, Loader2 } from 'lucide-vue-next'
import {
  getSettings,
  getSettingsSchema,
  getSettingsStatus,
  updateSettings,
  type SettingsSchema,
  type SettingsData,
  type SettingsStatus,
} from '@/api/settings'

// ==================== 常量 ====================

const groupLabels: Record<string, string> = {
  api_keys: 'API Keys',
  llm: 'LLM Configuration',
  app: 'Application',
}

// ==================== 状态 ====================

const loading = ref(true)
const saving = ref(false)
const saveSuccess = ref(false)
const schema = ref<SettingsSchema>({})
const status = ref<SettingsStatus | null>(null)
const formData = reactive<SettingsData>({})
const showSecrets = reactive<Record<string, boolean>>({})

// ==================== 方法 ====================

function toggleSecret(key: string) {
  showSecrets[key] = !showSecrets[key]
}

async function loadAll() {
  loading.value = true
  try {
    const [schemaData, settingsData, statusData] = await Promise.all([
      getSettingsSchema(),
      getSettings(),
      getSettingsStatus(),
    ])

    schema.value = schemaData
    status.value = statusData

    // 初始化 formData
    for (const [groupKey, groupSchema] of Object.entries(schemaData)) {
      formData[groupKey] = {}
      for (const fieldKey of Object.keys(groupSchema)) {
        formData[groupKey][fieldKey] = settingsData?.[groupKey]?.[fieldKey] || ''
      }
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

  try {
    // 只发送非空值
    const updates: SettingsData = {}
    for (const [groupKey, fields] of Object.entries(formData)) {
      updates[groupKey] = {}
      for (const [key, value] of Object.entries(fields)) {
        if (value) {
          updates[groupKey][key] = value
        }
      }
    }

    await updateSettings(updates)
    status.value = await getSettingsStatus()
    saveSuccess.value = true

    // 3 秒后隐藏成功提示
    setTimeout(() => {
      saveSuccess.value = false
    }, 3000)
  } catch (e) {
    console.error('Failed to save settings:', e)
  } finally {
    saving.value = false
  }
}

// ==================== 生命周期 ====================

onMounted(loadAll)
</script>

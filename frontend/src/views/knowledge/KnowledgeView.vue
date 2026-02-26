<template>
  <div class="h-full flex flex-col overflow-hidden bg-white">
    <!-- 顶部工具栏 -->
    <div class="h-16 flex items-center justify-between px-6 border-b border-border bg-white sticky top-0 z-10 flex-shrink-0">
      <div class="flex items-center gap-4">
        <h1 class="text-lg font-bold flex items-center gap-2 text-foreground">
          <BookOpen class="w-6 h-6 text-primary" />
          知识库
        </h1>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="flex-1 overflow-y-auto scrollbar-overlay">
      <div class="max-w-xl mx-auto py-10 px-6 space-y-6">

        <!-- 搜索能力状态卡片 -->
        <div class="bg-white rounded-2xl border border-border p-6 space-y-4">
          <h2 class="text-sm font-semibold text-foreground">搜索能力</h2>

          <!-- 关键词搜索（始终可用） -->
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-success/10 flex items-center justify-center flex-shrink-0">
              <Check class="w-4 h-4 text-success" />
            </div>
            <div>
              <p class="text-sm font-medium text-foreground">关键词搜索</p>
              <p class="text-xs text-muted-foreground">SQLite FTS5 全文检索，支持中英文，零配置可用</p>
            </div>
          </div>

          <!-- 语义搜索（需要配置） -->
          <div class="flex items-center gap-3">
            <div
              class="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
              :class="embeddingStatus?.current_provider ? 'bg-success/10' : 'bg-muted'"
            >
              <Check v-if="embeddingStatus?.current_provider" class="w-4 h-4 text-success" />
              <Search v-else class="w-4 h-4 text-muted-foreground" />
            </div>
            <div class="flex-1">
              <p class="text-sm font-medium text-foreground">
                语义搜索
                <span
                  v-if="embeddingStatus?.current_provider"
                  class="ml-2 text-xs font-normal text-success"
                >
                  已启用 ({{ embeddingStatus.current_provider === 'local' ? '本地模型' : 'OpenAI' }})
                </span>
                <span v-else class="ml-2 text-xs font-normal text-muted-foreground">未启用</span>
              </p>
              <p class="text-xs text-muted-foreground">
                理解搜索意图，如搜"天气"也能匹配"气候"、"温度"
              </p>
            </div>
          </div>
        </div>

        <!-- 语义搜索安装引导（未启用时显示） -->
        <div
          v-if="!embeddingStatus?.semantic_enabled && !dismissed"
          class="bg-accent border border-primary/20 rounded-2xl p-6"
        >
          <div class="flex items-start gap-4">
            <div class="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
              <Sparkles class="w-5 h-5 text-primary" />
            </div>
            <div class="flex-1 space-y-3">
              <div>
                <p class="text-sm font-semibold text-accent-foreground">开启语义搜索</p>
                <p class="text-xs text-accent-foreground/70 mt-1">
                  下载本地模型后，搜索不再只是匹配文字——能真正理解你要找什么。
                  离线可用，无需 API Key，数据不出本机。
                </p>
              </div>

              <div class="bg-white rounded-xl border border-border p-3 space-y-2">
                <div class="flex items-center gap-2">
                  <Download class="w-4 h-4 text-muted-foreground flex-shrink-0" />
                  <p class="text-xs text-foreground">
                    <span class="font-medium">BGE-M3 Q4</span>
                    <span class="text-muted-foreground ml-1">中英文双语 · 438MB · 离线可用</span>
                  </p>
                </div>
                <!-- 下载进度条 -->
                <div v-if="downloadState === 'downloading'" class="space-y-1.5">
                  <div class="w-full h-1.5 rounded-full bg-muted overflow-hidden">
                    <div class="h-full rounded-full bg-primary animate-pulse" style="width: 100%" />
                  </div>
                  <p class="text-xs text-muted-foreground">正在下载模型，请稍候…</p>
                </div>
                <!-- 下载失败 -->
                <p v-if="downloadState === 'error'" class="text-xs text-destructive">
                  {{ downloadError }}
                </p>
              </div>

              <div class="flex items-center gap-3">
                <button
                  v-if="downloadState !== 'downloading'"
                  @click="handleDownload"
                  class="px-4 py-2 bg-primary text-white text-xs font-medium rounded-xl hover:bg-primary-hover transition-colors shadow-lg shadow-primary/20 flex items-center gap-1.5"
                >
                  <Download class="w-3.5 h-3.5" />
                  一键下载并启用
                </button>
                <button
                  v-if="downloadState !== 'downloading'"
                  @click="dismissed = true"
                  class="px-4 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  暂不需要
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 知识库管理占位 -->
        <div class="bg-white rounded-2xl border border-border p-6">
          <div class="flex flex-col items-center justify-center py-8 text-muted-foreground/50">
            <div class="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mb-4 border border-border">
              <FolderOpen class="w-8 h-8 opacity-30" />
            </div>
            <p class="text-sm font-medium text-muted-foreground">文件夹管理功能开发中</p>
            <p class="text-xs mt-1 text-muted-foreground/50">可在 config.yaml 中配置 knowledge.directories</p>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { BookOpen, Check, Search, Sparkles, FolderOpen, Download } from 'lucide-vue-next'
import {
  getEmbeddingStatus,
  setupSemanticSearch,
  getSemanticDownloadStatus,
  resetSemanticDownloadStatus,
  type EmbeddingStatus,
} from '@/api/settings'
import { useNotificationStore } from '@/stores/notification'

const notify = useNotificationStore()

const embeddingStatus = ref<EmbeddingStatus | null>(null)
const dismissed = ref(false)

type DownloadState = 'idle' | 'downloading' | 'done' | 'error'
const downloadState = ref<DownloadState>('idle')
const downloadError = ref('')

/** 轮询定时器 */
let pollTimer: ReturnType<typeof setInterval> | null = null
let isPolling = false

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

/** 开始轮询后台下载状态 */
function startPolling(notifId: string) {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (isPolling) return
    isPolling = true
    try {
      const status = await getSemanticDownloadStatus()
      if (status.status === 'done') {
        stopPolling()
        downloadState.value = 'done'
        notify.update(notifId, {
          type: 'success',
          title: '语义搜索已启用',
          message: `本地模型下载完成并自动生效${status.source === 'mirror' ? '（国内镜像）' : ''}`,
        })
        embeddingStatus.value = await getEmbeddingStatus()
        try { await resetSemanticDownloadStatus() } catch { /* ignore */ }
      } else if (status.status === 'error') {
        stopPolling()
        downloadState.value = 'error'
        downloadError.value = status.error || '下载失败，请检查网络后重试'
        notify.update(notifId, {
          type: 'error',
          title: '模型下载失败',
          message: status.error || '请检查网络连接',
        })
      }
    } catch {
      // polling failure, keep trying
    } finally {
      isPolling = false
    }
  }, 2000)
}

async function handleDownload() {
  downloadState.value = 'downloading'
  downloadError.value = ''

  const notifId = notify.push({
    type: 'progress',
    title: '正在下载语义模型',
    message: 'BGE-M3 Q4（438MB），后台下载中，可离开此页面…',
    progress: { step: 0, total: 1 },
  })

  try {
    const result = await setupSemanticSearch('local')

    if (result.downloading) {
      // 后端已启动后台下载，开始轮询
      startPolling(notifId)
      return
    }

    if (result.success) {
      downloadState.value = 'done'
      notify.update(notifId, {
        type: 'success',
        title: '语义搜索已启用',
        message: '本地模型已就绪并自动生效',
      })
      embeddingStatus.value = await getEmbeddingStatus()
    } else {
      downloadState.value = 'error'
      downloadError.value = result.error || '下载失败，请检查网络后重试'
      notify.update(notifId, {
        type: 'error',
        title: '模型下载失败',
        message: result.error || '请检查网络连接',
      })
    }
  } catch (e: any) {
    downloadState.value = 'error'
    downloadError.value = e?.message || '网络异常，请稍后重试'
    notify.update(notifId, {
      type: 'error',
      title: '模型下载失败',
      message: e?.message || '网络异常',
    })
  }
}

onMounted(async () => {
  try {
    embeddingStatus.value = await getEmbeddingStatus()
  } catch {
    // API not available, keep null
  }

  // 检查是否有后台下载正在进行（从其他页面发起的）
  try {
    const status = await getSemanticDownloadStatus()
    if (status.status === 'downloading') {
      downloadState.value = 'downloading'
      const notifId = notify.push({
        type: 'progress',
        title: '正在下载语义模型',
        message: 'BGE-M3 Q4（438MB），后台下载中…',
        progress: { step: 0, total: 1 },
      })
      startPolling(notifId)
    } else if (status.status === 'done') {
      // 下载已完成但前端未确认
      embeddingStatus.value = await getEmbeddingStatus()
      try { await resetSemanticDownloadStatus() } catch { /* ignore */ }
    }
  } catch {
    // ignore
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

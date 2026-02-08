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
    <div class="flex-1 overflow-y-auto scrollbar-thin">
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
                  安装本地模型后，搜索不再只是匹配文字——能真正理解你要找什么。
                  离线可用，无需 API Key，数据不出本机。
                </p>
              </div>

              <div class="bg-white rounded-xl border border-border p-3 space-y-2">
                <p class="text-xs font-medium text-muted-foreground">安装命令</p>
                <div class="flex items-center gap-2">
                  <code class="flex-1 px-3 py-1.5 bg-muted rounded-lg text-xs font-mono text-foreground">
                    pip install llama-cpp-python
                  </code>
                  <button
                    @click="copyCommand"
                    class="px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 rounded-lg transition-colors flex-shrink-0"
                  >
                    {{ copied ? '已复制' : '复制' }}
                  </button>
                </div>
                <p class="text-xs text-muted-foreground">
                  默认模型：<span class="font-medium">BGE-M3 Q4</span>（中英文双语，424MB，首次使用自动下载到 data/shared/models/）
                </p>
              </div>

              <div class="flex items-center gap-3">
                <router-link
                  to="/settings"
                  class="px-4 py-2 bg-primary text-white text-xs font-medium rounded-xl hover:bg-primary-hover transition-colors shadow-lg shadow-primary/20"
                >
                  去设置页开启
                </router-link>
                <button
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
import { ref, onMounted } from 'vue'
import { BookOpen, Check, Search, Sparkles, FolderOpen } from 'lucide-vue-next'
import { getEmbeddingStatus, type EmbeddingStatus } from '@/api/settings'

const embeddingStatus = ref<EmbeddingStatus | null>(null)
const dismissed = ref(false)
const copied = ref(false)

async function copyCommand() {
  try {
    await navigator.clipboard.writeText('pip install llama-cpp-python')
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    // Fallback
  }
}

onMounted(async () => {
  try {
    embeddingStatus.value = await getEmbeddingStatus()
  } catch {
    // API not available, keep null
  }
})
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden bg-background">
    <!-- Top toolbar -->
    <div class="h-14 flex items-center justify-between px-6 border-b border-border bg-background sticky top-0 z-10 flex-shrink-0">
      <div class="flex items-center gap-4">
        <router-link
          to="/"
          class="flex items-center gap-1.5 px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
        >
          <ArrowLeft class="w-4 h-4" />
          <span>返回</span>
        </router-link>

        <div class="w-px h-5 bg-border"></div>

        <!-- Status filter tabs -->
        <div class="flex items-center gap-1 bg-muted rounded-lg p-1">
          <button
            v-for="tab in statusTabs"
            :key="tab.value"
            @click="store.setStatusFilter(tab.value)"
            class="px-3 py-1.5 rounded-md text-sm font-medium transition-all"
            :class="store.statusFilter === tab.value
              ? 'bg-card text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground'"
          >
            {{ tab.label }}
            <span v-if="store.statusCounts[tab.value]" class="ml-1 text-xs opacity-60">{{ store.statusCounts[tab.value] }}</span>
          </button>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <button
          @click="store.fetchEntries()"
          :disabled="store.loading"
          class="flex items-center gap-1.5 px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
        >
          <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': store.loading }" />
          <span>刷新</span>
        </button>
        <button
          @click="showCreateModal = true"
          class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-xl bg-primary text-primary-foreground hover:bg-primary-hover shadow-sm transition-colors"
        >
          <Plus class="w-4 h-4" />
          <span>新建策略</span>
        </button>
      </div>
    </div>

    <!-- Main content -->
    <div class="flex-1 overflow-y-auto scrollbar-thin p-6">
      <!-- Loading -->
      <div v-if="store.loading && store.entries.length === 0" class="flex items-center justify-center py-20">
        <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
      </div>

      <!-- Empty state -->
      <div v-else-if="store.isEmpty" class="flex flex-col items-center justify-center py-20 text-muted-foreground/50">
        <div class="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mb-4 border border-border">
          <BookOpen class="w-8 h-8 opacity-30" />
        </div>
        <p class="text-sm font-medium text-muted-foreground mb-1">暂无策略</p>
        <p class="text-xs text-muted-foreground/60">在聊天中使用工具完成任务后，AI 会自动学习成功模式</p>
      </div>

      <!-- Entry list -->
      <div v-else class="max-w-4xl mx-auto space-y-3">
        <div
          v-for="entry in store.filteredEntries"
          :key="entry.id"
          class="bg-card border border-border rounded-2xl p-5 hover:shadow-sm transition-all cursor-pointer"
          :class="{ 'ring-2 ring-primary/30': selectedId === entry.id }"
          @click="toggleDetail(entry)"
        >
          <!-- Header -->
          <div class="flex items-start justify-between gap-4 mb-2">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <h3 class="text-sm font-medium text-foreground truncate">{{ entry.name }}</h3>
                <span class="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-lg flex-shrink-0" :class="statusClass(entry.status)">
                  {{ statusLabel(entry.status) }}
                </span>
                <span v-if="entry.is_stale" class="inline-flex items-center px-1.5 py-0.5 text-xs text-muted-foreground bg-muted rounded-lg">过期</span>
              </div>
              <p class="text-xs text-muted-foreground line-clamp-2">{{ entry.description }}</p>
            </div>
            <div class="text-xs text-muted-foreground/60 whitespace-nowrap flex-shrink-0">
              {{ formatDate(entry.created_at) }}
            </div>
          </div>

          <!-- Tool sequence -->
          <div v-if="entry.strategy?.suggested_tools?.length" class="flex items-center gap-1 flex-wrap mb-3">
            <span
              v-for="(tool, idx) in entry.strategy.suggested_tools.slice(0, 5)"
              :key="idx"
              class="inline-flex items-center gap-0.5"
            >
              <span class="px-2 py-0.5 text-xs bg-muted text-muted-foreground rounded-lg">{{ tool }}</span>
              <ChevronRight v-if="idx < Math.min(entry.strategy.suggested_tools.length, 5) - 1" class="w-3 h-3 text-muted-foreground/40" />
            </span>
            <span v-if="entry.strategy.suggested_tools.length > 5" class="text-xs text-muted-foreground/40">+{{ entry.strategy.suggested_tools.length - 5 }}</span>
          </div>

          <!-- Metrics + actions -->
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-4 text-xs text-muted-foreground/60">
              <span v-if="entry.quality_metrics?.success_rate != null">成功率 {{ Math.round((entry.quality_metrics.success_rate ?? 0) * 100) }}%</span>
              <span v-if="entry.quality_metrics?.avg_turns != null">~{{ Math.round(entry.quality_metrics.avg_turns ?? 0) }} 步</span>
              <span>使用 {{ entry.usage_count }} 次</span>
              <span class="capitalize">{{ entry.source }}</span>
            </div>

            <div class="flex items-center gap-1" @click.stop>
              <button
                v-if="entry.status === 'draft' || entry.status === 'pending'"
                @click="handleAction(entry.id, 'approve')"
                :disabled="store.actionLoading"
                class="px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/10 rounded-lg transition-colors"
              >通过</button>
              <button
                v-if="entry.status === 'draft' || entry.status === 'pending'"
                @click="handleAction(entry.id, 'reject')"
                :disabled="store.actionLoading"
                class="px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
              >拒绝</button>
              <button
                v-if="entry.status === 'approved'"
                @click="handleAction(entry.id, 'deprecate')"
                :disabled="store.actionLoading"
                class="px-2.5 py-1 text-xs text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
              >废弃</button>
              <button
                @click="handleDelete(entry.id)"
                :disabled="store.actionLoading"
                class="px-2.5 py-1 text-xs text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors"
              >
                <Trash2 class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <!-- Expanded detail panel -->
          <Transition
            enter-active-class="transition-all duration-200 ease-out"
            enter-from-class="opacity-0 max-h-0"
            enter-to-class="opacity-100 max-h-[600px]"
            leave-active-class="transition-all duration-150 ease-in"
            leave-from-class="opacity-100 max-h-[600px]"
            leave-to-class="opacity-0 max-h-0"
          >
            <div v-if="selectedId === entry.id" class="mt-4 pt-4 border-t border-border overflow-hidden" @click.stop>
              <div class="grid grid-cols-2 gap-4">
                <!-- Editable name -->
                <div>
                  <label class="block text-xs font-medium text-muted-foreground mb-1">名称</label>
                  <input
                    v-model="editForm.name"
                    class="w-full px-3 py-2 text-sm bg-muted border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/30"
                  />
                </div>
                <!-- Task types -->
                <div>
                  <label class="block text-xs font-medium text-muted-foreground mb-1">任务类型</label>
                  <input
                    :value="editForm.trigger?.task_types?.join(', ') || ''"
                    @change="onTaskTypesChange"
                    placeholder="general, data_analysis"
                    class="w-full px-3 py-2 text-sm bg-muted border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/30"
                  />
                </div>
                <!-- Description -->
                <div class="col-span-2">
                  <label class="block text-xs font-medium text-muted-foreground mb-1">描述</label>
                  <textarea
                    v-model="editForm.description"
                    rows="2"
                    class="w-full px-3 py-2 text-sm bg-muted border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
                  />
                </div>
                <!-- Read-only info -->
                <div class="col-span-2 flex items-center gap-4 text-xs text-muted-foreground/50">
                  <span>ID: {{ entry.id }}</span>
                  <span v-if="entry.reviewed_by">审核: {{ entry.reviewed_by }}</span>
                  <span>更新: {{ formatDate(entry.updated_at) }}</span>
                </div>
                <!-- Save button -->
                <div class="col-span-2 flex justify-end">
                  <button
                    @click="saveEdit(entry.id)"
                    :disabled="store.actionLoading"
                    class="px-4 py-1.5 text-sm font-medium rounded-xl bg-primary text-primary-foreground hover:bg-primary-hover shadow-sm transition-colors"
                  >
                    {{ store.actionLoading ? '保存中...' : '保存修改' }}
                  </button>
                </div>
              </div>
            </div>
          </Transition>
        </div>
      </div>
    </div>

    <!-- Create modal -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition duration-150 ease-in"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div v-if="showCreateModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm" @click.self="showCreateModal = false">
          <div class="bg-card rounded-3xl shadow-2xl border border-border w-full max-w-lg p-6">
            <h2 class="text-base font-semibold text-foreground mb-4">新建策略</h2>
            <div class="space-y-3">
              <div>
                <label class="block text-xs font-medium text-muted-foreground mb-1">名称 *</label>
                <input v-model="createForm.name" placeholder="如：网络搜索与信息整理" class="w-full px-3 py-2 text-sm bg-muted border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/30" />
              </div>
              <div>
                <label class="block text-xs font-medium text-muted-foreground mb-1">描述 *</label>
                <textarea v-model="createForm.description" rows="3" placeholder="描述这个策略适用于什么场景" class="w-full px-3 py-2 text-sm bg-muted border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none" />
              </div>
              <div>
                <label class="block text-xs font-medium text-muted-foreground mb-1">任务类型</label>
                <input v-model="createTaskTypes" placeholder="general, data_analysis（逗号分隔）" class="w-full px-3 py-2 text-sm bg-muted border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/30" />
              </div>
              <div>
                <label class="block text-xs font-medium text-muted-foreground mb-1">建议工具</label>
                <input v-model="createSuggestedTools" placeholder="browser, nodes（逗号分隔）" class="w-full px-3 py-2 text-sm bg-muted border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/30" />
              </div>
            </div>
            <div class="flex justify-end gap-2 mt-6">
              <button @click="showCreateModal = false" class="px-4 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted rounded-xl transition-colors">取消</button>
              <button
                @click="handleCreate"
                :disabled="!createForm.name || !createForm.description || store.actionLoading"
                class="px-4 py-2 text-sm font-medium rounded-xl bg-primary text-primary-foreground hover:bg-primary-hover shadow-sm transition-colors disabled:opacity-50"
              >
                {{ store.actionLoading ? '创建中...' : '创建' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { usePlaybookStore } from '@/stores/playbook'
import type { PlaybookEntry, PlaybookStatus } from '@/types'
import { ArrowLeft, RefreshCw, Plus, Loader2, BookOpen, ChevronRight, Trash2 } from 'lucide-vue-next'

const store = usePlaybookStore()

const selectedId = ref<string | null>(null)
const showCreateModal = ref(false)

const editForm = reactive({
  name: '',
  description: '',
  trigger: { task_types: [] as string[] },
})

const createForm = reactive({ name: '', description: '' })
const createTaskTypes = ref('')
const createSuggestedTools = ref('')

const statusTabs: { value: PlaybookStatus | 'all'; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'draft', label: '草稿' },
  { value: 'pending', label: '待审核' },
  { value: 'approved', label: '已发布' },
  { value: 'deprecated', label: '已废弃' },
]

function statusClass(status: PlaybookStatus) {
  switch (status) {
    case 'approved': return 'bg-success/10 text-success'
    case 'pending': case 'draft': return 'bg-primary/10 text-primary'
    case 'rejected': return 'bg-destructive/10 text-destructive'
    case 'deprecated': return 'bg-muted text-muted-foreground'
    default: return 'bg-muted text-muted-foreground'
  }
}

function statusLabel(status: PlaybookStatus) {
  const map: Record<string, string> = { draft: '草稿', pending: '待审核', approved: '已发布', rejected: '已拒绝', deprecated: '已废弃' }
  return map[status] || status
}

function formatDate(iso: string) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function toggleDetail(entry: PlaybookEntry) {
  if (selectedId.value === entry.id) {
    selectedId.value = null
    return
  }
  selectedId.value = entry.id
  editForm.name = entry.name
  editForm.description = entry.description
  editForm.trigger = { task_types: [...(entry.trigger?.task_types || [])] }
}

function onTaskTypesChange(e: Event) {
  const val = (e.target as HTMLInputElement).value
  editForm.trigger.task_types = val.split(',').map(s => s.trim()).filter(Boolean)
}

async function saveEdit(id: string) {
  await store.editEntry(id, {
    name: editForm.name,
    description: editForm.description,
    trigger: editForm.trigger,
  })
}

async function handleAction(id: string, action: 'approve' | 'reject' | 'deprecate') {
  await store.changeStatus(id, action)
}

async function handleDelete(id: string) {
  await store.removeEntry(id)
  if (selectedId.value === id) selectedId.value = null
}

async function handleCreate() {
  const taskTypes = createTaskTypes.value.split(',').map(s => s.trim()).filter(Boolean)
  const suggestedTools = createSuggestedTools.value.split(',').map(s => s.trim()).filter(Boolean)
  const entry = await store.addEntry({
    name: createForm.name,
    description: createForm.description,
    trigger: taskTypes.length ? { task_types: taskTypes } : {},
    strategy: suggestedTools.length ? { suggested_tools: suggestedTools } : {},
  })
  if (entry) {
    showCreateModal.value = false
    createForm.name = ''
    createForm.description = ''
    createTaskTypes.value = ''
    createSuggestedTools.value = ''
  }
}

onMounted(() => {
  store.fetchEntries()
})
</script>

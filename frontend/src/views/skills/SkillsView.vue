<template>
  <div class="h-full flex flex-col overflow-hidden bg-white">
    <!-- 顶部工具栏 -->
    <div class="h-16 flex items-center justify-between px-6 border-b border-border bg-white sticky top-0 z-10 flex-shrink-0">
      <div class="flex items-center gap-4">
        <h1 class="text-lg font-bold flex items-center gap-2 text-foreground">
          <Puzzle class="w-6 h-6 text-primary" />
          Skills 全局库
        </h1>
        <div class="text-sm text-muted-foreground bg-muted px-2.5 py-1 rounded-md border border-border">
          共 {{ globalSkills.length }} 个 Skill
        </div>
      </div>
      <div class="flex items-center gap-3">
        <button 
          @click="fetchGlobalSkills" 
          :disabled="loading"
          class="p-2.5 bg-muted border border-border rounded-xl text-muted-foreground hover:bg-muted hover:text-primary transition-all"
          title="刷新"
        >
          <RefreshCw class="w-4 h-4" :class="loading ? 'animate-spin' : ''" />
        </button>
        <button 
          @click="showUploadModal = true"
          class="flex items-center gap-2 px-5 py-2.5 bg-primary text-white text-sm font-medium rounded-xl hover:bg-primary-hover transition-all shadow-lg shadow-primary/20 active:scale-95"
        >
          <Upload class="w-4 h-4" />
          上传 Skill
        </button>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="flex-1 flex overflow-hidden">
      <!-- 左侧 Skill 列表 -->
      <div class="w-72 border-r border-border bg-muted overflow-y-auto p-4 flex flex-col flex-shrink-0">
        <!-- 搜索框 -->
        <div class="relative mb-4 group">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/50 group-focus-within:text-primary transition-colors" />
          <input 
            v-model="searchQuery" 
            type="text" 
            placeholder="搜索 Skill..."
            class="w-full pl-9 pr-4 py-2 bg-white border border-border rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all placeholder-gray-400"
          >
        </div>

        <!-- 加载中 -->
        <div v-if="loading" class="flex items-center justify-center py-12 text-muted-foreground/50">
          <Loader2 class="w-6 h-6 animate-spin mr-2" /> 加载中...
        </div>

        <!-- 空状态 -->
        <div v-else-if="filteredSkills.length === 0" class="text-center py-12 text-muted-foreground/50 bg-white/50 rounded-2xl border border-dashed border-border">
          <Puzzle class="w-8 h-8 mx-auto mb-2 text-gray-300" />
          <p class="text-sm">暂无 Skill</p>
          <p class="text-xs mt-1">上传新的 Skill 来扩展能力</p>
        </div>

        <!-- Skill 列表 -->
        <div v-else class="space-y-2">
          <div
            v-for="skill in filteredSkills"
            :key="skill.name"
            @click="selectSkill(skill)"
            class="p-4 rounded-xl cursor-pointer transition-all duration-200 border"
            :class="selectedSkill?.name === skill.name 
              ? 'bg-white shadow-md border-primary/20 ring-1 ring-primary/10' 
              : 'bg-white border-border hover:border-primary/50 hover:shadow-sm'"
          >
            <div class="flex items-start justify-between mb-2">
              <h3 class="font-semibold text-gray-900 text-sm truncate pr-2">{{ skill.name }}</h3>
            </div>
            <p class="text-xs text-muted-foreground line-clamp-2 leading-relaxed">{{ skill.description || '暂无描述' }}</p>
          </div>
        </div>
      </div>

      <!-- 右侧详情区 -->
      <div class="flex-1 flex flex-col overflow-hidden bg-white">
        <!-- 未选中状态 -->
        <div v-if="!selectedSkill" class="flex-1 flex flex-col items-center justify-center text-muted-foreground/50">
          <div class="w-20 h-20 bg-muted rounded-3xl flex items-center justify-center mb-4 border border-border">
            <Puzzle class="w-10 h-10 opacity-30" />
          </div>
          <p class="text-sm font-medium text-muted-foreground">选择一个 Skill 查看详情</p>
          <p class="text-xs mt-1 text-muted-foreground/50">或上传新的 Skill</p>
        </div>

        <!-- 详情视图 -->
        <template v-else>
          <!-- 详情头部 -->
          <div class="h-16 flex items-center justify-between px-8 border-b border-border bg-white flex-shrink-0">
            <h2 class="text-lg font-bold text-gray-900">{{ selectedSkill.name }}</h2>
            <button 
              @click="handleDelete"
              :disabled="actionLoading"
              class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-white border border-destructive/30 text-destructive hover:bg-destructive/10 transition-all"
            >
              <Trash2 class="w-4 h-4" />
              删除
            </button>
          </div>

          <!-- 详情内容 -->
          <div class="flex-1 overflow-y-auto p-6 scrollbar-thin">
            <div class="max-w-7xl mx-auto space-y-6">
            <!-- 加载详情中 -->
            <div v-if="detailLoading" class="flex items-center justify-center py-12 text-muted-foreground/50">
              <Loader2 class="w-6 h-6 animate-spin mr-2" /> 加载详情中...
            </div>

            <template v-else-if="skillDetail">
              <!-- 基本信息 -->
              <div class="bg-muted/50 rounded-2xl border border-border p-6">
                <h3 class="text-sm font-bold text-foreground mb-4 flex items-center gap-2 uppercase tracking-wide">
                  <ClipboardList class="w-4 h-4 text-muted-foreground" /> 基本信息
                </h3>
                
                <div class="space-y-4">
                  <div>
                    <label class="text-xs font-semibold text-muted-foreground mb-1.5 block uppercase">描述</label>
                    <p class="text-sm text-gray-700 leading-relaxed">{{ skillDetail.description || '暂无描述' }}</p>
                  </div>

                  <!-- 适用场景 -->
                  <div v-if="skillDetail.preferred_for?.length">
                    <label class="text-xs font-semibold text-muted-foreground mb-1.5 block uppercase">适用场景</label>
                    <div class="flex flex-wrap gap-2">
                      <span 
                        v-for="tag in skillDetail.preferred_for" 
                        :key="tag"
                        class="px-3 py-1 bg-accent text-accent-foreground border border-primary/20 rounded-lg text-xs font-medium"
                      >
                        {{ tag }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 文件信息 -->
              <div v-if="skillDetail.scripts?.length || skillDetail.resources?.length" class="bg-muted/50 rounded-2xl border border-border p-6">
                <h3 class="text-sm font-bold text-foreground mb-4 flex items-center gap-2 uppercase tracking-wide">
                  <FolderOpen class="w-4 h-4 text-muted-foreground" /> 文件结构
                </h3>
                
                <div class="grid grid-cols-2 gap-6">
                  <div>
                    <label class="text-xs font-semibold text-muted-foreground mb-2 block uppercase">脚本文件 (scripts/)</label>
                    <div class="space-y-2">
                      <div 
                        v-for="script in skillDetail.scripts" 
                        :key="script"
                        @click="viewFile('scripts', script)"
                        class="flex items-center gap-2 px-3 py-2 bg-white border border-border rounded-lg text-xs text-muted-foreground font-mono cursor-pointer hover:border-primary hover:bg-accent transition-all group"
                      >
                        <FileCode class="w-3.5 h-3.5 text-primary" /> 
                        <span class="flex-1">{{ script }}</span>
                        <Eye class="w-3.5 h-3.5 text-muted-foreground/50 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                      <div v-if="!skillDetail.scripts?.length" class="text-xs text-muted-foreground/50 italic bg-white/50 px-3 py-2 rounded-lg border border-dashed border-border">
                        无脚本文件
                      </div>
                    </div>
                  </div>
                  <div>
                    <label class="text-xs font-semibold text-muted-foreground mb-2 block uppercase">资源文件 (resources/)</label>
                    <div class="space-y-2">
                      <div 
                        v-for="res in skillDetail.resources" 
                        :key="res"
                        @click="viewFile('resources', res)"
                        class="flex items-center gap-2 px-3 py-2 bg-white border border-border rounded-lg text-xs text-muted-foreground font-mono cursor-pointer hover:border-success/50 hover:bg-success/10 transition-all group"
                      >
                        <FileJson class="w-3.5 h-3.5 text-success" /> 
                        <span class="flex-1">{{ res }}</span>
                        <Eye class="w-3.5 h-3.5 text-muted-foreground/50 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                      <div v-if="!skillDetail.resources?.length" class="text-xs text-muted-foreground/50 italic bg-white/50 px-3 py-2 rounded-lg border border-dashed border-border">
                        无资源文件
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- SKILL.md 文档内容 -->
              <div v-if="skillDetail.content" class="bg-white rounded-2xl border border-border p-6 shadow-sm">
                <h3 class="text-sm font-bold text-foreground mb-4 flex items-center gap-2 uppercase tracking-wide">
                  <FileText class="w-4 h-4 text-muted-foreground" /> SKILL.md 文档
                </h3>
                
                <div class="prose prose-sm max-w-none bg-muted rounded-xl p-4 border border-border max-h-[500px] overflow-y-auto">
                  <pre class="text-xs text-gray-700 whitespace-pre-wrap font-mono leading-relaxed">{{ skillDetail.content }}</pre>
                </div>
              </div>
            </template>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 上传 Modal -->
    <Teleport to="body">
      <div 
        v-if="showUploadModal"
        class="fixed inset-0 bg-primary/40 backdrop-blur-sm z-50 flex items-center justify-center p-6"
        @click.self="showUploadModal = false"
      >
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
          <div class="px-6 py-4 border-b border-border flex items-center justify-between">
            <h3 class="text-lg font-bold text-gray-900">上传新 Skill</h3>
            <button @click="showUploadModal = false" class="p-2 rounded-lg text-muted-foreground/50 hover:bg-muted">
              <X class="w-5 h-5" />
            </button>
          </div>
          <div class="p-6 space-y-4">
            <div>
              <label class="text-sm font-medium text-gray-700 mb-2 block">Skill 名称</label>
              <input 
                v-model="uploadSkillName"
                placeholder="例如: my-custom-skill"
                class="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
              >
              <p class="text-xs text-muted-foreground/50 mt-1">只能包含小写字母、数字和连字符</p>
            </div>
            <div>
              <label class="text-sm font-medium text-gray-700 mb-2 block">上传 ZIP 文件</label>
              <div 
                class="border-2 border-dashed border-border rounded-lg p-6 text-center hover:border-primary transition-colors cursor-pointer"
                @click="fileInput?.click()"
                @dragover.prevent
                @drop.prevent="handleFileDrop"
              >
                <Upload class="w-8 h-8 mx-auto mb-2 text-muted-foreground/50" />
                <p class="text-sm text-muted-foreground">
                  {{ uploadFile ? uploadFile.name : '点击选择或拖拽文件' }}
                </p>
                <p class="text-xs text-muted-foreground/50 mt-1">ZIP 文件，必须包含 SKILL.md</p>
              </div>
              <input 
                ref="fileInput"
                type="file" 
                accept=".zip"
                @change="handleFileSelect"
                class="hidden"
              >
            </div>
          </div>
          <div class="px-6 py-4 border-t border-border flex justify-end gap-3 bg-muted">
            <button @click="showUploadModal = false" class="px-4 py-2 text-sm text-muted-foreground hover:text-gray-900">取消</button>
            <button 
              @click="handleUpload"
              :disabled="!uploadSkillName || !uploadFile || actionLoading"
              class="px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-hover disabled:opacity-50"
            >
              {{ actionLoading ? '上传中...' : '上传' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 文件查看 Modal -->
    <Teleport to="body">
      <div 
        v-if="showFileModal"
        class="fixed inset-0 bg-primary/40 backdrop-blur-sm z-50 flex items-center justify-center p-6"
        @click.self="showFileModal = false"
      >
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[85vh] overflow-hidden flex flex-col">
          <!-- 弹窗头部 -->
          <div class="px-6 py-4 border-b border-border flex items-center justify-between flex-shrink-0">
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 rounded-lg flex items-center justify-center" :class="currentFileType === 'scripts' ? 'bg-accent' : 'bg-success/10'">
                <FileCode v-if="currentFileType === 'scripts'" class="w-5 h-5 text-primary" />
                <FileJson v-else class="w-5 h-5 text-success" />
              </div>
              <div>
                <h3 class="text-base font-bold text-gray-900">{{ currentFileName }}</h3>
                <p class="text-xs text-muted-foreground">
                  {{ currentFileType === 'scripts' ? '脚本文件' : '资源文件' }} · {{ selectedSkill?.name }}
                </p>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button 
                v-if="fileContent && !fileContent.is_binary"
                @click="copyFileContent"
                class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-muted-foreground bg-muted rounded-lg hover:bg-gray-200 transition-colors"
              >
                <Copy class="w-3.5 h-3.5" />
                复制
              </button>
              <button @click="showFileModal = false" class="p-2 rounded-lg text-muted-foreground/50 hover:bg-muted hover:text-muted-foreground transition-colors">
                <X class="w-5 h-5" />
              </button>
            </div>
          </div>
          
          <!-- 弹窗内容 -->
          <div class="flex-1 overflow-hidden">
            <!-- 加载中 -->
            <div v-if="fileLoading" class="flex items-center justify-center h-64 text-muted-foreground/50">
              <Loader2 class="w-6 h-6 animate-spin mr-2" /> 加载文件中...
            </div>
            
            <!-- 二进制文件提示 -->
            <div v-else-if="fileContent?.is_binary" class="flex flex-col items-center justify-center h-64 text-muted-foreground/50">
              <FileWarning class="w-12 h-12 mb-3 text-gray-300" />
              <p class="text-sm font-medium text-muted-foreground">此文件为二进制格式</p>
              <p class="text-xs mt-1">无法显示内容，文件大小: {{ formatFileSize(fileContent.size) }}</p>
            </div>
            
            <!-- 文件内容 -->
            <div v-else-if="fileContent" class="h-full overflow-auto">
              <div class="p-1">
                <div class="bg-primary rounded-xl overflow-hidden">
                  <!-- 语言标签 -->
                  <div class="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
                    <span class="text-xs font-medium text-muted-foreground/50">{{ fileContent.language?.toUpperCase() || 'TEXT' }}</span>
                    <span class="text-xs text-muted-foreground">{{ formatFileSize(fileContent.size) }}</span>
                  </div>
                  <!-- 代码内容 -->
                  <pre class="p-4 text-sm text-gray-300 font-mono leading-relaxed overflow-auto max-h-[calc(85vh-180px)] whitespace-pre-wrap break-words"><code>{{ fileContent.content }}</code></pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import * as skillsApi from '@/api/skills'
import type { SkillSummary } from '@/types'
import type { SkillDetailResponse } from '@/api/skills'
import { 
  Puzzle, 
  Search, 
  RefreshCw, 
  Loader2, 
  Trash2, 
  ClipboardList,
  X,
  Upload,
  FileCode,
  FileJson,
  FileText,
  FolderOpen,
  Eye,
  Copy,
  FileWarning
} from 'lucide-vue-next'
import type { SkillFileContentResponse } from '@/api/skills'

// ==================== 状态 ====================

const loading = ref(false)
const actionLoading = ref(false)
const detailLoading = ref(false)
const searchQuery = ref('')

// Skills 数据
const globalSkills = ref<SkillSummary[]>([])
const selectedSkill = ref<SkillSummary | null>(null)
const skillDetail = ref<SkillDetailResponse | null>(null)

// Modal 状态
const showUploadModal = ref(false)
const uploadSkillName = ref('')
const uploadFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

// 文件查看 Modal 状态
const showFileModal = ref(false)
const fileLoading = ref(false)
const currentFileType = ref<'scripts' | 'resources'>('scripts')
const currentFileName = ref('')
const fileContent = ref<SkillFileContentResponse | null>(null)

// ==================== 计算属性 ====================

const filteredSkills = computed(() => {
  if (!searchQuery.value) return globalSkills.value
  
  const query = searchQuery.value.toLowerCase()
  return globalSkills.value.filter(skill => 
    skill.name.toLowerCase().includes(query) ||
    skill.description.toLowerCase().includes(query)
  )
})

// ==================== 方法 ====================

async function fetchGlobalSkills() {
  loading.value = true
  try {
    globalSkills.value = await skillsApi.getGlobalSkills()
  } catch (error) {
    console.error('获取全局 Skills 失败:', error)
  } finally {
    loading.value = false
  }
}

async function selectSkill(skill: SkillSummary) {
  selectedSkill.value = skill
  skillDetail.value = null
  
  // 获取详细信息
  detailLoading.value = true
  try {
    skillDetail.value = await skillsApi.getSkillDetail(skill.name)
  } catch (error) {
    console.error('获取 Skill 详情失败:', error)
  } finally {
    detailLoading.value = false
  }
}

async function handleDelete() {
  if (!selectedSkill.value) return
  
  if (!confirm(`确定要从全局库删除 "${selectedSkill.value.name}" 吗？\n已安装到实例的副本不会受影响。`)) return
  
  actionLoading.value = true
  try {
    // TODO: 调用删除全局 Skill 的 API
    alert('删除功能开发中')
  } catch (error: any) {
    alert(error.response?.data?.detail?.message || '删除失败')
  } finally {
    actionLoading.value = false
  }
}

function handleFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files && input.files[0]) {
    uploadFile.value = input.files[0]
  }
}

function handleFileDrop(event: DragEvent) {
  if (event.dataTransfer?.files && event.dataTransfer.files[0]) {
    const file = event.dataTransfer.files[0]
    if (file.name.endsWith('.zip')) {
      uploadFile.value = file
    } else {
      alert('请上传 .zip 文件')
    }
  }
}

async function handleUpload() {
  if (!uploadSkillName.value || !uploadFile.value) return
  
  actionLoading.value = true
  try {
    const result = await skillsApi.uploadSkill(uploadFile.value, uploadSkillName.value)
    
    alert(result.message)
    showUploadModal.value = false
    uploadSkillName.value = ''
    uploadFile.value = null
    await fetchGlobalSkills()
  } catch (error: any) {
    alert(error.response?.data?.detail?.message || '上传失败')
  } finally {
    actionLoading.value = false
  }
}

async function viewFile(fileType: 'scripts' | 'resources', fileName: string) {
  if (!selectedSkill.value) return
  
  currentFileType.value = fileType
  currentFileName.value = fileName
  fileContent.value = null
  showFileModal.value = true
  fileLoading.value = true
  
  try {
    fileContent.value = await skillsApi.getSkillFileContent(
      selectedSkill.value.name,
      fileType,
      fileName
    )
  } catch (error: any) {
    console.error('获取文件内容失败:', error)
    alert(error.response?.data?.detail?.message || '获取文件内容失败')
    showFileModal.value = false
  } finally {
    fileLoading.value = false
  }
}

async function copyFileContent() {
  if (!fileContent.value?.content) return
  
  try {
    await navigator.clipboard.writeText(fileContent.value.content)
    alert('已复制到剪贴板')
  } catch (error) {
    console.error('复制失败:', error)
    alert('复制失败')
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// ==================== 生命周期 ====================

onMounted(async () => {
  await fetchGlobalSkills()
})
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>

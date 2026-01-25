<template>
  <div class="h-full flex flex-col overflow-hidden bg-white">
    <!-- 顶部工具栏 -->
    <div class="h-16 flex items-center justify-between px-8 border-b border-gray-100 bg-white sticky top-0 z-10">
      <div class="flex items-center gap-4">
        <h1 class="text-lg font-bold flex items-center gap-2 text-gray-800">
          <Puzzle class="w-6 h-6 text-blue-500" />
          Skill 管理
        </h1>
        <div class="text-sm text-gray-500 bg-gray-50 px-2.5 py-1 rounded-md border border-gray-100">
          共 {{ skills.length }} 个 Skill
        </div>
      </div>
      <div class="flex items-center gap-3">
        <button 
          @click="fetchSkills" 
          :disabled="loading"
          class="p-2.5 bg-gray-50 border border-gray-200 rounded-xl text-gray-600 hover:bg-gray-100 hover:text-blue-600 transition-all"
          title="刷新"
        >
          <RefreshCw class="w-4 h-4" :class="loading ? 'animate-spin' : ''" />
        </button>
        <button 
          @click="showCreateModal = true"
          class="flex items-center gap-2 px-5 py-2.5 bg-gray-900 text-white text-sm font-medium rounded-xl hover:bg-gray-800 transition-all shadow-lg shadow-gray-900/10 active:scale-95"
        >
          <Plus class="w-4 h-4" />
          创建 Skill
        </button>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="flex-1 flex overflow-hidden">
      <!-- 左侧 Skill 列表 -->
      <div class="w-[320px] border-r border-gray-100 bg-gray-50 overflow-y-auto p-4 flex flex-col">
        <!-- 搜索框 -->
        <div class="relative mb-4 group">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 group-focus-within:text-blue-500 transition-colors" />
          <input 
            v-model="searchQuery" 
            type="text" 
            placeholder="搜索 Skill..."
            class="w-full pl-9 pr-4 py-2 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all placeholder-gray-400"
          >
        </div>

        <!-- 加载中 -->
        <div v-if="loading" class="flex items-center justify-center py-12 text-gray-400">
          <Loader2 class="w-6 h-6 animate-spin mr-2" /> 加载中...
        </div>

        <!-- 空状态 -->
        <div v-else-if="filteredSkills.length === 0" class="text-center py-12 text-gray-400 bg-white/50 rounded-2xl border border-dashed border-gray-200">
          <Puzzle class="w-8 h-8 mx-auto mb-2 text-gray-300" />
          <p class="text-sm">暂无 Skill</p>
        </div>

        <!-- Skill 列表 -->
        <div v-else class="space-y-2">
          <div
            v-for="skill in filteredSkills"
            :key="skill.name"
            @click="selectSkill(skill)"
            class="p-4 rounded-xl cursor-pointer transition-all duration-200 border"
            :class="selectedSkill?.name === skill.name 
              ? 'bg-white shadow-md border-blue-500/20 ring-1 ring-blue-500/10' 
              : 'bg-white border-gray-200 hover:border-blue-300 hover:shadow-sm'"
          >
            <div class="flex items-start justify-between mb-2">
              <h3 class="font-semibold text-gray-900 text-sm truncate pr-2">{{ skill.name }}</h3>
              <span 
                class="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide border"
                :class="getPriorityClass(skill.priority)"
              >
                {{ skill.priority }}
              </span>
            </div>
            <p class="text-xs text-gray-500 line-clamp-2 mb-3 leading-relaxed">{{ skill.description }}</p>
            <div class="flex flex-wrap gap-1">
              <span 
                v-for="tag in skill.preferred_for.slice(0, 3)" 
                :key="tag"
                class="px-2 py-0.5 bg-gray-50 text-gray-600 rounded text-[10px] border border-gray-100"
              >
                {{ tag }}
              </span>
              <span 
                v-if="skill.preferred_for.length > 3" 
                class="px-2 py-0.5 bg-gray-50 text-gray-400 rounded text-[10px] border border-gray-100"
              >
                +{{ skill.preferred_for.length - 3 }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧详情/编辑区 -->
      <div class="flex-1 flex flex-col overflow-hidden bg-white">
        <!-- 未选中状态 -->
        <div v-if="!selectedSkill" class="flex-1 flex flex-col items-center justify-center text-gray-400">
          <div class="w-20 h-20 bg-gray-50 rounded-3xl flex items-center justify-center mb-4 border border-gray-100">
            <Puzzle class="w-10 h-10 opacity-30" />
          </div>
          <p class="text-sm font-medium text-gray-500">选择一个 Skill 查看详情</p>
          <p class="text-xs mt-1 text-gray-400">或创建新的 Skill</p>
        </div>

        <!-- 详情视图 -->
        <template v-else>
          <!-- 详情头部 -->
          <div class="h-16 flex items-center justify-between px-8 border-b border-gray-100 bg-white flex-shrink-0">
            <div class="flex items-center gap-3">
              <h2 class="text-lg font-bold text-gray-900">{{ selectedSkill.name }}</h2>
              <span 
                class="px-2.5 py-1 rounded-lg text-xs font-bold uppercase border"
                :class="getPriorityClass(selectedSkill.priority)"
              >
                {{ selectedSkill.priority }}
              </span>
            </div>
            <div class="flex items-center gap-2">
              <button 
                @click="isEditing = !isEditing"
                class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all"
                :class="isEditing 
                  ? 'bg-blue-600 text-white shadow-md' 
                  : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50 hover:text-gray-900'"
              >
                <Edit2 v-if="!isEditing" class="w-4 h-4" />
                <Save v-else class="w-4 h-4" />
                {{ isEditing ? '编辑中' : '编辑' }}
              </button>
              <button 
                @click="handleDelete"
                class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-white border border-red-200 text-red-500 hover:bg-red-50 transition-all"
              >
                <Trash2 class="w-4 h-4" />
                删除
              </button>
            </div>
          </div>

          <!-- 详情内容 -->
          <div class="flex-1 overflow-y-auto p-8 scrollbar-thin">
            <!-- 基本信息 -->
            <div class="bg-gray-50/50 rounded-2xl border border-gray-100 p-6 mb-6">
              <h3 class="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2 uppercase tracking-wide">
                <ClipboardList class="w-4 h-4 text-gray-500" /> 基本信息
              </h3>
              
              <div class="space-y-6">
                <div>
                  <label class="text-xs font-semibold text-gray-500 mb-1.5 block uppercase">描述</label>
                  <p v-if="!isEditing" class="text-sm text-gray-700 leading-relaxed">{{ selectedSkill.description }}</p>
                  <textarea 
                    v-else 
                    v-model="editForm.description"
                    rows="3"
                    class="w-full px-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                  ></textarea>
                </div>

                <div>
                  <label class="text-xs font-semibold text-gray-500 mb-1.5 block uppercase">适用场景</label>
                  <div v-if="!isEditing" class="flex flex-wrap gap-2">
                    <span 
                      v-for="tag in selectedSkill.preferred_for" 
                      :key="tag"
                      class="px-3 py-1 bg-blue-50 text-blue-700 border border-blue-100 rounded-lg text-xs font-medium"
                    >
                      {{ tag }}
                    </span>
                  </div>
                  <input 
                    v-else 
                    v-model="editForm.preferred_for_text"
                    placeholder="用逗号分隔多个标签"
                    class="w-full px-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                  >
                </div>

                <div class="grid grid-cols-2 gap-6">
                  <div>
                    <label class="text-xs font-semibold text-gray-500 mb-1.5 block uppercase">脚本</label>
                    <div class="space-y-2">
                      <div 
                        v-for="script in selectedSkill.scripts" 
                        :key="script"
                        class="flex items-center gap-2 px-3 py-2 bg-white border border-gray-200 rounded-lg text-xs text-gray-600 font-mono"
                      >
                        <FileCode class="w-3.5 h-3.5 text-gray-400" /> {{ script }}
                      </div>
                      <div v-if="selectedSkill.scripts.length === 0" class="text-xs text-gray-400 italic bg-white/50 px-3 py-2 rounded-lg border border-dashed border-gray-200">
                        无脚本
                      </div>
                    </div>
                  </div>
                  <div>
                    <label class="text-xs font-semibold text-gray-500 mb-1.5 block uppercase">资源</label>
                    <div class="space-y-2">
                      <div 
                        v-for="res in selectedSkill.resources" 
                        :key="res"
                        class="flex items-center gap-2 px-3 py-2 bg-white border border-gray-200 rounded-lg text-xs text-gray-600 font-mono"
                      >
                        <FolderOpen class="w-3.5 h-3.5 text-gray-400" /> {{ res }}
                      </div>
                      <div v-if="selectedSkill.resources.length === 0" class="text-xs text-gray-400 italic bg-white/50 px-3 py-2 rounded-lg border border-dashed border-gray-200">
                        无资源
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 文档内容 -->
            <div class="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm">
              <h3 class="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2 uppercase tracking-wide">
                <FileText class="w-4 h-4 text-gray-500" /> SKILL.md 文档
              </h3>
              
              <div v-if="!isEditing" class="prose prose-sm max-w-none prose-headings:font-bold prose-h1:text-xl prose-h2:text-lg prose-p:text-gray-600 prose-pre:bg-gray-50 prose-pre:border prose-pre:border-gray-100">
                <div class="text-sm text-gray-700 whitespace-pre-wrap font-mono leading-relaxed">{{ selectedSkill.content }}</div>
              </div>
              <textarea 
                v-else 
                v-model="editForm.content"
                rows="20"
                class="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all leading-relaxed"
              ></textarea>
            </div>

            <!-- 编辑模式下的保存按钮 -->
            <div v-if="isEditing" class="mt-8 flex justify-end gap-3 sticky bottom-0 bg-white py-4 border-t border-gray-100">
              <button 
                @click="cancelEdit"
                class="px-6 py-2.5 rounded-xl text-sm font-medium bg-white border border-gray-200 text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-all"
              >
                取消
              </button>
              <button 
                @click="saveEdit"
                class="px-6 py-2.5 rounded-xl text-sm font-medium bg-gray-900 text-white hover:bg-gray-800 transition-all shadow-lg shadow-gray-900/10 flex items-center gap-2"
              >
                <Save class="w-4 h-4" />
                保存更改
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 创建 Modal -->
    <Teleport to="body">
      <div 
        v-if="showCreateModal"
        class="fixed inset-0 bg-gray-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-6 transition-opacity"
        @click.self="showCreateModal = false"
      >
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col transform transition-all scale-100">
          <!-- Modal 头部 -->
          <div class="px-8 py-5 border-b border-gray-100 flex items-center justify-between bg-white sticky top-0 z-10">
            <h3 class="text-lg font-bold text-gray-900 flex items-center gap-2">
              <Plus class="w-5 h-5 text-blue-500" />
              创建新 Skill
            </h3>
            <button 
              @click="showCreateModal = false"
              class="p-2 rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
            >
              <X class="w-5 h-5" />
            </button>
          </div>

          <!-- Modal 内容 -->
          <div class="flex-1 overflow-y-auto p-8 space-y-6">
            <div>
              <label class="text-sm font-semibold text-gray-700 mb-2 block">Skill 名称 <span class="text-red-500">*</span></label>
              <input 
                v-model="createForm.name"
                placeholder="例如: my-custom-skill"
                class="w-full px-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
              >
              <p class="text-xs text-gray-400 mt-1.5 ml-1">只能包含小写字母、数字和连字符</p>
            </div>

            <div>
              <label class="text-sm font-semibold text-gray-700 mb-2 block">描述 <span class="text-red-500">*</span></label>
              <textarea 
                v-model="createForm.description"
                rows="3"
                placeholder="描述这个 Skill 的功能和用途..."
                class="w-full px-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all resize-none"
              ></textarea>
            </div>

            <div class="grid grid-cols-2 gap-6">
              <div>
                <label class="text-sm font-semibold text-gray-700 mb-2 block">优先级</label>
                <div class="relative">
                  <select 
                    v-model="createForm.priority"
                    class="w-full pl-4 pr-10 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all appearance-none cursor-pointer"
                  >
                    <option value="high">🔥 高 (High)</option>
                    <option value="medium">⚡ 中 (Medium)</option>
                    <option value="low">☕ 低 (Low)</option>
                  </select>
                  <ChevronDown class="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                </div>
              </div>
              <div>
                <label class="text-sm font-semibold text-gray-700 mb-2 block">适用场景</label>
                <input 
                  v-model="createForm.preferred_for_text"
                  placeholder="例如: task planning, coding"
                  class="w-full px-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                >
              </div>
            </div>

            <div>
              <label class="text-sm font-semibold text-gray-700 mb-2 block">SKILL.md 内容</label>
              <textarea 
                v-model="createForm.content"
                rows="12"
                placeholder="# My Skill&#10;&#10;Description of what this skill does...&#10;&#10;## When to Use&#10;&#10;- Scenario 1&#10;- Scenario 2"
                class="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all leading-relaxed"
              ></textarea>
            </div>
          </div>

          <!-- Modal 底部 -->
          <div class="px-8 py-5 border-t border-gray-100 flex justify-end gap-3 bg-gray-50 sticky bottom-0">
            <button 
              @click="showCreateModal = false"
              class="px-6 py-2.5 rounded-xl text-sm font-medium text-gray-600 hover:bg-white hover:shadow-sm border border-transparent hover:border-gray-200 transition-all"
            >
              取消
            </button>
            <button 
              @click="handleCreate"
              :disabled="!createForm.name || !createForm.description"
              class="px-8 py-2.5 rounded-xl text-sm font-medium bg-gray-900 text-white hover:bg-gray-800 transition-all shadow-lg shadow-gray-900/10 disabled:opacity-50 disabled:cursor-not-allowed transform active:scale-95"
            >
              创建 Skill
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import * as skillsApi from '@/api/skills'
import type { Skill, SkillPriority } from '@/types'
import { 
  Puzzle, 
  Search, 
  RefreshCw, 
  Plus, 
  Loader2, 
  Edit2, 
  Save, 
  Trash2, 
  ClipboardList, 
  FileCode, 
  FolderOpen, 
  FileText,
  X,
  ChevronDown
} from 'lucide-vue-next'

// ==================== 状态 ====================

const skills = ref<Skill[]>([])
const loading = ref(false)
const searchQuery = ref('')
const selectedSkill = ref<Skill | null>(null)
const isEditing = ref(false)
const showCreateModal = ref(false)

// 编辑表单
const editForm = ref({
  description: '',
  priority: 'medium' as SkillPriority,
  preferred_for_text: '',
  content: ''
})

// 创建表单
const createForm = ref({
  name: '',
  description: '',
  priority: 'medium' as SkillPriority,
  preferred_for_text: '',
  content: ''
})

// ==================== 计算属性 ====================

const filteredSkills = computed(() => {
  if (!searchQuery.value) return skills.value
  
  const query = searchQuery.value.toLowerCase()
  return skills.value.filter(skill => 
    skill.name.toLowerCase().includes(query) ||
    skill.description.toLowerCase().includes(query) ||
    skill.preferred_for.some(tag => tag.toLowerCase().includes(query))
  )
})

// ==================== 方法 ====================

/**
 * 获取 Skills 列表
 */
async function fetchSkills() {
  loading.value = true
  try {
    skills.value = await skillsApi.getSkills()
  } catch (error) {
    console.error('获取 Skills 失败:', error)
  } finally {
    loading.value = false
  }
}

/**
 * 选择 Skill
 */
function selectSkill(skill: Skill) {
  selectedSkill.value = skill
  isEditing.value = false
  
  // 初始化编辑表单
  editForm.value = {
    description: skill.description,
    priority: skill.priority,
    preferred_for_text: skill.preferred_for.join(', '),
    content: skill.content
  }
}

/**
 * 获取优先级样式类
 */
function getPriorityClass(priority: SkillPriority): string {
  const classes: Record<SkillPriority, string> = {
    high: 'bg-red-50 text-red-600 border-red-100',
    medium: 'bg-yellow-50 text-yellow-600 border-yellow-100',
    low: 'bg-green-50 text-green-600 border-green-100'
  }
  return classes[priority] || classes.medium
}

/**
 * 取消编辑
 */
function cancelEdit() {
  isEditing.value = false
  if (selectedSkill.value) {
    editForm.value = {
      description: selectedSkill.value.description,
      priority: selectedSkill.value.priority,
      preferred_for_text: selectedSkill.value.preferred_for.join(', '),
      content: selectedSkill.value.content
    }
  }
}

/**
 * 保存编辑
 */
async function saveEdit() {
  if (!selectedSkill.value) return
  
  try {
    await skillsApi.updateSkill(selectedSkill.value.name, {
      description: editForm.value.description,
      priority: editForm.value.priority,
      preferred_for: editForm.value.preferred_for_text.split(',').map(s => s.trim()).filter(Boolean),
      content: editForm.value.content
    })
    
    // 更新本地数据
    const index = skills.value.findIndex(s => s.name === selectedSkill.value?.name)
    if (index !== -1) {
      skills.value[index] = {
        ...skills.value[index],
        description: editForm.value.description,
        priority: editForm.value.priority,
        preferred_for: editForm.value.preferred_for_text.split(',').map(s => s.trim()).filter(Boolean),
        content: editForm.value.content
      }
      selectedSkill.value = skills.value[index]
    }
    
    isEditing.value = false
    alert('保存成功！')
  } catch (error) {
    console.error('保存失败:', error)
    alert('保存失败，请重试')
  }
}

/**
 * 创建 Skill
 */
async function handleCreate() {
  if (!createForm.value.name || !createForm.value.description) return
  
  try {
    const newSkill = await skillsApi.createSkill({
      name: createForm.value.name,
      description: createForm.value.description,
      priority: createForm.value.priority,
      preferred_for: createForm.value.preferred_for_text.split(',').map(s => s.trim()).filter(Boolean),
      content: createForm.value.content || `# ${createForm.value.name}\n\n${createForm.value.description}`
    })
    
    skills.value.push(newSkill)
    showCreateModal.value = false
    
    // 重置表单
    createForm.value = {
      name: '',
      description: '',
      priority: 'medium',
      preferred_for_text: '',
      content: ''
    }
    
    alert('创建成功！')
  } catch (error) {
    console.error('创建失败:', error)
    alert('创建失败，请重试')
  }
}

/**
 * 删除 Skill
 */
async function handleDelete() {
  if (!selectedSkill.value) return
  
  if (!confirm(`确定要删除 "${selectedSkill.value.name}" 吗？此操作不可恢复。`)) return
  
  try {
    await skillsApi.deleteSkill(selectedSkill.value.name)
    skills.value = skills.value.filter(s => s.name !== selectedSkill.value?.name)
    selectedSkill.value = null
    alert('删除成功！')
  } catch (error) {
    console.error('删除失败:', error)
    alert('删除失败，请重试')
  }
}

// ==================== 生命周期 ====================

onMounted(() => {
  fetchSkills()
})
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 滚动条优化 */
.scrollbar-thin::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-thin::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.3);
  border-radius: 3px;
}
.scrollbar-thin::-webkit-scrollbar-thumb:hover {
  background-color: rgba(156, 163, 175, 0.5);
}
</style>

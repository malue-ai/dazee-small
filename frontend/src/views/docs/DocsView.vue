<template>
  <div class="h-full flex flex-col overflow-hidden bg-white">
    <!-- 顶部工具栏 (统一布局) -->
    <div class="h-16 flex items-center justify-between px-6 border-b border-gray-100 bg-white sticky top-0 z-10 flex-shrink-0">
      <div class="flex items-center gap-4">
        <h1 class="text-lg font-bold flex items-center gap-2 text-gray-800">
          <BookOpen class="w-6 h-6 text-blue-500" />
          项目文档
        </h1>
        <div class="text-sm text-gray-500 bg-gray-50 px-2.5 py-1 rounded-md border border-gray-100">
          共 {{ structure?.total_files || 0 }} 篇
        </div>
      </div>
      <!-- 搜索框 (移到顶部，可选，或者保留在左侧) -->
      <!-- 这里我们暂时保留左侧搜索，顶部只放操作 -->
    </div>

    <!-- 主体区域 -->
    <div class="flex-1 flex overflow-hidden">
      <!-- 左侧文档目录 -->
      <div class="w-72 flex-shrink-0 border-r border-gray-100 bg-gray-50 overflow-y-auto flex flex-col">
        <!-- 搜索框 -->
        <div class="p-4 border-b border-gray-100 sticky top-0 bg-gray-50 z-10">
          <div class="relative">
            <Search class="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              v-model="searchQuery"
              type="text"
              placeholder="搜索文档..."
              class="w-full pl-9 pr-3 py-2 text-sm bg-white border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
            />
          </div>
        </div>

        <!-- 加载中 -->
        <div v-if="loading" class="p-4 text-center text-gray-500 text-sm">
          <Loader2 class="w-5 h-5 animate-spin mx-auto mb-2" />
          加载目录...
        </div>

        <!-- 文档列表 -->
        <div v-else class="p-3">
        <div
          v-for="category in filteredCategories"
          :key="category.id"
          class="mb-4"
        >
          <!-- 分类标题 -->
          <div 
            class="flex items-center gap-2 px-3 py-2 text-sm font-semibold text-gray-700 cursor-pointer hover:bg-white rounded-lg transition-colors"
            @click="toggleCategory(category.id)"
          >
            <span class="text-lg">{{ category.icon }}</span>
            <span class="flex-1">{{ category.name }}</span>
            <span class="text-xs text-gray-400">{{ category.files.length }}</span>
            <ChevronDown v-if="expandedCategories.includes(category.id)" class="w-3 h-3 text-gray-400" />
            <ChevronRight v-else class="w-3 h-3 text-gray-400" />
          </div>

          <!-- 文件列表 -->
          <div 
            v-show="expandedCategories.includes(category.id)"
            class="ml-4 mt-1 space-y-0.5"
          >
            <div
              v-for="file in category.files"
              :key="file.path"
              @click="selectDoc(file.path)"
              class="flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-all text-sm"
              :class="currentDocPath === file.path 
                ? 'bg-white shadow-sm text-blue-600 font-medium border border-gray-100' 
                : 'text-gray-600 hover:bg-white hover:text-gray-900'"
            >
              <FileText class="w-4 h-4 flex-shrink-0" :class="currentDocPath === file.path ? 'text-blue-500' : 'text-gray-400'" />
              <span class="flex-1 truncate">{{ file.title }}</span>
            </div>
          </div>
        </div>

        <!-- 无结果 -->
        <div v-if="filteredCategories.length === 0 && searchQuery" class="text-center text-gray-500 text-sm py-8">
          <Search class="w-8 h-8 mx-auto mb-2 text-gray-300" />
          未找到匹配的文档
        </div>
      </div>
    </div>

    <!-- 中间内容区 -->
    <div class="flex-1 flex flex-col overflow-hidden bg-white">
      <!-- 内容头部 -->
      <div class="h-14 flex items-center justify-between px-6 border-b border-gray-100 bg-white sticky top-0 z-10">
        <div v-if="currentDoc">
          <h1 class="text-lg font-bold text-gray-800">{{ currentDoc.title }}</h1>
          <p class="text-xs text-gray-500 mt-0.5 flex items-center gap-1">
            <Folder class="w-3 h-3" /> {{ getCategoryName(currentDoc.category) }}
          </p>
        </div>
        <div v-else class="text-gray-400 text-sm">
          选择一个文档开始阅读
        </div>

        <div v-if="currentDoc" class="flex items-center gap-2">
          <button 
            @click="copyDocPath"
            class="px-3 py-1.5 rounded-lg text-sm text-gray-500 hover:bg-gray-100 transition-colors flex items-center gap-1"
          >
            <Copy class="w-4 h-4" /> 复制路径
          </button>
        </div>
      </div>

      <!-- 文档内容 -->
      <div class="flex-1 overflow-y-auto bg-gray-50/30">
        <!-- 未选择文档 -->
        <div v-if="!currentDoc && !loadingContent" class="h-full flex flex-col items-center justify-center text-gray-400 p-8">
          <div class="w-24 h-24 bg-gray-50 rounded-3xl flex items-center justify-center mb-6 border border-gray-100">
            <BookOpen class="w-10 h-10 text-gray-300" />
          </div>
          <h2 class="text-xl font-bold text-gray-700 mb-2">项目文档中心</h2>
          <p class="text-sm text-center max-w-md mb-8 text-gray-500 leading-relaxed">
            浏览架构设计、API 文档、使用指南和部署文档，深入了解 ZenFlux Agent 系统。
          </p>
          <button 
            v-if="structure?.categories[0]?.files[0]"
            @click="selectDoc(structure.categories[0].files[0].path)"
            class="px-8 py-3 bg-gray-900 text-white rounded-xl font-medium hover:bg-gray-800 transition-all shadow-lg shadow-gray-900/10 active:scale-95"
          >
            📖 开始阅读
          </button>
        </div>

        <!-- 加载内容中 -->
        <div v-else-if="loadingContent" class="h-full flex items-center justify-center">
          <Loader2 class="w-8 h-8 animate-spin text-gray-400" />
        </div>

        <!-- 文档内容 -->
        <div v-else-if="currentDoc" class="max-w-7xl mx-auto p-6 pb-12">
          <div class="bg-white rounded-2xl border border-gray-200 p-6 md:p-8 shadow-sm">
            <MarkdownRenderer :content="currentDoc.content" />
          </div>
        </div>
      </div>
    </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getDocsStructure, getDocContent, type DocsStructure, type DocContent, type DocCategory } from '@/api/docs'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import { 
  FileText, 
  ChevronDown, 
  ChevronRight, 
  Search, 
  Loader2,
  BookOpen,
  Folder,
  Copy
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()

// ==================== 状态 ====================

const loading = ref(true)
const loadingContent = ref(false)
const structure = ref<DocsStructure | null>(null)
const currentDoc = ref<DocContent | null>(null)
const currentDocPath = ref<string>('')
const expandedCategories = ref<string[]>([])
const searchQuery = ref('')

// ==================== 计算属性 ====================

/**
 * 过滤后的分类列表
 */
const filteredCategories = computed(() => {
  if (!structure.value) return []
  
  if (!searchQuery.value.trim()) {
    return structure.value.categories
  }
  
  const query = searchQuery.value.toLowerCase()
  return structure.value.categories
    .map(category => ({
      ...category,
      files: category.files.filter(file => 
        file.title.toLowerCase().includes(query) ||
        file.name.toLowerCase().includes(query)
      )
    }))
    .filter(category => category.files.length > 0)
})

// ==================== 方法 ====================

/**
 * 加载文档结构
 */
async function loadStructure() {
  loading.value = true
  try {
    structure.value = await getDocsStructure()
    // 默认展开第一个分类
    if (structure.value.categories.length > 0) {
      expandedCategories.value = [structure.value.categories[0].id]
    }
  } catch (error) {
    console.error('加载文档结构失败:', error)
  } finally {
    loading.value = false
  }
}

/**
 * 切换分类展开状态
 */
function toggleCategory(categoryId: string) {
  const index = expandedCategories.value.indexOf(categoryId)
  if (index === -1) {
    expandedCategories.value.push(categoryId)
  } else {
    expandedCategories.value.splice(index, 1)
  }
}

/**
 * 选择文档
 */
async function selectDoc(docPath: string) {
  if (currentDocPath.value === docPath) return
  
  currentDocPath.value = docPath
  loadingContent.value = true
  
  try {
    currentDoc.value = await getDocContent(docPath)
    
    // 更新 URL
    const encodedPath = encodeURIComponent(docPath)
    router.replace({ path: `/documentation/${encodedPath}` })
    
    // 确保分类展开
    const category = docPath.split('/')[0]
    if (!expandedCategories.value.includes(category)) {
      expandedCategories.value.push(category)
    }
  } catch (error) {
    console.error('加载文档内容失败:', error)
    currentDoc.value = null
  } finally {
    loadingContent.value = false
  }
}

/**
 * 获取分类名称
 */
function getCategoryName(categoryId: string): string {
  const category = structure.value?.categories.find(c => c.id === categoryId)
  return category?.name || categoryId
}

/**
 * 复制文档路径
 */
function copyDocPath() {
  if (currentDocPath.value) {
    navigator.clipboard.writeText(`docs/${currentDocPath.value}`)
    alert('路径已复制到剪贴板')
  }
}

// ==================== 生命周期 ====================

onMounted(async () => {
  await loadStructure()
  
  // 从路由参数加载文档
  const docPath = route.params.docPath as string
  if (docPath) {
    await selectDoc(decodeURIComponent(docPath))
  }
})

// 监听路由变化
watch(() => route.params.docPath, async (newPath) => {
  if (newPath && typeof newPath === 'string') {
    await selectDoc(decodeURIComponent(newPath))
  }
})
</script>

<style scoped>
/* 样式由 Tailwind 处理 */
</style>

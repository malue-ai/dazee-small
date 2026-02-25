<template>
  <div class="h-full flex flex-col bg-muted overflow-hidden">
    <!-- 头部 -->
    <div class="flex items-center justify-between px-3 py-2.5 border-b border-border bg-white">
      <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide flex items-center gap-1.5">
        <Folder class="w-3.5 h-3.5" />
        工作区文件
      </h3>
      <div class="flex gap-1">
        <button 
          @click="refreshFiles" 
          class="p-1.5 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:opacity-40" 
          :disabled="isLoading" 
          title="刷新"
        >
          <RefreshCw class="w-3.5 h-3.5" :class="isLoading ? 'animate-spin' : ''" />
        </button>
        <button 
          @click="toggleExpandAll" 
          class="p-1.5 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors" 
          title="展开/收起全部"
        >
          <FolderOpen v-if="isAllExpanded" class="w-3.5 h-3.5" />
          <Folder v-else class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
    
    <!-- 加载状态 -->
    <div v-if="isLoading" class="flex-1 flex flex-col items-center justify-center text-muted-foreground/50 gap-2">
      <Loader2 class="w-5 h-5 animate-spin" />
      <span class="text-xs">加载中...</span>
    </div>
    
    <!-- 错误状态 -->
    <div v-else-if="loadError" class="flex-1 flex flex-col items-center justify-center text-red-400 gap-2 p-4">
      <AlertCircle class="w-6 h-6" />
      <span class="text-xs text-center">{{ loadError }}</span>
      <button @click="loadFiles" class="text-xs text-primary hover:underline mt-1">重试</button>
    </div>
    
    <!-- 空状态 -->
    <div v-else-if="!hasFiles" class="flex-1 flex flex-col items-center justify-center text-muted-foreground/50 p-4 text-center">
      <FolderOpen class="w-8 h-8 mb-2 opacity-50" />
      <p class="text-xs font-medium">暂无文件</p>
      <p class="text-[10px] opacity-70 mt-1">AI 创建的文件将显示在这里</p>
    </div>
    
    <!-- 文件树 -->
    <div v-else class="flex-1 overflow-y-auto py-2 scrollbar-overlay">
      <FileTreeNode
        v-for="item in files"
        :key="item.path"
        :item="item"
        :depth="0"
        @toggle="handleToggle"
        @select="handleSelect"
        @download="handleDownload"
      />
    </div>
    
    <!-- 项目卡片区域 -->
    <div v-if="hasProjects" class="border-t border-border bg-white p-3">
      <h4 class="text-[10px] font-semibold text-muted-foreground/50 uppercase tracking-wide mb-2 flex items-center gap-1">
        <Play class="w-3 h-3" />
        可运行项目
      </h4>
      <div class="space-y-1.5">
        <div 
          v-for="project in projects" 
          :key="project.path"
          class="flex items-center gap-2 px-2.5 py-2 bg-gray-50 hover:bg-gray-100 rounded-lg cursor-pointer transition-colors border border-transparent hover:border-gray-200"
          @click="$emit('project-click', project)"
        >
          <div class="w-7 h-7 rounded-md bg-white border border-gray-200 flex items-center justify-center">
            <component :is="getProjectIcon(project.type)" class="w-4 h-4 text-gray-600" />
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-xs font-medium text-gray-800 truncate">{{ project.name }}</div>
            <div class="text-[10px] text-muted-foreground/50 uppercase">{{ project.type || 'unknown' }}</div>
          </div>
          <button 
            class="flex items-center gap-1 px-2 py-1 bg-success hover:bg-success/90 text-white text-[10px] font-medium rounded-md transition-colors" 
            @click.stop="$emit('run-project', project)"
          >
            <Play class="w-3 h-3" />
            运行
          </button>
        </div>
      </div>
    </div>
    
    <!-- 底部统计 -->
    <div class="flex items-center justify-between px-3 py-2 bg-white border-t border-border text-[10px] text-muted-foreground/50" v-if="hasFiles">
      <span>{{ fileCount }} 个文件</span>
      <span>{{ formattedTotalSize }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import FileTreeNode from './FileTreeNode.vue'
import { Folder, FolderOpen, RefreshCw, Loader2, Play, Globe, Code2, Zap, FileCode, AlertCircle } from 'lucide-vue-next'

// Props
const props = defineProps({
  conversationId: {
    type: String,
    required: true
  }
})

// Emits
const emit = defineEmits(['file-select', 'project-click', 'run-project'])

// Store
const workspaceStore = useWorkspaceStore()

// 状态
const isAllExpanded = ref(false)
const loadError = ref<string | null>(null)

// 计算属性
const isLoading = computed(() => workspaceStore.isLoadingFiles)
const files = computed(() => workspaceStore.files)
const projects = computed(() => workspaceStore.projects)
const hasFiles = computed(() => workspaceStore.hasFiles)
const hasProjects = computed(() => workspaceStore.hasProjects)
const formattedTotalSize = computed(() => workspaceStore.formattedTotalSize)

// 计算文件总数
const fileCount = computed(() => {
  const countFiles = (items: any[]) => {
    let count = 0
    for (const item of items) {
      if (item.type === 'file') {
        count++
      } else if (item.children) {
        count += countFiles(item.children)
      }
    }
    return count
  }
  return countFiles(files.value)
})

// 加载文件
async function loadFiles() {
  if (!props.conversationId) return
  
  loadError.value = null
  
  try {
    // 获取文件列表
    await Promise.all([
      workspaceStore.fetchFiles(props.conversationId, { path: '/home/user/project', tree: true }),
      workspaceStore.fetchProjects(props.conversationId)
    ])
    // 默认展开所有目录
    workspaceStore.expandAll()
    isAllExpanded.value = true
  } catch (error: any) {
    loadError.value = error.message || '加载失败'
    console.error('加载文件失败:', error)
  }
}

// 刷新文件
function refreshFiles() {
  loadFiles()
}

// 展开/收起所有
function toggleExpandAll() {
  if (isAllExpanded.value) {
    workspaceStore.collapseAll()
  } else {
    workspaceStore.expandAll()
  }
  isAllExpanded.value = !isAllExpanded.value
}

// 处理目录展开/收起
function handleToggle(path: string) {
  workspaceStore.toggleDir(path)
}

// 处理文件选择
function handleSelect(item: any) {
  emit('file-select', item)
}

// 处理下载
function handleDownload(item: any) {
  workspaceStore.downloadFile(props.conversationId, item.path)
}

// 获取项目图标
function getProjectIcon(type: string) {
  const icons: Record<string, any> = {
    'vue': Code2,
    'react': Code2,
    'nextjs': Code2,
    'static': Globe,
    'python': FileCode,
    'gradio': FileCode,
    'streamlit': FileCode,
    'flask': FileCode,
    'fastapi': Zap,
    'nodejs': Code2
  }
  return icons[type] || FileCode
}

// 监听 conversationId 变化
watch(() => props.conversationId, (newId) => {
  if (newId) {
    loadFiles()
  } else {
    workspaceStore.reset()
  }
}, { immediate: true })
</script>


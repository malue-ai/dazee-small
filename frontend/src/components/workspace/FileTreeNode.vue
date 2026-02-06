<template>
  <div class="select-none">
    <!-- 节点内容 -->
    <div 
      class="flex items-center gap-1.5 py-1.5 pr-2 cursor-pointer transition-colors group border-l-2"
      :class="[
        isSelected 
          ? 'bg-accent border-primary text-accent-foreground' 
          : 'border-transparent hover:bg-muted text-muted-foreground',
        isDirectory ? 'font-medium' : ''
      ]"
      :style="{ paddingLeft: (depth * 12 + 12) + 'px' }"
      @click="handleClick"
    >
      <!-- 展开/收起图标 -->
      <span v-if="isDirectory" class="w-3 h-3 flex items-center justify-center text-muted-foreground/50 flex-shrink-0">
        <ChevronDown v-if="isExpanded" class="w-3 h-3" />
        <ChevronRight v-else class="w-3 h-3" />
      </span>
      <span v-else class="w-3 flex-shrink-0"></span>
      
      <!-- 文件/文件夹图标 -->
      <component :is="getIcon()" class="w-4 h-4 flex-shrink-0" :class="getIconClass()" />
      
      <!-- 名称 -->
      <span 
        class="flex-1 text-xs truncate" 
        :title="item.path"
      >
        {{ fileName }}
      </span>
      
      <!-- 文件大小（仅文件） -->
      <span v-if="!isDirectory && item.size" class="text-[10px] text-muted-foreground/50 flex-shrink-0">
        {{ formatSize(item.size) }}
      </span>
      
      <!-- 操作按钮 -->
      <div class="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button 
          v-if="!isDirectory" 
          class="p-1 rounded text-muted-foreground/50 hover:bg-muted hover:text-foreground transition-colors"
          @click.stop="$emit('download', item)"
          title="下载"
        >
          <Download class="w-3 h-3" />
        </button>
      </div>
    </div>
    
    <!-- 子节点 -->
    <template v-if="isDirectory && isExpanded && item.children">
      <FileTreeNode
        v-for="child in item.children"
        :key="child.path"
        :item="child"
        :depth="depth + 1"
        @toggle="$emit('toggle', $event)"
        @select="$emit('select', $event)"
        @download="$emit('download', $event)"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { 
  ChevronDown, 
  ChevronRight, 
  Folder, 
  FolderOpen, 
  FileText, 
  FileCode, 
  FileJson, 
  Image, 
  File, 
  FileArchive,
  Lock,
  Download
} from 'lucide-vue-next'

// Props
const props = defineProps({
  item: {
    type: Object,
    required: true
  },
  depth: {
    type: Number,
    default: 0
  }
})

// Emits
const emit = defineEmits(['toggle', 'select', 'download'])

// Store
const workspaceStore = useWorkspaceStore()

// 计算属性
const isDirectory = computed(() => props.item.type === 'directory')
const isExpanded = computed(() => workspaceStore.isDirExpanded(props.item.path))
const isSelected = computed(() => workspaceStore.selectedFile?.path === props.item.path)

// 获取文件名
const fileName = computed(() => {
  const parts = props.item.path.split('/')
  return parts[parts.length - 1] || props.item.path
})

// 获取图标组件
function getIcon() {
  if (isDirectory.value) {
    return isExpanded.value ? FolderOpen : Folder
  }
  
  // 根据扩展名返回不同图标
  const ext = fileName.value.split('.').pop()?.toLowerCase()
  const iconMap: Record<string, any> = {
    // 代码文件
    'js': FileCode,
    'ts': FileCode,
    'jsx': FileCode,
    'tsx': FileCode,
    'vue': FileCode,
    'py': FileCode,
    'html': FileCode,
    'css': FileCode,
    'scss': FileCode,
    
    // 数据/配置文件
    'json': FileJson,
    'yaml': FileJson,
    'yml': FileJson,
    'md': FileText,
    
    // 图片
    'png': Image,
    'jpg': Image,
    'jpeg': Image,
    'gif': Image,
    'svg': Image,
    
    // 文档
    'pdf': FileText,
    'doc': FileText,
    'docx': FileText,
    'pptx': FileText,
    'xlsx': FileText,
    
    // 压缩
    'zip': FileArchive,
    'tar': FileArchive,
    'gz': FileArchive,
    
    // 其他
    'env': Lock,
    'lock': Lock
  }
  
  return iconMap[ext || ''] || File
}

// 获取图标颜色类
function getIconClass() {
  if (isDirectory.value) {
    return 'text-primary'
  }
  
  const ext = fileName.value.split('.').pop()?.toLowerCase()
  const colorMap: Record<string, string> = {
    'js': 'text-yellow-500',
    'ts': 'text-blue-600',
    'jsx': 'text-cyan-500',
    'tsx': 'text-cyan-600',
    'vue': 'text-green-500',
    'py': 'text-blue-500',
    'html': 'text-orange-500',
    'css': 'text-pink-500',
    'scss': 'text-pink-600',
    'json': 'text-gray-500',
    'yaml': 'text-gray-500',
    'yml': 'text-gray-500',
    'md': 'text-gray-600',
    'png': 'text-purple-500',
    'jpg': 'text-purple-500',
    'jpeg': 'text-purple-500',
    'gif': 'text-purple-500',
    'svg': 'text-orange-400',
    'pdf': 'text-red-500',
    'env': 'text-yellow-600',
    'lock': 'text-muted-foreground/50'
  }
  
  return colorMap[ext || ''] || 'text-muted-foreground/50'
}

// 格式化文件大小
function formatSize(bytes: number): string {
  if (!bytes || bytes === 0) return ''
  
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

// 处理点击
function handleClick() {
  if (isDirectory.value) {
    emit('toggle', props.item.path)
  } else {
    emit('select', props.item)
  }
}
</script>
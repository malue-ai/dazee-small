<template>
  <div class="tree-node" :style="{ paddingLeft: depth * 16 + 'px' }">
    <!-- 节点内容 -->
    <div 
      class="node-content"
      :class="{ 
        'is-directory': isDirectory, 
        'is-file': !isDirectory,
        'is-expanded': isExpanded
      }"
      @click="handleClick"
    >
      <!-- 展开/收起图标 -->
      <span v-if="isDirectory" class="expand-icon">
        {{ isExpanded ? '▼' : '▶' }}
      </span>
      <span v-else class="file-spacer"></span>
      
      <!-- 文件/文件夹图标 -->
      <span class="node-icon">{{ getIcon() }}</span>
      
      <!-- 名称 -->
      <span class="node-name" :title="item.path">{{ fileName }}</span>
      
      <!-- 文件大小（仅文件） -->
      <span v-if="!isDirectory && item.size" class="node-size">
        {{ formatSize(item.size) }}
      </span>
      
      <!-- 操作按钮 -->
      <div class="node-actions">
        <button 
          v-if="!isDirectory" 
          class="action-btn download-btn"
          @click.stop="$emit('download', item)"
          title="下载"
        >
          ⬇️
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

<script setup>
import { computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'

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

// 获取文件名
const fileName = computed(() => {
  const parts = props.item.path.split('/')
  return parts[parts.length - 1] || props.item.path
})

// 获取图标
function getIcon() {
  if (isDirectory.value) {
    return isExpanded.value ? '📂' : '📁'
  }
  
  // 根据扩展名返回不同图标
  const ext = fileName.value.split('.').pop()?.toLowerCase()
  const iconMap = {
    // 代码文件
    'js': '📜',
    'ts': '📘',
    'jsx': '⚛️',
    'tsx': '⚛️',
    'vue': '💚',
    'py': '🐍',
    'html': '🌐',
    'css': '🎨',
    'scss': '🎨',
    'json': '📋',
    'yaml': '📋',
    'yml': '📋',
    'md': '📝',
    
    // 图片
    'png': '🖼️',
    'jpg': '🖼️',
    'jpeg': '🖼️',
    'gif': '🖼️',
    'svg': '🎭',
    
    // 文档
    'pdf': '📕',
    'doc': '📄',
    'docx': '📄',
    'pptx': '📊',
    'xlsx': '📈',
    
    // 其他
    'zip': '📦',
    'tar': '📦',
    'gz': '📦',
    'env': '🔐',
    'lock': '🔒'
  }
  
  return iconMap[ext] || '📄'
}

// 格式化文件大小
function formatSize(bytes) {
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

<style scoped>
.tree-node {
  user-select: none;
}

.node-content {
  display: flex;
  align-items: center;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  gap: 6px;
}

.node-content:hover {
  background: rgba(255, 255, 255, 0.08);
}

.node-content.is-directory:hover {
  background: rgba(102, 126, 234, 0.15);
}

.expand-icon {
  font-size: 8px;
  width: 12px;
  color: #a0a0b0;
  transition: transform 0.15s;
}

.file-spacer {
  width: 12px;
}

.node-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.node-name {
  flex: 1;
  font-size: 13px;
  color: #e5e5e5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.is-directory .node-name {
  font-weight: 500;
  color: #a8c0ff;
}

.node-size {
  font-size: 11px;
  color: #707080;
  margin-left: 8px;
  flex-shrink: 0;
}

.node-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}

.node-content:hover .node-actions {
  opacity: 1;
}

.action-btn {
  padding: 2px 6px;
  background: transparent;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.action-btn:hover {
  background: rgba(255, 255, 255, 0.15);
}

.download-btn:hover {
  background: rgba(102, 126, 234, 0.3);
}
</style>


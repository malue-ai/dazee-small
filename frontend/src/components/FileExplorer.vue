<template>
  <div class="file-explorer">
    <!-- 头部 -->
    <div class="explorer-header">
      <h3 class="explorer-title">📁 工作区文件</h3>
      <div class="explorer-actions">
        <button @click="refreshFiles" class="action-btn" :disabled="isLoading" title="刷新">
          🔄
        </button>
        <button @click="toggleExpandAll" class="action-btn" title="展开/收起全部">
          {{ isAllExpanded ? '📁' : '📂' }}
        </button>
      </div>
    </div>
    
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-state">
      <div class="loading-spinner"></div>
      <span>加载中...</span>
    </div>
    
    <!-- 空状态 -->
    <div v-else-if="!hasFiles" class="empty-state">
      <div class="empty-icon">📭</div>
      <p>暂无文件</p>
      <p class="empty-hint">AI 创建的文件将显示在这里</p>
    </div>
    
    <!-- 文件树 -->
    <div v-else class="file-tree">
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
    <div v-if="hasProjects" class="projects-section">
      <h4 class="section-title">🚀 可运行项目</h4>
      <div class="project-cards">
        <div 
          v-for="project in projects" 
          :key="project.path"
          class="project-card"
          :class="project.type"
          @click="$emit('project-click', project)"
        >
          <div class="project-icon">{{ getProjectIcon(project.type) }}</div>
          <div class="project-info">
            <div class="project-name">{{ project.name }}</div>
            <div class="project-type">{{ project.type || 'unknown' }}</div>
          </div>
          <div class="project-action">
            <button class="run-btn" @click.stop="$emit('run-project', project)">
              ▶️ 运行
            </button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 底部统计 -->
    <div class="explorer-footer" v-if="hasFiles">
      <span class="file-count">{{ fileCount }} 个文件</span>
      <span class="total-size">{{ formattedTotalSize }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import FileTreeNode from './FileTreeNode.vue'

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

// 计算属性
const isLoading = computed(() => workspaceStore.isLoadingFiles)
const files = computed(() => workspaceStore.files)
const projects = computed(() => workspaceStore.projects)
const hasFiles = computed(() => workspaceStore.hasFiles)
const hasProjects = computed(() => workspaceStore.hasProjects)
const formattedTotalSize = computed(() => workspaceStore.formattedTotalSize)

// 计算文件总数
const fileCount = computed(() => {
  const countFiles = (items) => {
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
  
  try {
    await Promise.all([
      workspaceStore.fetchFiles(props.conversationId, { tree: true }),
      workspaceStore.fetchProjects(props.conversationId)
    ])
    // 默认展开所有目录
    workspaceStore.expandAll()
    isAllExpanded.value = true
  } catch (error) {
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
function handleToggle(path) {
  workspaceStore.toggleDir(path)
}

// 处理文件选择
function handleSelect(item) {
  emit('file-select', item)
}

// 处理下载
function handleDownload(item) {
  workspaceStore.downloadFile(props.conversationId, item.path)
}

// 获取项目图标
function getProjectIcon(type) {
  const icons = {
    'vue': '💚',
    'react': '⚛️',
    'nextjs': '▲',
    'static': '🌐',
    'python': '🐍',
    'gradio': '🎨',
    'streamlit': '📊',
    'flask': '🍶',
    'fastapi': '⚡',
    'nodejs': '💚'
  }
  return icons[type] || '📦'
}

// 监听 conversationId 变化
watch(() => props.conversationId, (newId) => {
  if (newId) {
    loadFiles()
  } else {
    workspaceStore.reset()
  }
}, { immediate: true })

// 初始化
onMounted(() => {
  if (props.conversationId) {
    loadFiles()
  }
})
</script>

<style scoped>
.file-explorer {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: transparent;
  overflow: hidden;
}

/* 头部 */
.explorer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.02);
  border-bottom: 1px solid #2d2d44;
}

.explorer-title {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: #a0a0b0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.explorer-actions {
  display: flex;
  gap: 6px;
}

.action-btn {
  padding: 5px 8px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.15);
}

.action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 加载状态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  color: #666;
  gap: 10px;
}

.loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(102, 126, 234, 0.2);
  border-top-color: #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  color: #666;
  text-align: center;
}

.empty-icon {
  font-size: 36px;
  margin-bottom: 12px;
  opacity: 0.6;
}

.empty-state p {
  margin: 3px 0;
  font-size: 13px;
}

.empty-hint {
  font-size: 11px;
  opacity: 0.6;
}

/* 文件树 */
.file-tree {
  flex: 1;
  overflow-y: auto;
  padding: 6px 8px;
}

/* 项目区域 */
.projects-section {
  padding: 12px;
  border-top: 1px solid #2d2d44;
  background: rgba(102, 126, 234, 0.03);
}

.section-title {
  margin: 0 0 10px 0;
  font-size: 11px;
  font-weight: 600;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.project-cards {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.project-card {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.08) 0%, rgba(118, 75, 162, 0.04) 100%);
  border: 1px solid rgba(102, 126, 234, 0.15);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.project-card:hover {
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.12) 0%, rgba(118, 75, 162, 0.08) 100%);
  border-color: rgba(102, 126, 234, 0.35);
  transform: translateX(3px);
}

.project-card.flask { border-left: 3px solid #10b981; }
.project-card.fastapi { border-left: 3px solid #059669; }
.project-card.vue { border-left: 3px solid #42b883; }
.project-card.react { border-left: 3px solid #61dafb; }
.project-card.nextjs { border-left: 3px solid #fff; }
.project-card.static { border-left: 3px solid #f7df1e; }
.project-card.python { border-left: 3px solid #3776ab; }
.project-card.gradio { border-left: 3px solid #ff6b35; }
.project-card.streamlit { border-left: 3px solid #ff4b4b; }

.project-icon {
  font-size: 20px;
  margin-right: 10px;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 6px;
}

.project-info {
  flex: 1;
  min-width: 0;
}

.project-name {
  font-size: 13px;
  font-weight: 600;
  color: #e5e5e5;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.project-type {
  font-size: 10px;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.run-btn {
  padding: 6px 12px;
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  border: none;
  border-radius: 6px;
  color: white;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.run-btn:hover {
  transform: scale(1.03);
  box-shadow: 0 3px 10px rgba(16, 185, 129, 0.35);
}

/* 底部统计 */
.explorer-footer {
  display: flex;
  justify-content: space-between;
  padding: 10px 14px;
  background: rgba(0, 0, 0, 0.15);
  border-top: 1px solid #2d2d44;
  font-size: 11px;
  color: #666;
}

/* 滚动条样式 */
.file-tree::-webkit-scrollbar {
  width: 5px;
}

.file-tree::-webkit-scrollbar-track {
  background: transparent;
}

.file-tree::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
}

.file-tree::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.18);
}
</style>


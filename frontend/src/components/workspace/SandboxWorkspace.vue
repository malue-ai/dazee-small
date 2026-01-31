<template>
  <div class="sandbox-workspace">
    <!-- 顶部工具栏 -->
    <div class="workspace-toolbar">
      <div class="toolbar-left">
        <h3 class="workspace-title">🧪 沙盒工作区</h3>
        <div class="sandbox-status" :style="{ color: sandboxStatusColor }">
          <span class="status-dot" :style="{ background: sandboxStatusColor }"></span>
          {{ sandboxStatusText }}
        </div>
      </div>
      
      <div class="toolbar-actions">
        <!-- 沙盒控制按钮 -->
        <button 
          v-if="sandbox.status === 'none'" 
          @click="handleInitSandbox"
          class="action-btn primary"
          :disabled="isLoadingSandbox"
        >
          {{ isLoadingSandbox ? '⏳ 创建中...' : '🚀 启动沙盒' }}
        </button>
        
        <button 
          v-if="sandbox.status === 'running'" 
          @click="handlePauseSandbox"
          class="action-btn warning"
        >
          ⏸️ 暂停
        </button>
        
        <button 
          v-if="sandbox.status === 'paused'" 
          @click="handleResumeSandbox"
          class="action-btn success"
          :disabled="isLoadingSandbox"
        >
          {{ isLoadingSandbox ? '⏳ 恢复中...' : '▶️ 恢复' }}
        </button>
        
        <button 
          v-if="isSandboxAvailable" 
          @click="handleKillSandbox"
          class="action-btn danger"
        >
          🗑️ 终止
        </button>
        
        <!-- 刷新按钮 -->
        <button 
          @click="refreshFiles" 
          class="action-btn" 
          :disabled="!isSandboxRunning || isLoadingFiles"
          title="刷新文件"
        >
          🔄
        </button>
        
        <!-- 终端按钮 -->
        <button 
          @click="showTerminal = !showTerminal" 
          class="action-btn"
          :class="{ active: showTerminal }"
          title="切换终端"
        >
          <span class="icon">💻</span>
        </button>
        
        <!-- 预览切换 -->
        <button 
          v-if="hasPreviewUrl" 
          @click="togglePreview"
          class="action-btn"
          :class="{ active: showPreview }"
          title="切换预览"
        >
          {{ showPreview ? '👁️' : '👁️‍🗨️' }}
        </button>
      </div>
    </div>
    
    <!-- 主内容区 -->
    <div class="workspace-content">
      <!-- 左侧文件树 -->
      <div class="file-panel" :class="{ collapsed: !showFilePanel }">
        <div class="panel-header">
          <span>📁 文件</span>
          <button @click="showFilePanel = !showFilePanel" class="toggle-btn">
            {{ showFilePanel ? '◀' : '▶' }}
          </button>
        </div>
        
        <div v-if="showFilePanel" class="panel-content">
          <!-- 加载状态 -->
          <div v-if="isLoadingFiles" class="loading-state">
            <div class="loading-spinner"></div>
            <span>加载中...</span>
          </div>
          
          <!-- 空状态 -->
          <div v-else-if="!hasFiles && isSandboxRunning" class="empty-state">
            <div class="empty-icon">📭</div>
            <p>沙盒内暂无文件</p>
          </div>
          
          <!-- 未启动沙盒 -->
          <div v-else-if="!isSandboxRunning" class="empty-state">
            <div class="empty-icon">🚀</div>
            <p>请先启动沙盒</p>
          </div>
          
          <!-- 文件树 -->
          <div v-else class="file-tree">
            <FileTreeNode
              v-for="item in files"
              :key="item.path"
              :item="item"
              :depth="0"
              :selected-path="selectedFile?.path"
              @toggle="handleToggle"
              @select="handleFileSelect"
              @download="handleDownload"
            />
          </div>
          
          <!-- 项目列表 -->
          <div v-if="hasProjects" class="projects-section">
            <div class="section-title">🚀 可运行项目</div>
            <div 
              v-for="project in projects" 
              :key="project.path"
              class="project-item"
              :class="[project.type, { running: runningProject === project.name }]"
              @click.stop="handleRunProject(project)"
            >
              <span class="project-icon">{{ getProjectIcon(project.type) }}</span>
              <div class="project-info">
                <span class="project-name">{{ project.name }}</span>
                <span class="project-type-badge">{{ project.type.toUpperCase() }}</span>
              </div>
              <button 
                @click.stop="handleRunProject(project)"
                class="run-btn"
                :class="{ loading: runningProject === project.name }"
                :disabled="runningProject === project.name"
                type="button"
              >
                <span v-if="runningProject === project.name" class="btn-spinner"></span>
                <span v-else>▶️</span>
                {{ runningProject === project.name ? '启动中...' : '运行' }}
              </button>
            </div>
          </div>
        </div>
      </div>
      
      <!-- 中间编辑区 -->
      <div class="editor-panel" :class="{ expanded: !showPreview }">
        <div class="panel-header">
          <!-- 实时预览模式 -->
          <template v-if="isLivePreviewing">
            <span class="live-preview-title">
              <span class="live-indicator"></span>
              ✨ {{ livePreviewPath || '正在编辑...' }}
            </span>
            <span class="live-badge">LIVE</span>
          </template>
          <!-- 普通编辑模式 -->
          <template v-else>
            <span v-if="selectedFile">📝 {{ selectedFile.name }}</span>
            <span v-else>📝 编辑器</span>
            
            <div v-if="selectedFile" class="editor-actions">
              <button @click="handleSaveFile" class="save-btn" title="保存 (Ctrl+S)">
                💾 保存
              </button>
            </div>
          </template>
        </div>
        
        <div class="panel-content">
          <!-- 实时预览面板 -->
          <div v-if="isLivePreviewing" class="live-preview-container">
            <div class="live-preview-header">
              <span class="tool-name">{{ livePreview.toolName }}</span>
              <span class="file-language" v-if="livePreviewLanguage !== 'text'">
                {{ livePreviewLanguage.toUpperCase() }}
              </span>
            </div>
            <pre class="live-preview-content" :class="'language-' + livePreviewLanguage">{{ livePreviewContent || '// AI 正在编写代码...' }}</pre>
            <div class="live-preview-footer">
              <span class="typing-indicator">
                <span class="dot"></span>
                <span class="dot"></span>
                <span class="dot"></span>
              </span>
              <span>AI 正在编写中...</span>
            </div>
          </div>
          
          <!-- 普通编辑器 -->
          <textarea
            v-else-if="selectedFile"
            v-model="fileContent"
            class="code-editor"
            :placeholder="'编辑 ' + selectedFile.name"
            @keydown.ctrl.s.prevent="handleSaveFile"
          ></textarea>
          
          <div v-else class="empty-editor">
            <div class="empty-icon">📄</div>
            <p>选择一个文件开始编辑</p>
            <p class="hint">或让 AI 在沙盒中创建新文件</p>
          </div>
        </div>
      </div>
      
      <!-- 右侧预览 -->
      <div v-if="showPreview && hasPreviewUrl" class="preview-panel">
        <div class="panel-header">
          <span>🌐 预览</span>
          <a :href="previewUrl" target="_blank" class="external-link" title="在新窗口打开">
            ↗️
          </a>
        </div>
        
        <div class="panel-content">
          <iframe
            :src="previewUrl"
            class="preview-iframe"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
          ></iframe>
        </div>
      </div>
    </div>
    
    <!-- 底部终端区 -->
    <div v-if="showTerminal" class="terminal-container">
      <TerminalPanel 
        :logs="terminalLogs" 
        :is-running="isTerminalRunning"
        @close="showTerminal = false"
        @clear="clearTerminal"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import FileTreeNode from './FileTreeNode.vue'
import TerminalPanel from './TerminalPanel.vue'

// Props
const props = defineProps({
  conversationId: {
    type: String,
    required: true
  },
  userId: {
    type: String,
    required: true
  }
})

// Store
const workspaceStore = useWorkspaceStore()

// 本地状态
const showFilePanel = ref(true)
const showTerminal = ref(false)
const runningProject = ref(null) // 正在运行的项目名称

// 计算属性
const isLoadingSandbox = computed(() => workspaceStore.isLoadingSandbox)
const isLoadingFiles = computed(() => workspaceStore.isLoadingFiles)
const sandbox = computed(() => workspaceStore.sandbox)
const files = computed(() => workspaceStore.files)
const projects = computed(() => workspaceStore.projects)
const hasFiles = computed(() => workspaceStore.hasFiles)
const hasProjects = computed(() => workspaceStore.hasProjects)
const selectedFile = computed(() => workspaceStore.selectedFile)
const fileContent = computed({
  get: () => workspaceStore.fileContent,
  set: (val) => workspaceStore.fileContent = val
})
const showPreview = computed({
  get: () => workspaceStore.showPreview,
  set: (val) => workspaceStore.showPreview = val
})
const previewUrl = computed(() => workspaceStore.sandbox.previewUrl)
const terminalLogs = computed(() => workspaceStore.terminalLogs)
const isTerminalRunning = computed(() => workspaceStore.isTerminalRunning)
const isSandboxRunning = computed(() => workspaceStore.isSandboxRunning)
const isSandboxAvailable = computed(() => workspaceStore.isSandboxAvailable)
const hasPreviewUrl = computed(() => workspaceStore.hasPreviewUrl)
const sandboxStatusText = computed(() => workspaceStore.sandboxStatusText)
const sandboxStatusColor = computed(() => workspaceStore.sandboxStatusColor)

// 实时预览相关
const livePreview = computed(() => workspaceStore.livePreview)
const isLivePreviewing = computed(() => workspaceStore.isLivePreviewing)
const livePreviewContent = computed(() => workspaceStore.livePreviewContent)
const livePreviewPath = computed(() => workspaceStore.livePreviewPath)
const livePreviewLanguage = computed(() => workspaceStore.livePreviewLanguage)

// 初始化沙盒
async function handleInitSandbox() {
  try {
    await workspaceStore.initSandbox(props.conversationId, props.userId)
    await refreshFiles()
  } catch (error) {
    console.error('初始化沙盒失败:', error)
    alert('初始化沙盒失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 暂停沙盒
async function handlePauseSandbox() {
  try {
    await workspaceStore.pauseSandbox(props.conversationId)
  } catch (error) {
    console.error('暂停沙盒失败:', error)
  }
}

// 恢复沙盒
async function handleResumeSandbox() {
  try {
    await workspaceStore.resumeSandbox(props.conversationId)
    await refreshFiles()
  } catch (error) {
    console.error('恢复沙盒失败:', error)
  }
}

// 终止沙盒
async function handleKillSandbox() {
  if (!confirm('确定要终止沙盒吗？所有数据将丢失！')) return
  
  try {
    await workspaceStore.killSandbox(props.conversationId)
    workspaceStore.reset()
  } catch (error) {
    console.error('终止沙盒失败:', error)
  }
}

// 刷新文件
async function refreshFiles() {
  if (!isSandboxRunning.value) return
  
  try {
    await Promise.all([
      workspaceStore.fetchFiles(props.conversationId, { path: '/home/user', tree: false }),
      workspaceStore.fetchProjects(props.conversationId)
    ])
  } catch (error) {
    console.error('刷新文件失败:', error)
  }
}

// 清空终端日志
function clearTerminal() {
  workspaceStore.clearTerminalLogs()
}

// 切换预览
function togglePreview() {
  workspaceStore.togglePreview()
}

// 处理目录展开
function handleToggle(path) {
  workspaceStore.toggleDir(path)
}

// 处理文件选择
async function handleFileSelect(item) {
  await workspaceStore.selectFile(props.conversationId, item)
}

// 处理下载
function handleDownload(item) {
  workspaceStore.downloadFile(props.conversationId, item.path)
}

// 保存文件
async function handleSaveFile() {
  if (!selectedFile.value) return
  
  try {
    await workspaceStore.saveFile(
      props.conversationId,
      selectedFile.value.path,
      fileContent.value
    )
    // TODO: 显示保存成功提示
  } catch (error) {
    console.error('保存文件失败:', error)
    alert('保存失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 运行项目
async function handleRunProject(project) {
  console.log('🚀 handleRunProject 被调用:', project)
  console.log('📍 conversationId:', props.conversationId)
  console.log('📦 project.name:', project.name)
  console.log('📦 project.type:', project.type)
  
  // 防止重复点击
  if (runningProject.value === project.name) return
  runningProject.value = project.name
  
  try {
    const result = await workspaceStore.runProject(
      props.conversationId,
      project.name,
      project.type
    )
    
    console.log('✅ runProject 结果:', result)
    console.log('📍 preview_url:', result.preview_url)
    console.log('📍 success:', result.success)
    
    if (result.success && result.preview_url) {
      console.log('🌐 准备打开新窗口:', result.preview_url)
      
      // 尝试打开新窗口
      const newWindow = window.open(result.preview_url, '_blank')
      
      // 检测是否被浏览器拦截
      if (!newWindow || newWindow.closed || typeof newWindow.closed === 'undefined') {
        console.warn('⚠️ 弹窗被浏览器拦截，显示提示')
        // 如果被拦截，显示可点击的链接
        const shouldOpen = confirm(
          `项目已启动！\n\n预览地址：${result.preview_url}\n\n点击"确定"在新窗口打开预览`
        )
        if (shouldOpen) {
          window.open(result.preview_url, '_blank')
        }
      } else {
        console.log('✅ 新窗口已打开')
      }
    } else if (!result.success) {
      alert('启动项目失败: ' + (result.error || result.message))
    }
  } catch (error) {
    console.error('❌ 运行项目失败:', error)
    alert('运行项目失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    runningProject.value = null
  }
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

// 监听终端运行状态，自动打开终端
watch(isTerminalRunning, (isRunning) => {
  if (isRunning && !showTerminal.value) {
    showTerminal.value = true
  }
})

// 监听 conversationId 变化
watch(() => props.conversationId, async (newId) => {
  if (newId) {
    workspaceStore.reset()
    try {
      await workspaceStore.fetchSandboxStatus(newId)
      if (isSandboxRunning.value) {
        await refreshFiles()
      }
    } catch (error) {
      console.error('获取沙盒状态失败:', error)
    }
  }
}, { immediate: true })

// 初始化
onMounted(async () => {
  if (props.conversationId) {
    try {
      await workspaceStore.fetchSandboxStatus(props.conversationId)
      if (isSandboxRunning.value) {
        await refreshFiles()
      }
    } catch (error) {
      console.error('初始化失败:', error)
    }
  }
})
</script>

<style scoped>
.sandbox-workspace {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #0f0f1a;
  border-radius: 12px;
  overflow: hidden;
  font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* 工具栏 */
.workspace-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: linear-gradient(135deg, #1a1a2e 0%, #16162a 100%);
  border-bottom: 1px solid #2d2d44;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.workspace-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #fff;
}

.sandbox-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.toolbar-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  color: #e5e5e5;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.2);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-color: transparent;
}

.action-btn.success {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  border-color: transparent;
}

.action-btn.warning {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
  border-color: transparent;
}

.action-btn.danger {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  border-color: transparent;
}

.action-btn.active {
  background: rgba(102, 126, 234, 0.3);
  border-color: #667eea;
}

/* 主内容区 */
.workspace-content {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* 面板通用样式 */
.file-panel, .editor-panel, .preview-panel {
  display: flex;
  flex-direction: column;
  border-right: 1px solid #2d2d44;
  transition: width 0.3s;
}

.file-panel {
  width: 260px;
  min-width: 200px;
  background: #13131f;
}

.file-panel.collapsed {
  width: 40px;
  min-width: 40px;
}

.editor-panel {
  flex: 1;
  min-width: 300px;
  background: #0f0f1a;
}

.editor-panel.expanded {
  flex: 2;
}

.preview-panel {
  width: 45%;
  min-width: 300px;
  background: #0f0f1a;
  border-right: none;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.03);
  border-bottom: 1px solid #2d2d44;
  font-size: 13px;
  font-weight: 500;
  color: #a0a0b0;
}

.panel-content {
  flex: 1;
  overflow: auto;
}

.toggle-btn {
  padding: 4px 8px;
  background: transparent;
  border: none;
  color: #666;
  cursor: pointer;
  font-size: 12px;
}

/* 文件树 */
.file-tree {
  padding: 8px;
}

.loading-state, .empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 16px;
  color: #666;
  text-align: center;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid rgba(102, 126, 234, 0.3);
  border-top-color: #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 12px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-icon {
  font-size: 36px;
  margin-bottom: 12px;
}

.empty-state p {
  margin: 4px 0;
  font-size: 13px;
}

/* 项目列表 */
.projects-section {
  padding: 12px;
  border-top: 1px solid #2d2d44;
  margin-top: 12px;
}

.section-title {
  font-size: 11px;
  font-weight: 600;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
}

.project-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.08) 0%, rgba(118, 75, 162, 0.05) 100%);
  border: 1px solid rgba(102, 126, 234, 0.2);
  border-radius: 10px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.25s ease;
}

.project-item:hover {
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.15) 0%, rgba(118, 75, 162, 0.1) 100%);
  border-color: rgba(102, 126, 234, 0.4);
  transform: translateX(4px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
}

.project-item.running {
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(5, 150, 105, 0.1) 100%);
  border-color: rgba(16, 185, 129, 0.4);
  animation: runningPulse 1.5s ease-in-out infinite;
}

@keyframes runningPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.3); }
  50% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
}

.project-icon {
  font-size: 20px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
}

.project-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
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

.project-type-badge {
  font-size: 10px;
  font-weight: 500;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.run-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  border: none;
  border-radius: 6px;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.run-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #34d399 0%, #10b981 100%);
  transform: scale(1.02);
  box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
}

.run-btn:disabled {
  opacity: 0.8;
  cursor: wait;
}

.run-btn.loading {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
}

.btn-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* 编辑器 */
.code-editor {
  width: 100%;
  height: 100%;
  padding: 16px;
  background: transparent;
  border: none;
  color: #e5e5e5;
  font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', Consolas, monospace;
  font-size: 13px;
  line-height: 1.6;
  resize: none;
  outline: none;
}

.code-editor::placeholder {
  color: #4a4a5a;
}

.empty-editor {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #666;
}

.empty-editor .hint {
  font-size: 12px;
  opacity: 0.7;
}

.editor-actions {
  display: flex;
  gap: 8px;
}

.save-btn {
  padding: 4px 10px;
  background: rgba(16, 185, 129, 0.2);
  border: 1px solid rgba(16, 185, 129, 0.4);
  border-radius: 4px;
  color: #10b981;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.save-btn:hover {
  background: rgba(16, 185, 129, 0.3);
}

/* 预览 */
.preview-iframe {
  width: 100%;
  height: 100%;
  border: none;
  background: #fff;
}

.external-link {
  color: #667eea;
  text-decoration: none;
  font-size: 14px;
}

/* 终端面板 */
.terminal-container {
  height: 250px;
  border-top: 1px solid #2d2d44;
  background: #0d1117;
  flex-shrink: 0;
}

/* 实时预览样式 */
.live-preview-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #10b981;
  font-weight: 500;
}

.live-indicator {
  width: 8px;
  height: 8px;
  background: #10b981;
  border-radius: 50%;
  animation: livePulse 1.5s ease-in-out infinite;
}

@keyframes livePulse {
  0%, 100% { 
    opacity: 1; 
    transform: scale(1);
    box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.5);
  }
  50% { 
    opacity: 0.8; 
    transform: scale(1.1);
    box-shadow: 0 0 0 6px rgba(16, 185, 129, 0);
  }
}

.live-badge {
  padding: 2px 8px;
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  border-radius: 4px;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1px;
  animation: badgeGlow 2s ease-in-out infinite;
}

@keyframes badgeGlow {
  0%, 100% { box-shadow: 0 0 8px rgba(16, 185, 129, 0.4); }
  50% { box-shadow: 0 0 16px rgba(16, 185, 129, 0.6); }
}

.live-preview-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: linear-gradient(180deg, #0d1117 0%, #0a0e14 100%);
  border: 1px solid rgba(16, 185, 129, 0.2);
  border-radius: 8px;
  margin: 8px;
  overflow: hidden;
}

.live-preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: rgba(16, 185, 129, 0.08);
  border-bottom: 1px solid rgba(16, 185, 129, 0.15);
}

.tool-name {
  font-size: 12px;
  font-weight: 500;
  color: #10b981;
  font-family: 'JetBrains Mono', monospace;
}

.file-language {
  padding: 2px 6px;
  background: rgba(102, 126, 234, 0.15);
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  color: #667eea;
}

.live-preview-content {
  flex: 1;
  margin: 0;
  padding: 16px;
  overflow: auto;
  font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', Consolas, monospace;
  font-size: 13px;
  line-height: 1.7;
  color: #e6edf3;
  white-space: pre-wrap;
  word-break: break-word;
  /* 添加打字机效果的光标 */
  border-right: 2px solid transparent;
  animation: typewriterCursor 1s steps(1) infinite;
}

@keyframes typewriterCursor {
  0%, 50% { border-right-color: #10b981; }
  50.1%, 100% { border-right-color: transparent; }
}

/* 语言特定样式 */
.live-preview-content.language-python {
  color: #a5d6ff;
}

.live-preview-content.language-javascript,
.live-preview-content.language-typescript {
  color: #ffa657;
}

.live-preview-content.language-markdown {
  color: #c9d1d9;
}

.live-preview-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: rgba(16, 185, 129, 0.05);
  border-top: 1px solid rgba(16, 185, 129, 0.1);
  color: #8b949e;
  font-size: 12px;
}

.typing-indicator {
  display: flex;
  gap: 3px;
}

.typing-indicator .dot {
  width: 6px;
  height: 6px;
  background: #10b981;
  border-radius: 50%;
  animation: typingBounce 1.4s ease-in-out infinite;
}

.typing-indicator .dot:nth-child(1) { animation-delay: 0s; }
.typing-indicator .dot:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator .dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes typingBounce {
  0%, 60%, 100% { 
    transform: translateY(0);
    opacity: 0.5;
  }
  30% { 
    transform: translateY(-4px);
    opacity: 1;
  }
}

/* 滚动条 */
.panel-content::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.panel-content::-webkit-scrollbar-track {
  background: transparent;
}

.panel-content::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 3px;
}

.panel-content::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.25);
}
</style>


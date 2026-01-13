import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUIStore = defineStore('ui', () => {
  // 侧边栏状态
  const leftSidebarCollapsed = ref(false)
  const rightSidebarVisible = ref(true)
  const rightSidebarTab = ref<'plan' | 'mind'>('plan')
  
  // 工作区面板
  const workspacePanelVisible = ref(false)
  
  // 全局加载状态
  const globalLoading = ref(false)

  // 切换左侧边栏
  function toggleLeftSidebar() {
    leftSidebarCollapsed.value = !leftSidebarCollapsed.value
  }

  // 切换右侧边栏
  function toggleRightSidebar() {
    rightSidebarVisible.value = !rightSidebarVisible.value
  }

  // 切换工作区面板
  function toggleWorkspacePanel() {
    workspacePanelVisible.value = !workspacePanelVisible.value
  }

  // 设置右侧边栏标签
  function setRightSidebarTab(tab: 'plan' | 'mind') {
    rightSidebarTab.value = tab
    if (!rightSidebarVisible.value) {
      rightSidebarVisible.value = true
    }
  }

  return {
    leftSidebarCollapsed,
    rightSidebarVisible,
    rightSidebarTab,
    workspacePanelVisible,
    globalLoading,
    toggleLeftSidebar,
    toggleRightSidebar,
    toggleWorkspacePanel,
    setRightSidebarTab
  }
})


/**
 * Skill 管理 Store
 * 负责全局技能库和项目技能的状态管理
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as skillsApi from '@/api/skills'
import type { SkillSummary } from '@/types'
import type { SkillDetailResponse, SkillFileContentResponse } from '@/api/skills'

export const useSkillStore = defineStore('skill', () => {
  // ==================== 状态 ====================

  /** 当前活跃的 Tab：library = 技能库, project = 项目技能 */
  const activeTab = ref<'library' | 'project'>('library')

  /** 全局技能库列表 */
  const globalSkills = ref<SkillSummary[]>([])

  /** 当前项目已安装的技能列表 */
  const projectSkills = ref<SkillSummary[]>([])

  /** 项目技能 tab 选中的 agentId */
  const selectedAgentId = ref<string | null>(null)

  /** 当前选中查看详情的技能 */
  const selectedSkill = ref<SkillSummary | null>(null)

  /** 技能详情 */
  const skillDetail = ref<SkillDetailResponse | null>(null)

  /** 加载状态 */
  const globalLoading = ref(false)
  const projectLoading = ref(false)
  const detailLoading = ref(false)
  const actionLoading = ref(false)

  // ==================== 计算属性 ====================

  /** 当前 tab 对应的技能列表 */
  const currentSkills = computed(() => {
    return activeTab.value === 'library' ? globalSkills.value : projectSkills.value
  })

  /** 当前 tab 是否在加载 */
  const currentLoading = computed(() => {
    return activeTab.value === 'library' ? globalLoading.value : projectLoading.value
  })

  // ==================== 全局技能库 ====================

  /** 获取全局技能库列表 */
  async function fetchGlobal(): Promise<void> {
    globalLoading.value = true
    try {
      globalSkills.value = await skillsApi.getGlobalSkills()
    } catch (error) {
      console.error('获取全局技能库失败:', error)
    } finally {
      globalLoading.value = false
    }
  }

  /** 上传新技能到全局库 */
  async function uploadToGlobal(file: File, skillName: string): Promise<{ success: boolean; message: string }> {
    actionLoading.value = true
    try {
      const result = await skillsApi.uploadSkill(file, skillName)
      if (result.success) {
        await fetchGlobal()
      }
      return result
    } catch (error: any) {
      console.error('上传技能失败:', error?.response?.data || error)
      return { success: false, message: extractErrorMessage(error, '上传失败') }
    } finally {
      actionLoading.value = false
    }
  }

  // ==================== 项目技能 ====================

  /** 获取指定项目的已安装技能 */
  async function fetchProjectSkills(agentId: string): Promise<void> {
    selectedAgentId.value = agentId
    projectLoading.value = true
    try {
      projectSkills.value = await skillsApi.getInstanceSkills(agentId)
    } catch (error) {
      console.error(`获取项目 ${agentId} 技能失败:`, error)
      projectSkills.value = []
    } finally {
      projectLoading.value = false
    }
  }

  /** 从错误对象中提取可读消息 */
  function extractErrorMessage(error: any, fallback: string): string {
    const detail = error?.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (detail?.message && typeof detail.message === 'string') return detail.message
    if (error?.response?.data?.message && typeof error.response.data.message === 'string') return error.response.data.message
    if (error?.message && typeof error.message === 'string') return error.message
    return fallback
  }

  /** 安装全局技能到项目 */
  async function install(skillName: string, agentId: string): Promise<{ success: boolean; message: string }> {
    actionLoading.value = true
    try {
      const result = await skillsApi.installSkill({ skill_name: skillName, agent_id: agentId })
      // 如果当前正在查看该项目的技能，刷新列表
      if (selectedAgentId.value === agentId) {
        await fetchProjectSkills(agentId)
      }
      return { success: result.success, message: result.message || (result.success ? '安装成功' : '安装失败') }
    } catch (error: any) {
      console.error('安装技能失败:', error?.response?.data || error)
      return { success: false, message: extractErrorMessage(error, '安装失败') }
    } finally {
      actionLoading.value = false
    }
  }

  /** 从项目卸载技能 */
  async function uninstall(skillName: string, agentId: string): Promise<{ success: boolean; message: string }> {
    actionLoading.value = true
    try {
      const result = await skillsApi.uninstallSkill({ skill_name: skillName, agent_id: agentId })
      // 如果当前正在查看该项目的技能，刷新列表
      if (selectedAgentId.value === agentId) {
        await fetchProjectSkills(agentId)
      }
      // 如果卸载的是当前选中的技能，清除选中
      if (selectedSkill.value?.name === skillName) {
        selectedSkill.value = null
        skillDetail.value = null
      }
      return { success: result.success, message: result.message || (result.success ? '卸载成功' : '卸载失败') }
    } catch (error: any) {
      console.error('卸载技能失败:', error?.response?.data || error)
      return { success: false, message: extractErrorMessage(error, '卸载失败') }
    } finally {
      actionLoading.value = false
    }
  }

  // ==================== 详情 ====================

  /** 选中技能并加载详情 */
  async function selectSkill(skill: SkillSummary): Promise<void> {
    selectedSkill.value = skill
    skillDetail.value = null
    detailLoading.value = true
    try {
      // 项目技能 tab 下传 agentId 以获取实例维度的详情
      const agentId = activeTab.value === 'project' ? selectedAgentId.value || undefined : undefined
      skillDetail.value = await skillsApi.getSkillDetail(skill.name, agentId)
    } catch (error) {
      console.error('获取技能详情失败:', error)
    } finally {
      detailLoading.value = false
    }
  }

  /** 重新加载当前选中 skill 的详情 */
  async function reloadDetail(skillName?: string, agentId?: string): Promise<void> {
    const name = skillName || selectedSkill.value?.name
    if (!name) return
    detailLoading.value = true
    try {
      const aid = agentId ?? (activeTab.value === 'project' ? selectedAgentId.value || undefined : undefined)
      skillDetail.value = await skillsApi.getSkillDetail(name, aid)
    } catch (error) {
      console.error('刷新技能详情失败:', error)
    } finally {
      detailLoading.value = false
    }
  }

  /** 清除选中 */
  function clearSelection(): void {
    selectedSkill.value = null
    skillDetail.value = null
  }

  // ==================== Tab 切换 ====================

  /** 切换 tab */
  function switchTab(tab: 'library' | 'project'): void {
    activeTab.value = tab
    clearSelection()
  }

  // ==================== 重置 ====================

  /** 重置所有状态 */
  function reset(): void {
    activeTab.value = 'library'
    globalSkills.value = []
    projectSkills.value = []
    selectedAgentId.value = null
    selectedSkill.value = null
    skillDetail.value = null
  }

  return {
    // 状态
    activeTab,
    globalSkills,
    projectSkills,
    selectedAgentId,
    selectedSkill,
    skillDetail,
    globalLoading,
    projectLoading,
    detailLoading,
    actionLoading,

    // 计算属性
    currentSkills,
    currentLoading,

    // 全局技能库
    fetchGlobal,
    uploadToGlobal,

    // 项目技能
    fetchProjectSkills,
    install,
    uninstall,

    // 详情
    selectSkill,
    reloadDetail,
    clearSelection,

    // Tab
    switchTab,

    // 重置
    reset,
  }
})

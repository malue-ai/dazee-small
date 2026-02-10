/**
 * Agent（项目）管理 Store
 * 负责 Agent CRUD、Agent-Conversation 关联映射
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as agentApi from '@/api/agent'
import { storeLog } from '@/utils/logger'
import type { AgentSummary, AgentDetail, AgentCreateRequest, AgentUpdateRequest, AgentUpdateResponse } from '@/types'

// ==================== localStorage 常量 ====================

/** 全部对话历史映射 */
const AGENT_CONVERSATIONS_KEY = 'agentConversations'
/** 当前打开的标签页映射 */
const AGENT_OPEN_TABS_KEY = 'agentOpenTabs'

// ==================== 辅助函数 ====================

/** 从 localStorage 读取映射 */
function loadMapping(key: string): Record<string, string[]> {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

/** 写入映射到 localStorage */
function saveMapping(key: string, mapping: Record<string, string[]>): void {
  localStorage.setItem(key, JSON.stringify(mapping))
}

// ==================== Store ====================

export const useAgentStore = defineStore('agent', () => {
  // ==================== 状态 ====================

  /** Agent 列表 */
  const agents = ref<AgentSummary[]>([])

  /** 当前选中的 Agent ID */
  const currentAgentId = ref<string | null>(null)

  /** 当前 Agent 详情（按需加载） */
  const currentAgentDetail = ref<AgentDetail | null>(null)

  /** Agent → 全部对话历史映射 (localStorage) */
  const agentConversations = ref<Record<string, string[]>>(loadMapping(AGENT_CONVERSATIONS_KEY))

  /** Agent → 当前打开的标签页映射 (localStorage) */
  const agentOpenTabs = ref<Record<string, string[]>>(loadMapping(AGENT_OPEN_TABS_KEY))

  /** 加载状态 */
  const loading = ref(false)

  /** 正在进行的 fetchList Promise（竞态保护，避免并发请求返回过期数据） */
  let fetchPromise: Promise<AgentSummary[]> | null = null

  // ==================== 计算属性 ====================

  /** 当前 Agent 的摘要信息 */
  const currentAgent = computed(() => {
    if (!currentAgentId.value) return null
    return agents.value.find(a => a.agent_id === currentAgentId.value) ?? null
  })

  /** 当前 Agent 的全部对话 ID 列表（历史） */
  const currentConversationIds = computed(() => {
    if (!currentAgentId.value) return []
    return agentConversations.value[currentAgentId.value] ?? []
  })

  /** 当前 Agent 打开的标签页 ID 列表 */
  const currentOpenTabIds = computed(() => {
    if (!currentAgentId.value) return []
    return agentOpenTabs.value[currentAgentId.value] ?? []
  })

  // ==================== 方法 ====================

  /**
   * 获取 Agent 列表（带竞态保护，并发调用复用同一个 Promise）
   */
  async function fetchList(): Promise<AgentSummary[]> {
    // 如果已有进行中的请求，复用它而非返回旧数据
    if (fetchPromise) return fetchPromise

    loading.value = true
    fetchPromise = agentApi.getAgentList()
      .then((list) => {
        agents.value = list
        return list
      })
      .catch((error) => {
        storeLog.error('获取 Agent 列表失败', error)
        throw error
      })
      .finally(() => {
        loading.value = false
        fetchPromise = null
      })

    return fetchPromise
  }

  /**
   * 创建 Agent（异步模式）
   *
   * POST 立即返回 agent_id，后台异步 preload。
   * 进度通过 agentCreation store 的 WebSocket 推送到全局通知卡片。
   *
   * @param data - 创建请求参数
   * @returns { agent_id, name, status: "creating" }
   */
  async function createAgent(data: AgentCreateRequest): Promise<{ agent_id: string; name: string }> {
    try {
      const result = await agentApi.createAgent(data)
      storeLog.info(`Agent 创建已提交: ${result.agent_id}`)
      return { agent_id: result.agent_id, name: result.name }
    } catch (error) {
      storeLog.error('提交 Agent 创建失败', error)
      throw error
    }
  }

  /**
   * 加载 Agent 详情
   */
  async function loadDetail(agentId: string): Promise<AgentDetail> {
    try {
      const detail = await agentApi.getAgentDetail(agentId)
      currentAgentDetail.value = detail
      return detail
    } catch (error) {
      storeLog.error('加载 Agent 详情失败', error)
      throw error
    }
  }

  /**
   * 选中 Agent（切换项目）
   */
  async function selectAgent(agentId: string): Promise<void> {
    currentAgentId.value = agentId
    await loadDetail(agentId)
  }

  /**
   * 更新 Agent（异步模式）
   *
   * PUT 立即返回 { agent_id, name, status: "reloading" }。
   * 后台异步重载，前端通过 WebSocket 追踪进度。
   */
  async function updateAgent(agentId: string, data: AgentUpdateRequest): Promise<AgentUpdateResponse> {
    try {
      const result = await agentApi.updateAgent(agentId, data)
      return result
    } catch (error) {
      storeLog.error('更新 Agent 失败', error)
      throw error
    }
  }

  /**
   * 删除 Agent
   */
  async function removeAgent(agentId: string): Promise<void> {
    try {
      await agentApi.deleteAgent(agentId)

      // 清理映射
      delete agentConversations.value[agentId]
      delete agentOpenTabs.value[agentId]
      saveMapping(AGENT_CONVERSATIONS_KEY, agentConversations.value)
      saveMapping(AGENT_OPEN_TABS_KEY, agentOpenTabs.value)

      // 如果删了当前 Agent，重置
      if (currentAgentId.value === agentId) {
        currentAgentId.value = null
        currentAgentDetail.value = null
      }

      await fetchList()
      storeLog.info(`Agent 已删除: ${agentId}`)
    } catch (error) {
      storeLog.error('删除 Agent 失败', error)
      throw error
    }
  }

  // ==================== Agent-Conversation 映射 ====================

  /**
   * 将对话绑定到 Agent（同时加入历史和打开的标签页）
   */
  function linkConversation(agentId: string, conversationId: string): void {
    // 加入历史
    if (!agentConversations.value[agentId]) {
      agentConversations.value[agentId] = []
    }
    if (!agentConversations.value[agentId].includes(conversationId)) {
      agentConversations.value[agentId].push(conversationId)
      saveMapping(AGENT_CONVERSATIONS_KEY, agentConversations.value)
    }
    // 同时打开为标签页
    openTab(agentId, conversationId)
  }

  /**
   * 从 Agent 完全移除对话（历史 + 标签页都移除，用于真正删除）
   */
  function unlinkConversation(agentId: string, conversationId: string): void {
    // 从历史移除
    if (agentConversations.value[agentId]) {
      agentConversations.value[agentId] = agentConversations.value[agentId].filter(
        id => id !== conversationId
      )
      saveMapping(AGENT_CONVERSATIONS_KEY, agentConversations.value)
    }
    // 从标签页移除
    closeTab(agentId, conversationId)
  }

  /**
   * 获取 Agent 关联的全部对话 ID 列表（历史）
   */
  function getConversationIds(agentId: string): string[] {
    return agentConversations.value[agentId] ?? []
  }

  // ==================== 标签页管理 ====================

  /**
   * 打开标签页（将对话添加到标签栏，不影响历史）
   */
  function openTab(agentId: string, conversationId: string): void {
    if (!agentOpenTabs.value[agentId]) {
      agentOpenTabs.value[agentId] = []
    }
    if (!agentOpenTabs.value[agentId].includes(conversationId)) {
      agentOpenTabs.value[agentId].push(conversationId)
      saveMapping(AGENT_OPEN_TABS_KEY, agentOpenTabs.value)
    }
  }

  /**
   * 关闭标签页（仅从标签栏移除，对话仍保留在历史中）
   */
  function closeTab(agentId: string, conversationId: string): void {
    if (!agentOpenTabs.value[agentId]) return
    agentOpenTabs.value[agentId] = agentOpenTabs.value[agentId].filter(
      id => id !== conversationId
    )
    saveMapping(AGENT_OPEN_TABS_KEY, agentOpenTabs.value)
  }

  /**
   * 获取 Agent 当前打开的标签页 ID 列表
   */
  function getOpenTabIds(agentId: string): string[] {
    return agentOpenTabs.value[agentId] ?? []
  }

  /**
   * 同步 localStorage 中的对话映射，移除后端已不存在的对话 ID
   * @param agentId - Agent ID
   * @param validIds - 后端返回的有效对话 ID 集合
   */
  function syncConversations(agentId: string, validIds: Set<string>): void {
    let changed = false

    // 清理对话历史中的失效 ID
    if (agentConversations.value[agentId]) {
      const before = agentConversations.value[agentId].length
      agentConversations.value[agentId] = agentConversations.value[agentId].filter(
        id => validIds.has(id)
      )
      if (agentConversations.value[agentId].length !== before) {
        saveMapping(AGENT_CONVERSATIONS_KEY, agentConversations.value)
        changed = true
      }
    }

    // 清理打开标签页中的失效 ID
    if (agentOpenTabs.value[agentId]) {
      const before = agentOpenTabs.value[agentId].length
      agentOpenTabs.value[agentId] = agentOpenTabs.value[agentId].filter(
        id => validIds.has(id)
      )
      if (agentOpenTabs.value[agentId].length !== before) {
        saveMapping(AGENT_OPEN_TABS_KEY, agentOpenTabs.value)
        changed = true
      }
    }

    if (changed) {
      storeLog.info(`已清理 Agent ${agentId} 的失效对话缓存`)
    }
  }

  /**
   * 重置状态
   */
  function reset(): void {
    currentAgentId.value = null
    currentAgentDetail.value = null
  }

  return {
    // 状态
    agents,
    currentAgentId,
    currentAgentDetail,
    agentConversations,
    agentOpenTabs,
    loading,

    // 计算属性
    currentAgent,
    currentConversationIds,
    currentOpenTabIds,

    // 方法
    fetchList,
    createAgent,
    loadDetail,
    selectAgent,
    updateAgent,
    removeAgent,
    linkConversation,
    unlinkConversation,
    getConversationIds,
    syncConversations,
    openTab,
    closeTab,
    getOpenTabIds,
    reset
  }
})

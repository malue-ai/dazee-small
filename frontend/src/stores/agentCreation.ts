/**
 * Agent 创建任务 Store
 *
 * 职责单一：管理 Agent 创建的 WebSocket 连接和后台状态追踪。
 * 通知展示委托给通用的 notification store。
 *
 * 用户在创建页发起 POST → 立即返回 → 本 store 通过 WS 接收实时进度
 * → 推送到 notification store 驱动右上角通知卡片。
 */

import { defineStore } from 'pinia'
import { reactive, computed } from 'vue'
import { getApiBaseUrl } from '@/api'
import { useAgentStore } from './agent'
import { useNotificationStore } from './notification'
import type { AgentCreationEvent } from '@/types'

// ==================== 类型 ====================

export type CreationTaskStatus = 'creating' | 'complete' | 'error'

export interface CreationTask {
  agentId: string
  agentName: string
  status: CreationTaskStatus
  /** notification store 中对应的通知 ID */
  notificationId: string
}

// ==================== 常量 ====================

const WS_RECONNECT_MS = 2000
const MAX_RECONNECT = 5

// ==================== Store ====================

export const useAgentCreationStore = defineStore('agentCreation', () => {
  // ==================== 状态 ====================

  /** Active creation tasks: agentId → CreationTask */
  const tasks = reactive<Map<string, CreationTask>>(new Map())

  /** WebSocket instances (internal, not reactive) */
  const _wsMap = new Map<string, WebSocket>()
  const _reconnectCount = new Map<string, number>()

  // ==================== 计算属性 ====================

  const hasActiveCreation = computed(() =>
    Array.from(tasks.values()).some(t => t.status === 'creating')
  )

  // ==================== WebSocket URL ====================

  function getWsUrl(agentId: string): string {
    const baseUrl = getApiBaseUrl()
    if (baseUrl.startsWith('http')) {
      const wsBase = baseUrl.replace(/^http/, 'ws')
      return `${wsBase}/v1/agents/ws/create/${agentId}`
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}${baseUrl}/v1/agents/ws/create/${agentId}`
  }

  // ==================== WebSocket 连接管理 ====================

  function connectWs(agentId: string) {
    const existing = _wsMap.get(agentId)
    if (existing && existing.readyState <= WebSocket.OPEN) {
      existing.close()
    }

    const url = getWsUrl(agentId)
    const ws = new WebSocket(url)
    _wsMap.set(agentId, ws)

    ws.onopen = () => {
      _reconnectCount.set(agentId, 0)
    }

    ws.onmessage = (event) => {
      try {
        const data: AgentCreationEvent = JSON.parse(event.data)
        handleWsEvent(agentId, data)
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onclose = () => {
      _wsMap.delete(agentId)

      const task = tasks.get(agentId)
      if (!task || task.status !== 'creating') return

      const count = (_reconnectCount.get(agentId) ?? 0) + 1
      _reconnectCount.set(agentId, count)

      if (count <= MAX_RECONNECT) {
        setTimeout(() => {
          const t = tasks.get(agentId)
          if (t?.status === 'creating') {
            connectWs(agentId)
          }
        }, WS_RECONNECT_MS * count)
      } else {
        startPolling(agentId)
      }
    }
  }

  function handleWsEvent(agentId: string, event: AgentCreationEvent) {
    const task = tasks.get(agentId)
    if (!task) return

    const notif = useNotificationStore()

    if (event.type === 'progress') {
      notif.update(task.notificationId, {
        message: event.message,
        progress: { step: event.step, total: event.total },
      })
    } else if (event.type === 'complete') {
      task.status = 'complete'
      notif.update(task.notificationId, {
        type: 'success',
        message: '创建成功',
        progress: undefined,
        action: {
          label: '打开',
          route: { name: 'agent', params: { agentId } },
        },
      })
      onCreationComplete(agentId)
    } else if (event.type === 'error') {
      task.status = 'error'
      notif.update(task.notificationId, {
        type: 'error',
        message: event.message || '创建失败',
        progress: undefined,
      })
    }
    // type === 'ping' → keepalive, ignore
  }

  // ==================== Polling fallback ====================

  function startPolling(agentId: string) {
    const agentStore = useAgentStore()
    let attempts = 0
    const maxAttempts = 30

    const timer = setInterval(async () => {
      attempts++
      try {
        const list = await agentStore.fetchList()
        const found = list.find(a => a.agent_id === agentId)
        if (found) {
          clearInterval(timer)
          const task = tasks.get(agentId)
          if (task && task.status === 'creating') {
            task.status = 'complete'
            const notif = useNotificationStore()
            notif.update(task.notificationId, {
              type: 'success',
              message: '创建成功',
              progress: undefined,
              action: {
                label: '打开',
                route: { name: 'agent', params: { agentId } },
              },
            })
            onCreationComplete(agentId)
          }
        }
      } catch {
        // Network error, keep polling
      }

      if (attempts >= maxAttempts) {
        clearInterval(timer)
        const task = tasks.get(agentId)
        if (task && task.status === 'creating') {
          task.status = 'error'
          const notif = useNotificationStore()
          notif.update(task.notificationId, {
            type: 'error',
            message: '创建超时，请刷新页面查看',
            progress: undefined,
          })
        }
      }
    }, 2000)
  }

  // ==================== 任务生命周期 ====================

  /**
   * Start tracking a creation task.
   * Pushes a progress notification and connects WebSocket.
   */
  function startCreation(agentId: string, agentName: string) {
    const notif = useNotificationStore()

    // Push progress notification
    const notificationId = notif.push({
      id: `agent-create-${agentId}`,
      type: 'progress',
      title: agentName,
      message: '正在初始化...',
      progress: { step: 0, total: 7 },
    })

    const task: CreationTask = {
      agentId,
      agentName,
      status: 'creating',
      notificationId,
    }
    tasks.set(agentId, task)

    connectWs(agentId)
  }

  /**
   * Handle creation completion: refresh agent list.
   */
  function onCreationComplete(agentId: string) {
    const agentStore = useAgentStore()
    agentStore.fetchList()

    // Clean up task after a delay
    setTimeout(() => {
      tasks.delete(agentId)
      _reconnectCount.delete(agentId)
    }, 5000)
  }

  // ==================== Cleanup ====================

  function cleanup() {
    for (const ws of _wsMap.values()) {
      ws.close()
    }
    _wsMap.clear()
    _reconnectCount.clear()
    tasks.clear()
  }

  return {
    tasks,
    hasActiveCreation,
    startCreation,
    cleanup,
  }
})

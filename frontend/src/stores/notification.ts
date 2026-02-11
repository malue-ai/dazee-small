/**
 * 全局通知中心 Store
 *
 * 通用通知系统，支持多种通知类型：
 * - progress: 进度类（Agent 创建、文件处理等）
 * - success:  成功提示
 * - error:    错误提示
 * - message:  聊天消息提醒（不在当前会话时收到新消息）
 * - info:     普通信息
 * - reminder: 定时任务提醒（不自动消失）
 *
 * 任何模块都可以通过 push/update/dismiss 管理通知，
 * NotificationCenter.vue 统一渲染。
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

// ==================== 类型 ====================

export type NotificationType = 'progress' | 'success' | 'error' | 'message' | 'info' | 'reminder'

export interface NotificationAction {
  /** 按钮文字 */
  label: string
  /** 点击后跳转的路由 */
  route?: RouteLocationRaw
  /** 点击后执行的回调（与 route 二选一，都有时先回调再跳转） */
  handler?: () => void
}

export interface NotificationProgress {
  step: number
  total: number
}

export interface NotificationItem {
  /** 唯一标识（调用方传入或自动生成） */
  id: string
  /** 通知类型 */
  type: NotificationType
  /** 标题（加粗显示） */
  title: string
  /** 副标题/描述 */
  message?: string
  /** 进度信息（type=progress 时使用） */
  progress?: NotificationProgress
  /** 操作按钮 */
  action?: NotificationAction
  /** 可展开的完整内容（如 AI 回复文本） */
  fullContent?: string
  /** 是否已展开完整内容 */
  expanded?: boolean
  /** 自动消失延迟（ms），0 或 undefined = 不自动消失 */
  autoDismissMs?: number
  /** 是否可见 */
  visible: boolean
  /** 创建时间戳 */
  createdAt: number
}

/** push 时的输入，id/visible/createdAt 自动填充 */
export type NotificationInput = Omit<NotificationItem, 'id' | 'visible' | 'createdAt'> & {
  id?: string
}

/** update 时的部分更新 */
export type NotificationUpdate = Partial<Omit<NotificationItem, 'id' | 'createdAt'>>

// ==================== 常量 ====================

/** 默认自动消失延迟（用于 success/error/info） */
const DEFAULT_AUTO_DISMISS_MS: Record<NotificationType, number> = {
  progress: 0,       // progress 不自动消失，由调用方控制
  success: 10000,
  error: 15000,
  message: 30000,    // 聊天消息提醒
  info: 10000,
  reminder: 0,       // 定时任务提醒，不自动消失
}

/** 最大同时显示通知数 */
const MAX_VISIBLE = 5

// ==================== Store ====================

let _counter = 0

export const useNotificationStore = defineStore('notification', () => {
  // ==================== 状态 ====================

  const items = ref<NotificationItem[]>([])

  /** 自动消失 timer 映射 */
  const _timers = new Map<string, ReturnType<typeof setTimeout>>()

  // ==================== 计算属性 ====================

  /** 当前可见的通知列表（最新在前，限制数量） */
  const visibleItems = computed(() =>
    items.value.filter(n => n.visible).slice(0, MAX_VISIBLE)
  )

  /** 是否有可见通知 */
  const hasVisible = computed(() => visibleItems.value.length > 0)

  // ==================== 核心方法 ====================

  /**
   * 推送新通知
   *
   * @returns 通知 ID（用于后续 update/dismiss）
   */
  function push(input: NotificationInput): string {
    const id = input.id ?? `notif_${++_counter}_${Date.now()}`

    // 如果同 ID 已存在，先移除
    const existingIdx = items.value.findIndex(n => n.id === id)
    if (existingIdx >= 0) {
      _clearTimer(id)
      items.value.splice(existingIdx, 1)
    }

    const item: NotificationItem = {
      ...input,
      id,
      visible: true,
      createdAt: Date.now(),
    }

    // 插入到头部（最新的在前）
    items.value.unshift(item)

    // 设置自动消失
    const dismissMs = input.autoDismissMs ?? DEFAULT_AUTO_DISMISS_MS[input.type]
    if (dismissMs > 0) {
      _scheduleAutoDismiss(id, dismissMs)
    }

    return id
  }

  /**
   * 更新已有通知（部分字段）
   *
   * 常见场景：progress 类型的 step 更新、status 从 progress 变为 success/error
   */
  function update(id: string, partial: NotificationUpdate): void {
    const item = items.value.find(n => n.id === id)
    if (!item) return

    Object.assign(item, partial)

    // 如果 type 变了，重新计算自动消失
    if (partial.type && partial.type !== 'progress') {
      const dismissMs = partial.autoDismissMs ?? DEFAULT_AUTO_DISMISS_MS[partial.type]
      if (dismissMs > 0) {
        _scheduleAutoDismiss(id, dismissMs)
      }
    }
  }

  /**
   * 关闭/隐藏一条通知
   */
  function dismiss(id: string): void {
    _clearTimer(id)
    const item = items.value.find(n => n.id === id)
    if (item) {
      item.visible = false
      // 延迟从数组中移除（给离场动画留时间）
      setTimeout(() => {
        const idx = items.value.findIndex(n => n.id === id)
        if (idx >= 0) items.value.splice(idx, 1)
      }, 400)
    }
  }

  /**
   * 清除所有通知
   */
  function clear(): void {
    for (const [id] of _timers) {
      _clearTimer(id)
    }
    items.value = []
  }

  /**
   * 切换展开/收起完整内容
   */
  function toggleExpand(id: string): void {
    const item = items.value.find(n => n.id === id)
    if (item && item.fullContent) {
      item.expanded = !item.expanded
      // 展开时暂停自动消失
      if (item.expanded) {
        _clearTimer(id)
      }
    }
  }

  // ==================== 便捷方法 ====================

  /** 推送成功通知 */
  function success(title: string, message?: string, action?: NotificationAction): string {
    return push({ type: 'success', title, message, action })
  }

  /** 推送错误通知 */
  function error(title: string, message?: string): string {
    return push({ type: 'error', title, message })
  }

  /** 推送信息通知 */
  function info(title: string, message?: string, action?: NotificationAction): string {
    return push({ type: 'info', title, message, action })
  }

  /**
   * 推送聊天消息通知
   *
   * @param agentName - Agent 名称（标题）
   * @param preview   - 消息预览文字
   * @param route     - 点击后跳转的路由
   */
  function chatMessage(agentName: string, preview: string, route: RouteLocationRaw): string {
    return push({
      type: 'message',
      title: agentName,
      message: preview.length > 80 ? preview.slice(0, 80) + '...' : preview,
      action: { label: '查看', route },
    })
  }

  /**
   * 推送定时提醒通知（不自动消失）
   *
   * @param title  - 提醒标题
   * @param content - 提醒内容
   * @param route  - 点击后跳转的路由
   */
  function reminder(title: string, content: string, route: RouteLocationRaw): string {
    return push({
      type: 'reminder',
      title,
      message: content,
      action: { label: '查看', route },
    })
  }

  // ==================== 内部方法 ====================

  function _scheduleAutoDismiss(id: string, ms: number): void {
    _clearTimer(id)
    _timers.set(id, setTimeout(() => dismiss(id), ms))
  }

  function _clearTimer(id: string): void {
    const timer = _timers.get(id)
    if (timer) {
      clearTimeout(timer)
      _timers.delete(id)
    }
  }

  return {
    // 状态
    items,
    visibleItems,
    hasVisible,

    // 核心方法
    push,
    update,
    dismiss,
    clear,
    toggleExpand,

    // 便捷方法
    success,
    error,
    info,
    chatMessage,
    reminder,
  }
})

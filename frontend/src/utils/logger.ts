/**
 * 前端调试日志模块
 * 
 * 提供结构化日志记录，支持：
 * - 内存日志存储（供 DebugPanel 展示）
 * - 按模块分类（API / SSE / WS / APP）
 * - 按级别过滤（DEBUG / INFO / WARN / ERROR）
 * - 自动截断旧日志（防止内存泄漏）
 */

import { reactive } from 'vue'

// ==================== 类型定义 ====================

export type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR'

export type LogModule = 'APP' | 'API' | 'SSE' | 'WS' | 'STORE' | 'ROUTER' | 'TAURI'

export interface LogEntry {
  id: number
  timestamp: number
  level: LogLevel
  module: LogModule
  message: string
  /** 附加数据（请求体、响应体等） */
  data?: unknown
}

// ==================== 配置 ====================

const MAX_LOGS = 500
const IS_DEV = import.meta.env.DEV

// ==================== 响应式日志存储 ====================

let _nextId = 1

export const logStore = reactive({
  entries: [] as LogEntry[],
  /** 面板是否可见 */
  visible: false,
  /** 未读计数（面板隐藏时产生的新日志） */
  unreadCount: 0,
  /** 是否有错误（用于图标高亮） */
  hasError: false,
})

// ==================== 核心函数 ====================

function addLog(level: LogLevel, module: LogModule, message: string, data?: unknown): void {
  const entry: LogEntry = {
    id: _nextId++,
    timestamp: Date.now(),
    level,
    module,
    message,
    data,
  }

  logStore.entries.push(entry)

  // 截断旧日志
  if (logStore.entries.length > MAX_LOGS) {
    logStore.entries.splice(0, logStore.entries.length - MAX_LOGS)
  }

  // 更新未读计数
  if (!logStore.visible) {
    logStore.unreadCount++
  }

  // 标记错误
  if (level === 'ERROR') {
    logStore.hasError = true
  }

  // 同时输出到浏览器控制台（开发模式）
  if (IS_DEV) {
    const prefix = `[${module}]`
    const consoleMethod = level === 'ERROR' ? 'error'
      : level === 'WARN' ? 'warn'
      : level === 'DEBUG' ? 'debug'
      : 'log'
    if (data !== undefined) {
      console[consoleMethod](prefix, message, data)
    } else {
      console[consoleMethod](prefix, message)
    }
  }
}

// ==================== 模块级快捷方法 ====================

function createModuleLogger(module: LogModule) {
  return {
    debug: (msg: string, data?: unknown) => addLog('DEBUG', module, msg, data),
    info: (msg: string, data?: unknown) => addLog('INFO', module, msg, data),
    warn: (msg: string, data?: unknown) => addLog('WARN', module, msg, data),
    error: (msg: string, data?: unknown) => addLog('ERROR', module, msg, data),
  }
}

/** 应用级日志 */
export const appLog = createModuleLogger('APP')
/** API 请求日志 */
export const apiLog = createModuleLogger('API')
/** SSE 流日志 */
export const sseLog = createModuleLogger('SSE')
/** WebSocket 日志 */
export const wsLog = createModuleLogger('WS')
/** Store 日志 */
export const storeLog = createModuleLogger('STORE')
/** Router 日志 */
export const routerLog = createModuleLogger('ROUTER')
/** Tauri 日志 */
export const tauriLog = createModuleLogger('TAURI')

// ==================== 面板控制 ====================

export function toggleDebugPanel(): void {
  logStore.visible = !logStore.visible
  if (logStore.visible) {
    logStore.unreadCount = 0
    logStore.hasError = false
  }
}

export function clearLogs(): void {
  logStore.entries.splice(0, logStore.entries.length)
  logStore.unreadCount = 0
  logStore.hasError = false
}

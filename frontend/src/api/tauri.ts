/**
 * Tauri API 封装
 * 
 * 提供与 Tauri Rust 后端通信的接口
 * 用于执行本地系统命令、发送通知等
 */

import { invoke } from '@tauri-apps/api/core'

// ============================================================================
// 类型定义
// ============================================================================

export interface ShellResult {
  success: boolean
  stdout: string
  stderr: string
  exit_code: number
  elapsed_ms: number
  timed_out: boolean
}

export interface NodeInfo {
  node_id: string
  display_name: string
  platform: string
  version: string
  capabilities: string[]
}

export interface ConnectionStatus {
  connected: boolean
  server_url: string | null
  node_id: string | null
  latency_ms: number | null
}

// ============================================================================
// 环境检测
// ============================================================================

/**
 * 检测是否在 Tauri 环境中运行
 * 
 * 三重检测策略：
 * 1. tauri: 自定义协议（生产打包最可靠的检测方式）
 * 2. __TAURI_INTERNALS__（Tauri v2 IPC 桥接）
 * 3. __TAURI__（需要 withGlobalTauri: true）
 */
export function isTauriEnv(): boolean {
  if (typeof window === 'undefined') return false

  // 方式 1: 生产打包使用 tauri:// 自定义协议（最可靠）
  if (window.location.protocol === 'tauri:') return true

  // 方式 2: Tauri v2 内部 IPC 桥接
  if ('__TAURI_INTERNALS__' in window) return true

  // 方式 3: withGlobalTauri 暴露的全局对象
  if ('__TAURI__' in window) return true

  return false
}

// ============================================================================
// 系统命令执行
// ============================================================================

/**
 * 执行 Shell 命令
 * 
 * @param command 命令数组，如 ['ls', '-la']
 * @param options 可选参数
 * @returns 执行结果
 */
export async function runCommand(
  command: string[],
  options?: {
    cwd?: string
    env?: Record<string, string>
    timeout_ms?: number
  }
): Promise<ShellResult> {
  if (!isTauriEnv()) {
    throw new Error('Not running in Tauri environment')
  }
  
  return await invoke<ShellResult>('run_command', {
    command,
    cwd: options?.cwd ?? null,
    env: options?.env ?? null,
    timeout_ms: options?.timeout_ms ?? null,
  })
}

/**
 * 检查可执行文件是否存在
 * 
 * @param executable 可执行文件名
 * @returns 可执行文件路径，不存在则返回 null
 */
export async function whichCommand(executable: string): Promise<string | null> {
  if (!isTauriEnv()) {
    throw new Error('Not running in Tauri environment')
  }
  
  return await invoke<string | null>('which_command', { executable })
}

// ============================================================================
// 系统通知
// ============================================================================

/**
 * 发送系统通知
 * 
 * @param title 通知标题
 * @param body 通知内容
 * @param subtitle 副标题（可选，仅 macOS）
 */
export async function sendNotification(
  title: string,
  body: string,
  subtitle?: string
): Promise<void> {
  if (!isTauriEnv()) {
    // 在浏览器中使用 Web Notification API
    if ('Notification' in window) {
      if (Notification.permission === 'granted') {
        new Notification(title, { body })
      } else if (Notification.permission !== 'denied') {
        const permission = await Notification.requestPermission()
        if (permission === 'granted') {
          new Notification(title, { body })
        }
      }
    }
    return
  }
  
  await invoke('send_notification', {
    title,
    body,
    subtitle: subtitle ?? null,
  })
}

// ============================================================================
// 节点信息
// ============================================================================

/**
 * 获取当前节点信息
 */
export async function getNodeInfo(): Promise<NodeInfo> {
  if (!isTauriEnv()) {
    // 在浏览器中返回模拟数据
    return {
      node_id: 'browser-node',
      display_name: 'Browser',
      platform: 'web',
      version: '1.0.0',
      capabilities: [],
    }
  }
  
  return await invoke<NodeInfo>('get_node_info')
}

/**
 * 获取连接状态
 */
export async function getConnectionStatus(): Promise<ConnectionStatus> {
  if (!isTauriEnv()) {
    return {
      connected: false,
      server_url: null,
      node_id: null,
      latency_ms: null,
    }
  }
  
  return await invoke<ConnectionStatus>('get_connection_status')
}

/**
 * 设置连接状态
 */
export async function setConnectionStatus(
  connected: boolean,
  serverUrl?: string,
  nodeId?: string,
  latencyMs?: number
): Promise<void> {
  if (!isTauriEnv()) {
    return
  }
  
  await invoke('set_connection_status', {
    connected,
    server_url: serverUrl ?? null,
    node_id: nodeId ?? null,
    latency_ms: latencyMs ?? null,
  })
}

// ============================================================================
// 系统设置
// ============================================================================

/**
 * 打开系统偏好设置（用于请求权限）
 * 
 * @param pane 设置面板：camera, screen, location, accessibility
 */
export async function openSystemPreferences(
  pane: 'camera' | 'screen' | 'location' | 'accessibility'
): Promise<void> {
  if (!isTauriEnv()) {
    throw new Error('Not running in Tauri environment')
  }
  
  await invoke('open_system_preferences', { pane })
}

// ============================================================================
// 导出
// ============================================================================

export default {
  isTauriEnv,
  runCommand,
  whichCommand,
  sendNotification,
  getNodeInfo,
  getConnectionStatus,
  setConnectionStatus,
  openSystemPreferences,
}

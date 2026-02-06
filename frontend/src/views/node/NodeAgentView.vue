<script setup lang="ts">
/**
 * Node Agent 客户端页面
 * 
 * 显示节点状态、连接服务器、执行日志等
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { 
  Wifi, WifiOff, Terminal, Bell, Camera, Monitor, MapPin, 
  Settings, Power, RefreshCw, CheckCircle, XCircle, Clock,
  Loader2
} from 'lucide-vue-next'
import { 
  isTauriEnv, 
  getNodeInfo, 
  runCommand, 
  sendNotification,
  type NodeInfo,
  type ShellResult
} from '@/api/tauri'

// ============================================================================
// 状态
// ============================================================================

const isLoading = ref(true)
const isTauri = ref(false)
const nodeInfo = ref<NodeInfo | null>(null)

// 连接状态
const isConnected = ref(false)
const serverUrl = ref('wss://api.zenflux.ai/ws/node')
const connectionError = ref<string | null>(null)
const latencyMs = ref<number | null>(null)
const onlineTime = ref(0)

// 执行日志
interface ExecutionLog {
  id: string
  timestamp: Date
  command: string
  params: string
  success: boolean
  elapsed_ms: number
}
const executionLogs = ref<ExecutionLog[]>([])

// WebSocket
let ws: WebSocket | null = null
let heartbeatInterval: number | null = null
let onlineTimeInterval: number | null = null

// ============================================================================
// 能力配置
// ============================================================================

interface Capability {
  id: string
  name: string
  icon: any
  enabled: boolean
  needsAuth: boolean
}

const capabilities = ref<Capability[]>([
  { id: 'system.run', name: 'Shell 命令执行', icon: Terminal, enabled: true, needsAuth: false },
  { id: 'system.notify', name: '系统通知', icon: Bell, enabled: true, needsAuth: false },
  { id: 'camera.snap', name: '摄像头访问', icon: Camera, enabled: false, needsAuth: true },
  { id: 'screen.record', name: '屏幕录制', icon: Monitor, enabled: false, needsAuth: true },
  { id: 'location.get', name: '位置服务', icon: MapPin, enabled: false, needsAuth: true },
])

// ============================================================================
// 初始化
// ============================================================================

onMounted(async () => {
  isTauri.value = isTauriEnv()
  
  try {
    nodeInfo.value = await getNodeInfo()
    
    // 更新能力状态
    if (nodeInfo.value) {
      capabilities.value.forEach(cap => {
        cap.enabled = nodeInfo.value!.capabilities.includes(cap.id)
      })
    }
  } catch (e) {
    console.error('Failed to get node info:', e)
  }
  
  isLoading.value = false
})

onUnmounted(() => {
  disconnect()
})

// ============================================================================
// WebSocket 连接
// ============================================================================

async function connect() {
  if (isConnected.value || !nodeInfo.value) return
  
  connectionError.value = null
  
  try {
    // 构建 WebSocket URL
    const url = new URL(serverUrl.value)
    url.searchParams.set('node_id', nodeInfo.value.node_id)
    url.searchParams.set('platform', nodeInfo.value.platform)
    
    ws = new WebSocket(url.toString())
    
    ws.onopen = () => {
      isConnected.value = true
      connectionError.value = null
      onlineTime.value = 0
      
      // 发送注册消息
      ws?.send(JSON.stringify({
        type: 'node.register',
        info: nodeInfo.value,
      }))
      
      // 启动心跳
      startHeartbeat()
      
      // 启动在线计时
      onlineTimeInterval = window.setInterval(() => {
        onlineTime.value++
      }, 1000)
      
      // 发送通知
      sendNotification('ZenFlux Agent', '已连接到服务器')
    }
    
    ws.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data)
        await handleMessage(data)
      } catch (e) {
        console.error('Failed to parse message:', e)
      }
    }
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      connectionError.value = '连接错误'
    }
    
    ws.onclose = () => {
      isConnected.value = false
      stopHeartbeat()
      if (onlineTimeInterval) {
        clearInterval(onlineTimeInterval)
        onlineTimeInterval = null
      }
    }
  } catch (e) {
    connectionError.value = `连接失败: ${e}`
  }
}

function disconnect() {
  if (ws) {
    ws.close()
    ws = null
  }
  isConnected.value = false
  stopHeartbeat()
  if (onlineTimeInterval) {
    clearInterval(onlineTimeInterval)
    onlineTimeInterval = null
  }
}

function startHeartbeat() {
  heartbeatInterval = window.setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      const start = Date.now()
      ws.send(JSON.stringify({ type: 'node.ping', ts: start }))
    }
  }, 30000)
}

function stopHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval)
    heartbeatInterval = null
  }
}

// ============================================================================
// 消息处理
// ============================================================================

async function handleMessage(data: any) {
  switch (data.type) {
    case 'node.pong':
      latencyMs.value = Date.now() - data.ts
      break
      
    case 'node.invoke.request':
      await handleInvokeRequest(data)
      break
      
    case 'node.registered':
      console.log('Node registered:', data.node_id)
      break
  }
}

async function handleInvokeRequest(request: any) {
  const startTime = Date.now()
  let result: ShellResult | null = null
  let error: string | null = null
  
  try {
    switch (request.command) {
      case 'system.run':
        result = await runCommand(
          request.params.command,
          {
            cwd: request.params.cwd,
            env: request.params.env,
            timeout_ms: request.params.timeout_ms,
          }
        )
        break
        
      case 'system.notify':
        await sendNotification(
          request.params.title,
          request.params.message,
          request.params.subtitle
        )
        result = { success: true, stdout: '', stderr: '', exit_code: 0, elapsed_ms: 0, timed_out: false }
        break
        
      default:
        error = `Unknown command: ${request.command}`
    }
  } catch (e) {
    error = `Execution failed: ${e}`
  }
  
  const elapsed = Date.now() - startTime
  
  // 添加执行日志
  executionLogs.value.unshift({
    id: request.id,
    timestamp: new Date(),
    command: request.command,
    params: JSON.stringify(request.params).slice(0, 50),
    success: result?.success ?? false,
    elapsed_ms: elapsed,
  })
  
  // 保持日志数量
  if (executionLogs.value.length > 50) {
    executionLogs.value = executionLogs.value.slice(0, 50)
  }
  
  // 发送响应
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: 'node.invoke.result',
      id: request.id,
      ok: result?.success ?? false,
      payload: result ? {
        stdout: result.stdout,
        stderr: result.stderr,
        exit_code: result.exit_code,
        timed_out: result.timed_out,
      } : null,
      error,
      elapsed_ms: elapsed,
    }))
  }
}

// ============================================================================
// 辅助函数
// ============================================================================

function formatOnlineTime(seconds: number): string {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  
  if (hours > 0) {
    return `${hours}小时 ${minutes}分钟`
  } else if (minutes > 0) {
    return `${minutes}分钟 ${secs}秒`
  } else {
    return `${secs}秒`
  }
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

// 测试命令
async function testCommand() {
  if (!isTauri.value) {
    alert('需要在 Tauri 环境中运行')
    return
  }
  
  try {
    const result = await runCommand(['echo', 'Hello from ZenFlux Agent!'])
    await sendNotification('测试成功', result.stdout || '命令执行成功')
  } catch (e) {
    alert(`测试失败: ${e}`)
  }
}
</script>

<template>
  <div class="min-h-screen bg-muted">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="flex items-center justify-center min-h-screen">
      <Loader2 class="w-8 h-8 animate-spin text-primary" />
    </div>
    
    <!-- 主内容 -->
    <div v-else class="container mx-auto px-4 py-8 max-w-4xl">
      <!-- 标题 -->
      <div class="text-center mb-8">
        <h1 class="text-3xl font-bold text-foreground mb-2">
          ZenFlux Agent
        </h1>
        <p class="text-muted-foreground">
          {{ isTauri ? '本地客户端' : '浏览器模式（功能受限）' }}
        </p>
      </div>
      
      <!-- 连接状态卡片 -->
      <div class="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-6 mb-6">
        <div class="flex items-center justify-between mb-6">
          <div class="flex items-center gap-3">
            <div :class="[
              'w-12 h-12 rounded-full flex items-center justify-center',
              isConnected ? 'bg-success/10' : 'bg-muted'
            ]">
              <component 
                :is="isConnected ? Wifi : WifiOff" 
                :class="[
                  'w-6 h-6',
                  isConnected ? 'text-success' : 'text-muted-foreground/50'
                ]" 
              />
            </div>
            <div>
              <h2 class="text-xl font-semibold text-foreground">
                {{ isConnected ? '已连接到服务器' : '未连接' }}
              </h2>
              <p v-if="isConnected" class="text-sm text-muted-foreground">
                延迟: {{ latencyMs ?? '-' }}ms • 在线: {{ formatOnlineTime(onlineTime) }}
              </p>
              <p v-else-if="connectionError" class="text-sm text-red-500">
                {{ connectionError }}
              </p>
            </div>
          </div>
          
          <button
            v-if="!isConnected"
            @click="connect"
            class="px-6 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg font-medium transition-colors"
          >
            连接服务器
          </button>
          <button
            v-else
            @click="disconnect"
            class="px-6 py-2 bg-muted hover:bg-muted/80 text-foreground rounded-lg font-medium transition-colors"
          >
            断开连接
          </button>
        </div>
        
        <!-- 服务器地址 -->
        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            服务器地址
          </label>
          <input
            v-model="serverUrl"
            type="text"
            :disabled="isConnected"
            class="w-full px-4 py-2 border border-border rounded-lg bg-white text-foreground disabled:opacity-50"
            placeholder="wss://api.zenflux.ai/ws/node"
          />
        </div>
      </div>
      
      <!-- 设备信息 -->
      <div class="bg-white rounded-2xl shadow-lg p-6 mb-6">
        <h3 class="text-lg font-semibold text-foreground mb-4">
          设备信息
        </h3>
        <div class="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span class="text-muted-foreground">设备名称</span>
            <p class="text-foreground font-medium">
              {{ nodeInfo?.display_name ?? '-' }}
            </p>
          </div>
          <div>
            <span class="text-muted-foreground">设备 ID</span>
            <p class="text-foreground font-mono text-xs">
              {{ nodeInfo?.node_id ?? '-' }}
            </p>
          </div>
          <div>
            <span class="text-muted-foreground">平台</span>
            <p class="text-foreground font-medium">
              {{ nodeInfo?.platform ?? '-' }}
            </p>
          </div>
          <div>
            <span class="text-muted-foreground">版本</span>
            <p class="text-foreground font-medium">
              {{ nodeInfo?.version ?? '-' }}
            </p>
          </div>
        </div>
      </div>
      
      <!-- 已授权能力 -->
      <div class="bg-white rounded-2xl shadow-lg p-6 mb-6">
        <h3 class="text-lg font-semibold text-foreground mb-4">
          已授权能力
        </h3>
        <div class="space-y-3">
          <div
            v-for="cap in capabilities"
            :key="cap.id"
            class="flex items-center justify-between py-2"
          >
            <div class="flex items-center gap-3">
              <component :is="cap.icon" class="w-5 h-5 text-muted-foreground/50" />
              <span class="text-foreground">{{ cap.name }}</span>
            </div>
            <div class="flex items-center gap-2">
              <span 
                v-if="cap.needsAuth && !cap.enabled"
                class="text-xs text-primary"
              >
                需要授权
              </span>
              <component
                :is="cap.enabled ? CheckCircle : XCircle"
                :class="[
                  'w-5 h-5',
                  cap.enabled ? 'text-success' : 'text-muted-foreground/30'
                ]"
              />
            </div>
          </div>
        </div>
        
        <!-- 测试按钮 -->
        <button
          v-if="isTauri"
          @click="testCommand"
          class="mt-4 w-full py-2 bg-muted hover:bg-muted/80 text-foreground rounded-lg font-medium transition-colors"
        >
          测试系统命令
        </button>
      </div>
      
      <!-- 执行日志 -->
      <div class="bg-white rounded-2xl shadow-lg p-6">
        <h3 class="text-lg font-semibold text-foreground mb-4">
          最近执行
        </h3>
        
        <div v-if="executionLogs.length === 0" class="text-center py-8 text-muted-foreground/50">
          暂无执行记录
        </div>
        
        <div v-else class="space-y-2 max-h-64 overflow-y-auto">
          <div
            v-for="log in executionLogs"
            :key="log.id"
            class="flex items-center justify-between py-2 px-3 bg-muted rounded-lg"
          >
            <div class="flex items-center gap-3">
              <Clock class="w-4 h-4 text-muted-foreground/50" />
              <span class="text-sm text-muted-foreground">
                {{ formatTime(log.timestamp) }}
              </span>
              <span class="text-sm font-mono text-foreground">
                {{ log.command }}
              </span>
              <span class="text-xs text-muted-foreground/50 truncate max-w-32">
                {{ log.params }}
              </span>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-xs text-muted-foreground/50">
                {{ log.elapsed_ms }}ms
              </span>
              <component
                :is="log.success ? CheckCircle : XCircle"
                :class="[
                  'w-4 h-4',
                  log.success ? 'text-success' : 'text-destructive'
                ]"
              />
            </div>
          </div>
        </div>
      </div>
      
      <!-- 底部操作 -->
      <div class="flex justify-center gap-4 mt-8">
        <button
          class="flex items-center gap-2 px-4 py-2 text-muted-foreground hover:text-foreground transition-colors"
        >
          <Settings class="w-4 h-4" />
          设置
        </button>
        <button
          class="flex items-center gap-2 px-4 py-2 text-muted-foreground hover:text-foreground transition-colors"
        >
          <RefreshCw class="w-4 h-4" />
          刷新状态
        </button>
      </div>
    </div>
  </div>
</template>

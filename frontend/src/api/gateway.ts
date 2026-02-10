/**
 * Gateway API
 *
 * Multi-channel gateway configuration and status.
 */

import api from '.'

// ==================== Types ====================

export interface GatewayChannelField {
  key: string
  label: string
  placeholder: string
  secret?: boolean
  type?: 'list' | 'text'
}

export interface GatewaySetupStep {
  title: string
  detail: string
  link?: string
}

export interface GatewayChannel {
  id: string
  enabled: boolean
  display_name: string
  description: string
  fields: GatewayChannelField[]
  setup_steps: GatewaySetupStep[]
  params: Record<string, any>
  status: 'connected' | 'connecting' | 'disconnected' | 'error'
}

export interface GatewayBinding {
  channel: string
  agent_id: string
  conversation_id?: string
}

export interface GatewayConfig {
  enabled: boolean
  channels: GatewayChannel[]
  bindings: GatewayBinding[]
}

export interface GatewayChannelUpdate {
  enabled?: boolean
  params?: Record<string, any>
}

export interface GatewayConfigUpdate {
  enabled?: boolean
  channels?: Record<string, GatewayChannelUpdate>
  bindings?: GatewayBinding[]
}

export interface GatewayStatus {
  enabled: boolean
  channels: Array<{
    id: string
    display_name: string
    status: string
  }>
}

// ==================== API Functions ====================

/**
 * Get gateway configuration (secrets masked)
 */
export async function getGatewayConfig(): Promise<GatewayConfig> {
  const { data } = await api.get('/v1/gateway/config')
  return data.data
}

/**
 * Update gateway configuration (partial merge)
 */
export async function updateGatewayConfig(
  update: GatewayConfigUpdate
): Promise<{ message: string; needs_restart: boolean }> {
  const { data } = await api.put('/v1/gateway/config', update)
  return data.data
}

/**
 * Get gateway live status
 */
export async function getGatewayStatus(): Promise<GatewayStatus> {
  const { data } = await api.get('/v1/gateway/status')
  return data
}

// ==================== Connection Test ====================

export interface ChannelTestResult {
  valid: boolean
  message: string
  bot_info?: {
    name: string
    username: string
    id: number
  }
}

/**
 * Test channel credentials without starting the full adapter
 */
export async function testChannelConnection(
  channel: string,
  params: Record<string, any>,
): Promise<ChannelTestResult> {
  const { data } = await api.post('/v1/gateway/test-connection', { channel, params })
  return data.data
}

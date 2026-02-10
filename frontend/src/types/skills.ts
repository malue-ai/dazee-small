/**
 * Skills 相关类型定义
 */

/**
 * Skill 优先级
 */
export type SkillPriority = 'high' | 'medium' | 'low'

/**
 * Skill 状态
 */
export type SkillStatus = 'registered' | 'pending'

/**
 * Skill 运行时状态
 */
export type SkillRuntimeStatus = 'ready' | 'need_setup' | 'need_auth' | 'unavailable'

/**
 * Skill 所需的环境变量
 */
export interface EnvRequirement {
  /** 环境变量名称，如 GEMINI_API_KEY */
  name: string
  /** 显示标签，如 Gemini API Key */
  label: string
  /** 是否已配置 */
  is_set: boolean
}

/**
 * Skill 基础信息（旧版兼容）
 */
export interface Skill {
  /** 唯一标识（目录名） */
  name: string
  /** 描述 */
  description: string
  /** 优先级 */
  priority: SkillPriority
  /** 适用场景 */
  preferred_for: string[]
  /** 脚本文件列表 */
  scripts: string[]
  /** 资源文件列表 */
  resources: string[]
  /** SKILL.md 内容 */
  content: string
  /** 创建时间 */
  created_at?: string
  /** 更新时间 */
  updated_at?: string
}

/**
 * Skill 摘要（新版 API 格式）
 */
export interface SkillSummary {
  /** Skill 名称 */
  name: string
  /** 描述 */
  description: string
  /** 所属实例 ID（global 表示全局库） */
  agent_id: string
  /** 运行时状态 */
  status: SkillRuntimeStatus
  /** 状态说明 */
  status_message: string
  /** 是否已注册到 Claude API */
  is_registered: boolean
  /** Claude API 的 skill_id */
  skill_id: string | null
  /** 创建时间 */
  created_at: string
}

/**
 * 安装 Skill 请求
 */
export interface SkillInstallRequest {
  skill_name: string
  agent_id: string
  auto_register?: boolean
}

/**
 * 卸载 Skill 请求
 */
export interface SkillUninstallRequest {
  skill_name: string
  agent_id: string
}

/**
 * 更新 Skill 内容请求
 */
export interface SkillUpdateContentRequest {
  skill_name: string
  agent_id: string
  content: string
}

/**
 * 配置 Skill API Key 请求
 */
export interface SkillConfigureRequest {
  skill_name: string
  agent_id: string
  env_vars: Record<string, string>
}

/**
 * Skill 列表响应
 */
export interface SkillListResponse {
  skills: Skill[]
  total: number
}

/**
 * Skill 创建请求
 */
export interface SkillCreateRequest {
  name: string
  description: string
  priority: SkillPriority
  preferred_for: string[]
  content: string
  scripts?: Array<{
    filename: string
    content: string
  }>
  resources?: Array<{
    filename: string
    content: string
  }>
}

/**
 * Skill 更新请求
 */
export interface SkillUpdateRequest {
  description?: string
  priority?: SkillPriority
  preferred_for?: string[]
  content?: string
}

/**
 * Skill 脚本文件
 */
export interface SkillScript {
  filename: string
  content: string
  language: string
}

/**
 * Skill 资源文件
 */
export interface SkillResource {
  filename: string
  content: string
  type: string
}

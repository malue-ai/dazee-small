/**
 * Skills API
 */

import api from './index'
import type {
  ApiResponse,
  Skill,
  SkillListResponse,
  SkillCreateRequest,
  SkillUpdateRequest,
  SkillSummary,
  SkillInstallRequest,
  SkillUninstallRequest,
  SkillToggleRequest,
  SkillUpdateContentRequest
} from '@/types'

// ==================== 新版 API（全局/实例分离）====================

/**
 * 获取全局 Skills 列表
 */
export async function getGlobalSkills(): Promise<SkillSummary[]> {
  try {
    const response = await api.get<{ total: number; skills: SkillSummary[] }>('/v1/skills/global')
    return response.data.skills || []
  } catch (error) {
    console.warn('全局 Skills API 不可用:', error)
    return []
  }
}

/**
 * 获取实例已安装的 Skills
 */
export async function getInstanceSkills(agentId: string): Promise<SkillSummary[]> {
  try {
    const response = await api.get<{ total: number; skills: SkillSummary[] }>(`/v1/skills/instance/${agentId}`)
    return response.data.skills || []
  } catch (error) {
    console.warn(`实例 ${agentId} Skills API 不可用:`, error)
    return []
  }
}

/**
 * 安装 Skill 到实例
 */
export async function installSkill(data: SkillInstallRequest): Promise<{ success: boolean; skill_id?: string; message: string }> {
  const response = await api.post<{ success: boolean; skill_id?: string; message: string }>('/v1/skills/install', data)
  return response.data
}

/**
 * 从实例卸载 Skill
 */
export async function uninstallSkill(data: SkillUninstallRequest): Promise<{ success: boolean; message: string }> {
  const response = await api.post<{ success: boolean; message: string }>('/v1/skills/uninstall', data)
  return response.data
}

/**
 * 启用/禁用 Skill
 */
export async function toggleSkill(data: SkillToggleRequest): Promise<{ success: boolean; enabled: boolean; message: string }> {
  const response = await api.post<{ success: boolean; enabled: boolean; message: string }>('/v1/skills/toggle', data)
  return response.data
}

/**
 * 更新 Skill 内容
 */
export async function updateSkillContent(data: SkillUpdateContentRequest): Promise<{ success: boolean; message: string }> {
  const response = await api.post<{ success: boolean; message: string }>('/v1/skills/update_content', data)
  return response.data
}

/**
 * 文件内容响应
 */
export interface SkillFileContentResponse {
  skill_name: string
  file_type: string
  file_name: string
  content: string | null
  is_binary: boolean
  size: number
  language?: string
  message?: string
}

/**
 * 获取 Skill 文件内容（脚本或资源）
 */
export async function getSkillFileContent(
  skillName: string,
  fileType: 'scripts' | 'resources',
  fileName: string,
  agentId?: string
): Promise<SkillFileContentResponse> {
  const params = agentId ? { agent_id: agentId } : {}
  const response = await api.get<SkillFileContentResponse>(
    `/v1/skills/file/${skillName}/${fileType}/${fileName}`,
    { params }
  )
  return response.data
}

/**
 * 注册 Skill 到 Claude API
 */
export async function registerSkill(skillName: string, agentId: string): Promise<{ success: boolean; skill_id?: string; message: string }> {
  const response = await api.post<{ success: boolean; skill_id?: string; message: string }>(`/v1/skills/register?skill_name=${skillName}&agent_id=${agentId}`)
  return response.data
}

/**
 * Skill 详情类型
 */
export interface SkillDetailResponse {
  name: string
  description: string
  priority: string
  preferred_for: string[]
  scripts: string[]
  resources: string[]
  content: string
  agent_id: string
  is_enabled: boolean
  is_registered: boolean
  skill_id: string | null
  registered_at: string | null
  created_at: string | null
}

/**
 * 获取 Skill 详情
 */
export async function getSkillDetail(skillName: string, agentId?: string): Promise<SkillDetailResponse | null> {
  try {
    const params = agentId ? `?agent_id=${agentId}` : ''
    const response = await api.get<SkillDetailResponse>(`/v1/skills/detail/${skillName}${params}`)
    return response.data
  } catch (error) {
    console.warn('获取 Skill 详情失败:', error)
    return null
  }
}

/**
 * 上传新 Skill 到全局库
 */
export async function uploadSkill(file: File, skillName: string): Promise<{ success: boolean; skill_name: string; message: string }> {
  const formData = new FormData()
  formData.append('file', file)
  
  const response = await api.post<{ success: boolean; skill_name: string; message: string }>(
    `/v1/skills/upload?skill_name=${encodeURIComponent(skillName)}`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }
  )
  return response.data
}

// ==================== 旧版 API（兼容）====================

/**
 * 获取所有 Skills（旧版）
 */
export async function getSkills(): Promise<Skill[]> {
  try {
    const response = await api.get<ApiResponse<SkillListResponse>>('/v1/skills')
    return response.data.data?.skills || []
  } catch (error) {
    console.warn('Skills API 不可用，使用 mock 数据')
    return getMockSkills()
  }
}

/**
 * 获取单个 Skill 详情
 * @param name - Skill 名称
 */
export async function getSkill(name: string): Promise<Skill | null> {
  try {
    const response = await api.get<ApiResponse<Skill>>(`/v1/skills/${name}`)
    return response.data.data
  } catch (error) {
    console.warn(`Skill ${name} API 不可用，使用 mock 数据`)
    const skills = getMockSkills()
    return skills.find(s => s.name === name) || null
  }
}

/**
 * 创建 Skill
 * @param data - 创建请求数据
 */
export async function createSkill(data: SkillCreateRequest): Promise<Skill> {
  const response = await api.post<ApiResponse<Skill>>('/v1/skills', data)
  return response.data.data
}

/**
 * 更新 Skill
 * @param name - Skill 名称
 * @param data - 更新请求数据
 */
export async function updateSkill(name: string, data: SkillUpdateRequest): Promise<Skill> {
  const response = await api.put<ApiResponse<Skill>>(`/v1/skills/${name}`, data)
  return response.data.data
}

/**
 * 删除 Skill
 * @param name - Skill 名称
 */
export async function deleteSkill(name: string): Promise<void> {
  await api.delete(`/v1/skills/${name}`)
}

// ==================== Mock 数据 ====================

/**
 * 获取 Mock Skills 数据
 */
function getMockSkills(): Skill[] {
  return [
    {
      name: 'planning-task',
      description: '生成结构化任务计划和待办列表，用于复杂的多步骤项目。当用户需要将工作分解为有依赖关系的有序任务时使用。',
      priority: 'medium',
      preferred_for: ['project planning', 'task breakdown', 'work organization', 'multi-step tasks'],
      scripts: ['generate_plan.py', 'generate_todo.py'],
      resources: ['plan_template.json'],
      content: `# Task Planning Skill

Breaks down complex user requests into structured, trackable task plans with dependencies.

## When to Use

Load this skill when:
- User has a multi-step request
- Need to organize work into phases/steps
- User mentions: "plan", "tasks", "steps", "breakdown", "organize"

## Capabilities

1. **Task Decomposition**: Break complex goals into atomic tasks
2. **Dependency Management**: Identify which tasks must complete before others
3. **Progress Tracking**: Generate plan.json and todo.md for monitoring`
    },
    {
      name: 'ppt-generator',
      description: '生成 PowerPoint 演示文稿，支持多种模板和自定义样式。',
      priority: 'high',
      preferred_for: ['presentation', 'slides', 'ppt', 'powerpoint'],
      scripts: ['generate_ppt.py'],
      resources: [],
      content: `# PPT Generator Skill

Generates professional PowerPoint presentations from structured content.

## When to Use

- User needs to create a presentation
- User mentions: "PPT", "slides", "presentation", "演示文稿"

## Output

Creates .pptx files with customizable templates and layouts.`
    },
    {
      name: 'slidespeak-generator',
      description: '使用 SlideSpeak API 生成高质量演示文稿，支持 AI 驱动的内容生成。',
      priority: 'high',
      preferred_for: ['ai slides', 'smart presentation', 'automated ppt'],
      scripts: ['config_builder.py', 'validator.py'],
      resources: ['api_schema.json'],
      content: `# SlideSpeak Generator Skill

Uses SlideSpeak API to generate AI-powered presentations.

## Features

- AI-driven content generation
- Professional templates
- Smart layout optimization
- Multi-language support`
    },
    {
      name: 'ontology-builder',
      description: '构建知识本体和概念图，用于知识管理和可视化。',
      priority: 'low',
      preferred_for: ['knowledge graph', 'ontology', 'concept map', 'visualization'],
      scripts: ['build_ontology.py'],
      resources: [],
      content: `# Ontology Builder Skill

Builds knowledge ontologies and concept maps for knowledge management.

## Use Cases

- Knowledge graph construction
- Concept relationship mapping
- Domain modeling`
    },
    {
      name: 'slidespeak-editor',
      description: '编辑已有的 SlideSpeak 演示文稿，支持形状提取和样式修改。',
      priority: 'medium',
      preferred_for: ['edit slides', 'modify presentation', 'update ppt'],
      scripts: ['extract_shapes.py', 'validate_config.py'],
      resources: ['edit_api_schema.json'],
      content: `# SlideSpeak Editor Skill

Edits existing SlideSpeak presentations with shape extraction and style modifications.

## Capabilities

- Extract shapes from slides
- Modify text and styles
- Update layouts`
    },
    {
      name: 'slidespeak-slide-editor',
      description: '单页幻灯片编辑器，精确控制元素位置和样式。',
      priority: 'medium',
      preferred_for: ['single slide edit', 'precise positioning', 'element control'],
      scripts: ['position_helper.py'],
      resources: ['edit_slide_api_schema.json'],
      content: `# SlideSpeak Slide Editor Skill

Single slide editor with precise element positioning and styling control.

## Features

- Pixel-perfect positioning
- Element layering
- Style inheritance`
    }
  ]
}

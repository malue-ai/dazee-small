/**
 * Skills API
 */

import api from './index'
import type {
  ApiResponse,
  Skill,
  SkillListResponse,
  SkillCreateRequest,
  SkillUpdateRequest
} from '@/types'

/**
 * 获取所有 Skills
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

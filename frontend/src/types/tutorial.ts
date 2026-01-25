/**
 * 教程相关类型定义
 */

/**
 * 教程操作类型
 */
export type TutorialActionType = 'try_prompt' | 'create_agent' | 'add_skill' | 'navigate' | 'copy_code'

/**
 * 教程操作
 */
export interface TutorialAction {
  /** 操作类型 */
  type: TutorialActionType
  /** 按钮文本 */
  label: string
  /** Prompt 内容（用于 try_prompt） */
  prompt?: string
  /** 导航路径（用于 navigate） */
  path?: string
  /** 代码内容（用于 copy_code） */
  code?: string
}

/**
 * 教程步骤
 */
export interface TutorialStep {
  /** 步骤 ID */
  id: string
  /** 步骤标题 */
  title: string
  /** 步骤内容（Markdown） */
  content: string
  /** 代码示例 */
  code?: string
  /** 代码语言 */
  codeLanguage?: string
  /** 可选的操作 */
  action?: TutorialAction
  /** 提示信息 */
  tip?: string
  /** 警告信息 */
  warning?: string
}

/**
 * 教程章节
 */
export interface TutorialChapter {
  /** 章节 ID */
  id: string
  /** 章节标题 */
  title: string
  /** 章节描述 */
  description: string
  /** 预计时长（分钟） */
  duration: number
  /** 步骤列表 */
  steps: TutorialStep[]
}

/**
 * 教程
 */
export interface Tutorial {
  /** 教程 ID */
  id: string
  /** 教程标题 */
  title: string
  /** 教程描述 */
  description: string
  /** 图标 */
  icon: string
  /** 难度等级 */
  level: 'beginner' | 'intermediate' | 'advanced'
  /** 预计总时长（分钟） */
  totalDuration: number
  /** 章节列表 */
  chapters: TutorialChapter[]
  /** 标签 */
  tags: string[]
}

/**
 * 用户教程进度
 */
export interface TutorialProgress {
  /** 教程 ID */
  tutorialId: string
  /** 当前章节 ID */
  currentChapterId: string
  /** 当前步骤 ID */
  currentStepId: string
  /** 已完成的步骤 ID 列表 */
  completedSteps: string[]
  /** 开始时间 */
  startedAt: string
  /** 最后访问时间 */
  lastAccessedAt: string
}

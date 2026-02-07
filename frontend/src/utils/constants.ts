/**
 * 常量定义
 */

/**
 * 文件写入工具列表（用于实时预览检测）
 */
export const FILE_WRITE_TOOLS = [
  'write_file',
  'str_replace_editor',
  'create_file'
] as const

/**
 * 终端命令工具列表
 */
export const TERMINAL_TOOLS = [
  'run_project'
] as const

/**
 * 工具名称中文映射表
 */
export const TOOL_NAME_MAP: Record<string, string> = {
  // 文件操作
  'write_file': '写入文件',
  'read_file': '读取文件',
  'str_replace_editor': '编辑文件',
  'create_file': '创建文件',

  // API 调用
  'api_calling': '调用服务',

  // 搜索
  'web_search': '网络搜索',
  // tavily_search / exa_search 已迁移到 Skills-First，由 web_search + api_calling 覆盖
  'perplxity': '联网搜索',

  // 知识库
  'knowledge_search': '知识检索',
  'chatDocuments': '文档问答',

  // 计划与任务
  'plan_todo': '任务规划',
  'scheduled_task': '定时任务',

  // 文档生成
  // ppt_generator / slidespeak_render 已迁移到 PPT Skill + api_calling
  'text2document': '文档生成',

  // 数据分析
  // wenshu_analytics / wenshu_api 已移除（云端工具）

  // 流程图/图表
  'Ontology_TextToChart_zen0': '流程图生成',
  'nano_banana': '图表生成',

  // 人工确认
  'request_human_confirmation': '等待确认',

  // Dify/Coze 集成
  'dify_api': 'Dify 服务',
  'coze_api': 'Coze 服务'
}

/**
 * 工具状态文案映射
 */
export const TOOL_STATUS_TEXT: Record<string, string> = {
  'pending': '执行中...',
  'success': '已完成',
  'error': '执行失败'
}

/**
 * SSE 事件类型
 */
export const SSE_EVENT_TYPES = {
  SESSION_START: 'session_start',
  CONVERSATION_START: 'conversation_start',
  MESSAGE_START: 'message_start',
  CONTENT_START: 'content_start',
  CONTENT_DELTA: 'content_delta',
  CONTENT_STOP: 'content_stop',
  MESSAGE_DELTA: 'message_delta',
  MESSAGE_STOP: 'message_stop',
  COMPLETE: 'complete',
  DONE: 'done',
  SESSION_END: 'session_end',
  ERROR: 'error',
  RECONNECT_INFO: 'reconnect_info'
} as const

/**
 * Session 状态
 */
export const SESSION_STATUS = {
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  TIMEOUT: 'timeout',
  STOPPED: 'stopped'
} as const

/**
 * 默认配置
 */
export const DEFAULT_CONFIG = {
  /** 默认分页大小 */
  PAGE_SIZE: 20,
  
  /** 消息历史默认加载数量 */
  MESSAGE_LIMIT: 100,
  
  /** API 超时时间（毫秒） */
  API_TIMEOUT: 30000
} as const

/**
 * 后台任务类型
 */
export const BACKGROUND_TASKS = {
  TITLE_GENERATION: 'title_generation',
  RECOMMENDED_QUESTIONS: 'recommended_questions'
} as const

/**
 * 本地存储键名
 */
export const STORAGE_KEYS = {
  USER: 'user',
  USER_ID: 'userId',
  THEME: 'theme',
  SIDEBAR_COLLAPSED: 'sidebarCollapsed'
} as const

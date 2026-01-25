/**
 * 常量定义
 */

/**
 * 文件写入工具列表（用于实时预览检测）
 */
export const FILE_WRITE_TOOLS = [
  'write_file',
  'sandbox_write_file',
  'str_replace_editor',
  'create_file'
] as const

/**
 * 终端命令工具列表
 */
export const TERMINAL_TOOLS = [
  'sandbox_run_command',
  'run_project',
  'sandbox_run_project'
] as const

/**
 * 工具名称中文映射表
 */
export const TOOL_NAME_MAP: Record<string, string> = {
  // 沙盒/文件操作
  'sandbox_write_file': '写入文件',
  'sandbox_read_file': '读取文件',
  'sandbox_run_command': '执行命令',
  'sandbox_run_project': '运行项目',
  'sandbox_create_project': '创建项目',
  'write_file': '写入文件',
  'read_file': '读取文件',
  'str_replace_editor': '编辑文件',
  'create_file': '创建文件',

  // API 调用
  'api_calling': '调用服务',

  // 搜索
  'web_search': '网络搜索',
  'tavily_search': '网络搜索',
  'exa_search': '智能搜索',
  'perplxity': '联网搜索',

  // 知识库
  'ragie_retrieve': '知识检索',
  'knowledge_search': '知识检索',
  'chatDocuments': '文档问答',

  // 计划与任务
  'plan_todo': '任务规划',
  'scheduled_task': '定时任务',

  // 文档生成
  'ppt_generator': 'PPT 生成',
  'slidespeak_render': '幻灯片渲染',
  'text2document': '文档生成',

  // 数据分析
  'wenshu_analytics': '数据分析',
  'wenshu_api': '数据查询',

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
 * 沙盒状态
 */
export const SANDBOX_STATUS = {
  NONE: 'none',
  CREATING: 'creating',
  RUNNING: 'running',
  PAUSED: 'paused',
  KILLED: 'killed'
} as const

/**
 * 沙盒状态文字映射
 */
export const SANDBOX_STATUS_TEXT: Record<string, string> = {
  'none': '未创建',
  'creating': '创建中...',
  'running': '运行中',
  'paused': '已暂停',
  'killed': '已终止'
}

/**
 * 沙盒状态颜色映射
 */
export const SANDBOX_STATUS_COLOR: Record<string, string> = {
  'none': '#6b7280',
  'creating': '#f59e0b',
  'running': '#10b981',
  'paused': '#3b82f6',
  'killed': '#ef4444'
}

/**
 * 默认配置
 */
export const DEFAULT_CONFIG = {
  /** SSE 重连最大次数 */
  MAX_RECONNECT_ATTEMPTS: 3,
  
  /** SSE 重连基础延迟（毫秒） */
  RECONNECT_BASE_DELAY: 1000,
  
  /** SSE 重连最大延迟（毫秒） */
  RECONNECT_MAX_DELAY: 10000,
  
  /** 活跃会话轮询间隔（毫秒） */
  POLLING_INTERVAL: 3000,
  
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
  TOKEN: 'token',
  USER: 'user',
  USER_ID: 'userId',
  THEME: 'theme',
  SIDEBAR_COLLAPSED: 'sidebarCollapsed'
} as const

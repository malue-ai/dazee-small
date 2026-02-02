"""
Mem0 记忆模块 - Dazee 增强版

基于 Mem0 框架的用户记忆层，支持：
- 用户画像存储与检索
- 跨 Session 的长期记忆
- 个性化信息注入

Dazee 增强功能：
- FragmentExtractor: 碎片记忆提取（基于 LLM 语义理解）
- BehaviorAnalyzer: 5W1H 行为模式分析
- PDCAManager: 计划管理（PDCA 循环）
- Reminder: 智能提醒调度
- Reporter: 智能汇报生成

核心组件：
- Mem0MemoryPool: 全局缓存池（单例）
- format_memories_for_prompt: 格式化函数
- Mem0Config: 配置管理

使用示例：
    from core.memory.mem0 import get_mem0_pool, format_memories_for_prompt
    
    # 搜索用户相关记忆
    pool = get_mem0_pool()
    memories = pool.search(user_id="user_123", query="用户偏好")
    
    # 格式化为 Prompt 片段
    user_profile = format_memories_for_prompt(memories)
    
    # 注入到 System Prompt
    system_prompt = base_prompt + user_profile
    
Dazee 使用示例：
    from core.memory.mem0 import (
        get_fragment_extractor,
        get_behavior_analyzer,
        get_pdca_manager,
        get_reminder,
        get_reporter
    )
    
    # 提取碎片记忆
    extractor = get_fragment_extractor()
    fragment = await extractor.extract(user_id, session_id, message)
    
    # 分析行为模式
    analyzer = get_behavior_analyzer()
    pattern = await analyzer.analyze(user_id, fragments)
    
    # 管理计划
    planner = get_pdca_manager()
    plan = await planner.analyze_for_plan(user_id, message)
    
    # 生成汇报
    reporter = get_reporter()
    report = reporter.generate_daily_report(user_id, user_name, fragments, plans)
"""

# 配置
from .config import (
    Mem0Config,
    QdrantConfig,
    EmbedderConfig,
    LLMConfig,
    get_mem0_config,
    set_mem0_config,
)

# 缓存池
from .pool import (
    Mem0MemoryPool,
    get_mem0_pool,
    reset_mem0_pool,
)

# 格式化
from .formatter import (
    format_memories_for_prompt,
    format_memories_as_context,
    format_single_memory,
    format_memories_by_category,
    create_user_profile_section,
    format_dazee_persona_for_prompt,
    create_dazee_prompt_section,
)

# Dazee 碎片提取器
from .extractor import (
    FragmentExtractor,
    get_fragment_extractor,
    reset_fragment_extractor,
)

# Dazee 行为分析器
from .analyzer import (
    BehaviorAnalyzer,
    get_behavior_analyzer,
    reset_behavior_analyzer,
)

# Dazee PDCA 计划管理器
from .planner import (
    PDCAManager,
    get_pdca_manager,
    reset_pdca_manager,
)

# Dazee 智能提醒
from .reminder import (
    Reminder,
    get_reminder,
    reset_reminder,
)

# Dazee 智能汇报
from .reporter import (
    Reporter,
    get_reporter,
    reset_reporter,
)

# Schemas
from .schemas import (
    # Fragment
    FragmentMemory,
    TaskHint,
    TimeHint,
    EmotionHint,
    RelationHint,
    TodoHint,
    TimeSlot,
    DayOfWeek,
    # Behavior
    BehaviorPattern,
    DateRange,
    RoutineTask,
    TimePattern,
    WorkContext,
    Collaborator,
    Motivation,
    WorkStyle,
    # Plan
    WorkPlan,
    ReminderItem,
    ReminderType,
    PDCAPhase,
    CheckResult,
    ActionItem,
    # Emotion
    EmotionState,
    EmotionSignal,
    EmotionTrend,
    # Persona
    UserPersona,
)


__all__ = [
    # 配置
    "Mem0Config",
    "QdrantConfig",
    "EmbedderConfig",
    "LLMConfig",
    "get_mem0_config",
    "set_mem0_config",
    # 缓存池
    "Mem0MemoryPool",
    "get_mem0_pool",
    "reset_mem0_pool",
    # 格式化
    "format_memories_for_prompt",
    "format_memories_as_context",
    "format_single_memory",
    "format_memories_by_category",
    "create_user_profile_section",
    "format_dazee_persona_for_prompt",
    "create_dazee_prompt_section",
    # Dazee 碎片提取器
    "FragmentExtractor",
    "get_fragment_extractor",
    "reset_fragment_extractor",
    # Dazee 行为分析器
    "BehaviorAnalyzer",
    "get_behavior_analyzer",
    "reset_behavior_analyzer",
    # Dazee PDCA 计划管理器
    "PDCAManager",
    "get_pdca_manager",
    "reset_pdca_manager",
    # Dazee 智能提醒
    "Reminder",
    "get_reminder",
    "reset_reminder",
    # Dazee 智能汇报
    "Reporter",
    "get_reporter",
    "reset_reporter",
    # Schemas
    "FragmentMemory",
    "TaskHint",
    "TimeHint",
    "EmotionHint",
    "RelationHint",
    "TodoHint",
    "TimeSlot",
    "DayOfWeek",
    "BehaviorPattern",
    "DateRange",
    "RoutineTask",
    "TimePattern",
    "WorkContext",
    "Collaborator",
    "Motivation",
    "WorkStyle",
    "WorkPlan",
    "ReminderItem",
    "ReminderType",
    "PDCAPhase",
    "CheckResult",
    "ActionItem",
    "EmotionState",
    "EmotionSignal",
    "EmotionTrend",
    "UserPersona",
]

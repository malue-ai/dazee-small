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
    EmbedderConfig,
    LLMConfig,
    Mem0Config,
    get_mem0_config,
    set_mem0_config,
)

# 记忆抽取
from .extraction import (
    FragmentExtractor,
    get_fragment_extractor,
    reset_fragment_extractor,
)

# 缓存池
from .pool import (
    Mem0MemoryPool,
    get_mem0_pool,
    reset_mem0_pool,
)

# 在线检索
from .retrieval import (
    LLMReranker,
    create_dazee_prompt_section,
    create_user_profile_section,
    format_dazee_persona_for_prompt,
    format_memories_as_context,
    format_memories_by_category,
    format_memories_for_prompt,
    format_single_memory,
    get_reranker,
    reset_reranker,
)

# Schemas
from .schemas import (  # Fragment; Behavior; Plan; Emotion; Persona; Explicit Memory
    ActionItem,
    BehaviorPattern,
    CheckResult,
    Collaborator,
    ConflictDetection,
    ConstraintHint,
    DateRange,
    DayOfWeek,
    EmotionHint,
    EmotionSignal,
    EmotionState,
    EmotionTrend,
    FragmentMemory,
    GoalHint,
    MemoryCard,
    MemoryCardCategory,
    MemorySource,
    MemoryType,
    MemoryVisibility,
    Motivation,
    PDCAPhase,
    PeriodicityAnalysis,
    PlanSummary,
    PreferenceHint,
    PreferenceStability,
    RelationHint,
    ReminderItem,
    ReminderSummary,
    ReminderType,
    RoutineTask,
    TaskHint,
    TimeHint,
    TimePattern,
    TimeSlot,
    TodoHint,
    ToolHint,
    TopicHint,
    UserPersona,
    WorkContext,
    WorkPlan,
    WorkStyle,
)

# 记忆更新
from .update import (
    BehaviorAnalyzer,
    PDCAManager,
    PersonaBuilder,
    QualityController,
    Reminder,
    Reporter,
    aggregate_user_emotion,
    aggregate_weekly_summary,
    aggregate_work_summary,
    get_behavior_analyzer,
    get_pdca_manager,
    get_persona_builder,
    get_quality_controller,
    get_reminder,
    get_reporter,
    reset_behavior_analyzer,
    reset_pdca_manager,
    reset_persona_builder,
    reset_quality_controller,
    reset_reminder,
    reset_reporter,
)

__all__ = [
    # 配置
    "Mem0Config",
    "EmbedderConfig",
    "LLMConfig",
    "get_mem0_config",
    "set_mem0_config",
    # 缓存池
    "Mem0MemoryPool",
    "get_mem0_pool",
    "reset_mem0_pool",
    # 在线检索
    "format_memories_for_prompt",
    "format_memories_as_context",
    "format_single_memory",
    "format_memories_by_category",
    "create_user_profile_section",
    "format_dazee_persona_for_prompt",
    "create_dazee_prompt_section",
    "LLMReranker",
    "get_reranker",
    "reset_reranker",
    # 记忆抽取
    "FragmentExtractor",
    "get_fragment_extractor",
    "reset_fragment_extractor",
    # 记忆更新
    "QualityController",
    "get_quality_controller",
    "reset_quality_controller",
    "BehaviorAnalyzer",
    "get_behavior_analyzer",
    "reset_behavior_analyzer",
    "PDCAManager",
    "get_pdca_manager",
    "reset_pdca_manager",
    "Reminder",
    "get_reminder",
    "reset_reminder",
    "Reporter",
    "get_reporter",
    "reset_reporter",
    "PersonaBuilder",
    "get_persona_builder",
    "reset_persona_builder",
    "aggregate_user_emotion",
    "aggregate_work_summary",
    "aggregate_weekly_summary",
    # Schemas
    "FragmentMemory",
    "TaskHint",
    "TimeHint",
    "EmotionHint",
    "RelationHint",
    "TodoHint",
    "PreferenceHint",
    "TopicHint",
    "ConstraintHint",
    "ToolHint",
    "GoalHint",
    "TimeSlot",
    "DayOfWeek",
    "MemoryType",
    "MemorySource",
    "MemoryVisibility",
    "BehaviorPattern",
    "DateRange",
    "RoutineTask",
    "TimePattern",
    "WorkContext",
    "Collaborator",
    "Motivation",
    "WorkStyle",
    "PreferenceStability",
    "PeriodicityAnalysis",
    "ConflictDetection",
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
    "PlanSummary",
    "ReminderSummary",
    "MemoryCard",
    "MemoryCardCategory",
    "MemoryCard",
    "MemoryCardCategory",
    "MemoryType",
    "MemorySource",
    "MemoryVisibility",
]

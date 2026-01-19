"""
Agent 模块

提供 Agent 核心功能：
- SimpleAgent: 单智能体编排器（RVR 循环）
- MultiAgentOrchestrator: 多智能体编排器（Leader-Worker 模式）
- ContentHandler: 统一的 Content Block 处理器
- AgentFactory: Prompt 驱动的动态初始化
- IntentAnalyzer: 意图分析器
- 类型定义: IntentResult, TaskType, Complexity 等
- Schema: 强类型配置定义

目录结构：
- simple/: Simple Agent 模块
- multi/: Multi Agent 模块
- content_handler.py: 统一的 Content Block 处理器
- factory.py: Agent 工厂（动态初始化）
- intent_analyzer.py: 意图分析器
- types.py: 类型定义
"""

from core.agent.types import (
    TaskType,
    Complexity,
    IntentResult,
)
from core.agent.intent_analyzer import (
    IntentAnalyzer,
    create_intent_analyzer
)
from core.agent.simple import (
    SimpleAgent,
    create_simple_agent
)
from core.agent.multi import (
    MultiAgentOrchestrator,
    LeadAgent,
    CheckpointManager,
    ExecutionMode,
    AgentRole,
    MultiAgentConfig,
)
from core.agent.content_handler import (
    ContentHandler,
    create_content_handler
)
from core.agent.factory import (
    AgentFactory,
    AgentPresets,
    ComponentType,
    create_agent_from_prompt,
    create_agent_from_preset,
    create_schema_from_dict
)
# 从 schemas 模块导入强类型定义
from core.schemas import (
    AgentSchema,
    DEFAULT_AGENT_SCHEMA,
    IntentAnalyzerConfig,
    PlanManagerConfig,
    ToolSelectorConfig,
    MemoryManagerConfig,
    OutputFormatterConfig,
    SkillConfig,
    ContextLimitsConfig,
)

__all__ = [
    # 类型
    "TaskType",
    "Complexity",
    "IntentResult",
    # Simple Agent
    "SimpleAgent",
    "create_simple_agent",
    # Multi Agent
    "MultiAgentOrchestrator",
    "LeadAgent",
    "CheckpointManager",
    "ExecutionMode",
    "AgentRole",
    "MultiAgentConfig",
    # ContentHandler
    "ContentHandler",
    "create_content_handler",
    # Factory（Prompt 驱动）
    "AgentFactory",
    "AgentPresets",
    "ComponentType",
    "create_agent_from_prompt",
    "create_agent_from_preset",
    "create_schema_from_dict",
    # Schema（强类型配置）
    "AgentSchema",
    "DEFAULT_AGENT_SCHEMA",
    "IntentAnalyzerConfig",
    "PlanManagerConfig",
    "ToolSelectorConfig",
    "MemoryManagerConfig",
    "OutputFormatterConfig",
    "SkillConfig",
    "ContextLimitsConfig",
    # 意图分析
    "IntentAnalyzer",
    "create_intent_analyzer",
]


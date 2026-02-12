"""
Agent 模块

V11.0: 小搭子桌面端架构，固定 RVR-B 执行策略

架构：
- base.py: 统一 Agent 类
- factory.py: AgentFactory（创建入口）
- models.py: 数据模型
- execution/: 执行策略（RVR, RVR-B）
- components/: 可复用组件（Checkpoint）
- context/: Prompt/Context 构建
- tools/: 工具执行流

使用方式：
    # 推荐：通过 Factory 创建
    agent = AgentFactory.from_schema(schema, system_prompt, event_manager)
"""

# 统一 Agent 类
from core.agent.base import Agent, AgentState

# ContentHandler
from core.agent.content_handler import ContentHandler, create_content_handler

# Factory
from core.agent.factory import (
    AgentFactory,
    AgentPresets,
    ComponentType,
    create_agent_from_preset,
    create_agent_from_prompt,
    create_schema_from_dict,
    get_available_strategies,
)

# Models（单智能体）
from core.agent.models import (
    AgentConfig,
    AgentResult,
    AgentRole,
)

# 类型定义（从 routing 层导入）
from core.routing.types import (
    Complexity,
    IntentResult,
)

# Schema
from core.schemas import (
    DEFAULT_AGENT_SCHEMA,
    AgentSchema,
    ContextLimitsConfig,
    IntentAnalyzerConfig,
    MemoryManagerConfig,
    OutputFormatterConfig,
    PlanManagerConfig,
    SkillConfig,
    ToolSelectorConfig,
)


async def create_agent(
    event_manager=None,
    schema: AgentSchema = None,
    system_prompt: str = "",
    **kwargs
) -> Agent:
    """
    创建 Agent（便捷函数）

    V11.0: 固定使用 RVR-B 执行策略

    Args:
        event_manager: 事件管理器（必需）
        schema: AgentSchema 配置
        system_prompt: 系统提示词
        **kwargs: 其他参数

    Returns:
        Agent 实例
    """
    if event_manager is None:
        raise ValueError("event_manager 是必需参数")

    effective_schema = schema or DEFAULT_AGENT_SCHEMA

    # 固定使用 rvr-b 策略
    try:
        effective_schema = effective_schema.model_copy(update={"execution_strategy": "rvr-b"})
    except Exception:
        kwargs["strategy"] = "rvr-b"

    return await AgentFactory.from_schema(
        schema=effective_schema,
        system_prompt=system_prompt or "你是一个智能助手。",
        event_manager=event_manager,
        **kwargs
    )


__all__ = [
    # 类型
    "Complexity",
    "IntentResult",
    # Agent
    "Agent",
    "AgentState",
    # ContentHandler
    "ContentHandler",
    "create_content_handler",
    # Factory
    "AgentFactory",
    "AgentPresets",
    "ComponentType",
    "create_agent_from_prompt",
    "create_agent_from_preset",
    "create_schema_from_dict",
    "get_available_strategies",
    # 便捷函数
    "create_agent",
    # Models
    "AgentRole",
    "AgentConfig",
    "AgentResult",
    # Schema
    "AgentSchema",
    "DEFAULT_AGENT_SCHEMA",
    "IntentAnalyzerConfig",
    "PlanManagerConfig",
    "ToolSelectorConfig",
    "MemoryManagerConfig",
    "OutputFormatterConfig",
    "SkillConfig",
    "ContextLimitsConfig",
]

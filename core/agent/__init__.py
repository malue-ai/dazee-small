"""
Agent 模块

V10.0: 统一 Agent + Executor 策略模式
V10.3: 清理架构，解耦 MultiAgentOrchestrator

架构：
- base.py: 统一 Agent 类
- factory.py: AgentFactory（创建入口）
- models.py: 数据模型
- execution/: 执行策略（RVR, RVR-B, Multi）
- execution/_multi/: 多智能体内部实现（orchestrator + 子模块）
- components/: 可复用组件（Checkpoint, LeadAgent, Critic）
- context/: Prompt/Context 构建
- tools/: 工具执行流

使用方式：
    # 推荐：通过 Factory 创建
    agent = AgentFactory.from_schema(schema, system_prompt, event_manager)

    # 多智能体
    orchestrator = AgentFactory.create_multi_agent(schema=schema, broadcaster=bc)
"""

# 统一 Agent 类
from core.agent.base import Agent, AgentState

# ContentHandler
from core.agent.content_handler import ContentHandler, create_content_handler

# 多智能体编排器（内部实现，通过 MultiAgentExecutor 或 Factory 访问）
from core.agent.execution._multi import MultiAgentOrchestrator

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

# Models（多智能体相关）
from core.agent.models import (
    AgentConfig,
    AgentResult,
    AgentRole,
    CriticAction,
    CriticConfidence,
    CriticConfig,
    CriticResult,
    ExecutionMode,
    MultiAgentConfig,
    OrchestratorConfig,
    OrchestratorState,
    SubagentResult,
    TaskAssignment,
    WorkerConfig,
    load_multi_agent_config,
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
    strategy: str = "rvr",
    event_manager=None,
    schema: AgentSchema = None,
    system_prompt: str = "",
    **kwargs
) -> Agent:
    """
    创建 Agent（便捷函数）

    这是推荐的 Agent 创建入口，通过 strategy 参数指定执行策略。

    Args:
        strategy: 执行策略
            - "rvr": 标准 RVR 执行（默认）
            - "rvr-b": RVR-B 执行（带回溯）
            - "multi": 多智能体执行
        event_manager: 事件管理器（必需）
        schema: AgentSchema 配置
        system_prompt: 系统提示词
        **kwargs: 其他参数

    Returns:
        Agent 实例

    Example:
        # 创建标准 Agent
        agent = await create_agent(strategy="rvr", event_manager=em)

        # 创建带回溯的 Agent
        agent = await create_agent(strategy="rvr-b", event_manager=em)
    """
    if event_manager is None:
        raise ValueError("event_manager 是必需参数")

    effective_schema = schema or DEFAULT_AGENT_SCHEMA

    # 🆕 P0-5: 将 strategy 注入 schema（确保 Factory 使用正确的策略）
    # 如果 schema 有 execution_strategy 字段，优先使用；否则使用函数参数
    if hasattr(effective_schema, "execution_strategy") and effective_schema.execution_strategy:
        pass  # 使用 schema 自带的策略
    else:
        # 动态设置 execution_strategy
        try:
            effective_schema = effective_schema.model_copy(update={"execution_strategy": strategy})
        except Exception:
            # 如果 schema 不支持该字段，通过 kwargs 传递
            kwargs["strategy"] = strategy

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
    # 多智能体（内部实现）
    "MultiAgentOrchestrator",
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
    "ExecutionMode",
    "AgentRole",
    "AgentConfig",
    "MultiAgentConfig",
    "OrchestratorConfig",
    "WorkerConfig",
    "CriticConfig",
    "TaskAssignment",
    "AgentResult",
    "SubagentResult",
    "OrchestratorState",
    "CriticAction",
    "CriticConfidence",
    "CriticResult",
    "load_multi_agent_config",
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

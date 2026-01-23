"""
Agent 模块

V7.8 架构重构：

核心组件：
- AgentProtocol: 统一接口协议（SimpleAgent 和 MultiAgent 共同实现）
- AgentCoordinator: 协调器（整合路由和工厂，单一执行入口）
- AgentFactory: 创建工厂（无路由逻辑，统一创建入口）
- SimpleAgent: 单智能体编排器（RVR 循环）
- MultiAgentOrchestrator: 多智能体编排器（Leader-Worker + DAGScheduler）

设计原则：
1. 路由逻辑集中在 AgentRouter（不在 Factory）
2. AgentCoordinator.route_and_execute() 是推荐的单一入口
3. 所有 Agent 实现 AgentProtocol，上层调用无需类型判断

目录结构：
- protocol.py: Agent 统一接口
- coordinator.py: Agent 协调器
- factory.py: Agent 工厂
- simple/: Simple Agent 模块
- multi/: Multi Agent 模块
- content_handler.py: Content Block 处理器
- types.py: 类型定义
"""

# 类型定义
from core.agent.types import (
    TaskType,
    Complexity,
    IntentResult,
)

# 🆕 V7.8: Protocol 和 Coordinator
from core.agent.protocol import (
    AgentProtocol,
    is_agent,
    get_agent_type,
)
from core.agent.coordinator import (
    AgentCoordinator,
    get_agent_coordinator,
    create_agent_coordinator,
)

# Simple Agent
from core.agent.simple import (
    SimpleAgent,
    RVRBAgent,
    create_simple_agent
)

# Multi Agent
from core.agent.multi import (
    MultiAgentOrchestrator,
    LeadAgent,
    CheckpointManager,
    ExecutionMode,
    AgentRole,
    MultiAgentConfig,
)

# ContentHandler
from core.agent.content_handler import (
    ContentHandler,
    create_content_handler
)

# Factory
from core.agent.factory import (
    AgentFactory,
    AgentPresets,
    ComponentType,
    create_agent_from_prompt,
    create_agent_from_preset,
    create_schema_from_dict
)

# 意图分析器
from core.agent.intent_analyzer import (
    IntentAnalyzer,
    create_intent_analyzer
)

# Schema（强类型配置）
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
    # 🆕 V7.8: Protocol 和 Coordinator
    "AgentProtocol",
    "is_agent",
    "get_agent_type",
    "AgentCoordinator",
    "get_agent_coordinator",
    "create_agent_coordinator",
    
    # 类型
    "TaskType",
    "Complexity",
    "IntentResult",
    
    # Simple Agent
    "SimpleAgent",
    "RVRBAgent",
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
    
    # Factory
    "AgentFactory",
    "AgentPresets",
    "ComponentType",
    "create_agent_from_prompt",
    "create_agent_from_preset",
    "create_schema_from_dict",
    
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
    
    # 意图分析
    "IntentAnalyzer",
    "create_intent_analyzer",
]


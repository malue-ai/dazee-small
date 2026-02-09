"""
ZenFlux Agent V4.2 Core Module

核心组件：
- Agent: 统一 Agent 类（执行策略通过 Executor 实现）
- CapabilityRegistry: 能力注册表
- ToolSelector: 工具选择器
- SkillLoader: Skill 内容加载器
- MemoryManager: 记忆管理
- LLM Service: LLM 统一封装
- EventManager: 事件管理（SSE/WebSocket 通用协议）
- Context: 上下文管理
- Orchestration: Code-First 编排模块
"""

# Agent
from .agent import Agent, create_agent

# 上下文管理（新架构）
from .context import RuntimeContext, create_runtime_context

# 事件管理（SSE/WebSocket 通用协议）
from .events import (  # 事件存储（内存，开发环境用）
    ContentEventManager,
    ConversationEventManager,
    EventBroadcaster,
    EventManager,
    InMemoryEventStorage,
    MessageEventManager,
    SessionEventManager,
    SystemEventManager,
    UserEventManager,
    create_broadcaster,
    create_event_manager,
    get_memory_storage,
)

# LLM Service（从 llm 模块导入）
from .llm import (
    BaseLLMService,
    ClaudeLLMService,
    InvocationType,
    LLMConfig,
    LLMProvider,
    LLMResponse,
    Message,
    ToolType,
    create_claude_service,
    create_llm_service,
)

# 记忆管理（新架构 - 文件夹模块）
from .memory import (  # 基础类型; 会话级记忆; 用户级记忆; 系统级记忆（Skill = 本地工作流技能）; 统一管理器
    CacheMemory,
    EpisodicMemory,
    MemoryConfig,
    MemoryManager,
    MemoryScope,
    PreferenceMemory,
    PlanMemory,
    SkillMemory,
    StorageBackend,
    WorkingMemory,
    create_cache_memory,
    create_episodic_memory,
    create_memory_manager,
    create_preference_memory,
    create_plan_memory,
    create_skill_memory,
    create_user_memory_manager,
    create_working_memory,
)

# Code-First 编排模块（V4.2 新增）
from .orchestration import (  # 管道追踪器; 代码验证器; 代码编排器
    CodeOrchestrator,
    CodeValidator,
    E2EPipelineTracer,
    PipelineStage,
    ValidationResult,
    create_code_orchestrator,
    create_code_validator,
    create_pipeline_tracer,
)
from .tool.capability import SkillInfo, SkillLoader, create_skill_loader
from .tool.registry import CapabilityRegistry, create_capability_registry
from .tool.selector import RoutingResult, ToolSelector, create_tool_selector

# 工具系统
from .tool.types import Capability, CapabilityType

__all__ = [
    # Agent
    "Agent",
    "create_agent",
    # 工具系统
    "CapabilityRegistry",
    "Capability",
    "CapabilityType",
    "create_capability_registry",
    "ToolSelector",
    "RoutingResult",
    "create_tool_selector",
    # Skill 加载器
    "SkillLoader",
    "SkillInfo",
    "create_skill_loader",
    # 记忆管理
    "MemoryScope",
    "StorageBackend",
    "MemoryConfig",
    "WorkingMemory",
    "create_working_memory",
    "EpisodicMemory",
    "create_episodic_memory",
    "PreferenceMemory",
    "create_preference_memory",
    "PlanMemory",
    "create_plan_memory",
    # 系统级记忆（Skill = 本地工作流技能）
    "SkillMemory",
    "create_skill_memory",
    "CacheMemory",
    "create_cache_memory",
    "MemoryManager",
    "create_memory_manager",
    "create_user_memory_manager",
    # LLM Service
    "BaseLLMService",
    "ClaudeLLMService",
    "LLMResponse",
    "Message",
    "ToolType",
    "LLMProvider",
    "InvocationType",
    "LLMConfig",
    "create_llm_service",
    "create_claude_service",
    # 事件管理（SSE/WebSocket 通用协议）
    "EventManager",
    "create_event_manager",
    "SessionEventManager",
    "UserEventManager",
    "ConversationEventManager",
    "MessageEventManager",
    "ContentEventManager",
    "SystemEventManager",
    "EventBroadcaster",
    "create_broadcaster",
    # 事件存储（内存，开发环境用）
    "InMemoryEventStorage",
    "get_memory_storage",
    # 上下文管理
    "RuntimeContext",
    "create_runtime_context",
    # Code-First 编排模块（V4.2 新增）
    "E2EPipelineTracer",
    "PipelineStage",
    "create_pipeline_tracer",
    "CodeValidator",
    "ValidationResult",
    "create_code_validator",
    "CodeOrchestrator",
    "create_code_orchestrator",
]

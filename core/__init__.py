"""
ZenFlux Agent V4.2 Core Module

核心组件：
- SimpleAgent: 主Agent类
- CapabilityRegistry: 能力注册表
- CapabilityRouter: 能力路由器
- SkillLoader: Skills 内容加载器
- MemoryManager: 记忆管理
- LLM Service: LLM统一封装
- EventManager: 事件管理（SSE/WebSocket 通用协议）
- Context: 上下文管理
- Orchestration: Code-First + VM Scaffolding 编排模块（V4.2 新增）
"""

# Agent（新架构）
from .agent import SimpleAgent, create_simple_agent

# 能力路由（从新路径导入）
from .tool.capability import (
    CapabilityRegistry,
    Capability,
    CapabilityType,
    create_capability_registry,
    CapabilityRouter,
    RoutingResult,
    create_capability_router,
    extract_keywords,
    # Skills 加载器
    SkillLoader,
    SkillInfo,
    create_skill_loader
)

# 记忆管理（新架构 - 文件夹模块）
from .memory import (
    # 基础类型
    MemoryScope,
    StorageBackend,
    MemoryConfig,
    # 会话级记忆
    WorkingMemory,
    create_working_memory,
    # E2B 记忆
    E2BSandboxSession,
    E2BMemory,
    create_e2b_memory,
    # 用户级记忆
    EpisodicMemory,
    create_episodic_memory,
    PreferenceMemory,
    create_preference_memory,
    # 系统级记忆
    SkillMemory,
    create_skill_memory,
    CacheMemory,
    create_cache_memory,
    # 统一管理器
    MemoryManager,
    create_memory_manager,
    create_user_memory_manager,
)

# LLM Service（从 llm 模块导入）
from .llm import (
    BaseLLMService,
    ClaudeLLMService,
    LLMResponse,
    Message,
    ToolType,
    LLMProvider,
    InvocationType,
    LLMConfig,
    create_llm_service,
    create_claude_service
)

# 事件管理（SSE/WebSocket 通用协议）
from .events import (
    EventManager,
    create_event_manager,
    SessionEventManager,
    UserEventManager,
    ConversationEventManager,
    MessageEventManager,
    ContentEventManager,
    SystemEventManager,
    EventBroadcaster,
    create_broadcaster,
    # 事件存储（Redis / 内存）
    RedisEventStorage,
    InMemoryEventStorage,
    create_event_storage,
    get_memory_storage,
)

# 上下文管理（新架构）
from .context import (
    Context,
    create_context,
    RuntimeContext,
    create_runtime_context
)

# Code-First + VM Scaffolding 编排模块（V4.2 新增）
from .orchestration import (
    # 管道追踪器
    E2EPipelineTracer,
    PipelineStage,
    create_pipeline_tracer,
    # 代码验证器
    CodeValidator,
    ValidationResult,
    create_code_validator,
    # 代码编排器
    CodeOrchestrator,
    create_code_orchestrator,
)


__all__ = [
    # Agent
    "SimpleAgent",
    "create_simple_agent",
    
    # 能力路由
    "CapabilityRegistry",
    "Capability",
    "CapabilityType",
    "create_capability_registry",
    "CapabilityRouter",
    "RoutingResult",
    "create_capability_router",
    "extract_keywords",
    
    # Skills 加载器
    "SkillLoader",
    "SkillInfo",
    "create_skill_loader",
    
    # 记忆管理
    "MemoryScope",
    "StorageBackend",
    "MemoryConfig",
    "WorkingMemory",
    "create_working_memory",
    "E2BSandboxSession",
    "E2BMemory",
    "create_e2b_memory",
    "EpisodicMemory",
    "create_episodic_memory",
    "PreferenceMemory",
    "create_preference_memory",
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
    # 事件存储
    "RedisEventStorage",
    "InMemoryEventStorage",
    "create_event_storage",
    "get_memory_storage",
    
    # 上下文管理
    "Context",
    "create_context",
    "RuntimeContext",
    "create_runtime_context",
    
    # Code-First + VM Scaffolding 编排模块（V4.2 新增）
    "E2EPipelineTracer",
    "PipelineStage",
    "create_pipeline_tracer",
    "CodeValidator",
    "ValidationResult",
    "create_code_validator",
    "CodeOrchestrator",
    "create_code_orchestrator",
]


"""
Agent V3.4 Core Module

核心组件：
- SimpleAgent: 主Agent类
- CapabilityRegistry: 能力注册表
- CapabilityRouter: 能力路由器
- SkillsManager: Skills管理器
- MemoryManager: 记忆管理
- PlanningManager: 规划管理
- LLM Service: LLM统一封装
"""

# Agent
from .agent import SimpleAgent, create_simple_agent

# 能力路由
from .capability_registry import (
    CapabilityRegistry,
    Capability,
    CapabilityType,
    create_capability_registry
)
from .capability_router import (
    CapabilityRouter,
    RoutingResult,
    create_capability_router,
    extract_keywords
)

# Skills管理
from .skills_manager import (
    SkillsManager,
    SkillInfo,
    create_skills_manager
)

# 记忆管理
from .memory import (
    MemoryManager,
    WorkingMemory,
    EpisodicMemory,
    SkillMemory,
    create_memory_manager
)

# 规划管理
from .planning import (
    PlanningManager,
    TaskPlan,
    Task,
    TaskStatus,
    create_planning_manager
)

# LLM Service
from .llm_service import (
    BaseLLMService,
    ClaudeLLMService,
    LLMResponse,
    Message,
    ToolType,
    LLMProvider,
    create_llm_service,
    create_claude_service
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
    
    # Skills管理
    "SkillsManager",
    "SkillInfo",
    "create_skills_manager",
    
    # 记忆管理
    "MemoryManager",
    "WorkingMemory",
    "EpisodicMemory",
    "SkillMemory",
    "create_memory_manager",
    
    # 规划管理
    "PlanningManager",
    "TaskPlan",
    "Task",
    "TaskStatus",
    "create_planning_manager",
    
    # LLM Service
    "BaseLLMService",
    "ClaudeLLMService",
    "LLMResponse",
    "Message",
    "ToolType",
    "LLMProvider",
    "create_llm_service",
    "create_claude_service",
]


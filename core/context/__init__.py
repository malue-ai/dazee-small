"""
Context Engineering 模块

先进上下文管理策略实现
"""

# 运行时上下文
from .runtime import RuntimeContext, create_runtime_context

# 会话上下文
from .conversation import Context, create_context

# 上下文工程优化
from .context_engineering import (
    # KV-Cache 优化
    CacheOptimizer,
    
    # Todo 重写
    TodoRewriter,
    
    # 工具遮蔽
    AgentState,
    ToolMaskConfig,
    ToolMasker,
    
    # 可恢复压缩
    CompressedReference,
    RecoverableCompressor,
    
    # 结构化变异
    StructuralVariation,
    
    # 错误保留
    ErrorRecord,
    ErrorRetention,
    
    # 整合管理器
    ContextEngineeringManager,
    create_context_engineering_manager,
)

from .prompt_manager import (
    PromptManager,
    PromptAppendRule,
    PromptState,
    AppendedFragment,
    create_prompt_manager,
    get_prompt_manager,
)

__all__ = [
    # 运行时上下文
    "RuntimeContext",
    "create_runtime_context",
    
    # 会话上下文
    "Context",
    "create_context",
    
    # 上下文工程优化
    "CacheOptimizer",
    "TodoRewriter",
    "AgentState",
    "ToolMaskConfig",
    "ToolMasker",
    "CompressedReference",
    "RecoverableCompressor",
    "StructuralVariation",
    "ErrorRecord",
    "ErrorRetention",
    "ContextEngineeringManager",
    "create_context_engineering_manager",
    
    # Prompt 管理（与 RuntimeContext 集成）
    "PromptManager",
    "PromptAppendRule",
    "PromptState",
    "AppendedFragment",
    "create_prompt_manager",
    "get_prompt_manager",
]

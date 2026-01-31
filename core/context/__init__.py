"""
上下文管理框架

统一管理知识库（Ragie）、用户记忆（Mem0）、历史对话（DB）等数据源，
为 LLM 提供个性化上下文。

核心理念：
- Ragie 和 Mem0 本质相同：都是为 LLM 提供上下文的数据源
- 统一检索、融合、注入流程
- 易于扩展新的数据源

使用方式：
    from core.context import get_context_manager
    
    context_mgr = get_context_manager()
    
    # 获取增强后的提示词
    enhanced_prompt = await context_mgr.get_enhanced_prompt(
        base_prompt="你是一个智能助手",
        query="推荐一些适合我的书",
        user_id="user_123"
    )
    
    # 更新用户记忆
    await context_mgr.update_context(
        user_id="user_123",
        source_type=ContextType.MEMORY,
        data={"messages": [...]}
    )
"""
from .provider import ContextProvider, ContextType
from .manager import ContextManager, get_context_manager
from .retriever import ContextRetriever
from .fusion import FusionEngine
from .injector import ContextInjector

# 会话上下文管理
from .conversation import Context, create_context

# 运行时上下文
from .runtime import RuntimeContext, create_runtime_context

__all__ = [
    # 主入口
    "ContextManager",
    "get_context_manager",
    
    # 核心接口
    "ContextProvider",
    "ContextType",
    
    # 子组件（高级用法）
    "ContextRetriever",
    "FusionEngine",
    "ContextInjector",
    
    # 会话上下文
    "Context",
    "create_context",
    
    # 运行时上下文
    "RuntimeContext",
    "create_runtime_context",
]

"""
上下文管理框架

统一管理知识库（Ragie）、用户记忆（Mem0）、历史对话（DB）等数据源，
为 LLM 提供个性化上下文。

================================================================================
推荐使用 - Injector 模块（V9.0+）
================================================================================

Phase-based Injector 是新的上下文注入架构，提供更清晰的分层和缓存控制：

    from core.context.injectors import (
        InjectionOrchestrator,       # 编排器
        InjectionContext,            # 注入上下文
        create_default_orchestrator, # 创建默认编排器
    )

    # 创建编排器
    orchestrator = create_default_orchestrator()

    # 构建上下文
    context = InjectionContext(
        user_id="user_123",
        user_query="帮我写一段代码",
    )

    # Phase 1: System Message（带缓存元数据）
    system_blocks = await orchestrator.build_system_blocks(context)

    # Phase 2 & 3: User Messages
    messages = await orchestrator.build_messages(context)

================================================================================
压缩功能
================================================================================

    from core.context.compaction import (
        compress_with_summary,      # 带摘要的消息压缩
        load_with_existing_summary, # 加载已有摘要
        ConversationSummarizer,     # 摘要生成器
    )
"""

# 🆕 工具结果压缩（统一方案 V10.0）
from .compaction.tool_result import (
    COMPRESSED_MARKER,
    ToolResultCompressor,
    compress_tool_result,
    extract_ref_id,
    is_compressed,
)

# 上下文工程（KV-Cache 优化）
from .context_engineering import (
    CacheOptimizer,
    create_context_engineering_manager,
)
from .provider import ContextProvider, ContextType

# 元数据获取器
from .providers.metadata import (
    ConversationMetadataProvider,
    load_context_metadata,
    load_plan_for_context,
)
from .retriever import ContextRetriever

# 运行时上下文
from .runtime import RuntimeContext, create_runtime_context

# 便捷函数：稳定 JSON 序列化（保持键顺序一致，提高 KV-Cache 命中率）
stable_json_dumps = CacheOptimizer.stable_json_dumps

__all__ = [
    # Injector 模块（V9.0+）
    "injectors",
    # 运行时上下文
    "RuntimeContext",
    "create_runtime_context",
    # 核心接口（Provider 模式）
    "ContextProvider",
    "ContextType",
    # 上下文工程
    "CacheOptimizer",
    "create_context_engineering_manager",
    "stable_json_dumps",
    # 工具结果压缩
    "ToolResultCompressor",
    "compress_tool_result",
    "is_compressed",
    "extract_ref_id",
    "COMPRESSED_MARKER",
    # 元数据获取器
    "ConversationMetadataProvider",
    "load_plan_for_context",
    "load_context_metadata",
    # 检索器
    "ContextRetriever",
]

# 🆕 Injector 子模块（延迟导入，避免循环引用）
from . import injectors

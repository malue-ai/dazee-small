"""
Prompt Builder - System Blocks 构建器

职责：
- 使用 Injector 编排器构建 system blocks
- 管理多层缓存的 System Prompt
- 任务复杂度判断

架构位置：
- 这是 agent 内部的 Builder 层
- 组合 core/context/injectors 的能力
- 供 Agent 调用

调用链：
    Agent._build_system_message()
        ↓
    build_system_blocks_with_injector()
        ↓
    core.context.injectors.InjectorOrchestrator

注意：
- 用户画像检索（Mem0 + MEMORY.md）由 UserMemoryInjector 统一归口
- prompt_builder 不再直接接触 Mem0，职责仅为 Injector 编排
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from logger import get_logger

if TYPE_CHECKING:
    from core.context.compaction import ContextStrategy
    from core.context.runtime import RuntimeContext
    from core.prompt.instance_cache import InstancePromptCache
    from core.routing.types import IntentResult

logger = get_logger(__name__)


def get_task_complexity(intent: Optional["IntentResult"]):
    """
    从意图识别结果获取任务复杂度

    Args:
        intent: IntentResult 对象

    Returns:
        TaskComplexity 枚举值
    """
    from core.prompt import TaskComplexity

    if intent is None:
        return TaskComplexity.MEDIUM  # 默认中等复杂度

    # 从 intent 获取复杂度字符串
    complexity_str = getattr(intent, "complexity", "medium")
    if complexity_str is None:
        complexity_str = "medium"

    # 如果是枚举类型，获取其值
    if hasattr(complexity_str, "value"):
        complexity_str = complexity_str.value

    # 映射到 TaskComplexity 枚举
    complexity_map = {
        "simple": TaskComplexity.SIMPLE,
        "low": TaskComplexity.SIMPLE,
        "medium": TaskComplexity.MEDIUM,
        "high": TaskComplexity.COMPLEX,
        "complex": TaskComplexity.COMPLEX,
    }

    return complexity_map.get(complexity_str.lower(), TaskComplexity.MEDIUM)


# ============================================================
# V9.0+ Injector 编排器集成
# ============================================================


async def build_system_blocks_with_injector(
    intent: Optional["IntentResult"],
    prompt_cache: Optional["InstancePromptCache"],
    context_strategy: "ContextStrategy",
    user_id: str = None,
    user_query: str = None,
    available_tools: List[Dict[str, Any]] = None,
    history_messages: List[Dict[str, Any]] = None,
    variables: Dict[str, Any] = None,
    metadata: Dict[str, Any] = None,
) -> List[Dict[str, Any]]:
    """
    使用 Injector 编排器构建 system blocks

    这是 V9.0+ 的新方法，使用 Phase-based Injector 模式：
    - Phase 1: System Message（角色定义、工具定义、历史摘要）
    - Phase 2: User Context（用户记忆、知识库、GTD 计划）
    - Phase 3: Runtime（GTD Todo、页面编辑器上下文）

    Args:
        intent: IntentResult 对象
        prompt_cache: InstancePromptCache 实例
        context_strategy: ContextStrategy 配置
        user_id: 用户 ID
        user_query: 用户查询
        available_tools: 可用工具列表
        history_messages: 历史消息列表
        variables: 前端变量
        metadata: 额外元数据

    Returns:
        List[Dict] - 带 _cache_layer 元数据的 system blocks
    """
    from core.context.injectors import (
        InjectionContext,
        create_default_orchestrator,
    )

    # 获取任务复杂度
    task_complexity = get_task_complexity(intent)

    # 构建 InjectionContext
    context = InjectionContext(
        user_id=user_id,
        user_query=user_query,
        prompt_cache=prompt_cache,
        task_complexity=(
            task_complexity.value if hasattr(task_complexity, "value") else task_complexity
        ),
        intent=intent,
        available_tools=available_tools or [],
        history_messages=history_messages or [],
        variables=variables or {},
        metadata=metadata or {},
    )

    # 创建编排器并执行（用户画像由 UserMemoryInjector 在 Phase 2 自行获取）
    orchestrator = create_default_orchestrator()
    system_blocks = await orchestrator.build_system_blocks(context)

    # 追加 Memory Guidance Prompt（L1 策略）
    if context_strategy.enable_memory_guidance:
        from core.context.compaction import get_memory_guidance_prompt

        system_blocks.append(
            {
                "type": "text",
                "text": f"\n\n{get_memory_guidance_prompt()}",
                "_cache_layer": 0,  # 不缓存
            }
        )

    logger.info(
        f"✅ [Injector] System Blocks: "
        f"complexity={task_complexity.value if hasattr(task_complexity, 'value') else task_complexity}, "
        f"blocks={len(system_blocks)}"
    )

    return system_blocks


async def build_user_context_with_injector(
    intent: Optional["IntentResult"],
    user_id: str = None,
    user_query: str = None,
    prompt_cache: Optional["InstancePromptCache"] = None,
    available_tools: List[Dict[str, Any]] = None,
    history_messages: List[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    执行 Phase 2 Injectors，返回 user context 内容

    Phase 2 包括：
    - UserMemoryInjector: 用户记忆（MEMORY.md + Mem0 融合）
    - PlaybookHintInjector: 匹配的 Playbook 策略提示
    - KnowledgeContextInjector: 本地知识库上下文

    返回的内容应作为 user message 注入到对话历史之前，
    为 Agent 提供背景上下文。

    Args:
        intent: IntentResult 对象
        user_id: 用户 ID
        user_query: 用户查询
        prompt_cache: InstancePromptCache 实例
        available_tools: 可用工具列表
        history_messages: 历史消息列表

    Returns:
        组装后的 user context 字符串，无内容时返回 None
    """
    from core.context.injectors import (
        InjectionContext,
        create_default_orchestrator,
    )

    task_complexity = get_task_complexity(intent)

    context = InjectionContext(
        user_id=user_id,
        user_query=user_query,
        prompt_cache=prompt_cache,
        task_complexity=(
            task_complexity.value if hasattr(task_complexity, "value") else task_complexity
        ),
        intent=intent,
        available_tools=available_tools or [],
        history_messages=history_messages or [],
    )

    # 用户画像由 UserMemoryInjector 在 inject() 中自行获取，无需预加载
    orchestrator = create_default_orchestrator()
    user_context = await orchestrator.build_user_context_content(context)

    if user_context:
        logger.info(
            f"✅ [Injector] Phase 2 User Context: {len(user_context)} 字符"
        )

    return user_context


async def build_messages_with_injector(
    intent: Optional["IntentResult"],
    prompt_cache: Optional["InstancePromptCache"],
    context_strategy: "ContextStrategy",
    user_id: str = None,
    user_query: str = None,
    user_message: str = None,
    available_tools: List[Dict[str, Any]] = None,
    history_messages: List[Dict[str, Any]] = None,
    variables: Dict[str, Any] = None,
    metadata: Dict[str, Any] = None,
) -> List[Dict[str, Any]]:
    """
    使用 Injector 编排器构建完整的 messages 数组

    消息结构：
    - messages[0]: user context (Phase 2, systemInjection: true)
    - messages[1...n-1]: 对话历史
    - messages[n]: 最后一条用户消息 + Phase 3 追加

    注意：system message (Phase 1) 通过 build_system_blocks_with_injector() 单独构建

    Args:
        intent: IntentResult 对象
        prompt_cache: InstancePromptCache 实例
        context_strategy: ContextStrategy 配置
        user_id: 用户 ID
        user_query: 用户查询
        user_message: 当前用户消息
        available_tools: 可用工具列表
        history_messages: 历史消息列表
        variables: 前端变量
        metadata: 额外元数据

    Returns:
        messages 数组
    """
    from core.context.injectors import (
        InjectionContext,
        create_default_orchestrator,
    )

    # 获取任务复杂度
    task_complexity = get_task_complexity(intent)

    # 构建 InjectionContext
    context = InjectionContext(
        user_id=user_id,
        user_query=user_query or user_message,
        prompt_cache=prompt_cache,
        task_complexity=(
            task_complexity.value if hasattr(task_complexity, "value") else task_complexity
        ),
        intent=intent,
        available_tools=available_tools or [],
        history_messages=history_messages or [],
        variables=variables or {},
        metadata=metadata or {},
    )

    # 创建编排器并执行（用户画像由 UserMemoryInjector 在 Phase 2 自行获取）
    orchestrator = create_default_orchestrator()
    messages = await orchestrator.build_messages(
        context=context, user_message=user_message or user_query
    )

    logger.info(
        f"✅ [Injector] Messages: "
        f"count={len(messages)}, "
        f"complexity={task_complexity.value if hasattr(task_complexity, 'value') else task_complexity}"
    )

    return messages

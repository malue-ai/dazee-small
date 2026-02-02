"""
SimpleAgent 上下文和 Prompt 构建模块

职责：
- 多层缓存 System Prompt 构建
- Mem0 用户画像检索
- Memory Guidance Prompt 追加
- 任务复杂度判断
"""

from typing import Dict, Any, List, Optional, TYPE_CHECKING
from logger import get_logger

if TYPE_CHECKING:
    from core.agent.types import IntentResult
    from core.context.runtime import RuntimeContext
    from core.context.compaction import ContextStrategy

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
    complexity_str = getattr(intent, 'complexity', 'medium')
    if complexity_str is None:
        complexity_str = 'medium'
    
    # 如果是枚举类型，获取其值
    if hasattr(complexity_str, 'value'):
        complexity_str = complexity_str.value
    
    # 映射到 TaskComplexity 枚举
    complexity_map = {
        'simple': TaskComplexity.SIMPLE,
        'low': TaskComplexity.SIMPLE,
        'medium': TaskComplexity.MEDIUM,
        'high': TaskComplexity.COMPLEX,
        'complex': TaskComplexity.COMPLEX,
    }
    
    return complexity_map.get(complexity_str.lower(), TaskComplexity.MEDIUM)


def fetch_user_profile(
    user_id: str,
    user_query: str,
    skip_memory: bool = False
) -> Optional[str]:
    """
    获取 Mem0 用户画像
    
    Args:
        user_id: 用户 ID
        user_query: 用户查询（用于语义检索）
        skip_memory: 是否跳过 Mem0 检索
        
    Returns:
        用户画像字符串，失败时返回 None
    """
    if skip_memory or not user_id or not user_query:
        return None
    
    try:
        from prompts.universal_agent_prompt import _fetch_user_profile
        user_profile = _fetch_user_profile(user_id, user_query)
        if user_profile:
            logger.debug(f"📝 Mem0 用户画像: {len(user_profile)} 字符")
        return user_profile
    except Exception as e:
        logger.warning(f"⚠️ Mem0 检索失败: {e}")
        return None


def build_cached_system_prompt(
    intent: Optional["IntentResult"],
    prompt_cache,
    context_strategy: "ContextStrategy",
    user_id: str = None,
    user_query: str = None
) -> List[Dict[str, Any]]:
    """
    构建多层缓存的系统提示词（用于 Claude Prompt Caching）
    
    缓存策略：
    - Layer 1: 框架规则（1h 缓存）
    - Layer 2: 实例提示词（1h 缓存）
    - Layer 3: Skills + 工具（1h 缓存）
    - Layer 4: Mem0 用户画像（不缓存）
    
    Args:
        intent: IntentResult 对象
        prompt_cache: InstancePromptCache 实例
        context_strategy: ContextStrategy 配置
        user_id: 用户 ID（用于 Mem0 检索）
        user_query: 用户查询（用于 Mem0 语义检索）
        
    Returns:
        List[Dict] - Claude API 的 system blocks 格式
    """
    from core.prompt import TaskComplexity
    
    # 获取任务复杂度
    task_complexity = get_task_complexity(intent)
    
    # 检查是否跳过 Mem0 检索
    skip_memory = getattr(intent, 'skip_memory_retrieval', False)
    
    # 获取 Mem0 用户画像
    user_profile = fetch_user_profile(user_id, user_query, skip_memory)
    
    # 优先使用 prompt_cache 的多层缓存构建方法
    if prompt_cache and prompt_cache.is_loaded and prompt_cache.system_prompt_simple:
        system_blocks = prompt_cache.get_cached_system_blocks(
            complexity=task_complexity,
            user_profile=user_profile
        )
        
        # 追加 Memory Guidance Prompt（L1 策略）
        if context_strategy.enable_memory_guidance:
            from core.context.compaction import get_memory_guidance_prompt
            system_blocks.append({
                "type": "text",
                "text": f"\n\n{get_memory_guidance_prompt()}"
                # 不添加 cache_control，每次都更新
            })
        
        logger.info(f"✅ 多层缓存 System Prompt: complexity={task_complexity.value}, "
                   f"layers={len(system_blocks)} (含 Context Awareness)")
        
        return system_blocks
    
    # Fallback: 使用框架默认 Prompt（单层缓存）
    from prompts.universal_agent_prompt import get_universal_agent_prompt
    from core.context.compaction import get_memory_guidance_prompt
    
    base_prompt = get_universal_agent_prompt(
        user_id=user_id,
        user_query=user_query,
        skip_memory_retrieval=skip_memory
    )
    
    # 追加 Memory Guidance Prompt（L1 策略）
    memory_guidance = get_memory_guidance_prompt()
    full_prompt = f"{base_prompt}\n\n{memory_guidance}"
    
    # 单层格式（向后兼容）
    system_blocks = [{
        "type": "text",
        "text": full_prompt
    }]
    
    logger.info(f"✅ System Prompt (fallback): {len(base_prompt)} 字符")
    
    return system_blocks


def build_system_prompt(
    intent: Optional["IntentResult"],
    prompt_cache,
    prompt_manager,
    context_strategy: "ContextStrategy",
    system_prompt: str = None,
    llm_enable_caching: bool = True,
    user_id: str = None,
    user_query: str = None,
    ctx: "RuntimeContext" = None
):
    """
    选择并构建 System Prompt
    
    优先级：
    1. prompt_cache 多层缓存（LLM 配置启用缓存时）
    2. prompt_cache 单层缓存（LLM 配置未启用缓存时）
    3. 用户自定义 system_prompt
    4. 框架默认 Prompt
    
    Args:
        intent: IntentResult 对象
        prompt_cache: InstancePromptCache 实例
        prompt_manager: PromptManager 实例
        context_strategy: ContextStrategy 配置
        system_prompt: 用户自定义的 System Prompt
        llm_enable_caching: LLM 是否启用缓存
        user_id: 用户 ID
        user_query: 用户查询
        ctx: RuntimeContext（用于 PromptManager）
        
    Returns:
        System Prompt（字符串或 List[Dict]）
    """
    task_complexity = get_task_complexity(intent)
    skip_memory = getattr(intent, 'skip_memory_retrieval', False)
    
    # 条件 1: 使用多层缓存
    use_multi_layer_cache = (
        prompt_cache and 
        prompt_cache.is_loaded and 
        prompt_cache.system_prompt_simple and
        llm_enable_caching  # LLM 配置启用了缓存
    )
    
    if use_multi_layer_cache:
        # 使用多层缓存格式
        result = build_cached_system_prompt(
            intent=intent,
            prompt_cache=prompt_cache,
            context_strategy=context_strategy,
            user_id=user_id,
            user_query=user_query
        )
        logger.info(f"✅ 多层缓存 System Prompt: complexity={task_complexity.value}, "
                   f"layers={len(result)}")
        return result
    
    # 条件 2: 单层缓存（向后兼容）
    if prompt_cache and prompt_cache.is_loaded and prompt_cache.system_prompt_simple:
        base_prompt = prompt_cache.get_full_system_prompt(task_complexity)
        result = prompt_manager.build_system_prompt(ctx, base_prompt=base_prompt)
        
        cached_size = len(prompt_cache.get_system_prompt(task_complexity))
        full_size = len(base_prompt)
        logger.info(f"✅ 单层缓存路由: complexity={task_complexity.value}, "
                   f"缓存={cached_size}字符 + 运行时={full_size - cached_size}字符 = {full_size}字符")
        return result
    
    # 条件 3: 用户自定义 System Prompt
    if system_prompt:
        enhanced_prompt = system_prompt
        
        # 追加 Memory Guidance Prompt（L1 策略）
        if context_strategy.enable_memory_guidance:
            from core.context.compaction import get_memory_guidance_prompt
            memory_guidance = get_memory_guidance_prompt()
            enhanced_prompt = f"{system_prompt}\n\n{memory_guidance}"
        
        result = prompt_manager.build_system_prompt(ctx, base_prompt=enhanced_prompt)
        logger.info(f"✅ 使用用户定义的 System Prompt + PromptManager 追加 "
                   f"({len(system_prompt)}字符, L1={context_strategy.enable_memory_guidance})")
        return result
    
    # 条件 4: 框架默认 Prompt
    from prompts.universal_agent_prompt import get_universal_agent_prompt
    base_prompt = get_universal_agent_prompt(
        conversation_id=None,
        user_id=user_id,
        user_query=user_query,
        skip_memory_retrieval=skip_memory
    )
    result = prompt_manager.build_system_prompt(ctx, base_prompt=base_prompt)
    
    if skip_memory:
        logger.info("✅ 使用框架默认 System Prompt + PromptManager（跳过 Mem0 检索）")
    else:
        logger.info("✅ 使用框架默认 System Prompt + PromptManager（已检索 Mem0 画像）")
    
    return result

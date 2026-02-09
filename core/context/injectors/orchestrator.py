"""
注入编排器

职责：
1. 管理所有 Injector 的注册和执行
2. 按 Phase 和优先级排序执行
3. 构建完整的 messages 数组
4. 构建带缓存元数据的 system blocks

架构设计：
InjectionOrchestrator 是 Injector 系统的核心，负责：
- 注册和管理 Injector 实例
- 按 Phase 分组执行 Injector
- 组装最终的 messages 和 system blocks
- 处理缓存策略标记

使用示例：
```python
orchestrator = InjectionOrchestrator()

# 注册 Injector
orchestrator.register(SystemRoleInjector())
orchestrator.register(ToolSystemRoleProvider())
orchestrator.register(UserMemoryInjector())

# 构建 messages
messages = await orchestrator.build_messages(context)

# 构建 system blocks（用于 Claude Prompt Caching）
system_blocks = await orchestrator.build_system_blocks(context)
```
"""

import asyncio
import json
from typing import Any, Dict, List, Optional, Type

from logger import get_logger

from .base import BaseInjector, CacheStrategy, InjectionPhase, InjectionResult
from .context import InjectionContext

logger = get_logger("injectors.orchestrator")


class InjectionOrchestrator:
    """
    注入编排器

    管理所有 Injector 的执行，构建完整的消息结构

    消息结构：
    - messages[0]: system message (Phase 1)
    - messages[1]: user context (Phase 2, systemInjection: true)
    - messages[2...n-1]: 对话历史
    - messages[n]: 最后一条用户消息 + Phase 3 追加
    """

    def __init__(self) -> None:
        """初始化编排器"""
        # Injector 注册表，按 Phase 分组
        self._injectors: Dict[InjectionPhase, List[BaseInjector]] = {
            InjectionPhase.SYSTEM: [],
            InjectionPhase.USER_CONTEXT: [],
            InjectionPhase.RUNTIME: [],
        }

        # 是否已排序
        self._sorted = False

    def register(self, injector: BaseInjector) -> "InjectionOrchestrator":
        """
        注册 Injector

        Args:
            injector: Injector 实例

        Returns:
            self（支持链式调用）
        """
        phase = injector.phase
        self._injectors[phase].append(injector)
        self._sorted = False
        logger.debug(f"注册 Injector: {injector}")
        return self

    def register_many(self, injectors: List[BaseInjector]) -> "InjectionOrchestrator":
        """
        批量注册 Injector

        Args:
            injectors: Injector 列表

        Returns:
            self（支持链式调用）
        """
        for injector in injectors:
            self.register(injector)
        return self

    def _ensure_sorted(self) -> None:
        """确保 Injector 按优先级排序"""
        if self._sorted:
            return

        for phase in InjectionPhase:
            self._injectors[phase].sort(key=lambda i: -i.priority)

        self._sorted = True

    def get_injectors(self, phase: InjectionPhase) -> List[BaseInjector]:
        """
        获取指定阶段的 Injector 列表（按优先级排序）

        Args:
            phase: 注入阶段

        Returns:
            Injector 列表
        """
        self._ensure_sorted()
        return self._injectors[phase]

    async def _execute_phase(
        self, phase: InjectionPhase, context: InjectionContext
    ) -> List[InjectionResult]:
        """
        执行指定阶段的所有 Injector

        Args:
            phase: 注入阶段
            context: 注入上下文

        Returns:
            InjectionResult 列表（按优先级排序）
        """
        self._ensure_sorted()
        injectors = self._injectors[phase]
        results = []

        for injector in injectors:
            try:
                # 检查是否应该注入
                if not await injector.should_inject(context):
                    logger.debug(f"跳过 Injector: {injector.name} (should_inject=False)")
                    continue

                # 执行注入
                result = await injector.inject(context)

                if result and not result.is_empty:
                    # 添加元数据
                    result.metadata["injector"] = injector.name
                    result.metadata["phase"] = phase.name
                    result.metadata["cache_strategy"] = injector.cache_strategy.name
                    result.metadata["priority"] = injector.priority

                    results.append(result)
                    logger.debug(
                        f"Injector {injector.name} 输出: "
                        f"{len(result.content)} 字符, "
                        f"tag={result.xml_tag}"
                    )
                else:
                    logger.debug(f"Injector {injector.name} 输出为空，跳过")

            except Exception as e:
                logger.error(f"Injector {injector.name} 执行失败: {e}", exc_info=True)
                # 继续执行其他 Injector，不中断

        return results

    async def build_system_blocks(self, context: InjectionContext) -> List[Dict[str, Any]]:
        """
        构建 system blocks（用于 Claude Prompt Caching）

        执行 Phase 1 Injector，构建带 _cache_layer 元数据的 blocks

        缓存层级映射：
        - CacheStrategy.STABLE → _cache_layer = 1, 2, 3（按顺序）
        - CacheStrategy.SESSION → _cache_layer = 最后一个稳定层 + 1
        - CacheStrategy.DYNAMIC → _cache_layer = 0（不缓存）

        Args:
            context: 注入上下文

        Returns:
            system blocks 列表，带 _cache_layer 元数据
        """
        results = await self._execute_phase(InjectionPhase.SYSTEM, context)

        if not results:
            logger.warning("Phase 1 没有任何输出，返回空 blocks")
            return []

        # 构建 blocks 并分配缓存层级
        blocks = []
        stable_layer = 0  # 当前稳定层级

        for result in results:
            cache_strategy = result.metadata.get("cache_strategy", "DYNAMIC")

            # 根据缓存策略分配层级
            if cache_strategy == "STABLE":
                stable_layer += 1
                cache_layer = stable_layer
            elif cache_strategy == "SESSION":
                # SESSION 使用下一个层级
                cache_layer = stable_layer + 1
            else:
                # DYNAMIC 不缓存
                cache_layer = 0

            block = {
                "type": "text",
                "text": result.to_text(),
                "_cache_layer": cache_layer,
            }

            blocks.append(block)

            injector_name = result.metadata.get("injector", "unknown")
            logger.debug(
                f"System block: {injector_name}, "
                f"cache_layer={cache_layer}, "
                f"{len(result.content)} 字符"
            )

        logger.info(f"构建 system blocks: {len(blocks)} 块, " f"稳定层数: {stable_layer}")

        return blocks

    async def build_user_context_content(self, context: InjectionContext) -> Optional[str]:
        """
        构建 user context 内容（Phase 2）

        执行 Phase 2 Injector，组装为单个字符串

        Args:
            context: 注入上下文

        Returns:
            组装后的内容，如果为空则返回 None
        """
        results = await self._execute_phase(InjectionPhase.USER_CONTEXT, context)

        if not results:
            return None

        # 组装内容
        parts = [r.to_text() for r in results if not r.is_empty]

        if not parts:
            return None

        content = "\n\n".join(parts)
        logger.info(f"构建 user context: {len(content)} 字符, {len(parts)} 部分")

        return content

    async def build_runtime_content(self, context: InjectionContext) -> Optional[str]:
        """
        构建运行时追加内容（Phase 3）

        执行 Phase 3 Injector，组装为单个字符串

        Args:
            context: 注入上下文

        Returns:
            组装后的内容，如果为空则返回 None
        """
        results = await self._execute_phase(InjectionPhase.RUNTIME, context)

        if not results:
            return None

        # 组装内容
        parts = [r.to_text() for r in results if not r.is_empty]

        if not parts:
            return None

        content = "\n\n".join(parts)
        logger.info(f"构建 runtime content: {len(content)} 字符, {len(parts)} 部分")

        return content

    async def build_messages(
        self, context: InjectionContext, user_message: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        构建完整的 messages 数组

        消息结构：
        - messages[0]: system message (Phase 1) - 注意：可能不需要，取决于 LLM 调用方式
        - messages[1]: user context (Phase 2, systemInjection: true)
        - messages[2...n-1]: 对话历史
        - messages[n]: 最后一条用户消息 + Phase 3 追加

        工具结果压缩策略（V10.0 统一方案）：
        - 工具执行后立即压缩，入库时已是压缩格式，这里直接使用

        Args:
            context: 注入上下文
            user_message: 当前用户消息（如果为空，使用 context.user_query）

        Returns:
            messages 数组
        """
        messages = []
        current_user_message = user_message or context.user_query or ""

        # Phase 2: User Context (如果有内容)
        user_context = await self.build_user_context_content(context)
        if user_context:
            messages.append(
                {"role": "user", "content": user_context, "metadata": {"systemInjection": True}}
            )

        # 添加历史消息（工具结果在入库时已压缩）
        if context.has_history:
            messages.extend(context.history_messages)

        # Phase 3: 追加到最后一条用户消息
        runtime_content = await self.build_runtime_content(context)

        # 构建最终用户消息
        if runtime_content and current_user_message:
            final_user_content = f"{current_user_message}\n\n---\n\n{runtime_content}"
        elif runtime_content:
            final_user_content = runtime_content
        else:
            final_user_content = current_user_message

        if final_user_content:
            messages.append({"role": "user", "content": final_user_content})

        logger.info(f"构建 messages: {len(messages)} 条消息")

        return messages

    def clear(self) -> None:
        """清空所有注册的 Injector"""
        for phase in InjectionPhase:
            self._injectors[phase].clear()
        self._sorted = False
        logger.debug("清空所有 Injector")

    def __repr__(self) -> str:
        counts = {phase.name: len(self._injectors[phase]) for phase in InjectionPhase}
        return f"InjectionOrchestrator(injectors={counts})"


# 默认编排器实例（单例模式）
_default_orchestrator: Optional[InjectionOrchestrator] = None


def get_orchestrator() -> InjectionOrchestrator:
    """
    获取默认编排器实例

    Returns:
        InjectionOrchestrator 实例
    """
    global _default_orchestrator
    if _default_orchestrator is None:
        _default_orchestrator = InjectionOrchestrator()
    return _default_orchestrator


def reset_orchestrator() -> None:
    """重置默认编排器"""
    global _default_orchestrator
    if _default_orchestrator:
        _default_orchestrator.clear()
    _default_orchestrator = None

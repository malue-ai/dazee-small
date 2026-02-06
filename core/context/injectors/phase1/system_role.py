"""
SystemRoleInjector - 系统角色注入器

职责：
1. 从 InstancePromptCache 获取角色定义
2. 根据任务复杂度选择对应版本（simple/medium/complex）
3. 追加框架规则和环境信息

缓存策略：STABLE（1h 缓存）
注入位置：Phase 1 - System Message
优先级：100（最高，放在最前面）
"""

from typing import TYPE_CHECKING

from logger import get_logger

from ..base import BaseInjector, CacheStrategy, InjectionPhase, InjectionResult
from ..context import InjectionContext

if TYPE_CHECKING:
    from core.prompt.instance_cache import InstancePromptCache

logger = get_logger("injectors.phase1.system_role")


class SystemRoleInjector(BaseInjector):
    """
    系统角色注入器

    从 InstancePromptCache 获取系统角色定义，根据任务复杂度选择对应版本。

    输出示例：
    ```
    你是一个专业的编程助手，能够帮助用户完成各种编程任务...

    # 框架能力协议
    ...

    # 运行环境
    ...
    ```
    """

    @property
    def name(self) -> str:
        return "system_role"

    @property
    def phase(self) -> InjectionPhase:
        return InjectionPhase.SYSTEM

    @property
    def cache_strategy(self) -> CacheStrategy:
        return CacheStrategy.STABLE

    @property
    def priority(self) -> int:
        # 最高优先级，放在 system message 最前面
        return 100

    async def inject(self, context: InjectionContext) -> InjectionResult:
        """
        注入系统角色定义

        优先级：
        1. 从 prompt_cache 获取对应复杂度的版本
        2. 追加框架规则（如果有）
        3. 追加环境信息（如果有）
        """
        parts = []

        # 1. 从 prompt_cache 获取角色定义
        role_prompt = await self._get_role_prompt(context)
        if role_prompt:
            parts.append(role_prompt)

        # 2. 追加框架规则
        framework_prompt = await self._get_framework_prompt(context)
        if framework_prompt:
            parts.append(f"# 框架能力协议\n\n{framework_prompt}")

        # 3. 追加环境信息
        environment_prompt = await self._get_environment_prompt(context)
        if environment_prompt:
            parts.append(f"# 运行环境\n\n{environment_prompt}")

        if not parts:
            logger.warning("SystemRoleInjector: 无内容可注入")
            return InjectionResult()

        content = "\n\n".join(parts)
        logger.info(f"SystemRoleInjector: {len(content)} 字符")

        return InjectionResult(content=content)

    async def _get_role_prompt(self, context: InjectionContext) -> str:
        """
        从 prompt_cache 获取角色定义

        根据 task_complexity 选择对应版本
        """
        if not context.has_prompt_cache:
            logger.debug("无 prompt_cache，跳过角色定义")
            return ""

        prompt_cache = context.prompt_cache
        complexity = context.task_complexity or "medium"

        # 导入 TaskComplexity 枚举
        from core.prompt.prompt_layer import TaskComplexity

        # 转换字符串为枚举
        complexity_enum = {
            "simple": TaskComplexity.SIMPLE,
            "medium": TaskComplexity.MEDIUM,
            "complex": TaskComplexity.COMPLEX,
        }.get(complexity, TaskComplexity.MEDIUM)

        # 获取对应版本的提示词
        role_prompt = prompt_cache.get_system_prompt(complexity_enum)

        logger.debug(f"获取角色定义: complexity={complexity}, {len(role_prompt)} 字符")

        return role_prompt

    async def _get_framework_prompt(self, context: InjectionContext) -> str:
        """
        从 prompt_cache.runtime_context 获取框架规则
        """
        if not context.has_prompt_cache:
            return ""

        prompt_cache = context.prompt_cache

        if not prompt_cache.runtime_context:
            return ""

        return prompt_cache.runtime_context.get("framework_prompt", "")

    async def _get_environment_prompt(self, context: InjectionContext) -> str:
        """
        从 prompt_cache.runtime_context 获取环境信息
        """
        if not context.has_prompt_cache:
            return ""

        prompt_cache = context.prompt_cache

        if not prompt_cache.runtime_context:
            return ""

        return prompt_cache.runtime_context.get("environment_prompt", "")

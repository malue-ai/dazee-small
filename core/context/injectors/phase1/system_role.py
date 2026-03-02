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
        4. 追加用户个性化配置（如果有）
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

        根据 task_complexity 选择对应版本。
        当任务涉及桌面操作时追加桌面操作协议（prompt_desktop.md）。
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

        # 桌面操作协议注入：当涉及 UI 自动化时（不再仅限 complex）
        if self._needs_desktop_protocol(context, complexity):
            desktop_protocol = self._load_desktop_protocol(prompt_cache)
            if desktop_protocol:
                role_prompt = f"{role_prompt}\n\n{desktop_protocol}"
                logger.debug(f"追加桌面操作协议: {len(desktop_protocol)} 字符")

        logger.debug(f"获取角色定义: complexity={complexity}, {len(role_prompt)} 字符")

        return role_prompt

    _DESKTOP_SKILL_GROUPS = {
        "app_automation",
        "feishu",
        "productivity",
        "screen_memory",
    }

    @staticmethod
    def _needs_desktop_protocol(context: InjectionContext, complexity: str) -> bool:
        """
        判断是否需要注入桌面操作协议。

        注入条件（满足任一）：
        1. complexity == complex（原有逻辑，兼容）
        2. intent.relevant_skill_groups 与 _DESKTOP_SKILL_GROUPS 有交集
           （飞书/邮件/日历等本地 app 操作都需要 peekaboo）
        """
        if complexity == "complex":
            return True

        if context.intent:
            skill_groups = set(
                getattr(context.intent, "relevant_skill_groups", None) or []
            )
            if skill_groups & SystemRoleInjector._DESKTOP_SKILL_GROUPS:
                return True

        return False

    @staticmethod
    def _load_desktop_protocol(prompt_cache) -> str:
        """
        加载桌面操作协议（prompt_desktop.md）

        当涉及桌面操作时注入（complex 或 app_automation skill group）。
        文件从实例目录加载，缓存在 runtime_context 中避免重复读取。
        """
        # 先检查 runtime_context 缓存
        if prompt_cache.runtime_context:
            cached = prompt_cache.runtime_context.get("_desktop_protocol_cache")
            if cached is not None:
                return cached

        # 从实例目录加载
        try:
            if prompt_cache._instance_path:
                from pathlib import Path

                desktop_path = Path(prompt_cache._instance_path) / "prompt_desktop.md"
                if desktop_path.exists():
                    content = desktop_path.read_text(encoding="utf-8")
                    # 缓存到 runtime_context
                    if prompt_cache.runtime_context is not None:
                        prompt_cache.runtime_context["_desktop_protocol_cache"] = content
                    return content
        except Exception as e:
            logger.debug(f"加载桌面操作协议失败: {e}")

        # 缓存空字符串避免重复尝试
        if prompt_cache.runtime_context is not None:
            prompt_cache.runtime_context["_desktop_protocol_cache"] = ""
        return ""

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

    # persona 和 user_prompt 已在启动时合并到实例提示词（Layer 2 STABLE 缓存）
    # 不再需要每次请求动态追加，见 instance_loader.create_agent_from_instance()

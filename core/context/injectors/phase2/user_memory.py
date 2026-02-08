"""
UserMemoryInjector - 用户记忆注入器

职责：
1. 从 Mem0 获取用户画像
2. 格式化为 XML 标签注入

缓存策略：SESSION（5min 缓存）
注入位置：Phase 2 - User Context Message
优先级：90（最高，用户信息最重要）
"""

from typing import Optional

from logger import get_logger

from ..base import BaseInjector, CacheStrategy, InjectionPhase, InjectionResult
from ..context import InjectionContext

logger = get_logger("injectors.phase2.user_memory")


class UserMemoryInjector(BaseInjector):
    """
    用户记忆注入器

    从 Mem0 获取用户画像，注入到 user context message。

    输出示例：
    ```
    <user_memory>
    - 用户偏好 Python 编程
    - 喜欢简洁的代码风格
    - 常用 FastAPI 框架
    - 使用 macOS 开发环境
    </user_memory>
    ```
    """

    @property
    def name(self) -> str:
        return "user_memory"

    @property
    def phase(self) -> InjectionPhase:
        return InjectionPhase.USER_CONTEXT

    @property
    def cache_strategy(self) -> CacheStrategy:
        # 用户画像相对稳定，会话级缓存
        return CacheStrategy.SESSION

    @property
    def priority(self) -> int:
        # 用户信息最重要，放在最前面
        return 90

    async def should_inject(self, context: InjectionContext) -> bool:
        """需要有用户 ID 才能获取记忆"""
        return bool(context.user_id)

    async def inject(self, context: InjectionContext) -> InjectionResult:
        """
        注入用户记忆

        1. 检查是否有预加载的用户画像
        2. 否则尝试从 Mem0 获取
        """
        # 1. 检查预加载的用户画像
        user_profile = context.get("user_profile")

        if user_profile:
            logger.debug(f"使用预加载的用户画像: {len(user_profile)} 字符")
        else:
            # 2. 尝试从 Mem0 获取
            user_profile = await self._fetch_from_mem0(context)

        if not user_profile:
            logger.debug("用户画像为空，跳过")
            return InjectionResult()

        logger.info(f"UserMemoryInjector: {len(user_profile)} 字符")

        return InjectionResult(content=user_profile, xml_tag="user_memory")

    async def _fetch_from_mem0(self, context: InjectionContext) -> Optional[str]:
        """
        从 Mem0 获取用户画像

        Uses core.agent.context.prompt_builder module.
        """
        if not context.user_id:
            return None

        try:
            from core.agent.context.prompt_builder import fetch_user_profile

            profile = fetch_user_profile(
                user_id=context.user_id, user_query=context.user_query or ""
            )

            return profile

        except ImportError:
            logger.debug("prompt_builder 模块不可用，跳过用户画像获取")
            return None
        except Exception as e:
            logger.warning(f"获取用户画像失败: {e}")
            return None

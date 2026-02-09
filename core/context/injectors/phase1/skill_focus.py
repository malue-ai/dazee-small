"""
SkillFocusHintInjector - 根据任务复杂度注入 Skill 聚焦提示

设计原则：
  1. 缓存优先：完整 Skills 列表保留在 cached Layer 3.5（不动），
     本 Injector 只在 DYNAMIC 层添加轻量聚焦提示
  2. 零额外 LLM 调用：基于 IntentResult.complexity 判断，O(1)
  3. 减轻认知负荷：58 个 Skills 对 LLM 来说太多，
     聚焦提示让模型优先关注最相关的几个

缓存策略：DYNAMIC（不缓存）
注入位置：Phase 1 - System Message
优先级：70（在工具定义之后、历史摘要之前）
"""

from typing import Any, Dict, List

from logger import get_logger

from ..base import BaseInjector, CacheStrategy, InjectionPhase, InjectionResult
from ..context import InjectionContext

logger = get_logger("injectors.phase1.skill_focus")


class SkillFocusHintInjector(BaseInjector):
    """
    根据任务复杂度注入 Skill 聚焦提示

    simple → 直接回答，无需读取 Skills
    medium → 保持默认行为
    complex → 提示桌面操作相关的 Skill 组合模式
    """

    @property
    def name(self) -> str:
        return "skill_focus_hint"

    @property
    def phase(self) -> InjectionPhase:
        return InjectionPhase.SYSTEM

    @property
    def cache_strategy(self) -> CacheStrategy:
        # DYNAMIC: 不缓存，因为每次请求的 complexity 可能不同
        return CacheStrategy.DYNAMIC

    @property
    def priority(self) -> int:
        # 在 ToolSystemRoleProvider (80) 之后
        return 70

    async def should_inject(self, context: InjectionContext) -> bool:
        """只在 simple 和 complex 时注入（medium 保持默认）"""
        complexity = context.task_complexity or "medium"
        return complexity in ("simple", "complex")

    async def inject(self, context: InjectionContext) -> InjectionResult:
        complexity = context.task_complexity or "medium"

        if complexity == "simple":
            hint = (
                "<skill_focus>\n"
                "这是一个简单查询，直接回答即可。\n"
                "无需读取 SKILL.md，除非用户明确要求使用某个功能。\n"
                "</skill_focus>"
            )
        elif complexity == "complex":
            hint = (
                "<skill_focus>\n"
                "这是一个复杂任务，可能需要多个 Skills 协同。\n"
                "桌面 UI 操作组合模式：\n"
                "- 观察：observe_screen → 获取界面元素和文字\n"
                "- 交互：nodes run peekaboo click/type/hotkey\n"
                "- 验证：observe_screen → 确认操作结果\n"
                "- 输入长文本：echo '内容' | pbcopy → peekaboo hotkey --keys cmd+v\n"
                "- 应用管理：peekaboo app --action launch/focus\n"
                "每一步操作后必须验证结果，确认成功再继续。\n"
                "</skill_focus>"
            )
        else:
            return InjectionResult()

        logger.debug(
            f"SkillFocusHintInjector: complexity={complexity}, hint={len(hint)} chars"
        )
        return InjectionResult(content=hint)

"""
Dazee 用户画像生成器

聚合碎片、行为、计划、情绪与显式记忆，生成综合用户画像
用于 Prompt 注入和个性化响应
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from logger import get_logger

from ..pool import get_mem0_pool
from ..schemas import (
    BehaviorPattern,
    EmotionState,
    FragmentMemory,
    MemoryCard,
    PlanSummary,
    ReminderSummary,
    UserPersona,
    WorkPlan,
)
from .analyzer import get_behavior_analyzer

logger = get_logger("dazee.persona_builder")


class PersonaBuilder:
    """
    用户画像生成器

    聚合多维记忆数据，生成综合用户画像
    """

    def __init__(self):
        """初始化画像生成器"""
        logger.info("[PersonaBuilder] 初始化完成")

    def _summarize_check_results(self, plan: WorkPlan, limit: int = 2) -> List[str]:
        """
        提取 Check 阶段摘要

        Args:
            plan: 工作计划
            limit: 最多返回条数

        Returns:
            Check 阶段摘要列表
        """
        summaries: List[str] = []
        if not plan.check_results:
            return summaries

        for item in plan.check_results[-limit:]:
            date_str = item.checked_at.strftime("%m月%d日") if item.checked_at else "未知时间"
            parts: List[str] = []
            if item.completion_rate is not None:
                parts.append(f"完成率 {int(item.completion_rate * 100)}%")
            if item.actual_result:
                parts.append(item.actual_result)
            if item.gaps:
                parts.append(f"问题: {item.gaps[0]}")
            if item.lessons_learned:
                parts.append(f"经验: {item.lessons_learned[0]}")
            summary = "，".join(parts) if parts else "检查完成"
            summaries.append(f"{date_str}: {summary}")

        return summaries

    def _summarize_act_actions(self, plan: WorkPlan, limit: int = 2) -> List[str]:
        """
        提取 Act 阶段行动摘要

        Args:
            plan: 工作计划
            limit: 最多返回条数

        Returns:
            Act 阶段行动摘要列表
        """
        summaries: List[str] = []
        if not plan.action_history:
            return summaries

        for item in plan.action_history[-limit:]:
            date_str = item.created_at.strftime("%m月%d日") if item.created_at else "未知时间"
            decision = item.decision or "行动"
            action_taken = item.action_taken or ""
            if action_taken:
                summaries.append(f"{date_str}: {decision} - {action_taken}")
            else:
                summaries.append(f"{date_str}: {decision}")

        return summaries

    async def build_persona(
        self,
        user_id: str,
        fragments: Optional[List[FragmentMemory]] = None,
        behavior: Optional[BehaviorPattern] = None,
        emotion: Optional[EmotionState] = None,
        plans: Optional[List[WorkPlan]] = None,
        explicit_memories: Optional[List[MemoryCard]] = None,
        force_rebuild: bool = False,
    ) -> UserPersona:
        """
        构建用户画像

        Args:
            user_id: 用户 ID
            fragments: 碎片记忆列表（可选，如果不提供则从 Mem0 检索）
            behavior: 行为模式（可选，如果不提供则重新分析）
            emotion: 情绪状态（可选）
            plans: 工作计划列表（可选）
            explicit_memories: 显式记忆卡片列表（可选，如果不提供则从 Mem0 检索）
            force_rebuild: 是否强制重建（忽略缓存）

        Returns:
            UserPersona 对象
        """
        # 获取显式记忆
        if explicit_memories is None:
            try:
                from core.memory import create_memory_manager

                manager = create_memory_manager(user_id=user_id)
                explicit_memories = manager.list_memory_cards(limit=50)
            except Exception as e:
                logger.warning(f"[PersonaBuilder] 获取显式记忆失败: {e}")
                explicit_memories = []

        # 构建画像
        persona = UserPersona(user_id=user_id, generated_at=datetime.now())

        # 1. 身份推断（从行为模式）
        if behavior:
            persona.inferred_role = behavior.inferred_role
            persona.role_confidence = behavior.role_confidence
            persona.last_behavior_analysis = behavior.updated_at

        # 2. 行为摘要
        if behavior:
            # 工作规律概述
            routine_parts = []
            if behavior.routine_tasks:
                routine_parts.append("常规任务：")
                for task in behavior.routine_tasks[:3]:
                    routine_parts.append(f"- {task.name}（{task.frequency}）")

            if behavior.time_pattern and behavior.time_pattern.work_start:
                routine_parts.append(
                    f"工作时间：{behavior.time_pattern.work_start} - "
                    f"{behavior.time_pattern.work_end or '未知'}"
                )

            persona.routine_overview = "\n".join(routine_parts) if routine_parts else ""

            # 工作风格
            if behavior.work_style:
                style_parts = []
                style_parts.append(f"工作风格：{behavior.work_style.work_style}")
                style_parts.append(f"沟通偏好：{behavior.work_style.communication_preference}")
                style_parts.append(f"响应格式：{behavior.work_style.response_format_preference}")
                persona.work_style = "，".join(style_parts)

            # 从偏好稳定性中提取稳定偏好
            if behavior.preference_stability:
                stable = behavior.preference_stability.stable_preferences
                if "response_format" in stable:
                    persona.response_format = stable["response_format"]
                if "communication_style" in stable:
                    persona.greeting_style = stable.get("communication_style", "professional")

        # 3. 当前状态
        if emotion:
            persona.mood = emotion.current_mood
            persona.stress_level = emotion.stress_level
            persona.support_flag = emotion.support_needed
            persona.last_emotion_analysis = emotion.last_updated

            # 从情绪趋势中提取关注点
            if emotion.trend and emotion.trend.main_stressors:
                persona.main_concerns = emotion.trend.main_stressors[:3]
        else:
            # 从碎片记忆中推断情绪
            if fragments:
                stressed_count = sum(
                    1
                    for f in fragments[-10:]
                    if f.emotion_hint and f.emotion_hint.stress_level > 0.6
                )
                if stressed_count > len(fragments[-10:]) * 0.3:
                    persona.mood = "slightly_stressed"
                    persona.stress_level = 0.6
                    persona.support_flag = True

        # 4. 活跃计划
        if plans:
            persona.active_plans = [
                PlanSummary(
                    title=plan.title,
                    deadline=plan.deadline,
                    progress=plan.progress,
                    status=plan.status,
                    blockers=plan.blockers[:2],  # 最多2个阻碍
                    check_results=self._summarize_check_results(plan),
                    act_actions=self._summarize_act_actions(plan),
                )
                for plan in plans
                if plan.status in ["active", "at_risk"]
            ][
                :3
            ]  # 最多3个计划

        # 5. 显式记忆注入
        if explicit_memories:
            # 从显式记忆中提取偏好和配置
            for card in explicit_memories[:10]:  # 最多处理10个
                if card.category == "preference":
                    # 提取偏好设置
                    if "response_format" in card.content.lower():
                        # 尝试从内容中提取格式偏好
                        pass  # 这里可以添加更复杂的解析逻辑

                # 将显式记忆的标签添加到 metadata
                if card.tags:
                    persona.metadata.setdefault("explicit_tags", []).extend(card.tags)

        # 6. 元数据
        persona.source_fragments = len(fragments) if fragments else 0

        # 7. 个性化配置（基于行为模式）
        if behavior and behavior.work_style:
            if behavior.work_style.response_format_preference == "structured":
                persona.response_format = "structured"
            elif behavior.work_style.response_format_preference == "detailed":
                persona.response_format = "detailed"
            else:
                persona.response_format = "concise"

        # 情绪支持标志
        if persona.stress_level > 0.7 or persona.support_flag:
            persona.emotional_support = True
            persona.proactive_level = "high"

        logger.info(
            f"[PersonaBuilder] 画像生成完成: user={user_id}, "
            f"role={persona.inferred_role}, mood={persona.mood}, "
            f"plans={len(persona.active_plans)}"
        )

        return persona

    async def build_persona_from_memory(
        self, user_id: str, analysis_days: int = 7, include_explicit: bool = True
    ) -> UserPersona:
        """
        从 Mem0 记忆库构建画像（便捷方法）

        Args:
            user_id: 用户 ID
            analysis_days: 分析最近多少天的记忆
            include_explicit: 是否包含显式记忆

        Returns:
            UserPersona 对象
        """
        # 1. 获取碎片记忆（从 Mem0 检索）
        pool = get_mem0_pool()
        memories = pool.get_all(user_id=user_id, limit=100)

        # 过滤时间范围
        cutoff = datetime.now() - timedelta(days=analysis_days)
        # 注意：Mem0 的记忆可能没有时间戳，这里简化处理
        fragments = []  # 这里应该从 Mem0 记忆转换为 FragmentMemory

        # 2. 分析行为模式
        if fragments:
            analyzer = get_behavior_analyzer()
            behavior = await analyzer.analyze(
                user_id=user_id, fragments=fragments, analysis_days=analysis_days
            )
        else:
            behavior = None

        # 3. 获取显式记忆
        explicit_memories = None
        if include_explicit:
            try:
                from core.memory import create_memory_manager

                manager = create_memory_manager(user_id=user_id)
                explicit_memories = manager.list_memory_cards(limit=50)
            except Exception as e:
                logger.warning(f"[PersonaBuilder] 获取显式记忆失败: {e}")

        # 4. 构建画像
        return await self.build_persona(
            user_id=user_id,
            fragments=fragments,
            behavior=behavior,
            explicit_memories=explicit_memories,
        )


# ==================== 工厂函数 ====================

_persona_builder_instance: Optional[PersonaBuilder] = None


def get_persona_builder() -> PersonaBuilder:
    """获取画像生成器单例"""
    global _persona_builder_instance
    if _persona_builder_instance is None:
        _persona_builder_instance = PersonaBuilder()
    return _persona_builder_instance


def reset_persona_builder() -> None:
    """重置画像生成器（用于测试）"""
    global _persona_builder_instance
    _persona_builder_instance = None

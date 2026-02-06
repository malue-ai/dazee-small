"""
Mem0 格式化模块

职责：
- 将 Mem0 搜索结果格式化为 System Prompt 片段
- 将 Dazee 用户画像格式化为 Prompt 注入
- 提供多种格式化模板
- 支持自定义格式化逻辑

设计原则：
- 格式化与存储分离
- 可读性优先
- 支持国际化

Dazee 增强:
- 支持 UserPersona 画像格式化
- 支持情绪状态和计划显示
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from logger import get_logger

if TYPE_CHECKING:
    from ..schemas import EmotionState, MemoryCard, UserPersona, WorkPlan

logger = get_logger("memory.mem0.formatter")


# ==================== 格式化模板 ====================

USER_PROFILE_HEADER_ZH = """# 用户画像（基于历史交互）

以下是与当前问题相关的用户信息，请据此提供个性化回答：
"""

USER_PROFILE_HEADER_EN = """# User Profile (Based on Historical Interactions)

The following user information is relevant to the current query. Please provide personalized responses accordingly:
"""

MEMORY_ITEM_TEMPLATE_ZH = "- {memory}"
MEMORY_ITEM_TEMPLATE_EN = "- {memory}"

NO_RELEVANT_MEMORIES_ZH = "(暂无相关用户记忆)"
NO_RELEVANT_MEMORIES_EN = "(No relevant user memories available)"


# ==================== 核心格式化函数 ====================


def format_memories_for_prompt(
    memories: List[Dict[str, Any]],
    language: str = "zh",
    max_memories: int = 10,
    include_metadata: bool = False,
    min_score: float = 0.0,
) -> Optional[str]:
    """
    将 Mem0 搜索结果格式化为 System Prompt 片段

    Args:
        memories: Mem0 搜索返回的记忆列表
            每个记忆包含：
            - id: 记忆 ID
            - memory: 记忆内容（核心字段）
            - score: 相关性分数
            - user_id: 用户 ID
            - created_at: 创建时间
            - metadata: 元数据
        language: 语言（"zh" 或 "en"）
        max_memories: 最大返回记忆数
        include_metadata: 是否包含元数据（时间、来源等）
        min_score: 最低相关性分数阈值

    Returns:
        格式化后的字符串，或 None（如果没有有效记忆）

    示例输出：
        # 用户画像（基于历史交互）

        以下是与当前问题相关的用户信息，请据此提供个性化回答：

        - 用户偏好使用 Python 进行开发
        - 用户是前端工程师，熟悉 React
        - 用户喜欢简洁的代码风格
    """
    if not memories:
        return None

    # 筛选有效记忆
    valid_memories = [m for m in memories if m.get("memory") and (m.get("score", 1.0) >= min_score)]

    if not valid_memories:
        return None

    # 限制数量
    valid_memories = valid_memories[:max_memories]

    # 选择模板
    if language == "zh":
        header = USER_PROFILE_HEADER_ZH
        item_template = MEMORY_ITEM_TEMPLATE_ZH
    else:
        header = USER_PROFILE_HEADER_EN
        item_template = MEMORY_ITEM_TEMPLATE_EN

    # 构建输出
    lines = [header]

    for mem in valid_memories:
        memory_text = mem.get("memory", "")

        if include_metadata:
            # 包含元数据
            score = mem.get("score", 0)
            created_at = mem.get("created_at", "")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    created_str = dt.strftime("%Y-%m-%d")
                except (ValueError, AttributeError) as e:
                    created_str = created_at[:10] if len(created_at) >= 10 else ""
                line = f"- {memory_text} (相关度: {score:.2f}, 来源: {created_str})"
            else:
                line = f"- {memory_text} (相关度: {score:.2f})"
        else:
            line = item_template.format(memory=memory_text)

        lines.append(line)

    result = "\n".join(lines)

    logger.debug(
        f"[Mem0Formatter] 格式化完成: "
        f"输入={len(memories)}, 有效={len(valid_memories)}, 语言={language}"
    )

    return result


def format_memories_as_context(memories: List[Dict[str, Any]], max_memories: int = 5) -> str:
    """
    将记忆格式化为简洁的上下文字符串（用于非 Prompt 场景）

    Args:
        memories: 记忆列表
        max_memories: 最大数量

    Returns:
        简洁的上下文字符串
    """
    if not memories:
        return ""

    valid_memories = [m for m in memories if m.get("memory")][:max_memories]

    if not valid_memories:
        return ""

    return " | ".join([m["memory"] for m in valid_memories])


def format_single_memory(memory: Dict[str, Any], include_score: bool = True) -> str:
    """
    格式化单条记忆

    Args:
        memory: 单条记忆
        include_score: 是否包含分数

    Returns:
        格式化的字符串
    """
    text = memory.get("memory", "")
    if not text:
        return ""

    if include_score:
        score = memory.get("score", 0)
        return f"{text} (score: {score:.2f})"

    return text


# ==================== 高级格式化函数 ====================


def format_memories_by_category(
    memories: List[Dict[str, Any]], categories: Optional[Dict[str, List[str]]] = None
) -> str:
    """
    格式化记忆列表（按时间倒序）

    🔑 设计原则：不使用关键词匹配分类，直接呈现记忆让 LLM 理解语义

    Args:
        memories: 记忆列表
        categories: （已废弃，保留参数兼容性）

    Returns:
        格式化的记忆字符串
    """
    if not memories:
        return ""

    # 按时间或重要性排序（如果有这些字段）
    sorted_memories = sorted(
        memories, key=lambda m: m.get("created_at", "") or m.get("timestamp", ""), reverse=True
    )

    # 构建输出：简单列表，不做分类
    lines = ["# 用户相关记忆\n"]

    # 最多显示 15 条最新记忆
    for mem in sorted_memories[:15]:
        text = mem.get("memory", "")
        if text:
            lines.append(f"- {text}")

    lines.append("")

    return "\n".join(lines)


def create_user_profile_section(
    memories: List[Dict[str, Any]], user_query: str = "", style: str = "concise"
) -> Optional[str]:
    """
    创建用户画像 Section（用于 System Prompt 注入）

    Args:
        memories: 相关记忆列表
        user_query: 用户当前问题（可选，用于上下文）
        style: 风格 ("concise" 简洁, "detailed" 详细, "structured" 结构化)

    Returns:
        格式化的用户画像 Section
    """
    if not memories:
        return None

    if style == "concise":
        return format_memories_for_prompt(
            memories, language="zh", max_memories=5, include_metadata=False
        )

    elif style == "detailed":
        return format_memories_for_prompt(
            memories, language="zh", max_memories=10, include_metadata=True
        )

    elif style == "structured":
        return format_memories_by_category(memories)

    else:
        return format_memories_for_prompt(memories)


# ==================== Dazee 画像格式化 ====================

DAZEE_PERSONA_HEADER = """## Dazee 用户洞察
"""

ROLE_NAMES = {
    "product_manager": "产品经理",
    "developer": "开发工程师",
    "sales": "销售",
    "operations": "运营",
    "designer": "设计师",
    "analyst": "分析师",
    "unknown": "未知",
}

MOOD_NAMES = {
    "neutral": "平和",
    "positive": "积极",
    "slightly_stressed": "略有压力",
    "stressed": "压力较大",
    "frustrated": "沮丧",
    "fatigue": "疲惫",
}


def format_dazee_persona_for_prompt(
    persona: "UserPersona",
    include_plans: bool = True,
    include_emotion: bool = True,
    include_reminders: bool = True,
    include_explicit_memories: bool = True,
    max_plans: int = 2,
    max_explicit: int = 3,
    max_tokens: Optional[int] = None,
) -> str:
    """
    将 Dazee UserPersona 格式化为 Prompt 注入文本

    Args:
        persona: UserPersona 对象
        include_plans: 是否包含活跃计划
        include_emotion: 是否包含情绪状态
        include_reminders: 是否包含待提醒事项
        include_explicit_memories: 是否包含显式记忆（新增）
        max_plans: 最多显示几个计划
        max_explicit: 最多显示几个显式记忆（新增）
        max_tokens: Token 上限（新增，超过则裁剪内容）

    Returns:
        格式化的 Prompt 文本

    示例输出:
        ## Dazee 用户洞察

        **身份**: 产品经理（置信度: 82%）

        **工作规律**:
        - 早上通常处理客户反馈
        - 下午有常规会议

        **当前状态**:
        - 情绪: 略有压力（连续3天提到"催"）
        - 关注: 需求变更频繁

        **活跃计划**:
        - Q1 汇报 PPT（⚠️ 周三到期，进度 25%）
          - 阻碍: 缺少销售部门数据
    """
    sections = [DAZEE_PERSONA_HEADER]

    # 身份信息
    if persona.inferred_role != "unknown":
        role_name = ROLE_NAMES.get(persona.inferred_role, persona.inferred_role)
        confidence_pct = int(persona.role_confidence * 100)
        sections.append(f"**身份**: {role_name}（置信度: {confidence_pct}%）\n")

    # 工作规律
    if persona.routine_overview:
        sections.append("**工作规律**:")
        for line in persona.routine_overview.split("\n"):
            if line.strip():
                sections.append(f"- {line.strip()}")
        sections.append("")

    # 当前状态（情绪 + 关注点）
    if include_emotion:
        state_lines = []
        if persona.mood != "neutral":
            mood_name = MOOD_NAMES.get(persona.mood, persona.mood)
            state_lines.append(f"- 情绪: {mood_name}")
        if persona.main_concerns:
            concerns = ", ".join(persona.main_concerns[:2])
            state_lines.append(f"- 关注: {concerns}")
        if state_lines:
            sections.append("**当前状态**:")
            sections.extend(state_lines)
            sections.append("")

    # 活跃计划
    if include_plans and persona.active_plans:
        sections.append("**活跃计划**:")
        for plan in persona.active_plans[:max_plans]:
            # 状态 emoji
            status_emoji = (
                "⚠️" if plan.status == "at_risk" else "🔄" if plan.status == "active" else "✅"
            )
            # 截止时间
            if plan.deadline:
                deadline_str = plan.deadline.strftime("%m月%d日")
            else:
                deadline_str = "无截止"
            # 进度
            progress_pct = int(plan.progress * 100)
            sections.append(
                f"- {plan.title}（{status_emoji} {deadline_str}，进度 {progress_pct}%）"
            )
            # 阻碍
            if plan.blockers:
                sections.append(f"  - 阻碍: {plan.blockers[0]}")
            if plan.check_results:
                sections.append(f"  - 检查: {plan.check_results[0]}")
            if plan.act_actions:
                sections.append(f"  - 行动: {plan.act_actions[0]}")
        sections.append("")

    # 待提醒
    if include_reminders and persona.upcoming_reminders:
        sections.append("**待提醒**:")
        for reminder in persona.upcoming_reminders[:2]:
            time_str = reminder.time.strftime("%m月%d日 %H:%M")
            sections.append(f"- [{time_str}] {reminder.content}")
        sections.append("")

    # 显式记忆（新增）
    if include_explicit_memories and persona.metadata.get("explicit_memories"):
        explicit_cards = persona.metadata.get("explicit_memories", [])
        if explicit_cards:
            sections.append("**用户记忆卡片**:")
            for card in explicit_cards[:max_explicit]:
                if card.get("title"):
                    sections.append(f"- {card['title']}: {card.get('content', '')[:50]}...")
                else:
                    sections.append(f"- {card.get('content', '')[:60]}...")
            sections.append("")

    # 注意事项
    notes = []
    if persona.response_format == "structured":
        notes.append("响应格式: 结构化 + 摘要优先")
    if persona.emotional_support and persona.support_flag:
        notes.append("用户近期压力较大，适时关怀")
    if notes:
        sections.append("**注意事项**:")
        for note in notes:
            sections.append(f"- {note}")
        sections.append("")

    result = "\n".join(sections)

    # Token 限制检查（使用 tiktoken）
    if max_tokens:
        from core.llm.base import count_tokens

        current_tokens = count_tokens(result)
        if current_tokens > max_tokens:
            # 估算裁剪位置（保守估计：每个 token 约 2 字符）
            # 迭代裁剪以确保不超过 max_tokens
            target_chars = int(len(result) * max_tokens / current_tokens * 0.95)
            result = result[:target_chars] + "\n...（内容已裁剪）"
            logger.warning(
                f"[Formatter] 画像内容超过 Token 限制: {current_tokens} > {max_tokens}, "
                f"已裁剪到约 {count_tokens(result)} tokens"
            )

    return result


def format_plan_summary(plans: List["WorkPlan"], max_plans: int = 3) -> Optional[str]:
    """
    格式化计划摘要

    Args:
        plans: 计划列表
        max_plans: 最多显示几个

    Returns:
        格式化的摘要，或 None
    """
    if not plans:
        return None

    lines = ["**待办计划**:"]

    for plan in plans[:max_plans]:
        # 状态判断
        if plan.blockers:
            status = "🚧 有阻碍"
        elif plan.deadline:
            from datetime import datetime

            days_left = (plan.deadline - datetime.now()).days
            if days_left < 0:
                status = "❌ 已过期"
            elif days_left <= 1:
                status = "⚠️ 即将到期"
            elif days_left <= 3:
                status = "📅 临近"
            else:
                status = "🔄 进行中"
        else:
            status = "🔄 进行中"

        progress_pct = int(plan.progress * 100)
        lines.append(f"- {plan.title}（{status}，{progress_pct}%）")

    return "\n".join(lines)


def format_emotion_summary(emotion: "EmotionState") -> Optional[str]:
    """
    格式化情绪摘要

    Args:
        emotion: 情绪状态

    Returns:
        格式化的摘要，或 None
    """
    if emotion.current_mood == "neutral" and emotion.stress_level < 0.3:
        return None

    mood_name = MOOD_NAMES.get(emotion.current_mood, emotion.current_mood)
    stress_pct = int(emotion.stress_level * 100)

    lines = [f"**情绪状态**: {mood_name}（压力指数: {stress_pct}%）"]

    if emotion.trend and emotion.trend.main_stressors:
        stressors = ", ".join(emotion.trend.main_stressors[:2])
        lines.append(f"- 主要压力源: {stressors}")

    if emotion.support_needed:
        lines.append("- 💙 建议适时关怀")

    return "\n".join(lines)


def create_dazee_prompt_section(
    persona: Optional["UserPersona"] = None,
    memories: Optional[List[Dict[str, Any]]] = None,
    plans: Optional[List["WorkPlan"]] = None,
    emotion: Optional["EmotionState"] = None,
    explicit_memories: Optional[List["MemoryCard"]] = None,
    max_tokens: Optional[int] = None,
) -> Optional[str]:
    """
    创建完整的 Dazee Prompt 注入 Section

    优先使用 UserPersona，如果没有则回退到传统 memories 格式

    Args:
        persona: UserPersona 画像（推荐）
        memories: 传统 Mem0 记忆列表（回退）
        plans: 计划列表（可选增强）
        emotion: 情绪状态（可选增强）
        explicit_memories: 显式记忆卡片列表（新增）
        max_tokens: Token 上限（新增）

    Returns:
        格式化的 Prompt Section
    """
    # 优先使用 Persona
    if persona:
        # 如果有显式记忆，添加到 persona 的 metadata 中
        if explicit_memories:
            persona.metadata["explicit_memories"] = [card.to_dict() for card in explicit_memories]
        return format_dazee_persona_for_prompt(
            persona,
            include_explicit_memories=True,
            max_tokens=max_tokens or persona.max_prompt_tokens,
        )

    # 回退到传统格式
    sections = []

    # 传统记忆
    if memories:
        mem_section = format_memories_for_prompt(memories, language="zh", max_memories=5)
        if mem_section:
            sections.append(mem_section)

    # 计划摘要
    if plans:
        plan_section = format_plan_summary(plans)
        if plan_section:
            sections.append(plan_section)

    # 情绪摘要
    if emotion:
        emotion_section = format_emotion_summary(emotion)
        if emotion_section:
            sections.append(emotion_section)

    if not sections:
        return None

    return "\n\n".join(sections)

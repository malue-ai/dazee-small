"""
意图识别提示词生成器 - IntentPromptGenerator

V12.0: 适配桌面端意图识别提示词

设计原则：
1. 直接使用 V12.0 桌面端提示词
2. 支持自定义规则追加
3. 一次性生成，运行时直接使用

生成的提示词用于 IntentAnalyzer:
- complexity: 复杂度等级 (simple/medium/complex)
- skip_memory: 是否跳过记忆检索
- is_follow_up: 是否为追问
- wants_to_stop: 用户是否希望停止/取消
- relevant_skill_groups: 需要哪些技能分组
"""

# 1. 标准库
from typing import Any, Dict, List, Optional

# 3. 本地模块
from logger import get_logger
from prompts.intent_recognition_prompt import (
    INTENT_RECOGNITION_PROMPT,
    get_intent_recognition_prompt,
)

# 2. 第三方库（无）


logger = get_logger("intent_prompt_generator")


class IntentPromptGenerator:
    """
    意图识别提示词生成器

    V12.0 版本：使用桌面端提示词，支持自定义规则追加

    使用方式：
    ```python
    # 从 PromptSchema 生成（如果有自定义规则则追加）
    intent_prompt = IntentPromptGenerator.generate(prompt_schema)

    # 获取默认提示词
    intent_prompt = IntentPromptGenerator.get_default()
    ```
    """

    @classmethod
    def generate(cls, schema) -> str:
        """
        根据 PromptSchema 生成意图识别提示词

        V12.0：使用桌面端基础提示词，支持追加自定义规则

        Args:
            schema: PromptSchema 对象

        Returns:
            意图识别提示词
        """
        # 提取自定义规则（如果有）
        custom_rules = cls._extract_custom_rules(schema)

        if custom_rules:
            logger.info(f"   追加自定义意图规则: {len(custom_rules)} 字符")
            return get_intent_recognition_prompt(custom_rules)

        return INTENT_RECOGNITION_PROMPT

    @classmethod
    def _extract_custom_rules(cls, schema) -> Optional[str]:
        """
        从 schema 提取自定义意图规则

        支持：
        - intent_types: 自定义意图类型
        - complexity_keywords: 自定义复杂度关键词

        Returns:
            自定义规则字符串，无则返回 None
        """
        if not schema:
            return None

        rules_parts = []

        # 1. 提取自定义意图类型
        if hasattr(schema, "intent_types") and schema.intent_types:
            intent_rules = cls._format_custom_intent_types(schema.intent_types)
            if intent_rules:
                rules_parts.append(intent_rules)

        # 2. 提取自定义复杂度关键词
        if hasattr(schema, "complexity_keywords") and schema.complexity_keywords:
            complexity_rules = cls._format_custom_complexity(schema.complexity_keywords)
            if complexity_rules:
                rules_parts.append(complexity_rules)

        if rules_parts:
            return "\n\n## 自定义规则\n\n" + "\n\n".join(rules_parts)

        return None

    @classmethod
    def _format_custom_intent_types(cls, intent_types: List[Dict[str, Any]]) -> Optional[str]:
        """格式化自定义意图类型为提示词片段"""
        if not intent_types:
            return None

        lines = ["### 特定意图类型"]

        for intent in intent_types:
            name = intent.get("name", "unknown")
            keywords = intent.get("keywords", [])
            examples = intent.get("examples", keywords[:3])

            if keywords:
                lines.append(f"- **{name}**: {', '.join(keywords[:5])}")
                if examples:
                    lines.append(f"  - 例: {', '.join(examples[:3])}")

        return "\n".join(lines) if len(lines) > 1 else None

    @classmethod
    def _format_custom_complexity(cls, complexity_keywords: Dict[str, List[str]]) -> Optional[str]:
        """格式化自定义复杂度关键词"""
        if not complexity_keywords:
            return None

        has_custom = any(keywords for keywords in complexity_keywords.values())
        if not has_custom:
            return None

        lines = ["### 复杂度补充规则"]

        for level, keywords in complexity_keywords.items():
            if keywords:
                level_name = level.value if hasattr(level, "value") else str(level)
                lines.append(f"- **{level_name}**: {', '.join(keywords[:5])}")

        return "\n".join(lines) if len(lines) > 1 else None

    @classmethod
    def get_default(cls) -> str:
        """
        获取默认意图识别提示词

        Returns:
            V12.0 桌面端意图识别提示词
        """
        return INTENT_RECOGNITION_PROMPT


# ============================================================
# 便捷函数
# ============================================================


def generate_intent_prompt(schema=None) -> str:
    """
    生成意图识别提示词（便捷函数）

    Args:
        schema: PromptSchema 对象（可选）

    Returns:
        意图识别提示词
    """
    if schema:
        return IntentPromptGenerator.generate(schema)
    return IntentPromptGenerator.get_default()


def get_default_intent_prompt(skill_groups_description: str = "") -> str:
    """
    获取默认意图识别提示词

    Args:
        skill_groups_description: Skill 分组描述（从 SkillGroupRegistry 获取）
    """
    if skill_groups_description:
        return get_intent_recognition_prompt(skill_groups_description=skill_groups_description)
    return IntentPromptGenerator.get_default()

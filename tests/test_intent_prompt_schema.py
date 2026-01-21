"""
测试意图识别提示词的字段一致性
"""

from core.prompt import get_default_intent_prompt
from prompts.intent_recognition_prompt import get_intent_recognition_prompt


def _assert_required_fields(prompt: str) -> None:
    """
    校验意图提示词输出字段是否完整
    """
    required_fields = [
        '"task_type"',
        '"complexity"',
        '"complexity_score"',
        '"needs_plan"',
        '"skip_memory_retrieval"',
        '"needs_multi_agent"',
        '"is_follow_up"',
    ]
    for field in required_fields:
        assert field in prompt


def test_default_intent_prompt_schema_fields() -> None:
    """
    默认意图识别提示词包含 7 字段
    """
    prompt = get_default_intent_prompt()
    _assert_required_fields(prompt)


def test_intent_recognition_prompt_schema_fields() -> None:
    """
    统一意图识别提示词包含 7 字段
    """
    prompt = get_intent_recognition_prompt()
    _assert_required_fields(prompt)

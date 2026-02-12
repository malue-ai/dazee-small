"""
V5.0 统一语义推理模块

核心理念：
- 所有推理都通过 LLM 语义理解完成
- 使用 Few-Shot 提示词教会 LLM 推理模式
- 代码只做调用和解析，不做规则判断
- 保守的 fallback（默认值），不做关键词猜测
"""

from .semantic_inference import (
    InferenceResult,
    InferenceType,
    SemanticInference,
    get_semantic_inference,
    infer_capability,
    infer_complexity,
    infer_intent,
)

__all__ = [
    "SemanticInference",
    "InferenceType",
    "InferenceResult",
    "get_semantic_inference",
    "infer_complexity",
    "infer_intent",
    "infer_capability",
]

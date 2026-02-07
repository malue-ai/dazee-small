"""
评分器模块

三层评分器设计（基于Anthropic方法论）：
1. Code-based Graders - 快速、便宜、客观（优先使用）
2. Model-based Graders - 灵活、处理主观任务（补充使用）
3. Human Graders - 黄金标准（定期校准）
"""

from evaluation.graders.code_based import CodeBasedGraders
from evaluation.graders.model_based import ModelBasedGraders
from evaluation.graders.human import HumanGrader

__all__ = [
    "CodeBasedGraders",
    "ModelBasedGraders",
    "HumanGrader",
]

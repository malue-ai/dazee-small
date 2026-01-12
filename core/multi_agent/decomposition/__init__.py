"""
任务分解模块

职责：
- LLM 语义任务分解（Prompt-First）
- 生成子任务列表和依赖关系
- 生成 Worker 系统提示词建议

设计原则：
- 使用 Few-shot 引导 LLM 分解，不使用关键词匹配
- 复用 SemanticInference 基础设施
"""

from .task_decomposer import TaskDecomposer, create_task_decomposer
from .prompts import DECOMPOSITION_FEW_SHOT, WORKER_PROMPT_FEW_SHOT

__all__ = [
    "TaskDecomposer",
    "create_task_decomposer",
    "DECOMPOSITION_FEW_SHOT",
    "WORKER_PROMPT_FEW_SHOT",
]

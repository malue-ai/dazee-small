"""
Code-First 核心编排模块

设计哲学：
- E2EPipelineTracer: 端到端管道追踪器，记录每个环节的输入-处理-输出
- CodeOrchestrator: 统一代码生成、验证、执行的编排器
- CodeValidator: 代码验证器，支持语法检查和执行结果验证

参考架构：先进 Agent 设计策略 + Claude Code 最佳实践
"""

from .code_orchestrator import CodeOrchestrator, create_code_orchestrator
from .code_validator import CodeValidator, ValidationResult, create_code_validator
from .pipeline_tracer import E2EPipelineTracer, PipelineStage, create_pipeline_tracer

__all__ = [
    # Pipeline Tracer
    "E2EPipelineTracer",
    "PipelineStage",
    "create_pipeline_tracer",
    # Code Orchestrator
    "CodeOrchestrator",
    "create_code_orchestrator",
    # Code Validator
    "CodeValidator",
    "ValidationResult",
    "create_code_validator",
]

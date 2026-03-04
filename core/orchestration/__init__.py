"""
核心编排模块

- E2EPipelineTracer: 端到端管道追踪器
- CodeOrchestrator: 代码生成→验证→执行编排器
- CodeValidator: 代码验证器
- PipelineExecutor: 确定性工作流引擎（YAML 管道定义 + 审批卡点 + 断点恢复）
"""

from .background import (
    BackgroundTaskManager,
    create_background_task_manager,
    get_global_bg_manager,
    init_global_bg_manager,
)
from .code_orchestrator import CodeOrchestrator, create_code_orchestrator
from .code_validator import CodeValidator, ValidationResult, create_code_validator
from .pipeline import (
    PipelineDefinition,
    PipelineExecutor,
    PipelineState,
    PipelineStep,
    create_pipeline_executor,
)
from .pipeline_integration import (
    SkillStepExecutor,
    create_hitl_approval_adapter,
    create_integrated_pipeline_executor,
    create_progress_adapter,
)
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
    # Pipeline DSL Executor
    "PipelineDefinition",
    "PipelineStep",
    "PipelineState",
    "PipelineExecutor",
    "create_pipeline_executor",
    # Pipeline Integration
    "SkillStepExecutor",
    "create_hitl_approval_adapter",
    "create_progress_adapter",
    "create_integrated_pipeline_executor",
    # Background Task Manager
    "BackgroundTaskManager",
    "create_background_task_manager",
    "get_global_bg_manager",
    "init_global_bg_manager",
]

"""
多智能体内部实现模块（私有）

此目录包含多智能体的核心实现，仅供 execution/multi.py 使用。
外部模块不应直接导入此目录下的内容。

V10.1: orchestrator.py 从 core/agent/ 迁移到此处
V10.3: orchestrator 拆分为职责单一的子模块
  - events.py: EventEmitter（事件发送）
  - task_decomposer.py: TaskDecomposer（任务分解）
  - worker_runner.py: WorkerRunner（Worker 执行）
  - critic_evaluator.py: CriticEvaluator（Critic 评估）
  - result_aggregator.py: ResultAggregator（结果聚合）
"""

from core.agent.execution._multi.critic_evaluator import CriticEvaluator
from core.agent.execution._multi.events import EventEmitter
from core.agent.execution._multi.orchestrator import MultiAgentOrchestrator
from core.agent.execution._multi.result_aggregator import ResultAggregator
from core.agent.execution._multi.task_decomposer import TaskDecomposer
from core.agent.execution._multi.worker_runner import WorkerRunner

__all__ = [
    "MultiAgentOrchestrator",
    "EventEmitter",
    "TaskDecomposer",
    "WorkerRunner",
    "CriticEvaluator",
    "ResultAggregator",
]

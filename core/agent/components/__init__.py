"""
Agent 组件模块

提供多智能体协作所需的组件：
- CheckpointManager: 检查点管理（故障恢复）
- LeadAgent: 主控智能体（任务分解、结果综合）
- CriticAgent: 评估智能体（质量验证）
"""

from core.agent.components.checkpoint import (
    Checkpoint,
    CheckpointManager,
)
from core.agent.components.critic import CriticAgent
from core.agent.components.lead_agent import (
    ContextDependency,
    LeadAgent,
    SubTask,
    TaskDecompositionPlan,
)

__all__ = [
    # Checkpoint
    "Checkpoint",
    "CheckpointManager",
    # Lead Agent
    "LeadAgent",
    "SubTask",
    "TaskDecompositionPlan",
    "ContextDependency",
    # Critic
    "CriticAgent",
]

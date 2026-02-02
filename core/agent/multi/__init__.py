"""
多智能体框架模块

V7.1 核心组件（基于 Anthropic Multi-Agent System 启发）：
- MultiAgentOrchestrator: 编排器（支持检查点、恢复）
- CheckpointManager: 检查点管理（故障恢复）
- LeadAgent: 主控智能体（任务分解、结果综合）
- Models: 数据模型

设计理念：
1. **可恢复性**：长时间运行的工作流支持从检查点恢复
2. **明确分工**：Lead Agent (Opus) 分解任务，Worker Agents (Sonnet) 执行
3. **完整追踪**：记录每个决策、工具调用、状态转换
"""

from core.agent.multi.models import (
    # 执行模式
    ExecutionMode,
    
    # 角色
    AgentRole,
    
    # 配置
    AgentConfig,
    MultiAgentConfig,
    OrchestratorConfig,
    WorkerConfig,
    CriticConfig,  # V7.2
    
    # 任务
    TaskAssignment,
    
    # 结果
    AgentResult,
    SubagentResult,
    OrchestratorState,
    
    # Critic 相关（V7.2）
    CriticAction,
    CriticConfidence,
    CriticResult,
    
    # Agent 选择（V7.9）
    AgentSelectionResult,
)

from core.agent.multi.orchestrator import MultiAgentOrchestrator

from core.agent.multi.checkpoint import (
    Checkpoint,
    CheckpointManager,
)

from core.agent.multi.lead_agent import (
    LeadAgent,
    SubTask,
    TaskDecompositionPlan,
)

__all__ = [
    # 执行模式
    "ExecutionMode",
    
    # 角色
    "AgentRole",
    
    # 配置
    "AgentConfig",
    "MultiAgentConfig",
    "OrchestratorConfig",
    "WorkerConfig",
    "CriticConfig",  # V7.2
    
    # 任务
    "TaskAssignment",
    
    # 结果
    "AgentResult",
    "SubagentResult",
    "OrchestratorState",
    
    # Critic 相关（V7.2）
    "CriticAction",
    "CriticConfidence",
    "CriticResult",
    
    # Agent 选择（V7.9）
    "AgentSelectionResult",
    
    # 编排器
    "MultiAgentOrchestrator",
    
    # 检查点
    "Checkpoint",
    "CheckpointManager",
    
    # Lead Agent
    "LeadAgent",
    "SubTask",
    "TaskDecompositionPlan",
]

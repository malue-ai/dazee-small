"""
Agent 执行策略模块

V10.0 统一执行器架构：
- 单智能体：RVRExecutor, RVRBExecutor
- 多智能体：MultiAgentExecutor (Sequential/Parallel/Hierarchical)

扩展点：新增策略只需：
1. 新增 execution/*.py 实现 ExecutorProtocol
2. 在 factory.py 的 _get_executor_registry() 注册

目录结构：
- protocol.py: 执行器协议定义
- rvr.py: 标准 RVR 执行策略
- rvrb.py: 带回溯的 RVR-B 执行策略
- multi.py: 多智能体执行策略适配器
"""

from core.agent.execution.multi import (
    HierarchicalMultiExecutor,
    MultiAgentExecutor,
    ParallelMultiExecutor,
    SequentialMultiExecutor,
)
from core.agent.execution.protocol import (
    BaseExecutor,
    ExecutionContext,
    ExecutionResult,
    ExecutorConfig,
    ExecutorProtocol,
)
from core.agent.execution.rvr import (
    RVRExecutor,
    create_rvr_executor,
)
from core.agent.execution.rvrb import (
    RVRBExecutor,
    RVRBState,
    create_rvrb_executor,
)

__all__ = [
    # Protocol
    "ExecutorProtocol",
    "ExecutorConfig",
    "ExecutionContext",
    "ExecutionResult",
    "BaseExecutor",
    # RVR (单智能体)
    "RVRExecutor",
    "create_rvr_executor",
    # RVR-B (单智能体 + 回溯)
    "RVRBExecutor",
    "RVRBState",
    "create_rvrb_executor",
    # Multi-Agent (多智能体)
    "MultiAgentExecutor",
    "SequentialMultiExecutor",
    "ParallelMultiExecutor",
    "HierarchicalMultiExecutor",
]

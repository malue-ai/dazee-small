"""
Agent 执行策略模块

V11.0 小搭子架构：固定使用 RVR-B 执行策略

扩展点：新增策略只需：
1. 新增 execution/*.py 实现 ExecutorProtocol
2. 在 factory.py 的 _get_executor_registry() 注册

目录结构：
- protocol.py: 执行器协议定义
- rvr.py: 标准 RVR 执行策略
- rvrb.py: 带回溯的 RVR-B 执行策略（默认）
"""

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
    # RVR（RVR-B 的基类）
    "RVRExecutor",
    "create_rvr_executor",
    # RVR-B（默认执行策略）
    "RVRBExecutor",
    "RVRBState",
    "create_rvrb_executor",
]

"""
FSM 状态机模块

职责：
- 管理 Multi-Agent 任务的生命周期状态
- 验证状态转换合法性
- 持久化状态到 PlanMemory（支持检查点恢复）
- 发布状态变更事件

参考：
- 白皮书 1.3 节：将 Agent 执行循环建模为有限状态机
"""

from .states import TaskState, TaskStatus, SubTaskState, SubTaskStatus
from .engine import FSMEngine, create_fsm_engine
from .transitions import TransitionRule, VALID_TRANSITIONS

__all__ = [
    "TaskState",
    "TaskStatus", 
    "SubTaskState",
    "SubTaskStatus",
    "FSMEngine",
    "create_fsm_engine",
    "TransitionRule",
    "VALID_TRANSITIONS",
]

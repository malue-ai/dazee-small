"""
FSM 状态转换规则

定义合法的状态转换路径
"""

from dataclasses import dataclass
from typing import Dict, Set, Optional, Callable
from .states import TaskStatus


@dataclass
class TransitionRule:
    """
    状态转换规则
    
    定义从一个状态到另一个状态的转换条件
    """
    from_status: TaskStatus
    to_status: TaskStatus
    event: str                          # 触发事件名
    description: str = ""               # 转换描述
    guard: Optional[Callable] = None    # 守卫条件（可选）


# ==================== 合法状态转换定义 ====================

VALID_TRANSITIONS: Dict[TaskStatus, Dict[str, TaskStatus]] = {
    # PENDING 状态可以转换到的状态
    TaskStatus.PENDING: {
        "start": TaskStatus.DECOMPOSING,
        "cancel": TaskStatus.CANCELLED,
    },
    
    # DECOMPOSING 状态可以转换到的状态
    TaskStatus.DECOMPOSING: {
        "decompose_complete": TaskStatus.PLANNING,
        "decompose_error": TaskStatus.FAILED,
        "cancel": TaskStatus.CANCELLED,
    },
    
    # PLANNING 状态可以转换到的状态
    TaskStatus.PLANNING: {
        "plan_ready": TaskStatus.DISPATCHING,
        "plan_error": TaskStatus.FAILED,
        "cancel": TaskStatus.CANCELLED,
    },
    
    # DISPATCHING 状态可以转换到的状态
    TaskStatus.DISPATCHING: {
        "workers_assigned": TaskStatus.EXECUTING,
        "dispatch_error": TaskStatus.FAILED,
        "cancel": TaskStatus.CANCELLED,
    },
    
    # EXECUTING 状态可以转换到的状态
    TaskStatus.EXECUTING: {
        "all_complete": TaskStatus.OBSERVING,
        "partial_complete": TaskStatus.OBSERVING,  # 部分完成也进入观察
        "execution_error": TaskStatus.FAILED,
        "cancel": TaskStatus.CANCELLED,
    },
    
    # OBSERVING 状态可以转换到的状态
    TaskStatus.OBSERVING: {
        "observe_complete": TaskStatus.VALIDATING,
        "need_retry": TaskStatus.EXECUTING,        # 重试
        "observe_error": TaskStatus.FAILED,
        "cancel": TaskStatus.CANCELLED,
    },
    
    # VALIDATING 状态可以转换到的状态
    TaskStatus.VALIDATING: {
        "validation_pass": TaskStatus.AGGREGATING,
        "validation_fail_retry": TaskStatus.EXECUTING,  # 验证失败重试
        "validation_fail_final": TaskStatus.FAILED,     # 验证失败且不可重试
        "cancel": TaskStatus.CANCELLED,
    },
    
    # AGGREGATING 状态可以转换到的状态
    TaskStatus.AGGREGATING: {
        "aggregate_complete": TaskStatus.COMPLETED,
        "aggregate_error": TaskStatus.FAILED,
    },
    
    # 终态（不能再转换）
    TaskStatus.COMPLETED: {},
    TaskStatus.FAILED: {},
    TaskStatus.CANCELLED: {},
}


def is_valid_transition(from_status: TaskStatus, event: str) -> bool:
    """
    检查状态转换是否合法
    
    Args:
        from_status: 当前状态
        event: 触发事件
        
    Returns:
        是否合法
    """
    transitions = VALID_TRANSITIONS.get(from_status, {})
    return event in transitions


def get_next_status(from_status: TaskStatus, event: str) -> Optional[TaskStatus]:
    """
    获取转换后的状态
    
    Args:
        from_status: 当前状态
        event: 触发事件
        
    Returns:
        目标状态，如果转换不合法则返回 None
    """
    transitions = VALID_TRANSITIONS.get(from_status, {})
    return transitions.get(event)


def get_valid_events(status: TaskStatus) -> Set[str]:
    """
    获取当前状态可用的事件
    
    Args:
        status: 当前状态
        
    Returns:
        可用事件集合
    """
    transitions = VALID_TRANSITIONS.get(status, {})
    return set(transitions.keys())


def is_terminal_status(status: TaskStatus) -> bool:
    """
    检查是否为终态
    
    Args:
        status: 状态
        
    Returns:
        是否为终态
    """
    return status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}


# ==================== 状态转换描述（用于日志和事件） ====================

TRANSITION_DESCRIPTIONS: Dict[str, str] = {
    "start": "开始任务分解",
    "decompose_complete": "任务分解完成",
    "decompose_error": "任务分解失败",
    "plan_ready": "执行计划就绪",
    "plan_error": "计划生成失败",
    "workers_assigned": "Worker 分配完成",
    "dispatch_error": "Worker 分配失败",
    "all_complete": "所有子任务完成",
    "partial_complete": "部分子任务完成",
    "execution_error": "执行过程出错",
    "observe_complete": "结果观察完成",
    "need_retry": "需要重试",
    "observe_error": "观察过程出错",
    "validation_pass": "验证通过",
    "validation_fail_retry": "验证失败，重试",
    "validation_fail_final": "验证失败，终止",
    "aggregate_complete": "结果聚合完成",
    "aggregate_error": "聚合过程出错",
    "cancel": "任务被取消",
}


def get_transition_description(event: str) -> str:
    """获取转换事件的描述"""
    return TRANSITION_DESCRIPTIONS.get(event, event)

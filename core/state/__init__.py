"""
状态一致性模块

提供任务前快照、操作日志、回滚能力与安全保障。
"""

from typing import Any, Callable

from core.state.consistency_manager import (
    ConsistencyCheckConfig,
    EnvironmentState,
    PostCheckResult,
    PreCheckResult,
    RollbackConfig,
    Snapshot,
    SnapshotConfig,
    StateConsistencyConfig,
    StateConsistencyManager,
)
from core.state.operation_log import (
    OperationLog,
    OperationRecord,
    create_file_create_record,
    create_file_delete_record,
    create_file_write_record,
)

__all__ = [
    # 管理器
    "StateConsistencyManager",
    # 配置
    "StateConsistencyConfig",
    "SnapshotConfig",
    "RollbackConfig",
    "ConsistencyCheckConfig",
    # 数据模型
    "Snapshot",
    "EnvironmentState",
    "PreCheckResult",
    "PostCheckResult",
    # 操作日志
    "OperationLog",
    "OperationRecord",
    # 便捷工厂
    "create_file_write_record",
    "create_file_create_record",
    "create_file_delete_record",
    # Devtools
    "create_state_devtools_logger",
]


def create_state_devtools_logger() -> Callable[..., None]:
    """
    创建状态一致性调试日志回调（devtools 风格）

    用于 StateConsistencyManager.subscribe(callback)。
    将 record/rollback 事件以结构化方式写入日志，便于调试。

    Returns:
        可作为 manager.subscribe(cb) 的 callback
    """
    from logger import get_logger

    log = get_logger("state.devtools")

    def _on_event(event_type: str, task_id: str, *args: Any) -> None:
        if event_type == "record":
            (record_dict,) = args
            log.debug(
                "[state] record task_id=%s action=%s target=%s",
                task_id,
                record_dict.get("action"),
                record_dict.get("target"),
            )
        elif event_type == "rollback":
            snapshot_id, messages = args[0], args[1]
            log.debug(
                "[state] rollback task_id=%s snapshot_id=%s messages_count=%s",
                task_id,
                snapshot_id,
                len(messages),
            )

    return _on_event

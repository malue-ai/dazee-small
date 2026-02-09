"""
操作日志 - Operation Log

记录可回滚的操作序列，支持逆序回滚。

增强：
- 持久化支持（序列化/反序列化）
- inverse-patch 自动生成逆操作（常见文件操作）
- 操作统计
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class OperationRecord:
    """
    单条操作记录

    Attributes:
        operation_id: 操作唯一标识
        action: 操作类型（如 file_write, file_delete, file_create, file_rename）
        target: 操作目标（如文件路径）
        before_state: 操作前状态（用于回滚）
        after_state: 操作后状态（可选）
        rollback_action: 回滚时的动作（如恢复 before_state）
        timestamp: 记录时间
    """

    operation_id: str
    action: str
    target: str
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    rollback_action: Optional[Callable[[], Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（不含 rollback_action 闭包）"""
        return {
            "operation_id": self.operation_id,
            "action": self.action,
            "target": self.target,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OperationRecord":
        """从字典反序列化（不含 rollback_action，需重新生成）"""
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        elif ts is None:
            ts = datetime.now()

        record = cls(
            operation_id=data.get("operation_id", ""),
            action=data.get("action", ""),
            target=data.get("target", ""),
            before_state=data.get("before_state"),
            after_state=data.get("after_state"),
            timestamp=ts,
        )
        # 反序列化后自动生成逆操作
        record.rollback_action = _generate_inverse_action(record)
        return record


class OperationLog:
    """
    操作日志

    按顺序追加操作记录，支持逆序回滚全部或部分。
    支持序列化/反序列化用于磁盘持久化。
    支持订阅监听（append/rollback）用于前端进度或 devtools 调试。
    """

    def __init__(self) -> None:
        self._records: List[OperationRecord] = []
        self._listeners: List[Callable[..., None]] = []

    def subscribe(self, callback: Callable[[str, Any], None]) -> None:
        """
        订阅操作日志变更（仿 subscribeWithSelector 思路）

        Args:
            callback: 接收 (event_type, payload)，event_type 为 "append" | "rollback"
                      payload: append 时为 record.to_dict()，rollback 时为 messages 列表
        """
        if callback not in self._listeners:
            self._listeners.append(callback)

    def append(self, record: OperationRecord) -> None:
        """追加一条操作记录"""
        self._records.append(record)
        for cb in self._listeners:
            try:
                cb("append", record.to_dict())
            except Exception as e:
                logger.debug(f"OperationLog 监听器异常: {e}")

    def rollback_all(self) -> List[str]:
        """
        逆序执行所有记录的回滚动作

        Returns:
            回滚结果消息列表
        """
        messages: List[str] = []
        for record in reversed(self._records):
            try:
                if record.rollback_action:
                    record.rollback_action()
                    messages.append(f"已回滚: {record.action} {record.target}")
                elif record.before_state:
                    # 无显式 rollback_action 时，尝试自动生成
                    auto_action = _generate_inverse_action(record)
                    if auto_action:
                        auto_action()
                        messages.append(
                            f"已自动回滚: {record.action} {record.target}"
                        )
                    else:
                        messages.append(
                            f"无回滚动作: {record.action} {record.target}"
                        )
                else:
                    messages.append(
                        f"无回滚动作: {record.action} {record.target}"
                    )
            except Exception as e:
                logger.warning(
                    f"回滚失败 {record.operation_id}: {e}", exc_info=True
                )
                messages.append(f"回滚失败: {record.target} - {e}")
        for cb in self._listeners:
            try:
                cb("rollback", messages)
            except Exception as e:
                logger.debug(f"OperationLog 监听器异常: {e}")
        self.clear()
        return messages

    def clear(self) -> None:
        """清空日志"""
        self._records.clear()

    def get_rollback_options(self) -> List[Dict[str, Any]]:
        """
        获取可展示给用户的回滚选项（供 HITL 展示）

        Returns:
            [{"id": "...", "action": "...", "target": "..."}, ...]
        """
        return [
            {
                "id": r.operation_id,
                "action": r.action,
                "target": r.target,
            }
            for r in self._records
        ]

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """序列化为字典列表（用于持久化）"""
        return [r.to_dict() for r in self._records]

    @classmethod
    def from_dict_list(cls, data: List[Dict[str, Any]]) -> "OperationLog":
        """从字典列表反序列化"""
        log = cls()
        for item in data:
            log.append(OperationRecord.from_dict(item))
        return log

    @property
    def stats(self) -> Dict[str, Any]:
        """操作统计"""
        action_counts: Dict[str, int] = {}
        for r in self._records:
            action_counts[r.action] = action_counts.get(r.action, 0) + 1
        return {
            "total": len(self._records),
            "by_action": action_counts,
        }

    def __len__(self) -> int:
        return len(self._records)


# ==================== Inverse-Patch 自动生成 ====================


def _generate_inverse_action(
    record: OperationRecord,
) -> Optional[Callable[[], Any]]:
    """
    根据操作记录自动生成逆操作（inverse-patch 模式）

    支持的操作类型：
    - file_write: 恢复 before_state 中的原始内容
    - file_create: 删除创建的文件
    - file_delete: 恢复 before_state 中的原始内容
    - file_rename: 重命名回原始名称

    Args:
        record: 操作记录

    Returns:
        回滚动作闭包，None 表示无法自动生成
    """
    action = record.action
    target = record.target
    before = record.before_state or {}

    if action == "file_write" and "content" in before:
        # 恢复原始文件内容
        def _rollback_write() -> None:
            Path(target).write_text(
                before["content"], encoding="utf-8"
            )

        return _rollback_write

    if action == "file_create":
        # 删除创建的文件
        def _rollback_create() -> None:
            p = Path(target)
            if p.exists():
                p.unlink()

        return _rollback_create

    if action == "file_delete" and "content" in before:
        # 恢复被删除的文件
        def _rollback_delete() -> None:
            p = Path(target)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(before["content"], encoding="utf-8")

        return _rollback_delete

    if action == "file_rename" and "original_path" in before:
        # 重命名回原始路径
        original = before["original_path"]

        def _rollback_rename() -> None:
            p = Path(target)
            if p.exists():
                p.rename(original)

        return _rollback_rename

    return None


# ==================== 便捷工厂方法 ====================


def create_file_write_record(
    file_path: str,
    original_content: Optional[str] = None,
    new_content: Optional[str] = None,
) -> OperationRecord:
    """
    创建文件写入操作记录（自动生成逆操作）

    Args:
        file_path: 文件路径
        original_content: 原始内容（写入前的内容）
        new_content: 新内容

    Returns:
        带有自动逆操作的 OperationRecord
    """
    record = OperationRecord(
        operation_id=f"op_{uuid.uuid4().hex[:12]}",
        action="file_write",
        target=file_path,
        before_state={"content": original_content} if original_content is not None else None,
        after_state={"content": new_content} if new_content is not None else None,
    )
    record.rollback_action = _generate_inverse_action(record)
    return record


def create_file_create_record(file_path: str) -> OperationRecord:
    """创建文件创建操作记录"""
    record = OperationRecord(
        operation_id=f"op_{uuid.uuid4().hex[:12]}",
        action="file_create",
        target=file_path,
    )
    record.rollback_action = _generate_inverse_action(record)
    return record


def create_file_delete_record(
    file_path: str, original_content: Optional[str] = None
) -> OperationRecord:
    """创建文件删除操作记录"""
    record = OperationRecord(
        operation_id=f"op_{uuid.uuid4().hex[:12]}",
        action="file_delete",
        target=file_path,
        before_state={"content": original_content} if original_content is not None else None,
    )
    record.rollback_action = _generate_inverse_action(record)
    return record

"""
后台任务上下文 - 定义任务所需的所有参数

设计原则：
- 统一传递所有任务可能需要的参数
- 避免每个任务单独定义参数
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class TaskContext:
    """
    后台任务上下文 - 统一传递所有任务可能需要的参数

    新增任务时，如果需要新参数，在这里添加即可
    """

    session_id: str
    conversation_id: str
    user_id: str
    message_id: str
    user_message: str  # 用户消息文本
    assistant_response: str = ""  # 助手回复文本
    is_new_conversation: bool = False
    event_manager: Optional[Any] = None
    conversation_service: Optional[Any] = None

    # 🆕 扩展字段（未来可能需要）
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Mem0UpdateResult:
    """单用户 Mem0 更新结果"""

    user_id: str
    success: bool
    memories_added: int = 0
    conversations_processed: int = 0
    error: Optional[str] = None
    duration_ms: int = 0


@dataclass
class Mem0BatchUpdateResult:
    """批量 Mem0 更新结果"""

    total_users: int
    successful: int
    failed: int
    total_memories_added: int = 0
    results: List["Mem0UpdateResult"] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @property
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

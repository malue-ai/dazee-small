"""
Mem0 记忆更新任务 - 更新用户的长期记忆

触发条件：
- 有用户 ID
"""

from typing import TYPE_CHECKING

from logger import get_logger
from ..registry import background_task

if TYPE_CHECKING:
    from ..context import TaskContext
    from ..service import BackgroundTaskService

logger = get_logger("background_tasks.mem0_update")


@background_task("mem0_update")
async def update_mem0_memories(ctx: "TaskContext", service: "BackgroundTaskService") -> None:
    """
    Mem0 记忆更新任务
    
    更新用户在最近一段时间内的会话记忆
    """
    if not ctx.user_id:
        logger.debug("○ 跳过 Mem0 更新（无用户 ID）")
        return
    
    await service.update_user_memories(
        user_id=ctx.user_id,
        since_hours=24,
        session_id=ctx.session_id,
        event_manager=ctx.event_manager
    )


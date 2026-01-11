"""
标题生成任务 - 为新对话生成标题

触发条件：
- 新对话（is_new_conversation=True）
- 有用户消息
"""

from typing import TYPE_CHECKING

from logger import get_logger
from ..registry import background_task

if TYPE_CHECKING:
    from ..context import TaskContext
    from ..service import BackgroundTaskService

logger = get_logger("background_tasks.title_generation")


@background_task("title_generation")
async def generate_title(ctx: "TaskContext", service: "BackgroundTaskService") -> None:
    """
    标题生成任务
    
    只对新对话生成标题
    """
    # 只对新对话生成标题
    if not ctx.is_new_conversation:
        logger.debug("○ 跳过标题生成（非新对话）")
        return
    
    if not ctx.user_message:
        logger.debug("○ 跳过标题生成（无用户消息）")
        return
    
    await service.generate_conversation_title(
        conversation_id=ctx.conversation_id,
        first_message=ctx.user_message,
        session_id=ctx.session_id,
        event_manager=ctx.event_manager,
        conversation_service=ctx.conversation_service
    )


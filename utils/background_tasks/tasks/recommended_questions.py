"""
推荐问题生成任务 - 生成用户可能感兴趣的后续问题

触发条件：
- 有用户消息
- 有助手回复
"""

from typing import TYPE_CHECKING

from logger import get_logger
from ..registry import background_task

if TYPE_CHECKING:
    from ..context import TaskContext
    from ..service import BackgroundTaskService

logger = get_logger("background_tasks.recommended_questions")


@background_task("recommended_questions")
async def generate_recommended_questions(ctx: "TaskContext", service: "BackgroundTaskService") -> None:
    """
    推荐问题生成任务
    
    根据对话内容生成用户可能感兴趣的后续问题
    """
    if not ctx.user_message or not ctx.assistant_response:
        logger.debug("○ 跳过推荐问题生成（缺少用户消息或助手回复）")
        return
    
    await service.generate_recommended_questions(
        session_id=ctx.session_id,
        message_id=ctx.message_id,
        user_message=ctx.user_message,
        assistant_response=ctx.assistant_response,
        event_manager=ctx.event_manager
    )


"""
标题生成任务 - 为新对话生成标题

触发条件：
- 新对话（is_new_conversation=True）
- 有用户消息

实现：
- 使用 LLM 生成标题
- 更新数据库
- 通过 SSE 推送给前端
"""

from typing import TYPE_CHECKING, Optional

from logger import get_logger

from ..registry import background_task

if TYPE_CHECKING:
    from ..context import TaskContext
    from ..service import BackgroundTaskService

from core.llm.base import Message

logger = get_logger("background_tasks.title_generation")


@background_task("title_generation")
async def generate_title(ctx: "TaskContext", service: "BackgroundTaskService") -> None:
    """
    标题生成任务

    只对新对话生成标题
    """
    if not ctx.user_message:
        logger.debug("○ 跳过标题生成（无用户消息）")
        return

    should_generate = ctx.is_new_conversation

    # Non-new conversations can also need title generation when the title is
    # still missing/default (e.g., external channel history migrated into local).
    if not should_generate and ctx.conversation_service:
        try:
            conv = await ctx.conversation_service.get_conversation(ctx.conversation_id)
            current_title = (conv.title or "").strip() if conv else ""
            should_generate = current_title in {"", "新对话"}
        except Exception as e:
            logger.warning(f"⚠️ 读取会话标题失败，跳过标题生成判断: {e}")
            should_generate = False

    if not should_generate:
        logger.debug("○ 跳过标题生成（已有有效标题）")
        return

    await _generate_conversation_title(
        conversation_id=ctx.conversation_id,
        first_message=ctx.user_message,
        session_id=ctx.session_id,
        event_manager=ctx.event_manager,
        conversation_service=ctx.conversation_service,
        service=service,
    )


async def _generate_conversation_title(
    conversation_id: str,
    first_message: str,
    session_id: Optional[str],
    event_manager,
    conversation_service,
    service: "BackgroundTaskService",
) -> Optional[str]:
    """
    生成对话标题（后台任务）

    流程：
    1. 使用 LLM 生成标题
    2. 更新数据库（ConversationService）
    3. 通过 SSE 推送给前端（EventManager）
    """
    try:
        logger.info(f"🏷️ 开始生成对话标题: conversation_id={conversation_id}")

        # 1. 截取消息前 200 字符
        message_preview = first_message[:200] if len(first_message) > 200 else first_message

        # 2. 使用 LLM 生成标题
        title = await _generate_title_with_llm(message_preview, service)

        if not title:
            logger.warning(f"⚠️ LLM 返回空标题")
            return None

        # 3. 清理标题（去除引号、标点等）
        title = _clean_title(title)

        logger.info(f"✅ 标题已生成: {title}")

        # 4. 更新数据库
        if conversation_service:
            await conversation_service.update_conversation(
                conversation_id=conversation_id, title=title
            )
            logger.info(f"💾 数据库已更新")

        # 5. 通过 SSE 推送给前端
        if session_id and event_manager:
            # 🆕 使用 event_manager 已配置的 output_format 和 adapter
            await event_manager.conversation.emit_conversation_delta(
                session_id=session_id,
                conversation_id=conversation_id,
                delta={"title": title},
                output_format=getattr(event_manager, "output_format", "zenflux"),
                adapter=getattr(event_manager, "adapter", None),
            )
            logger.info(f"📤 标题更新事件已推送到前端: {title}")

        return title

    except Exception as e:
        logger.warning(f"⚠️ 生成对话标题失败: {str(e)}")
        return None


async def _generate_title_with_llm(message: str, service: "BackgroundTaskService") -> Optional[str]:
    """使用 LLM 生成标题"""
    try:
        llm = await service.get_llm()
        prompt = service.title_generation_prompt.format(message=message)

        response = await llm.create_message_async(
            messages=[Message(role="user", content=prompt)],
        )

        if response and response.content:
            return response.content.strip()

        return None

    except Exception as e:
        logger.error(f"❌ LLM 生成标题失败: {str(e)}", exc_info=True)
        return None


def _clean_title(title: str) -> str:
    """清理标题（去除引号、标点等）"""
    title = title.strip('"\'「」『』【】《》""' "")
    if len(title) > 20:
        title = title[:17] + "..."
    return title

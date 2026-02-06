"""
推荐问题生成任务 - 生成用户可能感兴趣的后续问题

触发条件：
- 有用户消息
- 有助手回复

实现：
- 使用 LLM 生成问题
- JSON 解析和回退方案
- 通过 SSE 推送给前端
"""

import json
import re
from typing import TYPE_CHECKING, List, Optional

from logger import get_logger
from utils.json_utils import extract_json_list

from ..registry import background_task

if TYPE_CHECKING:
    from ..context import TaskContext
    from ..service import BackgroundTaskService

from core.llm.base import Message

logger = get_logger("background_tasks.recommended_questions")


@background_task("recommended_questions")
async def generate_recommended_questions_task(
    ctx: "TaskContext", service: "BackgroundTaskService"
) -> None:
    """
    推荐问题生成任务

    根据对话内容生成用户可能感兴趣的后续问题
    """
    if not ctx.user_message or not ctx.assistant_response:
        logger.debug("○ 跳过推荐问题生成（缺少用户消息或助手回复）")
        return

    await _generate_recommended_questions(
        session_id=ctx.session_id,
        conversation_id=ctx.conversation_id,
        message_id=ctx.message_id,
        user_message=ctx.user_message,
        assistant_response=ctx.assistant_response,
        event_manager=ctx.event_manager,
        service=service,
    )


async def _generate_recommended_questions(
    session_id: str,
    conversation_id: str,
    message_id: str,
    user_message: str,
    assistant_response: str,
    event_manager,
    service: "BackgroundTaskService",
) -> Optional[List[str]]:
    """
    生成推荐问题（后台任务）

    根据对话内容生成用户可能感兴趣的后续问题，
    通过 SSE 推送到前端显示在消息底部
    """
    try:
        logger.info(f"💡 开始生成推荐问题: session_id={session_id}, message_id={message_id}")

        # 1. 截取内容（避免过长）
        user_preview = user_message[:300] if len(user_message) > 300 else user_message
        assistant_preview = (
            assistant_response[:500] if len(assistant_response) > 500 else assistant_response
        )

        # 2. 使用 LLM 生成推荐问题
        questions = await _generate_questions_with_llm(user_preview, assistant_preview, service)

        if not questions:
            logger.warning("⚠️ LLM 返回空的推荐问题")
            return None

        logger.info(f"✅ 推荐问题已生成: {len(questions)} 个")

        # 3. 通过 SSE 推送给前端
        if session_id and event_manager:
            # 🆕 使用 event_manager 已配置的 output_format 和 adapter
            await event_manager.message.emit_message_delta(
                session_id=session_id,
                conversation_id=conversation_id,
                delta={"type": "recommended", "content": {"questions": questions}},
                message_id=message_id,
                output_format=getattr(event_manager, "output_format", "zenflux"),
                adapter=getattr(event_manager, "adapter", None),
            )
            logger.info(f"📤 推荐问题已推送到前端")

        return questions

    except Exception as e:
        logger.warning(f"⚠️ 生成推荐问题失败: {str(e)}")
        return None


async def _generate_questions_with_llm(
    user_message: str, assistant_response: str, service: "BackgroundTaskService"
) -> Optional[List[str]]:
    """使用 LLM 生成推荐问题"""
    try:
        llm = await service.get_llm()

        prompt = service.recommended_questions_prompt.format(
            user_message=user_message, assistant_response=assistant_response
        )

        response = await llm.create_message_async(
            messages=[Message(role="user", content=prompt)],
        )

        if response and hasattr(response, "content") and response.content:
            content = response.content

            # 提取原始文本：支持字符串或 TextBlock 列表
            raw_text = None
            if isinstance(content, str):
                # content 直接是字符串
                raw_text = content.strip()
            elif isinstance(content, list):
                # content 是 TextBlock 列表
                for block in content:
                    if hasattr(block, "text"):
                        raw_text = block.text.strip()
                        break

            if raw_text:
                logger.debug(f"📝 LLM 原始返回: {raw_text[:300]}...")

                # 使用 JSON 提取器
                questions = extract_json_list(raw_text, key="questions")
                logger.debug(f"📋 JSON 提取结果: {questions}")

                if questions:
                    cleaned = []
                    for q in questions[:3]:
                        q = q.strip().strip("\"'「」『』,")

                        # 过滤掉明显不是问题的内容（markdown/JSON 语法）
                        if _is_invalid_question(q):
                            logger.debug(f"⚠️ 跳过无效问题: {q}")
                            continue

                        if len(q) > 30:
                            q = q[:27] + "..."
                        if q and len(q) >= 5:
                            cleaned.append(q)

                    if cleaned:
                        return cleaned

                # JSON 提取失败或结果无效，回退到逐行解析
                logger.debug("JSON 提取失败或结果无效，回退到逐行解析")
                return _parse_questions_fallback(raw_text)

        return None

    except Exception as e:
        logger.error(f"❌ LLM 生成推荐问题失败: {str(e)}", exc_info=True)
        return None


def _is_invalid_question(text: str) -> bool:
    """检查文本是否是无效的问题（markdown/JSON 语法等）"""
    if not text:
        return True

    # 无效模式
    invalid_patterns = [
        r"^```",  # markdown 代码块
        r'^"?questions"?\s*:',  # JSON key
        r"^\[",  # JSON 数组
        r"^\]",
        r"^\{",  # JSON 对象
        r"^\}",
        r"^json$",  # 单独的 json 标记
    ]

    for pattern in invalid_patterns:
        if re.match(pattern, text, re.IGNORECASE):
            return True

    return False


def _parse_questions_fallback(raw_text: str) -> List[str]:
    """回退方案：逐行解析 LLM 返回的问题文本"""
    questions = []

    # 需要跳过的模式（markdown 代码块、JSON 语法等）
    skip_patterns = [
        r"^```",  # markdown 代码块标记
        r'^"?questions"?\s*:',  # JSON key
        r"^\[",  # JSON 数组开始
        r"^\]",  # JSON 数组结束
        r"^\{",  # JSON 对象开始
        r"^\}",  # JSON 对象结束
    ]

    for line in raw_text.split("\n"):
        line = line.strip()

        if not line:
            continue

        # 跳过 markdown 和 JSON 语法
        should_skip = False
        for pattern in skip_patterns:
            if re.match(pattern, line, re.IGNORECASE):
                should_skip = True
                break
        if should_skip:
            continue

        line = re.sub(r"^[\d]+[.、)\]]\s*", "", line)
        line = re.sub(r"^[-•·]\s*", "", line)
        line = line.strip().strip("\"'「」『』,")  # 也去掉尾部逗号

        # 过滤掉太短或包含 JSON 语法的内容
        if len(line) < 5:
            continue

        if len(line) > 30:
            line = line[:27] + "..."

        if line:
            questions.append(line)

    return questions[:3]

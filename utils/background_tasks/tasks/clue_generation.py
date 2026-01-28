"""
线索生成任务 - 每次对话完成后生成操作线索

触发条件：
- 每次对话完成后自动触发

实现：
- 根据对话内容生成可操作的线索（clue）
- 支持多种操作类型：reply, forward, confirm, upload 等
- 通过 SSE 推送给前端

事件格式：
{
    "type": "message_delta",  # zenflux 格式
    "data": {
        "type": "clue",
        "content": "{\"tasks\":[...]}"
    }
}

或 Zeno 格式：
{
    "type": "message.assistant.delta",
    "message_id": "msg_123",
    "timestamp": 1735000000000,
    "delta": {
        "type": "clue",
        "content": "{\"tasks\":[...]}"
    }
}

ClueData 结构：
{
    "tasks": [
        {
            "id": "clue_1",              # 线索唯一标识（可选）
            "text": "确认是否需要...",    # 线索文本
            "act": "reply",              # 操作类型
            "status": "pending",         # 线索状态（可选）
            "payload": {...},            # 额外数据（可选）
            "metadata": {...}            # 元数据（可选）
        }
    ]
}

操作类型（act）：
- reply: 回复确认
- forward: 转发分享
- confirm: 确认操作
- upload: 上传文件
"""

import json
from typing import TYPE_CHECKING, Optional, List, Dict, Any
from uuid import uuid4

from logger import get_logger
from utils.json_utils import extract_json
from ..registry import background_task

if TYPE_CHECKING:
    from core.llm.base import Message
    from ..context import TaskContext
    from ..service import BackgroundTaskService

logger = get_logger("background_tasks.clue_generation")

# 线索生成提示词
CLUE_GENERATION_PROMPT = """基于以下对话内容，分析用户可能需要执行的后续操作，生成操作线索列表。

操作类型说明：
- reply: 需要用户回复确认的问题
- forward: 可以转发/分享的内容
- confirm: 需要用户确认的配置或操作
- upload: 需要用户上传文件

生成规则：
1. 每个线索应该具体、可操作
2. 线索文本不超过 30 个字
3. 最多生成 4 个线索
4. 优先生成与当前任务相关的线索
5. 如果助手已完成某项任务，生成后续延伸类线索
6. 不要生成已经完成的操作

对话内容：
用户：{user_message}
助手：{assistant_response}

返回格式（只返回 JSON，不要其他内容）：
{{
    "tasks": [
        {{
            "id": "clue_1",
            "text": "线索描述",
            "act": "reply|forward|confirm|upload",
            "payload": {{}}
        }}
    ]
}}

如果没有合适的线索，返回：
{{"tasks": []}}
"""


@background_task("clue_generation")
async def generate_clue_task(
    ctx: "TaskContext",
    service: "BackgroundTaskService"
) -> None:
    """
    线索生成任务
    
    根据对话内容生成用户可能需要的操作线索
    每次对话完成后自动触发
    """
    if not ctx.user_message:
        logger.debug("○ 跳过线索生成（缺少用户消息）")
        return
    
    await _generate_clues(
        session_id=ctx.session_id,
        conversation_id=ctx.conversation_id,
        message_id=ctx.message_id,
        user_message=ctx.user_message,
        assistant_response=ctx.assistant_response,
        event_manager=ctx.event_manager,
        service=service
    )


async def _generate_clues(
    session_id: str,
    conversation_id: str,
    message_id: str,
    user_message: str,
    assistant_response: str,
    event_manager,
    service: "BackgroundTaskService"
) -> Optional[Dict[str, Any]]:
    """
    生成操作线索（后台任务）
    
    根据对话内容生成用户可能需要的操作线索，
    通过 SSE 推送到前端
    """
    try:
        logger.info(f"🔍 开始生成线索: session_id={session_id}, message_id={message_id}")
        
        # 1. 截取内容（避免过长）
        user_preview = user_message[:500] if len(user_message) > 500 else user_message
        assistant_preview = assistant_response[:800] if len(assistant_response) > 800 else assistant_response
        
        # 2. 使用 LLM 生成线索
        clue_data = await _generate_clues_with_llm(user_preview, assistant_preview, service)
        
        if not clue_data or not clue_data.get("tasks"):
            logger.info("○ 未生成线索（无合适的操作建议）")
            return None
        
        tasks = clue_data.get("tasks", [])
        logger.info(f"✅ 线索已生成: {len(tasks)} 个")
        
        # 3. 通过 SSE 推送给前端
        if session_id and event_manager:
            # 将 clue_data 序列化为 JSON 字符串
            clue_content = json.dumps(clue_data, ensure_ascii=False)
            
            await event_manager.message.emit_message_delta(
                session_id=session_id,
                conversation_id=conversation_id,
                delta={
                    "type": "clue",
                    "content": clue_content  # JSON 字符串格式
                },
                message_id=message_id,
                output_format=getattr(event_manager, 'output_format', 'zenflux'),
                adapter=getattr(event_manager, 'adapter', None)
            )
            logger.info(f"📤 线索已推送到前端: {len(tasks)} 个任务")
        
        return clue_data
    
    except Exception as e:
        logger.warning(f"⚠️ 生成线索失败: {str(e)}", exc_info=True)
        return None


async def _generate_clues_with_llm(
    user_message: str,
    assistant_response: str,
    service: "BackgroundTaskService"
) -> Optional[Dict[str, Any]]:
    """使用 LLM 生成操作线索"""
    try:
        from core.llm.base import Message  # 延迟导入，避免循环依赖
        
        llm = service.get_llm()
        
        prompt = CLUE_GENERATION_PROMPT.format(
            user_message=user_message,
            assistant_response=assistant_response
        )
        
        response = await llm.create_message_async(
            messages=[Message(role="user", content=prompt)],
        )
        
        if response and hasattr(response, 'content') and response.content:
            content = response.content
            
            # 提取原始文本
            raw_text = None
            if isinstance(content, str):
                raw_text = content.strip()
            elif isinstance(content, list):
                for block in content:
                    if hasattr(block, 'text'):
                        raw_text = block.text.strip()
                        break
            
            if raw_text:
                logger.debug(f"📝 LLM 线索返回: {raw_text[:500]}...")
                
                # 解析 JSON
                parsed = extract_json(raw_text)
                
                if parsed and isinstance(parsed, dict):
                    tasks = parsed.get("tasks", [])
                    
                    # 验证和清理 tasks
                    valid_tasks = []
                    valid_acts = {"reply", "forward", "confirm", "upload"}
                    
                    for i, task in enumerate(tasks[:4]):  # 最多 4 个
                        if not isinstance(task, dict):
                            continue
                        
                        text = task.get("text", "").strip()
                        act = task.get("act", "reply")
                        
                        if not text:
                            continue
                        
                        # 验证 act 类型
                        if act not in valid_acts:
                            act = "reply"  # 默认回退
                        
                        # 截断过长的文本
                        if len(text) > 30:
                            text = text[:27] + "..."
                        
                        valid_task = {
                            "id": task.get("id") or f"clue_{i + 1}",
                            "text": text,
                            "act": act
                        }
                        
                        # 添加可选字段
                        if task.get("payload"):
                            valid_task["payload"] = task["payload"]
                        if task.get("status"):
                            valid_task["status"] = task["status"]
                        if task.get("metadata"):
                            valid_task["metadata"] = task["metadata"]
                        
                        valid_tasks.append(valid_task)
                    
                    if valid_tasks:
                        return {"tasks": valid_tasks}
        
        return None
    
    except Exception as e:
        logger.error(f"❌ LLM 生成线索失败: {str(e)}", exc_info=True)
        return None

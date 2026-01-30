"""
请求预处理工具函数 - Query Utilities

提供请求预处理相关的通用工具函数：
- 变量格式化
- Conversation delta 应用

职责边界：
- 本模块：简单的数据格式化和 DB 操作
- message_utils.py：消息格式转换、追加操作
- file_processor.py：文件处理（下载、解析、分类、构建 content blocks）
"""

from typing import Any, Dict, TYPE_CHECKING

from logger import get_logger

if TYPE_CHECKING:
    from services.conversation_service import ConversationService

logger = get_logger("query_utils")


def format_variables(variables: Dict[str, Any]) -> str:
    """
    格式化前端变量为文本
    
    纯粹的数据格式化，不涉及消息操作。
    调用方自行决定如何使用这段文本（如追加到消息）。
    
    Args:
        variables: 前端变量 {"location": {"value": "北京", "description": "..."}, ...}
        
    Returns:
        格式化后的文本，空 variables 返回空字符串
        
    Examples:
        >>> format_variables({"location": {"value": "Beijing"}})
        '[User Context]\\n- location: Beijing'
        
        >>> format_variables({})
        ''
    """
    if not variables:
        return ""
    
    lines = ["[User Context]"]
    
    for var_name, var_data in variables.items():
        if isinstance(var_data, dict):
            value = var_data.get("value", "")
            description = var_data.get("description", "")
            if value:
                if description:
                    lines.append(f"- {var_name}: {value} ({description})")
                else:
                    lines.append(f"- {var_name}: {value}")
        else:
            lines.append(f"- {var_name}: {var_data}")
    
    return "\n".join(lines)


async def apply_conversation_delta(
    conversation_service: "ConversationService",
    event: Dict[str, Any],
    conversation_id: str
) -> None:
    """
    应用 conversation_delta 事件到数据库
    
    Args:
        conversation_service: ConversationService 实例
        event: conversation_delta 事件
        conversation_id: 对话 ID
        
    支持的字段：
        {"data": {"title": "新标题"}}
        {"data": {"metadata": {...}}}
    """
    try:
        data = event.get("data", {})
        
        if "title" in data:
            await conversation_service.update_conversation(
                conversation_id=conversation_id,
                title=data["title"]
            )
            logger.info(f"📝 Conversation 标题已更新: {data['title']}")
            
        if "metadata" in data:
            await conversation_service.update_conversation(
                conversation_id=conversation_id,
                metadata=data["metadata"]
            )
            logger.info(f"📝 Conversation metadata 已更新")
            
    except Exception as e:
        logger.warning(f"⚠️ 处理 conversation_delta 失败: {str(e)}")

"""
消息工具函数 - Message Utilities

提供消息处理相关的通用工具函数：
- 消息格式标准化
- 消息内容提取
- dict <-> Message 对象转换

职责边界：
- 本模块：通用消息转换（dict <-> Message）
- core/llm/adaptor.py：LLM 厂商格式转换（Claude/OpenAI/Gemini）
"""

from typing import Any, List, Dict, Optional, TYPE_CHECKING

from logger import get_logger

# 避免循环导入
if TYPE_CHECKING:
    from core.llm import Message

logger = get_logger("message_utils")


def normalize_message_format(message: Any) -> List[Dict[str, str]]:
    """
    标准化消息格式为 Claude API 格式
    
    将各种格式的消息统一转换为：[{"type": "text", "text": "..."}]
    
    支持的输入格式：
    1. 标准格式：[{"type": "text", "text": "..."}] → 直接返回
    2. 纯文本：str → 转换为标准格式
    3. 其他格式：转换为字符串后包装
    
    Args:
        message: 消息内容（str 或 list）
        
    Returns:
        标准化后的消息列表
        
    Examples:
        >>> normalize_message_format("你好")
        [{"type": "text", "text": "你好"}]
        
        >>> normalize_message_format([{"type": "text", "text": "你好"}])
        [{"type": "text", "text": "你好"}]
    """
    # 格式1：已经是标准格式
    if isinstance(message, list):
        # 验证格式是否正确
        if all(isinstance(block, dict) and "type" in block for block in message):
            return message
        # 如果不是标准格式，尝试转换
        logger.warning(f"消息列表格式不标准，尝试转换")
    
    # 格式2：纯文本字符串
    if isinstance(message, str):
        return [{"type": "text", "text": message}]
    
    # 未知格式，尝试转换为字符串
    logger.warning(f"未知消息格式，尝试转换为字符串: {type(message)}")
    return [{"type": "text", "text": str(message)}]


def extract_text_from_message(message: Any) -> str:
    """
    从消息中提取纯文本内容
    
    支持多种格式，自动提取文本部分
    
    Args:
        message: 消息内容（str 或 list）
        
    Returns:
        提取的文本内容
        
    Examples:
        >>> extract_text_from_message("你好")
        "你好"
        
        >>> extract_text_from_message([{"type": "text", "text": "你好"}])
        "你好"
    """
    if isinstance(message, str):
        return message
    elif isinstance(message, list):
        # 从 content blocks 中提取文本
        for block in message:
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("text", "")
    return ""


# ============================================================
# dict <-> Message 转换函数
# ============================================================

def dict_list_to_messages(messages: List[Dict[str, Any]]) -> List["Message"]:
    """
    将 dict 列表转换为 Message 对象列表
    
    Args:
        messages: 消息字典列表 [{"role": "user", "content": "..."}]
        
    Returns:
        Message 对象列表
        
    Examples:
        >>> msgs = dict_list_to_messages([{"role": "user", "content": "你好"}])
        >>> msgs[0].role
        'user'
    """
    from core.llm import Message
    return [Message(role=msg["role"], content=msg["content"]) for msg in messages]


def messages_to_dict_list(messages: List["Message"]) -> List[Dict[str, Any]]:
    """
    将 Message 对象列表转换为 dict 列表（Claude API 格式）
    
    Args:
        messages: Message 对象列表
        
    Returns:
        消息字典列表 [{"role": "user", "content": "..."}]
        
    Examples:
        >>> from core.llm import Message
        >>> dicts = messages_to_dict_list([Message(role="user", content="你好")])
        >>> dicts[0]["role"]
        'user'
    """
    return [{"role": msg.role, "content": msg.content} for msg in messages]


def append_assistant_message(
    messages: List["Message"],
    raw_content: Any
) -> None:
    """
    追加 assistant 消息到列表
    
    Args:
        messages: Message 对象列表（会被修改）
        raw_content: 响应内容（通常是 response.raw_content）
    """
    from core.llm import Message
    messages.append(Message(role="assistant", content=raw_content))


def append_user_message(
    messages: List["Message"],
    content: Any
) -> None:
    """
    追加 user 消息到列表（工具结果等）
    
    Args:
        messages: Message 对象列表（会被修改）
        content: 消息内容（通常是 tool_results 列表）
    """
    from core.llm import Message
    messages.append(Message(role="user", content=content))


def append_text_to_last_block(
    content_blocks: List[Dict[str, Any]],
    text: str
) -> bool:
    """
    将文本追加到消息的最后一个 text block
    
    用于向用户消息中注入系统上下文（如前端变量、用户记忆等），
    保持用户 query 在前，系统注入信息在后。
    
    Args:
        content_blocks: 消息内容块列表（会被原地修改）
        text: 要追加的文本
        
    Returns:
        是否成功追加（找到 text block 并修改）
        
    Examples:
        >>> blocks = [{"type": "text", "text": "帮我创建一个项目"}]
        >>> append_text_to_last_block(blocks, "\\n---\\n[上下文]\\n- timezone: Asia/Shanghai")
        True
        >>> blocks[0]["text"]
        '帮我创建一个项目\\n---\\n[上下文]\\n- timezone: Asia/Shanghai'
    """
    if not text:
        return False
    
    # 从后往前找第一个 text block
    for i in range(len(content_blocks) - 1, -1, -1):
        block = content_blocks[i]
        if isinstance(block, dict) and block.get("type") == "text":
            block["text"] += text
            return True
    
    return False


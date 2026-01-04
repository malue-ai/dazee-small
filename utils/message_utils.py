"""
消息工具函数 - Message Utilities

提供消息处理相关的通用工具函数：
- 消息格式标准化
- 消息内容提取

"""

from typing import Any, List, Dict, Optional
from logger import get_logger

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


"""
Working Memory - 会话级短期记忆

职责：
- 存储当前会话的消息历史（messages）
- 存储工具调用记录（tool_calls）
- 存储临时元数据（metadata）

设计原则：
- 纯净版：不包含 plan/todo（由 plan_todo_tool 自己管理）
- 不包含 session_id（由上层 Agent/Service 管理）
- 会话结束后自动清除
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from logger import get_logger

logger = get_logger("memory.working")


class WorkingMemory:
    """
    工作记忆 - 当前会话的短期记忆
    
    存储内容：
    - messages: 消息历史
    - tool_calls: 工具调用记录
    - metadata: 临时元数据
    
    注意：此类不再包含 plan_json/todo_md/session_id
    """
    
    def __init__(self) -> None:
        self.messages: List[Dict[str, Any]] = []
        self.tool_calls: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        self._created_at = datetime.now()
    
    # ==================== 消息管理 ====================
    
    def add_message(self, role: str, content: Any) -> None:
        """
        添加消息
        
        Args:
            role: 角色（user/assistant/system）
            content: 消息内容
        """
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        
        content_preview = str(content)[:80] + '...' if len(str(content)) > 80 else str(content)
        logger.debug(f"💾 添加消息: role={role}, 总数={len(self.messages)}, 内容={content_preview}")
    
    def get_messages(self, last_n: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取消息历史
        
        Args:
            last_n: 只返回最近 N 条（None 则返回全部）
        """
        if last_n:
            return self.messages[-last_n:]
        return self.messages
    
    def clear_messages(self) -> None:
        """清空消息历史"""
        self.messages.clear()
    
    # ==================== 工具调用记录 ====================
    
    def add_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        result: Any = None
    ):
        """
        记录工具调用
        
        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
            result: 工具执行结果（可选）
        """
        self.tool_calls.append({
            "tool": tool_name,
            "input": tool_input,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_tool_history(self, last_n: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取工具调用历史
        
        Args:
            last_n: 只返回最近 N 条（None 则返回全部）
        """
        if last_n:
            return self.tool_calls[-last_n:]
        return self.tool_calls
    
    def clear_tool_history(self) -> None:
        """清空工具调用历史"""
        self.tool_calls.clear()
    
    # ==================== 元数据管理 ====================
    
    def update_metadata(self, key: str, value: Any) -> None:
        """更新元数据"""
        self.metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """获取元数据"""
        return self.metadata.get(key, default)
    
    def clear_metadata(self) -> None:
        """清空元数据"""
        self.metadata.clear()
    
    # ==================== 通用操作 ====================
    
    def clear(self) -> None:
        """清空所有工作记忆"""
        self.messages.clear()
        self.tool_calls.clear()
        self.metadata.clear()
        logger.debug("🧹 WorkingMemory 已清空")
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "messages": self.messages,
            "tool_calls": self.tool_calls,
            "metadata": self.metadata,
            "created_at": self._created_at.isoformat()
        }
    
    def summary(self) -> str:
        """
        获取摘要信息
        
        Returns:
            摘要字符串
        """
        return (
            f"WorkingMemory("
            f"messages={len(self.messages)}, "
            f"tool_calls={len(self.tool_calls)}, "
            f"metadata_keys={list(self.metadata.keys())})"
        )


def create_working_memory() -> WorkingMemory:
    """创建 WorkingMemory 实例"""
    return WorkingMemory()


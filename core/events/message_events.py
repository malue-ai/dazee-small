"""
Message 级事件管理

职责：管理 Message（消息/Turn）级别的事件
"""

from typing import Dict, Any, Optional
from core.events.base import BaseEventManager


class MessageEventManager(BaseEventManager):
    """
    Message 级事件管理器
    
    负责消息轮次相关的事件
    """
    
    async def emit_message_start(
        self,
        session_id: str,
        message_id: str,
        model: str
    ) -> Dict[str, Any]:
        """
        发送 message_start 事件（符合 Claude API 标准）
        
        Args:
            session_id: Session ID
            message_id: 消息ID
            model: 模型名称
            
        Returns:
            事件对象
        """
        event = {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": 0
                }
            },
            "timestamp": self._get_timestamp()
        }
        
        return await self._send_event(session_id, event)
    
    async def emit_message_delta(
        self,
        session_id: str,
        stop_reason: Optional[str] = None,
        output_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        发送 message_delta 事件
        
        Args:
            session_id: Session ID
            stop_reason: 停止原因
            output_tokens: 输出 token 数（累积值）
            
        Returns:
            事件对象
        """
        delta = {}
        if stop_reason:
            delta["stop_reason"] = stop_reason
        
        usage = {}
        if output_tokens is not None:
            usage["output_tokens"] = output_tokens
        
        event = self._create_event(
            event_type="message_delta",
            data={
                "delta": delta,
                "usage": usage
            }
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_message_stop(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        发送 message_stop 事件
        
        Args:
            session_id: Session ID
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="message_stop",
            data={}
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_tool_call_start(
        self,
        session_id: str,
        tool_call_id: str,
        tool_name: str,
        tool_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送 tool_call_start 事件
        
        Args:
            session_id: Session ID
            tool_call_id: 工具调用ID
            tool_name: 工具名称
            tool_input: 工具输入参数
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="tool_call_start",
            data={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "input": tool_input
            }
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_tool_call_complete(
        self,
        session_id: str,
        tool_call_id: str,
        tool_name: str,
        status: str,
        result: Any,
        duration_ms: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        发送 tool_call_complete 事件
        
        Args:
            session_id: Session ID
            tool_call_id: 工具调用ID
            tool_name: 工具名称
            status: 状态（success/error）
            result: 执行结果
            duration_ms: 执行耗时（毫秒）
            
        Returns:
            事件对象
        """
        event_data = {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "status": status,
            "result": result
        }
        
        if duration_ms is not None:
            event_data["duration_ms"] = duration_ms
        
        event = self._create_event(
            event_type="tool_call_complete",
            data=event_data
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_tool_call_error(
        self,
        session_id: str,
        tool_call_id: str,
        tool_name: str,
        error_type: str,
        error_message: str
    ) -> Dict[str, Any]:
        """
        发送 tool_call_error 事件
        
        Args:
            session_id: Session ID
            tool_call_id: 工具调用ID
            tool_name: 工具名称
            error_type: 错误类型
            error_message: 错误消息
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="tool_call_error",
            data={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "error": {
                    "type": error_type,
                    "message": error_message
                }
            }
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_plan_step_start(
        self,
        session_id: str,
        step_index: int,
        action: str,
        capability: str,
        message_id: str
    ) -> Dict[str, Any]:
        """
        发送 plan_step_start 事件
        
        Args:
            session_id: Session ID
            step_index: 步骤索引
            action: 动作描述
            capability: 能力类型
            message_id: 消息ID
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="plan_step_start",
            data={
                "step_index": step_index,
                "action": action,
                "capability": capability,
                "message_id": message_id
            }
        )
        
        return await self._send_event(session_id, event)
    
    async def emit_plan_step_complete(
        self,
        session_id: str,
        step_index: int,
        status: str,
        result: str,
        message_id: str
    ) -> Dict[str, Any]:
        """
        发送 plan_step_complete 事件
        
        Args:
            session_id: Session ID
            step_index: 步骤索引
            status: 状态（completed/failed）
            result: 执行结果
            message_id: 消息ID
            
        Returns:
            事件对象
        """
        event = self._create_event(
            event_type="plan_step_complete",
            data={
                "step_index": step_index,
                "status": status,
                "result": result,
                "message_id": message_id
            }
        )
        
        return await self._send_event(session_id, event)
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳（ISO格式）"""
        from datetime import datetime
        return datetime.now().isoformat()


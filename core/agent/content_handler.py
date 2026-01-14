"""
ContentHandler - 统一的 Content Block 处理器

职责：
1. 统一处理所有 Content Block 类型（text, thinking, tool_use, tool_result）
2. 管理 BlockState（开始/关闭 block）
3. 调用 EventBroadcaster 发送 SSE 事件
4. 支持流式和非流式两种发送模式

设计原则：
- 单一职责：只负责 Content Block 的发送逻辑
- 统一抽象：所有内容类型使用相同的接口
- 事件驱动：流式/非流式只是事件序列的区别
  - 非流式：content_start → content_stop
  - 流式：content_start → content_delta × N → content_stop

使用方式：
    handler = ContentHandler(broadcaster, ctx.block)
    
    # 非流式发送
    await handler.emit_block(session_id, "tool_result", {
        "tool_use_id": "xxx",
        "content": "执行结果",
        "is_error": False
    })
    
    # 流式发送
    async for event in handler.emit_block_stream(
        session_id, "text", {}, text_generator()
    ):
        yield event
"""

import json
from typing import Dict, Any, Optional, AsyncGenerator, Union

from logger import get_logger

logger = get_logger(__name__)


class ContentHandler:
    """
    统一的 Content Block 处理器
    
    所有内容类型（text, thinking, tool_use, tool_result）使用相同的抽象
    
    EventBroadcaster 会自动处理：
    - 累积内容到 ContentAccumulator
    - 消息持久化（checkpoint + 最终保存）
    
    本类负责：
    - 管理 BlockState（开始/关闭 block）
    - 构建 content_block 结构
    - 选择流式/非流式发送模式
    """
    
    def __init__(self, broadcaster, block_state):
        """
        初始化 ContentHandler
        
        Args:
            broadcaster: EventBroadcaster 实例
            block_state: BlockState 实例（来自 RuntimeContext.block）
        """
        self.broadcaster = broadcaster
        self.block_state = block_state
    
    # ==================== 非流式发送 ====================
    
    async def emit_block(
        self,
        session_id: str,
        block_type: str,
        content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        发送完整 content block（非流式）
        
        事件序列：content_start → content_stop
        
        Args:
            session_id: Session ID
            block_type: "text" | "thinking" | "tool_use" | "tool_result"
            content: 内容数据，根据类型不同：
                - text: {"text": "..."}
                - thinking: {"thinking": "...", "signature": "..."}
                - tool_use: {"id": "...", "name": "...", "input": {...}}
                - tool_result: {"tool_use_id": "...", "content": "...", "is_error": bool}
                
        Returns:
            最后一个事件对象（content_stop）
        """
        # 关闭之前的 block（如果有）
        if self.block_state.is_block_open():
            await self.broadcaster.emit_content_stop(
                session_id=session_id,
                index=self.block_state.current_index
            )
            self.block_state.close_current_block()
        
        # 开始新 block
        index = self.block_state.start_new_block(block_type)
        content_block = self._build_content_block(block_type, content)
        
        # 发送 content_start（完整内容）
        await self.broadcaster.emit_content_start(
            session_id=session_id,
            index=index,
            content_block=content_block
        )
        
        # 发送 content_stop
        result = await self.broadcaster.emit_content_stop(
            session_id=session_id,
            index=index
        )
        
        self.block_state.close_current_block()
        return result
    
    # ==================== 流式发送 ====================
    
    async def emit_block_stream(
        self,
        session_id: str,
        block_type: str,
        initial: Dict[str, Any],
        delta_source: AsyncGenerator[str, None]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        发送流式 content block
        
        事件序列：content_start → content_delta × N → content_stop
        
        Args:
            session_id: Session ID
            block_type: "text" | "thinking" | "tool_use" | "tool_result"
            initial: 初始内容（用于 content_start，通常为空或部分数据）
            delta_source: 异步生成器，产生字符串增量
            
        Yields:
            事件对象（content_start, content_delta, content_stop）
        """
        # 关闭之前的 block（如果有）
        if self.block_state.is_block_open():
            yield await self.broadcaster.emit_content_stop(
                session_id=session_id,
                index=self.block_state.current_index
            )
            self.block_state.close_current_block()
        
        # 开始新 block
        index = self.block_state.start_new_block(block_type)
        content_block = self._build_content_block(block_type, initial, is_stream_start=True)
        
        # 发送 content_start（初始内容，通常为空）
        yield await self.broadcaster.emit_content_start(
            session_id=session_id,
            index=index,
            content_block=content_block
        )
        
        # 发送 content_delta（流式内容）
        async for delta in delta_source:
            yield await self.broadcaster.emit_content_delta(
                session_id=session_id,
                index=index,
                delta=delta
            )
        
        # 发送 content_stop
        yield await self.broadcaster.emit_content_stop(
            session_id=session_id,
            index=index
        )
        
        self.block_state.close_current_block()
    
    # ==================== 单步发送（细粒度控制）====================
    
    async def start_block(
        self,
        session_id: str,
        block_type: str,
        initial: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        开始一个新 block（手动控制模式）
        
        用于需要细粒度控制的场景，如 LLM 流式响应处理
        
        Args:
            session_id: Session ID
            block_type: block 类型
            initial: 初始内容
            
        Returns:
            content_start 事件对象
        """
        # 关闭之前的 block（如果有）
        if self.block_state.is_block_open():
            await self.broadcaster.emit_content_stop(
                session_id=session_id,
                index=self.block_state.current_index
            )
            self.block_state.close_current_block()
        
        index = self.block_state.start_new_block(block_type)
        content_block = self._build_content_block(block_type, initial or {}, is_stream_start=True)
        
        return await self.broadcaster.emit_content_start(
            session_id=session_id,
            index=index,
            content_block=content_block
        )
    
    async def send_delta(
        self,
        session_id: str,
        delta: str
    ) -> Dict[str, Any]:
        """
        发送增量内容（手动控制模式）
        
        Args:
            session_id: Session ID
            delta: 增量内容字符串
            
        Returns:
            content_delta 事件对象
        """
        if not self.block_state.is_block_open():
            logger.warning("尝试发送 delta 但没有打开的 block")
            return {}
        
        return await self.broadcaster.emit_content_delta(
            session_id=session_id,
            index=self.block_state.current_index,
            delta=delta
        )
    
    async def stop_block(
        self,
        session_id: str,
        signature: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        关闭当前 block（手动控制模式）
        
        Args:
            session_id: Session ID
            signature: thinking 的签名（可选）
            
        Returns:
            content_stop 事件对象
        """
        if not self.block_state.is_block_open():
            logger.warning("尝试关闭 block 但没有打开的 block")
            return {}
        
        result = await self.broadcaster.emit_content_stop(
            session_id=session_id,
            index=self.block_state.current_index,
            signature=signature
        )
        
        self.block_state.close_current_block()
        return result
    
    # ==================== 状态查询 ====================
    
    def is_block_open(self) -> bool:
        """检查是否有打开的 block"""
        return self.block_state.is_block_open()
    
    def needs_transition(self, new_type: str) -> bool:
        """检查是否需要切换 block 类型"""
        return self.block_state.needs_transition(new_type)
    
    @property
    def current_index(self) -> Optional[int]:
        """获取当前 block 索引"""
        return self.block_state.current_index
    
    @property
    def current_type(self) -> Optional[str]:
        """获取当前 block 类型"""
        return self.block_state.current_type
    
    # ==================== 辅助方法 ====================
    
    def _build_content_block(
        self,
        block_type: str,
        content: Dict[str, Any],
        is_stream_start: bool = False
    ) -> Dict[str, Any]:
        """
        构建 content_block 结构
        
        Args:
            block_type: "text" | "thinking" | "tool_use" | "tool_result"
            content: 内容数据
            is_stream_start: 是否是流式开始（内容字段为空）
            
        Returns:
            content_block 字典
        """
        if block_type == "text":
            return {
                "type": "text",
                "text": "" if is_stream_start else content.get("text", "")
            }
        
        elif block_type == "thinking":
            block = {
                "type": "thinking",
                "thinking": "" if is_stream_start else content.get("thinking", "")
            }
            if content.get("signature"):
                block["signature"] = content["signature"]
            return block
        
        elif block_type == "tool_use":
            return {
                "type": "tool_use",
                "id": content.get("id", ""),
                "name": content.get("name", ""),
                "input": {} if is_stream_start else content.get("input", {})
            }
        
        elif block_type == "tool_result":
            # tool_result 的 content 可能是字符串或对象
            result_content = content.get("content", "")
            if not isinstance(result_content, str):
                result_content = json.dumps(result_content, ensure_ascii=False)
            
            return {
                "type": "tool_result",
                "tool_use_id": content.get("tool_use_id", ""),
                "content": "" if is_stream_start else result_content,
                "is_error": content.get("is_error", False)
            }
        
        elif block_type == "server_tool_use":
            # 服务端工具（如 web_search）
            return {
                "type": "tool_use",  # 统一为 tool_use，前端不需要知道是服务端
                "id": content.get("id", ""),
                "name": content.get("name", ""),
                "input": content.get("input", {})
            }
        
        else:
            # 未知类型，直接返回
            logger.warning(f"未知的 block_type: {block_type}")
            return {"type": block_type, **content}


def create_content_handler(broadcaster, block_state) -> ContentHandler:
    """
    创建 ContentHandler 实例
    
    Args:
        broadcaster: EventBroadcaster 实例
        block_state: BlockState 实例（来自 RuntimeContext.block）
        
    Returns:
        ContentHandler 实例
    """
    return ContentHandler(broadcaster=broadcaster, block_state=block_state)


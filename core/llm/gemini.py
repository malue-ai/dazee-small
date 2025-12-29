"""
Gemini LLM 服务实现（占位）

TODO: 实现 Gemini Pro / Ultra 支持

参考：
- https://ai.google.dev/docs
"""

from typing import Dict, Any, Optional, List, Union, AsyncIterator, Callable

from .base import (
    BaseLLMService,
    LLMConfig,
    LLMResponse,
    Message,
    ToolType
)


class GeminiLLMService(BaseLLMService):
    """
    Gemini LLM 服务实现
    
    TODO: 实现以下功能
    - Gemini Pro / Ultra 支持
    - Function Calling
    - Streaming
    - 响应格式转换（转为 Claude 兼容格式）
    """
    
    def __init__(self, config: LLMConfig):
        """初始化 Gemini 服务"""
        self.config = config
        # TODO: 初始化 Gemini 客户端
        raise NotImplementedError("Gemini service not implemented yet")
    
    async def create_message_async(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        tools: Optional[List[Union[ToolType, str, Dict]]] = None,
        **kwargs
    ) -> LLMResponse:
        """创建消息（异步）"""
        raise NotImplementedError("Gemini service not implemented yet")
    
    async def create_message_stream(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        tools: Optional[List[Union[ToolType, str, Dict]]] = None,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_content: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[Dict], None]] = None,
        **kwargs
    ) -> AsyncIterator[LLMResponse]:
        """创建消息（流式）"""
        raise NotImplementedError("Gemini service not implemented yet")
        yield  # 使其成为生成器
    
    def count_tokens(self, text: str) -> int:
        """计算 token 数量"""
        if not text:
            return 0
        return max(1, len(text) // 4)


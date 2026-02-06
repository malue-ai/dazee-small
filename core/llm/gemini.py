"""
Gemini LLM 服务实现（占位）

TODO: 实现 Gemini Pro / Ultra 支持

参考：
- https://ai.google.dev/docs
"""

from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

from .base import BaseLLMService, LLMConfig, LLMResponse, Message, ToolType


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
        """
        计算 token 数量

        TODO: 使用 Gemini 官方 API 精确计算
        - model.count_tokens() 方法
        - 参考: https://ai.google.dev/gemini-api/docs/tokens

        当前使用父类的 tiktoken 实现（近似）。

        Args:
            text: 要计算的文本

        Returns:
            token 数量
        """
        # TODO: 实现 Gemini 官方 token 计算
        return super().count_tokens(text)


# ============================================================
# 注册到 LLMRegistry
# ============================================================


def _register_gemini():
    """延迟注册 Gemini Provider（避免循环导入）"""
    from .adaptor import GeminiAdaptor
    from .registry import LLMRegistry

    LLMRegistry.register(
        name="gemini",
        service_class=GeminiLLMService,
        adaptor_class=GeminiAdaptor,
        default_model="gemini-pro",
        api_key_env="GOOGLE_API_KEY",
        display_name="Gemini",
        description="Google Gemini 系列模型（待实现）",
        supported_features=[
            "streaming",
            "tool_calling",
        ],
    )


# 模块加载时注册
_register_gemini()

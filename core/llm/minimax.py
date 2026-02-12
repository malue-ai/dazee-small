"""
MiniMax LLM 服务实现

基于 Anthropic API 兼容接口实现，使用 Anthropic SDK 连接 MiniMax 服务。
与 Claude 服务保持相同的消息格式和工具调用协议。

支持的功能：
- 基础对话（流式/非流式）
- Function Calling（工具调用）
- 思考模式（thinking）
- 流式断连重试与降级

模型系列：
- MiniMax-M2.1:           旗舰模型，~60 tps
- MiniMax-M2.1-lightning:  极速版，~100 tps
- MiniMax-M2:             Agent/Coding 专精

参考文档：
- https://platform.minimaxi.com/docs/api-reference/text-anthropic-api
"""

import os
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

import anthropic
import httpx

from infra.resilience import with_retry
from logger import get_logger

from .adaptor import ClaudeAdaptor
from .base import BaseLLMService, LLMConfig, LLMProvider, LLMResponse, Message, ToolType

logger = get_logger("llm.minimax")


# ============================================================
# MiniMax 常量与模型能力
# ============================================================

class MiniMaxEndpoints:
    """MiniMax API 端点"""

    # Anthropic 兼容端点（推荐）
    ANTHROPIC = "https://api.minimaxi.com/anthropic"


class MiniMaxModelCapability:
    """MiniMax model capability detection"""

    # 支持思考模式的模型
    THINKING_MODELS = {
        "MiniMax-M2.1",
        "MiniMax-M2.1-lightning",
        "MiniMax-M2",
    }

    # 支持 Function Calling 的模型
    TOOL_CALLING_MODELS = {
        "MiniMax-M2.1",
        "MiniMax-M2.1-lightning",
        "MiniMax-M2",
    }

    @staticmethod
    def supports_thinking(model: str) -> bool:
        """Check if model supports thinking mode"""
        return any(m in model for m in MiniMaxModelCapability.THINKING_MODELS)

    @staticmethod
    def supports_tools(model: str) -> bool:
        """Check if model supports tool calling"""
        return any(m in model for m in MiniMaxModelCapability.TOOL_CALLING_MODELS)

    @staticmethod
    def get_max_tokens(model: str) -> int:
        """Get max output tokens for the model"""
        # MiniMax M2 系列默认 max_tokens
        return 32768


# ============================================================
# MiniMax LLM 服务
# ============================================================


class MiniMaxLLMService(BaseLLMService):
    """
    MiniMax LLM 服务实现

    基于 Anthropic API 兼容接口 (https://api.minimaxi.com/anthropic)，
    使用 Anthropic SDK，与 Claude 服务保持相同的消息格式。

    使用示例：
    ```python
    config = LLMConfig(
        provider=LLMProvider.MINIMAX,
        model="MiniMax-M2.1",
        api_key=os.getenv("MINIMAX_API_KEY"),
        enable_thinking=True
    )
    llm = MiniMaxLLMService(config)

    response = await llm.create_message_async(
        messages=[Message(role="user", content="Hello")],
        system="You are helpful"
    )
    ```
    """

    def __init__(self, config: LLMConfig):
        """
        Initialize MiniMax service.

        Args:
            config: LLM configuration
        """
        self.config = config

        # Message adaptor (reuse Claude format — MiniMax is Anthropic API compatible)
        self._adaptor = ClaudeAdaptor()

        # API Key (priority: config > env)
        api_key = config.api_key or os.getenv("MINIMAX_API_KEY")
        if not api_key:
            raise ValueError(
                "MiniMax API Key 未设置。请设置 MINIMAX_API_KEY 环境变量或传入 api_key 参数"
            )

        masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
        logger.info(f"🔑 MiniMax API Key: {masked_key} (长度: {len(api_key)})")

        # API endpoint (priority: config.base_url > env > default)
        base_url = (
            getattr(config, "base_url", None)
            or os.getenv("MINIMAX_BASE_URL")
            or MiniMaxEndpoints.ANTHROPIC
        )
        logger.info(f"🌐 MiniMax 端点: {base_url}")

        # Initialize Anthropic-compatible client
        timeout = getattr(config, "timeout", 120.0)
        max_retries = getattr(config, "max_retries", 3)

        self.async_client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

        # Custom tool storage
        self._custom_tools: List[Dict[str, Any]] = []

        logger.info(f"✅ MiniMax 服务初始化成功: model={self.config.model}")

    # ============================================================
    # Custom tool management
    # ============================================================

    def add_custom_tool(self, name: str, description: str, input_schema: Dict[str, Any]) -> None:
        """Add a custom tool."""
        for i, tool in enumerate(self._custom_tools):
            if tool["name"] == name:
                self._custom_tools[i] = {
                    "name": name,
                    "description": description,
                    "input_schema": input_schema,
                }
                logger.debug(f"更新自定义工具: {name}")
                return

        self._custom_tools.append(
            {"name": name, "description": description, "input_schema": input_schema}
        )
        logger.debug(f"注册自定义工具: {name}")

    def remove_custom_tool(self, name: str) -> bool:
        """Remove a custom tool."""
        for i, tool in enumerate(self._custom_tools):
            if tool["name"] == name:
                self._custom_tools.pop(i)
                logger.debug(f"移除自定义工具: {name}")
                return True
        return False

    def get_custom_tools(self) -> List[Dict[str, Any]]:
        """Get all custom tools."""
        return self._custom_tools.copy()

    def clear_custom_tools(self) -> None:
        """Clear all custom tools."""
        self._custom_tools.clear()
        logger.debug("清空所有自定义工具")

    def _format_tools(self, tools: List[Union[ToolType, str, Dict]]) -> List[Dict[str, Any]]:
        """
        Format tool list for Anthropic tool format.

        Supports three input types:
        1. ToolType enum (skipped)
        2. String (tool name, looked up from custom tools)
        3. Complete schema dict (Anthropic native format)
        """
        formatted = []

        for tool in tools:
            if isinstance(tool, ToolType):
                continue
            elif isinstance(tool, str):
                for custom_tool in self._custom_tools:
                    if custom_tool.get("name") == tool:
                        formatted.append(custom_tool.copy())
                        break
            elif isinstance(tool, dict):
                # Anthropic native format: {name, description, input_schema}
                formatted.append(tool.copy())
            else:
                logger.warning(f"未知工具格式: {type(tool)}")

        return formatted

    # ============================================================
    # Core API methods
    # ============================================================

    @with_retry(
        max_retries=3,
        base_delay=1.0,
        retryable_errors=(
            httpx.RemoteProtocolError,
            httpx.ConnectError,
            httpx.TimeoutException,
        ),
    )
    async def create_message_async(
        self,
        messages: List[Message],
        system: Optional[Union[str, List[Dict[str, Any]]]] = None,
        tools: Optional[List[Union[ToolType, str, Dict]]] = None,
        invocation_type: Optional[str] = None,
        override_thinking: Optional[bool] = None,
        is_probe: bool = False,
        **kwargs,
    ) -> LLMResponse:
        """
        Create message (async, non-streaming).

        Args:
            messages: Message list
            system: System prompt (string or block list)
            tools: Tool list
            invocation_type: Invocation type (unused)
            override_thinking: Dynamic thinking override
            is_probe: Whether this is a probe request
            **kwargs: Additional parameters

        Returns:
            LLMResponse
        """
        # Convert messages via Claude adaptor (MiniMax uses same format)
        converted = self._adaptor.convert_messages_to_provider(messages)
        formatted_messages = converted["messages"]

        # Build request
        request_params: Dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": formatted_messages,
        }

        # System prompt
        if system:
            if isinstance(system, list):
                # Multi-block format — strip cache_control (MiniMax doesn't support caching)
                system_blocks = []
                for block in system:
                    if isinstance(block, dict):
                        clean_block = {k: v for k, v in block.items()
                                       if k not in ("cache_control", "_cache_layer")}
                        system_blocks.append(clean_block)
                    else:
                        system_blocks.append({"type": "text", "text": str(block)})
                request_params["system"] = system_blocks
            else:
                request_params["system"] = str(system)

        # Thinking mode
        effective_thinking = (
            override_thinking
            if override_thinking is not None
            else getattr(self.config, "enable_thinking", False)
        )
        if effective_thinking and MiniMaxModelCapability.supports_thinking(self.config.model):
            request_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": getattr(self.config, "thinking_budget", 10000),
            }
            # MiniMax temperature range: (0.0, 1.0], recommended 1.0 with thinking
            request_params["temperature"] = 1.0
        else:
            request_params["temperature"] = kwargs.get(
                "temperature", self.config.temperature
            )

        # Tools
        all_tools: List[Dict[str, Any]] = []
        tool_names_seen: set = set()

        if tools:
            for tool in self._format_tools(tools):
                tool_name = tool.get("name", "")
                if tool_name and tool_name not in tool_names_seen:
                    all_tools.append(tool)
                    tool_names_seen.add(tool_name)

        for custom_tool in self._custom_tools:
            tool_name = custom_tool.get("name", "")
            if tool_name and tool_name not in tool_names_seen:
                all_tools.append(custom_tool.copy())
                tool_names_seen.add(tool_name)

        if all_tools:
            request_params["tools"] = all_tools
            tool_choice = kwargs.get("tool_choice")
            if tool_choice:
                request_params["tool_choice"] = tool_choice

        logger.debug(
            f"📤 MiniMax 请求: model={self.config.model}, "
            f"messages={len(formatted_messages)}, "
            f"tools={len(all_tools)}"
        )

        # API call
        try:
            response = await self.async_client.messages.create(**request_params)
        except Exception as e:
            if not is_probe:
                logger.error(f"MiniMax API 调用失败: {e}")
            raise

        return self._parse_response(response)

    async def create_message_stream(
        self,
        messages: List[Message],
        system: Optional[Union[str, List[Dict[str, Any]]]] = None,
        tools: Optional[List[Union[ToolType, str, Dict]]] = None,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_content: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[Dict], None]] = None,
        override_thinking: Optional[bool] = None,
        **kwargs,
    ) -> AsyncIterator[LLMResponse]:
        """
        Create message (streaming).

        Args:
            messages: Message list
            system: System prompt
            tools: Tool list
            on_thinking: Thinking callback
            on_content: Content callback
            on_tool_call: Tool call callback
            override_thinking: Dynamic thinking override
            **kwargs: Additional parameters

        Yields:
            LLMResponse fragments
        """
        # Convert messages
        converted = self._adaptor.convert_messages_to_provider(messages)
        formatted_messages = converted["messages"]

        # Build request params (same as async)
        request_params: Dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "messages": formatted_messages,
        }

        # System prompt (strip cache_control)
        if system:
            if isinstance(system, list):
                system_blocks = []
                for block in system:
                    if isinstance(block, dict):
                        clean_block = {k: v for k, v in block.items()
                                       if k not in ("cache_control", "_cache_layer")}
                        system_blocks.append(clean_block)
                    else:
                        system_blocks.append({"type": "text", "text": str(block)})
                request_params["system"] = system_blocks
            else:
                request_params["system"] = str(system)

        # Thinking mode
        effective_thinking = (
            override_thinking
            if override_thinking is not None
            else getattr(self.config, "enable_thinking", False)
        )
        if effective_thinking and MiniMaxModelCapability.supports_thinking(self.config.model):
            request_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": getattr(self.config, "thinking_budget", 10000),
            }
            request_params["temperature"] = 1.0
        else:
            request_params["temperature"] = kwargs.get(
                "temperature", self.config.temperature
            )

        # Tools
        all_tools: List[Dict[str, Any]] = []
        tool_names_seen: set = set()

        if tools:
            for tool in self._format_tools(tools):
                tool_name = tool.get("name", "")
                if tool_name and tool_name not in tool_names_seen:
                    all_tools.append(tool)
                    tool_names_seen.add(tool_name)

        for custom_tool in self._custom_tools:
            tool_name = custom_tool.get("name", "")
            if tool_name and tool_name not in tool_names_seen:
                all_tools.append(custom_tool.copy())
                tool_names_seen.add(tool_name)

        if all_tools:
            request_params["tools"] = all_tools
            tool_choice = kwargs.get("tool_choice")
            if tool_choice:
                request_params["tool_choice"] = tool_choice

        logger.info(
            f"📤 MiniMax 流式请求: model={self.config.model}, "
            f"messages={len(formatted_messages)}"
        )

        # Accumulation variables
        accumulated_thinking = ""
        accumulated_content = ""
        tool_calls: List[Dict[str, Any]] = []
        stop_reason = None
        usage: Dict[str, int] = {}
        final_message = None

        # Stream retry config
        _STREAM_MAX_RETRIES = 2
        _stream_attempt = 0

        try:
            stream_ctx = self.async_client.messages.stream(**request_params)
            async with stream_ctx as stream:
                async for event in stream:
                    if event.type == "content_block_start":
                        block = event.content_block
                        if block.type == "thinking" and on_thinking:
                            on_thinking("")
                        elif block.type == "text" and on_content:
                            on_content("")
                        elif block.type == "tool_use":
                            tool_id = getattr(block, "id", "")
                            tool_name = getattr(block, "name", "")
                            if on_tool_call:
                                on_tool_call({
                                    "id": tool_id,
                                    "name": tool_name,
                                    "input": {},
                                    "type": "tool_use",
                                })
                            yield LLMResponse(
                                content="",
                                model=self.config.model,
                                is_stream=True,
                                tool_use_start={
                                    "type": "tool_use",
                                    "id": tool_id,
                                    "name": tool_name,
                                },
                            )

                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "thinking_delta":
                            text = getattr(delta, "thinking", "")
                            accumulated_thinking += text
                            if on_thinking:
                                on_thinking(text)
                            yield LLMResponse(
                                content="",
                                thinking=text,
                                model=self.config.model,
                                is_stream=True,
                            )
                        elif delta.type == "text_delta":
                            text = getattr(delta, "text", "")
                            accumulated_content += text
                            if on_content:
                                on_content(text)
                            yield LLMResponse(
                                content=text,
                                model=self.config.model,
                                is_stream=True,
                            )
                        elif delta.type == "input_json_delta":
                            partial_json = getattr(delta, "partial_json", "")
                            if on_tool_call:
                                on_tool_call({
                                    "partial_input": partial_json,
                                    "type": "input_delta",
                                })
                            yield LLMResponse(
                                content="",
                                model=self.config.model,
                                is_stream=True,
                                input_delta=partial_json,
                            )

                    elif event.type == "message_stop":
                        final_message = await stream.get_final_message()
                        stop_reason = getattr(final_message, "stop_reason", None)

                        # Extract usage
                        if hasattr(final_message, "usage") and final_message.usage:
                            usage = {
                                "input_tokens": final_message.usage.input_tokens,
                                "output_tokens": final_message.usage.output_tokens,
                                "thinking_tokens": 0,
                            }
                            if accumulated_thinking:
                                usage["thinking_tokens"] = self.count_tokens(
                                    accumulated_thinking
                                )
                            logger.info(
                                f"📊 Token 使用: "
                                f"input={usage['input_tokens']:,}, "
                                f"output={usage['output_tokens']:,}, "
                                f"thinking={usage['thinking_tokens']:,}"
                            )

                        # Extract tool calls from final message
                        if hasattr(final_message, "content"):
                            for block in final_message.content:
                                if block.type == "tool_use":
                                    tool_calls.append({
                                        "id": getattr(block, "id", ""),
                                        "name": getattr(block, "name", ""),
                                        "input": getattr(block, "input", {}),
                                        "type": "tool_use",
                                    })

        except (
            httpx.RemoteProtocolError,
            httpx.ConnectError,
            httpx.TimeoutException,
        ) as stream_error:
            _stream_attempt += 1
            logger.warning(
                f"⚠️ MiniMax 流式中断 (attempt {_stream_attempt}/{_STREAM_MAX_RETRIES}): "
                f"{stream_error}"
            )

            if _stream_attempt <= _STREAM_MAX_RETRIES and not tool_calls:
                import asyncio as _asyncio
                import random as _random

                delay = _random.uniform(0, min(1.0 * (2 ** (_stream_attempt - 1)), 60.0))
                logger.info(f"🔄 {delay:.1f}s 后回退到非流式调用...")
                await _asyncio.sleep(delay)

                try:
                    fallback_response = await self.create_message_async(
                        messages=messages,
                        system=system,
                        tools=tools,
                        override_thinking=override_thinking,
                        **kwargs,
                    )
                    yield fallback_response
                    return
                except Exception as fallback_err:
                    logger.error(f"❌ MiniMax 非流式 fallback 也失败: {fallback_err}")

            if accumulated_content or accumulated_thinking:
                raw_content = self._build_raw_content_from_parts(
                    accumulated_thinking, accumulated_content, []
                )
                yield LLMResponse(
                    content=accumulated_content,
                    thinking=accumulated_thinking if accumulated_thinking else None,
                    stop_reason="stream_error",
                    model=self.config.model,
                    raw_content=raw_content,
                    is_stream=False,
                )
                return
            raise

        except Exception as e:
            logger.error(f"MiniMax 流式传输错误: {e}")
            if accumulated_content or accumulated_thinking:
                raw_content = self._build_raw_content_from_parts(
                    accumulated_thinking, accumulated_content, []
                )
                yield LLMResponse(
                    content=accumulated_content,
                    thinking=accumulated_thinking if accumulated_thinking else None,
                    stop_reason="stream_error",
                    model=self.config.model,
                    raw_content=raw_content,
                    is_stream=False,
                )
                return
            raise

        # Build raw_content from final message or accumulated parts
        if final_message and hasattr(final_message, "content"):
            raw_content = self._build_raw_content(final_message)
        else:
            raw_content = self._build_raw_content_from_parts(
                accumulated_thinking, accumulated_content, tool_calls
            )

        logger.info(f"📥 MiniMax 响应: stop_reason={stop_reason or 'end_turn'}")

        # Final response
        yield LLMResponse(
            content=accumulated_content,
            thinking=accumulated_thinking if accumulated_thinking else None,
            tool_calls=tool_calls if tool_calls else None,
            stop_reason=stop_reason or "end_turn",
            usage=usage if usage else None,
            model=self.config.model,
            raw_content=raw_content,
            is_stream=False,
        )

    def count_tokens(self, text: str) -> int:
        """Count tokens (approximate, using tiktoken cl100k_base)."""
        return super().count_tokens(text)

    # ============================================================
    # Helper methods
    # ============================================================

    def _parse_response(self, response) -> LLMResponse:
        """
        Parse Anthropic-format response into unified LLMResponse.

        Args:
            response: Anthropic Messages API response

        Returns:
            LLMResponse
        """
        content_text = ""
        thinking_text = None
        tool_calls = []

        for block in response.content:
            if block.type == "thinking":
                thinking_text = getattr(block, "thinking", "")
            elif block.type == "text":
                content_text += getattr(block, "text", "")
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": getattr(block, "id", ""),
                    "name": getattr(block, "name", ""),
                    "input": getattr(block, "input", {}),
                    "type": "tool_use",
                })

        # Usage
        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "thinking_tokens": 0,
            }
            if thinking_text:
                usage["thinking_tokens"] = self.count_tokens(thinking_text)

            logger.info(
                f"📊 Token 使用: "
                f"input={usage['input_tokens']:,}, "
                f"output={usage['output_tokens']:,}, "
                f"thinking={usage['thinking_tokens']:,}"
            )

        # Build raw_content
        raw_content = self._build_raw_content(response)

        return LLMResponse(
            content=content_text,
            thinking=thinking_text,
            tool_calls=tool_calls if tool_calls else None,
            stop_reason=response.stop_reason or "end_turn",
            usage=usage,
            model=self.config.model,
            raw_content=raw_content,
        )

    @staticmethod
    def _build_raw_content(response) -> List[Dict[str, Any]]:
        """Build raw_content from Anthropic response."""
        raw_content: List[Dict[str, Any]] = []
        for block in response.content:
            if block.type == "thinking":
                raw_content.append({
                    "type": "thinking",
                    "thinking": getattr(block, "thinking", ""),
                    "signature": getattr(block, "signature", ""),
                })
            elif block.type == "text":
                raw_content.append({"type": "text", "text": getattr(block, "text", "")})
            elif block.type == "tool_use":
                raw_content.append({
                    "type": "tool_use",
                    "id": getattr(block, "id", ""),
                    "name": getattr(block, "name", ""),
                    "input": getattr(block, "input", {}),
                })
        return raw_content

    @staticmethod
    def _build_raw_content_from_parts(
        thinking: str, content: str, tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Build raw_content from accumulated parts."""
        raw_content: List[Dict[str, Any]] = []
        if thinking:
            raw_content.append({"type": "thinking", "thinking": thinking})
        if content:
            raw_content.append({"type": "text", "text": content})
        for tc in tool_calls:
            raw_content.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["input"],
            })
        return raw_content


# ============================================================
# Factory function
# ============================================================


def create_minimax_service(
    model: str = "MiniMax-M2.1",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    enable_thinking: bool = True,
    **kwargs,
) -> MiniMaxLLMService:
    """
    Create a MiniMax service (convenience function).

    Args:
        model: Model name (MiniMax-M2.1, MiniMax-M2.1-lightning, MiniMax-M2)
        api_key: API key (defaults to MINIMAX_API_KEY env var)
        base_url: Custom API endpoint
        enable_thinking: Enable thinking mode
        **kwargs: Additional config parameters

    Returns:
        MiniMaxLLMService instance

    Examples:
        # MiniMax-M2.1: flagship model (~60 tps)
        llm = create_minimax_service(
            model="MiniMax-M2.1",
            enable_thinking=True
        )

        # MiniMax-M2.1-lightning: fast version (~100 tps)
        llm = create_minimax_service(
            model="MiniMax-M2.1-lightning",
            enable_thinking=False
        )
    """
    if api_key is None:
        api_key = os.getenv("MINIMAX_API_KEY")

    if not api_key:
        raise ValueError(
            "MiniMax API key is required. Set MINIMAX_API_KEY env var or pass api_key."
        )

    config = LLMConfig(
        provider=LLMProvider.MINIMAX,
        model=model,
        api_key=api_key,
        base_url=base_url,
        enable_thinking=enable_thinking,
        enable_caching=False,  # MiniMax doesn't support prompt caching
        **kwargs,
    )

    return MiniMaxLLMService(config)


# ============================================================
# Register with LLMRegistry
# ============================================================


def _register_minimax():
    """Register MiniMax provider (lazy, avoids circular imports)."""
    from .registry import LLMRegistry

    LLMRegistry.register(
        name="minimax",
        service_class=MiniMaxLLMService,
        adaptor_class=ClaudeAdaptor,
        default_model="MiniMax-M2.1",
        api_key_env="MINIMAX_API_KEY",
        display_name="MiniMax",
        description="MiniMax M2 系列模型（Anthropic API 兼容）",
        supported_features=[
            "streaming",
            "tool_calling",
            "thinking",
        ],
    )


# Register on module load
_register_minimax()

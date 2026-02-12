"""
DeepSeek LLM 服务实现

基于 OpenAI 兼容接口实现，与 Claude/Qwen 服务保持相同的接口规范。

支持的功能：
- 基础对话（流式/非流式）
- Function Calling（工具调用）
- 思考模式（deepseek-reasoner / thinking 参数）
- 流式断连重试与降级

模型对应关系：
- deepseek-reasoner ↔ claude-sonnet-4-5 / qwen3-max（重推理模型）
- deepseek-chat     ↔ claude-haiku-4-5  / qwen-plus（快速模型）

思考模式 + 工具调用注意事项：
- 同一问题的工具调用循环内，必须将 reasoning_content 传回 API
- 新问题开始时，API 会忽略旧轮次的 reasoning_content
- DeepSeekAdaptor 自动处理 thinking blocks → reasoning_content 的转换

参考文档：
- https://api-docs.deepseek.com/
- https://api-docs.deepseek.com/guides/thinking_mode
"""

import json
import os
import re
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

import httpx
from openai import AsyncOpenAI

from infra.resilience import with_retry
from logger import get_logger

from .adaptor import DeepSeekAdaptor
from .base import BaseLLMService, LLMConfig, LLMProvider, LLMResponse, Message, ToolType

logger = get_logger("llm.deepseek")

# Verbose debug logging toggle
LLM_DEBUG_VERBOSE = os.getenv("LLM_DEBUG_VERBOSE", "").lower() in ("1", "true", "yes")

# ============================================================
# DeepSeek 常量与模型能力
# ============================================================

# max_tokens 上限
# deepseek-reasoner: 输出最大 64K（含 CoT）
# deepseek-chat:     输出最大 8K
DEEPSEEK_MAX_TOKENS_REASONER = 65536
DEEPSEEK_MAX_TOKENS_CHAT = 8192


class DeepSeekModelCapability:
    """DeepSeek model capability detection"""

    REASONER_MODELS = {
        "deepseek-reasoner",
    }

    THINKING_CAPABLE_MODELS = {
        "deepseek-chat",
        "deepseek-reasoner",
    }

    TOOL_CALLING_MODELS = {
        "deepseek-chat",
        "deepseek-reasoner",
    }

    @staticmethod
    def is_reasoner(model: str) -> bool:
        """Check if model always produces reasoning (built-in thinking)"""
        return any(m in model for m in DeepSeekModelCapability.REASONER_MODELS)

    @staticmethod
    def supports_thinking(model: str) -> bool:
        """Check if model supports thinking mode"""
        return any(m in model for m in DeepSeekModelCapability.THINKING_CAPABLE_MODELS)

    @staticmethod
    def supports_tools(model: str) -> bool:
        """Check if model supports tool calling"""
        return any(m in model for m in DeepSeekModelCapability.TOOL_CALLING_MODELS)

    @staticmethod
    def get_max_tokens(model: str) -> int:
        """Get max output tokens for the model"""
        if DeepSeekModelCapability.is_reasoner(model):
            return DEEPSEEK_MAX_TOKENS_REASONER
        return DEEPSEEK_MAX_TOKENS_CHAT


# ============================================================
# Thinking marker cleanup
# ============================================================

# DeepSeek thinking markers (full-width pipe U+FF5C)
_THINKING_END_RE = re.compile(r"<\uff5c?end\u2581of\u2581thinking\uff5c?>")
_THINKING_BEGIN_RE = re.compile(r"<\uff5c?begin\u2581of\u2581thinking\uff5c?>")
# <think>...</think> wrapper used by some DeepSeek model variants
_THINK_TAG_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def _strip_thinking_markers(text: str) -> tuple[str, str]:
    """
    Strip leaked thinking content from DeepSeek response text.

    deepseek-chat with thinking enabled may embed thinking tokens
    directly in the content field using markers like:
      <｜end▁of▁thinking｜>  (full-width pipes)
      <think>...</think>

    Returns:
        (cleaned_content, extracted_thinking)
    """
    if not text:
        return text, ""

    extracted = ""

    # Pattern 1: <｜end▁of▁thinking｜> splits thinking from content
    m = _THINKING_END_RE.search(text)
    if m:
        extracted = text[: m.start()].strip()
        text = text[m.end() :].strip()

    # Pattern 2: <｜begin▁of▁thinking｜> ... <｜end▁of▁thinking｜> wrapper
    # (already handled above for end marker; strip residual begin marker)
    text = _THINKING_BEGIN_RE.sub("", text).strip()

    # Pattern 3: <think>...</think> blocks
    think_matches = _THINK_TAG_RE.findall(text)
    if think_matches:
        extracted_parts = [extracted] if extracted else []
        extracted_parts.extend(think_matches)
        extracted = "\n".join(p.strip() for p in extracted_parts if p.strip())
        text = _THINK_TAG_RE.sub("", text).strip()

    return text, extracted


# ============================================================
# DeepSeek LLM 服务
# ============================================================


class DeepSeekLLMService(BaseLLMService):
    """
    DeepSeek LLM 服务实现

    基于 OpenAI 兼容接口 (https://api.deepseek.com)，
    保持与 Claude/Qwen 服务相同的接口规范。

    使用示例：
    ```python
    config = LLMConfig(
        provider=LLMProvider.DEEPSEEK,
        model="deepseek-reasoner",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        enable_thinking=True
    )
    llm = DeepSeekLLMService(config)

    response = await llm.create_message_async(
        messages=[Message(role="user", content="Hello")],
        system="You are helpful"
    )
    ```
    """

    def __init__(self, config: LLMConfig):
        """
        Initialize DeepSeek service.

        Args:
            config: LLM configuration
        """
        self.config = config

        # Message adaptor (handles thinking → reasoning_content conversion)
        self._adaptor = DeepSeekAdaptor()

        # API Key
        api_key = config.api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError(
                "DeepSeek API Key 未设置。请设置 DEEPSEEK_API_KEY 环境变量或传入 api_key 参数"
            )

        masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
        logger.info(f"🔑 DeepSeek API Key: {masked_key} (长度: {len(api_key)})")

        # API endpoint (single region, no multi-region like Qwen)
        base_url = (
            getattr(config, "base_url", None)
            or os.getenv("DEEPSEEK_BASE_URL")
            or "https://api.deepseek.com"
        )
        logger.info(f"🌐 DeepSeek 端点: {base_url}")

        # Initialize OpenAI-compatible client
        timeout = getattr(config, "timeout", 120.0)
        max_retries = getattr(config, "max_retries", 3)

        self.client = AsyncOpenAI(  # type: ignore[reportCallIssue]
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

        # Custom tool storage
        self._custom_tools: List[Dict[str, Any]] = []

        logger.info(f"✅ DeepSeek 服务初始化成功: model={self.config.model}")

    # ============================================================
    # Custom tool management (same interface as Claude/Qwen)
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

    def convert_to_tool_schema(self, capability: Dict[str, Any]) -> Dict[str, Any]:
        """Convert capability to DeepSeek API format (OpenAI Function Calling)."""
        name = capability.get("name", "")
        input_schema = capability.get(
            "input_schema", {"type": "object", "properties": {}, "required": []}
        )
        description = capability.get("metadata", {}).get("description", f"Tool: {name}")

        return {
            "type": "function",
            "function": {"name": name, "description": description, "parameters": input_schema},
        }

    def _format_tools(self, tools: List[Union[ToolType, str, Dict]]) -> List[Dict[str, Any]]:
        """
        Format tool list for OpenAI Function Calling format.

        Supports three input types:
        1. ToolType enum (skipped – DeepSeek has no native tools)
        2. String (tool name, looked up from custom tools)
        3. Complete schema dict
        """
        formatted = []

        for idx, tool in enumerate(tools):
            try:
                if isinstance(tool, ToolType):
                    logger.warning(f"DeepSeek 不支持 ToolType 枚举: {tool}，已跳过")
                    continue

                elif isinstance(tool, str):
                    found = False
                    for custom_tool in self._custom_tools:
                        if custom_tool.get("name") == tool:
                            formatted.append(self._convert_tool_to_openai_format(custom_tool))
                            found = True
                            break
                    if not found:
                        logger.warning(f"未找到工具: {tool}")

                elif isinstance(tool, dict):
                    formatted.append(self._convert_tool_to_openai_format(tool))

                else:
                    raise ValueError(f"Invalid tool format: {tool}")

                if formatted:
                    json.dumps(formatted[-1])

            except Exception as e:
                logger.error(f"处理工具 #{idx} 时出错: {e}")
                raise

        return formatted

    def _convert_tool_to_openai_format(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a tool definition to OpenAI Function Calling format."""
        if tool.get("type") == "function":
            return tool

        return {
            "type": "function",
            "function": {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            },
        }

    @staticmethod
    def _normalize_tool_choice(tool_choice: Any) -> Any:
        """Convert Claude-style tool_choice to OpenAI-compatible format.

        Claude format:  {"type": "tool", "name": "func_name"}
        OpenAI format:  {"type": "function", "function": {"name": "func_name"}}
        """
        if isinstance(tool_choice, str):
            return tool_choice
        if isinstance(tool_choice, dict) and tool_choice.get("type") == "tool":
            return {
                "type": "function",
                "function": {"name": tool_choice["name"]},
            }
        return tool_choice

    # ============================================================
    # Core API methods
    # ============================================================

    def _build_extra_body(
        self, override_thinking: Optional[bool], kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build DeepSeek-specific extra parameters.

        Thinking mode control:
        - deepseek-reasoner: always produces reasoning, no extra param needed
        - deepseek-chat + enable_thinking: pass {"thinking": {"type": "enabled"}}
        """
        extra = {}

        effective_thinking = (
            override_thinking
            if override_thinking is not None
            else getattr(self.config, "enable_thinking", False)
        )

        # Only need explicit thinking param for non-reasoner models
        if effective_thinking and not DeepSeekModelCapability.is_reasoner(self.config.model):
            extra["thinking"] = {"type": "enabled"}

        # Structured output
        response_format = kwargs.get("response_format")
        if response_format:
            extra["response_format"] = response_format

        return extra

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
            invocation_type: Invocation type (unused for DeepSeek)
            override_thinking: Dynamic thinking override
            is_probe: Whether this is a probe request
            **kwargs: Additional parameters

        Returns:
            LLMResponse
        """
        # Convert messages via adaptor
        converted = self._adaptor.convert_messages_to_provider(messages)
        openai_messages = converted["messages"]

        # Clamp max_tokens to model limit
        model_max = DeepSeekModelCapability.get_max_tokens(self.config.model)
        max_tokens = min(kwargs.get("max_tokens", self.config.max_tokens), model_max)

        # Build request
        request_params = {
            "model": self.config.model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "stream": False,
        }

        # Temperature: reasoner mode ignores it but doesn't error
        is_reasoner = DeepSeekModelCapability.is_reasoner(self.config.model)
        if not is_reasoner:
            request_params["temperature"] = kwargs.get("temperature", self.config.temperature)

        # System prompt
        if system:
            if isinstance(system, list):
                system_message = self._build_system_message(system)
                request_params["messages"].insert(0, system_message)
            elif isinstance(system, dict):
                system_message = self._build_system_message([system])
                request_params["messages"].insert(0, system_message)
            else:
                request_params["messages"].insert(0, {"role": "system", "content": str(system)})

        # DeepSeek-specific extra params (must use extra_body for non-standard fields)
        extra_body = self._build_extra_body(override_thinking, kwargs)
        if extra_body:
            request_params["extra_body"] = extra_body

        # Tools (Function Calling)
        all_tools = []
        tool_names_seen = set()

        if tools:
            for tool in self._format_tools(tools):
                tool_name = tool.get("function", {}).get("name", "")
                if tool_name and tool_name not in tool_names_seen:
                    all_tools.append(tool)
                    tool_names_seen.add(tool_name)

        for custom_tool in self._custom_tools:
            tool_name = custom_tool.get("name", "")
            if tool_name and tool_name not in tool_names_seen:
                all_tools.append(self._convert_tool_to_openai_format(custom_tool))
                tool_names_seen.add(tool_name)

        if all_tools:
            request_params["tools"] = all_tools
            request_params["tool_choice"] = self._normalize_tool_choice(
                kwargs.get("tool_choice", "auto")
            )
            logger.debug(f"Tools: {[t['function']['name'] for t in all_tools]}")

        # Warn if max_tokens was clamped
        original_max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if original_max_tokens > model_max:
            logger.warning(
                f"⚠️ max_tokens 已限制: {original_max_tokens} → {model_max} "
                f"(DeepSeek {self.config.model} 上限)"
            )

        logger.debug(
            f"📤 DeepSeek 请求: model={self.config.model}, messages={len(openai_messages)}"
        )

        if LLM_DEBUG_VERBOSE:
            logger.info("=" * 80)
            logger.info("🔍 [DEBUG-ASYNC] 完整 request_params:")
            logger.info(f"   model: {request_params.get('model')}")
            logger.info(f"   messages: {len(request_params.get('messages', []))}")
            for i, msg in enumerate(request_params.get("messages", [])):
                logger.info(
                    f"   [{i}] role={msg.get('role')}, content={str(msg.get('content'))[:200]}..."
                )
            logger.info("=" * 80)

        # API call
        try:
            response = await self.client.chat.completions.create(**request_params)
        except Exception as e:
            if not is_probe:
                logger.error(f"DeepSeek API 调用失败: {e}")
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
        # Convert messages via adaptor
        converted = self._adaptor.convert_messages_to_provider(messages)
        openai_messages = converted["messages"]

        # Clamp max_tokens
        model_max = DeepSeekModelCapability.get_max_tokens(self.config.model)
        max_tokens = min(kwargs.get("max_tokens", self.config.max_tokens), model_max)

        request_params = {
            "model": self.config.model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        # Temperature
        is_reasoner = DeepSeekModelCapability.is_reasoner(self.config.model)
        if not is_reasoner:
            request_params["temperature"] = kwargs.get("temperature", self.config.temperature)

        # System prompt
        if system:
            if isinstance(system, list):
                system_message = self._build_system_message(system)
                request_params["messages"].insert(0, system_message)
            elif isinstance(system, dict):
                system_message = self._build_system_message([system])
                request_params["messages"].insert(0, system_message)
            else:
                request_params["messages"].insert(0, {"role": "system", "content": str(system)})

        # DeepSeek-specific extra params
        extra_body = self._build_extra_body(override_thinking, kwargs)
        if extra_body:
            request_params["extra_body"] = extra_body

        # Tools
        all_tools = []
        tool_names_seen = set()

        if tools:
            for tool in self._format_tools(tools):
                tool_name = tool.get("function", {}).get("name", "")
                if tool_name and tool_name not in tool_names_seen:
                    all_tools.append(tool)
                    tool_names_seen.add(tool_name)

        for custom_tool in self._custom_tools:
            tool_name = custom_tool.get("name", "")
            if tool_name and tool_name not in tool_names_seen:
                all_tools.append(self._convert_tool_to_openai_format(custom_tool))
                tool_names_seen.add(tool_name)

        if all_tools:
            request_params["tools"] = all_tools
            request_params["tool_choice"] = self._normalize_tool_choice(
                kwargs.get("tool_choice", "auto")
            )

        # Warn if clamped
        original_max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        if original_max_tokens > model_max:
            logger.warning(
                f"⚠️ max_tokens 已限制: {original_max_tokens} → {model_max} "
                f"(DeepSeek {self.config.model} 上限)"
            )

        logger.info(
            f"📤 DeepSeek 流式请求: model={self.config.model}, "
            f"messages={len(openai_messages)}"
        )

        # Accumulation variables
        accumulated_thinking = ""
        accumulated_content = ""
        tool_calls = []
        stop_reason = None
        usage = {}

        # Stream retry config
        _STREAM_MAX_RETRIES = 2
        _stream_attempt = 0

        try:
            stream = await self.client.chat.completions.create(**request_params)

            async for chunk in stream:
                if not chunk.choices:
                    # Final chunk with usage
                    if chunk.usage:
                        usage = {
                            "input_tokens": chunk.usage.prompt_tokens,
                            "output_tokens": chunk.usage.completion_tokens,
                            "thinking_tokens": 0,
                        }
                        if accumulated_thinking:
                            usage["thinking_tokens"] = self.count_tokens(accumulated_thinking)

                        logger.info(
                            f"📊 Token 使用: input={usage['input_tokens']:,}, "
                            f"output={usage['output_tokens']:,}, "
                            f"thinking={usage['thinking_tokens']:,}"
                        )
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                # Thinking content (reasoning_content field)
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    accumulated_thinking += delta.reasoning_content
                    if on_thinking:
                        on_thinking(delta.reasoning_content)
                    yield LLMResponse(
                        content="",
                        thinking=delta.reasoning_content,
                        model=self.config.model,
                        is_stream=True,
                    )

                # Normal content
                if delta.content:
                    accumulated_content += delta.content
                    if on_content:
                        on_content(delta.content)
                    yield LLMResponse(
                        content=delta.content,
                        model=self.config.model,
                        is_stream=True,
                    )

                # Tool calls
                if delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        if tool_call.id or (tool_call.function and tool_call.function.name):
                            logger.info(
                                f"🔍 收到工具调用 delta: index={tool_call.index}, "
                                f"id={tool_call.id}, "
                                f"name={tool_call.function.name if tool_call.function else 'None'}"
                            )
                        else:
                            logger.debug(
                                f"🔍 累积 arguments chunk: index={tool_call.index}"
                            )

                        index = tool_call.index
                        while len(tool_calls) <= index:
                            tool_calls.append(
                                {"id": "", "name": "", "arguments": "", "type": "function"}
                            )

                        if tool_call.id:
                            tool_calls[index]["id"] = tool_call.id
                            yield LLMResponse(
                                content="",
                                model=self.config.model,
                                is_stream=True,
                                tool_use_start={
                                    "type": "tool_use",
                                    "id": tool_call.id,
                                    "name": (
                                        tool_call.function.name if tool_call.function else ""
                                    ),
                                },
                            )

                        if tool_call.function:
                            if tool_call.function.name:
                                tool_calls[index]["name"] = tool_call.function.name
                            if tool_call.function.arguments:
                                tool_calls[index]["arguments"] += tool_call.function.arguments
                                yield LLMResponse(
                                    content="",
                                    model=self.config.model,
                                    is_stream=True,
                                    input_delta=tool_call.function.arguments,
                                )

                        if on_tool_call:
                            on_tool_call(
                                {
                                    "id": tool_call.id,
                                    "name": (
                                        tool_call.function.name if tool_call.function else ""
                                    ),
                                    "arguments": (
                                        tool_call.function.arguments if tool_call.function else ""
                                    ),
                                }
                            )

                # Stop reason
                if choice.finish_reason:
                    stop_reason = choice.finish_reason

            # Guard: stream ended without finish_reason (silent disconnect)
            if stop_reason is None and (accumulated_content or accumulated_thinking):
                logger.warning(
                    f"⚠️ DeepSeek 流式结束但无 finish_reason "
                    f"(content={len(accumulated_content)} chars) — 视为静默断连"
                )
                if _stream_attempt < _STREAM_MAX_RETRIES and not tool_calls:
                    _stream_attempt += 1
                    import asyncio as _asyncio

                    delay = 1.0 * _stream_attempt
                    logger.info(f"🔄 {delay}s 后重试（静默断连恢复）...")
                    await _asyncio.sleep(delay)

                    _saved_content = accumulated_content
                    _saved_thinking = accumulated_thinking

                    logger.info("🔄 回退到非流式调用以确保完整性...")
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
                        logger.error(f"❌ DeepSeek 非流式 fallback 也失败: {fallback_err}")
                        accumulated_content = _saved_content
                        accumulated_thinking = _saved_thinking

                # Return partial response
                raw_content = []
                if accumulated_thinking:
                    raw_content.append({"type": "thinking", "thinking": accumulated_thinking})
                if accumulated_content:
                    raw_content.append({"type": "text", "text": accumulated_content})
                yield LLMResponse(
                    content=accumulated_content,
                    thinking=accumulated_thinking if accumulated_thinking else None,
                    stop_reason="stream_error",
                    model=self.config.model,
                    raw_content=raw_content,
                    is_stream=False,
                )
                return

            # Format accumulated tool calls
            formatted_tool_calls = []
            if tool_calls:
                logger.info(f"🔍 累积的工具调用数量: {len(tool_calls)}")
                for tc in tool_calls:
                    if tc.get("name"):
                        try:
                            input_dict = (
                                json.loads(tc["arguments"], strict=False)
                                if tc["arguments"]
                                else {}
                            )
                            formatted_tool_calls.append(
                                {
                                    "id": tc["id"],
                                    "name": tc["name"],
                                    "input": input_dict,
                                    "type": "tool_use",
                                }
                            )
                        except json.JSONDecodeError as e:
                            logger.error(f"❌ 工具调用参数解析失败: {e}")
                            logger.error(
                                f"   原始 arguments: "
                                f"{tc['arguments'][:200] if tc.get('arguments') else 'None'}"
                            )

            # Strip thinking markers leaked into accumulated content
            accumulated_content, leaked = _strip_thinking_markers(accumulated_content)
            if leaked:
                accumulated_thinking = (
                    (leaked + "\n" + accumulated_thinking)
                    if accumulated_thinking
                    else leaked
                )
                logger.debug(
                    f"[stream] Stripped {len(leaked)} chars of leaked thinking"
                )

            # Build raw_content
            raw_content = []
            if accumulated_thinking:
                raw_content.append({"type": "thinking", "thinking": accumulated_thinking})
            if accumulated_content:
                raw_content.append({"type": "text", "text": accumulated_content})
            for tc in formatted_tool_calls:
                raw_content.append(
                    {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["input"]}
                )

            logger.info(f"📥 DeepSeek 响应: stop_reason={stop_reason or 'stop'}")

            # Normalize stop_reason: OpenAI "tool_calls" → Claude "tool_use"
            if stop_reason == "tool_calls" or (formatted_tool_calls and stop_reason == "stop"):
                stop_reason = "tool_use"
                logger.debug("🔄 转换 stop_reason: tool_calls -> tool_use")

            # Final response
            yield LLMResponse(
                content=accumulated_content,
                thinking=accumulated_thinking if accumulated_thinking else None,
                tool_calls=formatted_tool_calls if formatted_tool_calls else None,
                stop_reason=stop_reason or "stop",
                usage=usage if usage else None,
                model=self.config.model,
                raw_content=raw_content,
                is_stream=False,
            )

        except (
            httpx.RemoteProtocolError,
            httpx.ConnectError,
            httpx.TimeoutException,
        ) as stream_error:
            _stream_attempt += 1
            logger.warning(
                f"⚠️ DeepSeek 流式中断 (attempt {_stream_attempt}/{_STREAM_MAX_RETRIES}): "
                f"{stream_error}"
            )

            if _stream_attempt <= _STREAM_MAX_RETRIES and not tool_calls:
                import asyncio as _asyncio

                delay = 1.0 * _stream_attempt
                logger.info(f"🔄 {delay}s 后重试...")
                await _asyncio.sleep(delay)

                _saved_content = accumulated_content
                _saved_thinking = accumulated_thinking

                logger.info("🔄 回退到非流式调用以确保完整性...")
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
                    logger.error(f"❌ DeepSeek 非流式 fallback 也失败: {fallback_err}")
                    accumulated_content = _saved_content
                    accumulated_thinking = _saved_thinking

            if accumulated_content or accumulated_thinking or tool_calls:
                logger.warning("⚠️ 返回部分响应（重试已耗尽）...")
                raw_content = []
                if accumulated_thinking:
                    raw_content.append({"type": "thinking", "thinking": accumulated_thinking})
                if accumulated_content:
                    raw_content.append({"type": "text", "text": accumulated_content})
                yield LLMResponse(
                    content=accumulated_content,
                    thinking=accumulated_thinking if accumulated_thinking else None,
                    tool_calls=None,
                    stop_reason="stream_error",
                    model=self.config.model,
                    raw_content=raw_content,
                    is_stream=False,
                )
                return
            raise

        except Exception as e:
            logger.error(f"DeepSeek 流式传输错误: {e}")
            if accumulated_content or accumulated_thinking:
                logger.warning("⚠️ 返回部分响应（非网络错误）...")
                raw_content = []
                if accumulated_thinking:
                    raw_content.append({"type": "thinking", "thinking": accumulated_thinking})
                if accumulated_content:
                    raw_content.append({"type": "text", "text": accumulated_content})
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

    def count_tokens(self, text: str) -> int:
        """
        Count tokens (approximate, using tiktoken cl100k_base).

        Args:
            text: Text to count

        Returns:
            Token count
        """
        return super().count_tokens(text)

    # ============================================================
    # Helper methods
    # ============================================================

    def _build_system_message(self, system_blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Build system message from block list.

        Args:
            system_blocks: System prompt blocks

        Returns:
            System message dict
        """
        content_blocks = []

        for block in system_blocks:
            if isinstance(block, dict):
                content_blocks.append(block)
            else:
                content_blocks.append({"type": "text", "text": str(block)})

        # Simplify if only a single text block
        if len(content_blocks) == 1 and content_blocks[0].get("type") == "text":
            return {"role": "system", "content": content_blocks[0].get("text", "")}

        return {"role": "system", "content": content_blocks}

    def _parse_response(self, response) -> LLMResponse:
        """
        Parse DeepSeek response into unified format.

        Args:
            response: OpenAI-format response

        Returns:
            LLMResponse
        """
        choice = response.choices[0]
        message = choice.message

        # Extract content
        content_text = message.content or ""
        thinking_text = getattr(message, "reasoning_content", None)

        # Strip thinking markers leaked into content.
        # deepseek-chat with thinking enabled may embed thinking tokens
        # directly in the content field with markers like <｜end▁of▁thinking｜>.
        content_text, leaked = _strip_thinking_markers(content_text)
        if leaked:
            # Prepend leaked thinking to reasoning_content so nothing is lost
            thinking_text = (leaked + "\n" + thinking_text) if thinking_text else leaked
            logger.debug(
                f"Stripped {len(leaked)} chars of leaked thinking from content"
            )

        # Extract tool calls
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                input_dict = json.loads(tc.function.arguments) if tc.function.arguments else {}
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "input": input_dict,
                        "type": "tool_use",
                    }
                )
        else:
            logger.debug(f"message.tool_calls 为空（stop_reason={choice.finish_reason}）")

        # Usage
        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "thinking_tokens": 0,
            }
            if thinking_text:
                usage["thinking_tokens"] = self.count_tokens(thinking_text)

            logger.info(
                f"📊 Token 使用: input={usage['input_tokens']:,}, "
                f"output={usage['output_tokens']:,}, "
                f"thinking={usage['thinking_tokens']:,}"
            )

        # Normalize stop_reason: OpenAI → Claude format
        stop_reason = choice.finish_reason
        if stop_reason == "tool_calls" or (tool_calls and stop_reason == "stop"):
            stop_reason = "tool_use"
            logger.debug("🔄 转换 stop_reason: tool_calls -> tool_use")

        # Build raw_content
        raw_content = []
        if thinking_text:
            raw_content.append({"type": "thinking", "thinking": thinking_text})
        if content_text:
            raw_content.append({"type": "text", "text": content_text})
        for tc in tool_calls:
            raw_content.append(
                {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["input"]}
            )

        return LLMResponse(
            content=content_text,
            thinking=thinking_text,
            tool_calls=tool_calls if tool_calls else None,
            stop_reason=stop_reason,
            usage=usage,
            model=self.config.model,
            raw_content=raw_content,
        )


# ============================================================
# Factory function
# ============================================================


def create_deepseek_service(
    model: str = "deepseek-reasoner",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    enable_thinking: bool = True,
    **kwargs,
) -> DeepSeekLLMService:
    """
    Create a DeepSeek service (convenience function).

    Args:
        model: Model name (deepseek-reasoner or deepseek-chat)
        api_key: API key (defaults to DEEPSEEK_API_KEY env var)
        base_url: Custom API endpoint
        enable_thinking: Enable thinking mode
        **kwargs: Additional config parameters

    Returns:
        DeepSeekLLMService instance
    """
    if api_key is None:
        api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise ValueError("DeepSeek API key is required. Set DEEPSEEK_API_KEY env var or pass api_key.")

    config = LLMConfig(
        provider=LLMProvider.DEEPSEEK,
        model=model,
        api_key=api_key,
        base_url=base_url,
        enable_thinking=enable_thinking,
        **kwargs,
    )

    return DeepSeekLLMService(config)


# ============================================================
# Register with LLMRegistry
# ============================================================


def _register_deepseek():
    """Register DeepSeek provider (lazy, avoids circular imports)."""
    from .registry import LLMRegistry

    LLMRegistry.register(
        name="deepseek",
        service_class=DeepSeekLLMService,
        adaptor_class=DeepSeekAdaptor,
        default_model="deepseek-reasoner",
        api_key_env="DEEPSEEK_API_KEY",
        display_name="DeepSeek",
        description="DeepSeek V3.2 系列模型（深度求索）",
        supported_features=[
            "streaming",
            "tool_calling",
            "thinking",
        ],
    )


# Register on module load
_register_deepseek()

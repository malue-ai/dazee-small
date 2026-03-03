"""
智谱 GLM LLM 服务实现

基于 OpenAI 兼容接口实现，与 Claude/Qwen/DeepSeek 服务保持相同的接口规范。

支持的功能：
- 基础对话（流式/非流式）
- Function Calling（工具调用）
- 思考模式（thinking.type = enabled/disabled）
- 视觉模型（GLM-4.6V / GLM-4.5V）
- 上下文缓存（context caching）
- 结构化输出（response_format）
- 流式断连重试与降级

模型系列：
- GLM-5:     744B MoE 旗舰（激活 40B），200K 上下文，128K 输出，Coding/Agent SOTA
- GLM-4.7:   上一代旗舰模型
- GLM-4.6:   旗舰模型
- GLM-4.5:   355B MoE 旗舰，对标 claude-sonnet-4-6
- GLM-4.5-Air: 106B MoE 轻量旗舰
- GLM-4.5-X:  高性能加速版
- GLM-4.5-AirX: 轻量加速版
- GLM-4.5-Flash: 免费快速模型

参考文档：
- https://docs.bigmodel.cn/cn/guide/models/text/glm-5
- https://docs.bigmodel.cn/cn/api/introduction
"""

import json
import os
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

import httpx
from openai import AsyncOpenAI

from infra.resilience import with_retry
from logger import get_logger

from .adaptor import OpenAIAdaptor
from .base import BaseLLMService, LLMConfig, LLMProvider, LLMResponse, Message, ToolType

logger = get_logger("llm.glm")

# Verbose debug logging toggle
LLM_DEBUG_VERBOSE = os.getenv("LLM_DEBUG_VERBOSE", "").lower() in ("1", "true", "yes")


# ============================================================
# GLM 常量与模型能力
# ============================================================

# GLM-5 最大输出 token 数（128K），GLM-4.x 系列为 96K
GLM5_MAX_TOKENS = 128000  # GLM-5 官方最大输出 128K
GLM4_MAX_TOKENS = 96000   # GLM-4.5/4.6/4.7 系列最大输出 96K


class GLMEndpoints:
    """GLM API 端点"""

    # 国内端点
    CN = "https://open.bigmodel.cn/api/paas/v4"
    # 国际端点
    INTL = "https://api.z.ai/api/paas/v4"
    # Coding 专用端点
    CODING = "https://open.bigmodel.cn/api/coding/paas/v4"

    MAPPING = {
        "cn": CN,
        "intl": INTL,
        "coding": CODING,
    }


class GLMModelCapability:
    """GLM model capability detection"""

    # 支持思考模式的模型（thinking.type = enabled）
    THINKING_MODELS = {
        "glm-5",
        "glm-4.7",
        "glm-4.6",
        "glm-4.5",
        "glm-4.5-air",
        "glm-4.5-x",
        "glm-4.5-airx",
        "glm-4.5-flash",
    }

    # 支持视觉的模型
    VISION_MODELS = {
        "glm-4.6v",
        "glm-4.5v",
    }

    # 支持 Function Calling 的模型
    TOOL_CALLING_MODELS = {
        "glm-5",
        "glm-4.7",
        "glm-4.6",
        "glm-4.5",
        "glm-4.5-air",
        "glm-4.5-x",
        "glm-4.5-airx",
        "glm-4.5-flash",
        "glm-4.6v",
        "glm-4.5v",
    }

    @staticmethod
    def supports_thinking(model: str) -> bool:
        """Check if model supports thinking mode"""
        return any(m in model for m in GLMModelCapability.THINKING_MODELS)

    @staticmethod
    def supports_vision(model: str) -> bool:
        """Check if model supports vision"""
        return any(m in model for m in GLMModelCapability.VISION_MODELS)

    @staticmethod
    def supports_tools(model: str) -> bool:
        """Check if model supports tool calling"""
        return any(m in model for m in GLMModelCapability.TOOL_CALLING_MODELS)

    @staticmethod
    def get_max_tokens(model: str) -> int:
        """Get max output tokens for the model"""
        # GLM-5: 128K max output
        if "glm-5" in model:
            return GLM5_MAX_TOKENS
        # GLM-4.5/4.6/4.7 系列: 96K max output
        if "4.5" in model or "4.6" in model or "4.7" in model:
            return GLM4_MAX_TOKENS
        return 4096  # 旧模型默认


# ============================================================
# GLM LLM 服务
# ============================================================


class GLMLLMService(BaseLLMService):
    """
    智谱 GLM LLM 服务实现

    基于 OpenAI 兼容接口 (https://open.bigmodel.cn/api/paas/v4)，
    保持与 Claude/Qwen/DeepSeek 服务相同的接口规范。

    使用示例：
    ```python
    config = LLMConfig(
        provider=LLMProvider.GLM,
        model="glm-5",
        api_key=os.getenv("ZHIPUAI_API_KEY"),
        enable_thinking=True
    )
    llm = GLMLLMService(config)

    response = await llm.create_message_async(
        messages=[Message(role="user", content="Hello")],
        system="You are helpful"
    )
    ```
    """

    def __init__(self, config: LLMConfig):
        """
        Initialize GLM service.

        Args:
            config: LLM configuration
        """
        self.config = config

        # Message adaptor (GLM uses OpenAI-compatible format)
        self._adaptor = OpenAIAdaptor()

        # API Key (priority: config > env)
        api_key = config.api_key or os.getenv("ZHIPUAI_API_KEY")
        if not api_key:
            raise ValueError(
                "GLM API Key 未设置。请设置 ZHIPUAI_API_KEY 环境变量或传入 api_key 参数"
            )

        masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
        logger.info(f"🔑 GLM API Key: {masked_key} (长度: {len(api_key)})")

        # API endpoint (priority: config.base_url > env > default CN)
        base_url = (
            getattr(config, "base_url", None)
            or os.getenv("ZHIPUAI_BASE_URL")
            or GLMEndpoints.CN
        )
        logger.info(f"🌐 GLM 端点: {base_url}")

        # Initialize OpenAI-compatible client
        timeout = getattr(config, "timeout", 120.0)
        max_retries = getattr(config, "max_retries", 3)

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

        # Custom tool storage
        self._custom_tools: List[Dict[str, Any]] = []

        logger.info(f"✅ GLM 服务初始化成功: model={self.config.model}")

    # ============================================================
    # Custom tool management (same interface as Claude/Qwen/DeepSeek)
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
        """Convert capability to GLM API format (OpenAI Function Calling)."""
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
        1. ToolType enum (skipped - GLM has no native tools)
        2. String (tool name, looked up from custom tools)
        3. Complete schema dict
        """
        formatted = []

        for idx, tool in enumerate(tools):
            try:
                if isinstance(tool, ToolType):
                    logger.warning(f"GLM 不支持 ToolType 枚举: {tool}，已跳过")
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
        Build GLM-specific extra parameters.

        Thinking mode control:
        - GLM uses {"thinking": {"type": "enabled"}} to enable thinking
        - Dynamic thinking is enabled by default for GLM-5 / GLM-4.5+ models
        """
        extra = {}

        effective_thinking = (
            override_thinking
            if override_thinking is not None
            else getattr(self.config, "enable_thinking", False)
        )

        if GLMModelCapability.supports_thinking(self.config.model):
            if effective_thinking:
                extra["thinking"] = {"type": "enabled"}
            else:
                extra["thinking"] = {"type": "disabled"}

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
            invocation_type: Invocation type (unused for GLM)
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
        model_max = GLMModelCapability.get_max_tokens(self.config.model)
        max_tokens = min(kwargs.get("max_tokens", self.config.max_tokens), model_max)

        # Build request
        request_params = {
            "model": self.config.model,
            "messages": openai_messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": max_tokens,
            "stream": False,
        }

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

        # GLM-specific extra params (thinking mode via extra_body)
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
                f"(GLM {self.config.model} 上限)"
            )

        logger.debug(
            f"📤 GLM 请求: model={self.config.model}, messages={len(openai_messages)}"
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
                logger.error(f"GLM API 调用失败: {e}")
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
        model_max = GLMModelCapability.get_max_tokens(self.config.model)
        max_tokens = min(kwargs.get("max_tokens", self.config.max_tokens), model_max)

        request_params = {
            "model": self.config.model,
            "messages": openai_messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

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

        # GLM-specific extra params
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
                f"(GLM {self.config.model} 上限)"
            )

        logger.info(
            f"📤 GLM 流式请求: model={self.config.model}, "
            f"messages={len(openai_messages)}"
        )

        # Accumulation variables
        accumulated_thinking = ""
        accumulated_content = ""
        tool_calls: List[Dict[str, Any]] = []
        stop_reason = None
        usage: Dict[str, int] = {}

        # Stream retry config (exponential backoff + jitter)
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

                        # Extract reasoning_tokens from completion_tokens_details
                        _details = getattr(chunk.usage, "completion_tokens_details", None)
                        if _details and hasattr(_details, "reasoning_tokens"):
                            usage["thinking_tokens"] = _details.reasoning_tokens or 0
                        elif accumulated_thinking:
                            # Fallback: local estimate (approximate)
                            usage["thinking_tokens"] = self.count_tokens(accumulated_thinking)

                        logger.info(
                            f"📊 Token 使用: input={usage['input_tokens']:,}, "
                            f"output={usage['output_tokens']:,}, "
                            f"thinking={usage['thinking_tokens']:,}"
                        )
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                # Thinking content (GLM returns via reasoning_content)
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
                    f"⚠️ GLM 流式结束但无 finish_reason "
                    f"(content={len(accumulated_content)} chars) — 视为静默断连"
                )
                if _stream_attempt < _STREAM_MAX_RETRIES and not tool_calls:
                    _stream_attempt += 1
                    import asyncio as _asyncio
                    import random as _random

                    exp_delay = min(1.0 * (2 ** (_stream_attempt - 1)), 60.0)
                    delay = _random.uniform(0, exp_delay)
                    logger.info(f"🔄 {delay:.1f}s 后重试（静默断连恢复）...")
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
                        logger.error(f"❌ GLM 非流式 fallback 也失败: {fallback_err}")
                        accumulated_content = _saved_content
                        accumulated_thinking = _saved_thinking

                # Return partial response
                raw_content: List[Dict[str, Any]] = []
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

            logger.info(f"📥 GLM 响应: stop_reason={stop_reason or 'stop'}")

            # Normalize stop_reason: OpenAI "tool_calls" -> Claude "tool_use"
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
                f"⚠️ GLM 流式中断 (attempt {_stream_attempt}/{_STREAM_MAX_RETRIES}): "
                f"{stream_error}"
            )

            if _stream_attempt <= _STREAM_MAX_RETRIES and not tool_calls:
                import asyncio as _asyncio
                import random as _random

                exp_delay = min(1.0 * (2 ** (_stream_attempt - 1)), 60.0)
                delay = _random.uniform(0, exp_delay)
                logger.info(f"🔄 {delay:.1f}s 后重试（指数退避 + jitter）...")
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
                    logger.error(f"❌ GLM 非流式 fallback 也失败: {fallback_err}")
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
            logger.error(f"GLM 流式传输错误: {e}")
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
        Parse GLM response into unified format.

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

            # Extract reasoning_tokens from completion_tokens_details
            _details = getattr(response.usage, "completion_tokens_details", None)
            if _details and hasattr(_details, "reasoning_tokens"):
                usage["thinking_tokens"] = _details.reasoning_tokens or 0
            elif thinking_text:
                usage["thinking_tokens"] = self.count_tokens(thinking_text)

            logger.info(
                f"📊 Token 使用: input={usage['input_tokens']:,}, "
                f"output={usage['output_tokens']:,}, "
                f"thinking={usage['thinking_tokens']:,}"
            )

        # Normalize stop_reason: OpenAI -> Claude format
        stop_reason = choice.finish_reason
        if stop_reason == "tool_calls" or (tool_calls and stop_reason == "stop"):
            stop_reason = "tool_use"
            logger.debug("🔄 转换 stop_reason: tool_calls -> tool_use")

        # Build raw_content
        raw_content: List[Dict[str, Any]] = []
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


def create_glm_service(
    model: str | None = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    enable_thinking: bool = True,
    **kwargs,
) -> GLMLLMService:
    """
    Create a GLM service (convenience function).

    Args:
        model: Model name (defaults from defaults.py)
        api_key: API key (defaults to ZHIPUAI_API_KEY env var)
        base_url: Custom API endpoint
        enable_thinking: Enable thinking mode
        **kwargs: Additional config parameters

    Returns:
        GLMLLMService instance
    """
    if model is None:
        from .defaults import get_default_model
        model = get_default_model("glm")

    if api_key is None:
        api_key = os.getenv("ZHIPUAI_API_KEY")

    if not api_key:
        raise ValueError(
            "GLM API key is required. Set ZHIPUAI_API_KEY env var or pass api_key."
        )

    config = LLMConfig(
        provider=LLMProvider.GLM,
        model=model,
        api_key=api_key,
        base_url=base_url,
        enable_thinking=enable_thinking,
        **kwargs,
    )

    return GLMLLMService(config)


# ============================================================
# Register with LLMRegistry
# ============================================================


def _register_glm():
    """Register GLM provider (lazy, avoids circular imports)."""
    from .defaults import get_default_model
    from .registry import LLMRegistry

    LLMRegistry.register(
        name="glm",
        service_class=GLMLLMService,
        adaptor_class=OpenAIAdaptor,
        default_model=get_default_model("glm"),
        api_key_env="ZHIPUAI_API_KEY",
        display_name="GLM",
        description="智谱 GLM 系列模型",
        supported_features=[
            "streaming",
            "tool_calling",
            "thinking",
            "vision",
            "context_caching",
            "structured_output",
        ],
    )


# Register on module load
_register_glm()

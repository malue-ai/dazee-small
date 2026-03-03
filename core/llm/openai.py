"""
OpenAI LLM 服务实现

基于 OpenAI SDK 实现，支持 OpenAI 官方 API 及兼容接口。

支持的功能：
- 基础对话（流式/非流式）
- Function Calling（工具调用）
- 结构化输出（response_format）

参考文档：
- https://platform.openai.com/docs/api-reference/chat
"""

import json
import os
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

import httpx
from openai import AsyncOpenAI

from infra.resilience import with_retry
from logger import get_logger

from .adaptor import OpenAIAdaptor
from .base import (
    BaseLLMService,
    LLMConfig,
    LLMResponse,
    Message,
    ToolType,
)

logger = get_logger("llm.openai")

# 详细日志开关
LLM_DEBUG_VERBOSE = os.getenv("LLM_DEBUG_VERBOSE", "").lower() in ("1", "true", "yes")

# 支持音频输入/输出的模型
OPENAI_AUDIO_MODELS = {
    "gpt-audio",
    "gpt-4o-audio-preview",
    "gpt-4o-audio-preview-2024-12-17",
}


def _is_audio_model(model: str) -> bool:
    """Check if the model supports audio input/output."""
    return any(m in model for m in OPENAI_AUDIO_MODELS)


# ============================================================
# OpenAI LLM 服务
# ============================================================


class OpenAILLMService(BaseLLMService):
    """
    OpenAI LLM 服务实现

    支持 OpenAI 官方 API 及兼容接口（如 DeepSeek）。

    使用示例：
    ```python
    config = LLMConfig(
        provider=LLMProvider.OPENAI,
        model="gpt-4o",
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    llm = OpenAILLMService(config)

    response = await llm.create_message_async(
        messages=[Message(role="user", content="你好")],
        system="你是一个有帮助的助手"
    )
    ```
    """

    def __init__(self, config: LLMConfig):
        """
        初始化 OpenAI 服务

        Args:
            config: LLM 配置
        """
        self.config = config

        # 消息适配器
        self._adaptor = OpenAIAdaptor()

        # API Key
        api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OpenAI API Key 未设置。请设置 OPENAI_API_KEY 环境变量或传入 api_key 参数"
            )

        # API 端点（优先级：config.base_url > OPENAI_BASE_URL 环境变量 > 官方默认）
        base_url = self.config.base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"

        # 初始化 OpenAI 客户端
        timeout = getattr(self.config, "timeout", 120.0)
        max_retries = getattr(self.config, "max_retries", 3)

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

        # 自定义工具存储
        self._custom_tools: List[Dict[str, Any]] = []

        logger.info(f"✅ OpenAI 服务初始化成功: model={self.config.model}, base_url={base_url}")

    # ============================================================
    # 自定义工具管理
    # ============================================================

    def add_custom_tool(self, name: str, description: str, input_schema: Dict[str, Any]) -> None:
        """
        添加自定义工具

        Args:
            name: 工具名称
            description: 工具描述
            input_schema: 输入参数 schema
        """
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
        """移除自定义工具"""
        for i, tool in enumerate(self._custom_tools):
            if tool["name"] == name:
                self._custom_tools.pop(i)
                logger.debug(f"移除自定义工具: {name}")
                return True
        return False

    def get_custom_tools(self) -> List[Dict[str, Any]]:
        """获取所有自定义工具"""
        return self._custom_tools.copy()

    def clear_custom_tools(self) -> None:
        """清空所有自定义工具"""
        self._custom_tools.clear()
        logger.debug("清空所有自定义工具")

    def _format_tools(self, tools: List[Union[ToolType, str, Dict]]) -> List[Dict[str, Any]]:
        """
        格式化工具列表为 OpenAI 格式
        """
        formatted = []

        for tool in tools:
            if isinstance(tool, ToolType):
                # OpenAI 没有原生工具，跳过
                logger.warning(f"OpenAI 不支持 ToolType 枚举: {tool}，已跳过")
                continue

            elif isinstance(tool, str):
                # 从自定义工具中查找
                for custom_tool in self._custom_tools:
                    if custom_tool.get("name") == tool:
                        formatted.append(self._convert_tool_to_openai_format(custom_tool))
                        break
                else:
                    logger.warning(f"未找到工具: {tool}")

            elif isinstance(tool, dict):
                formatted.append(self._convert_tool_to_openai_format(tool))

        return formatted

    def _convert_tool_to_openai_format(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换工具为 OpenAI Function Calling 格式
        """
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
    # 核心 API 方法
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
        is_probe: bool = False,
        **kwargs,
    ) -> LLMResponse:
        """
        创建消息（异步）

        Args:
            messages: 消息列表
            system: 系统提示词
            tools: 工具列表
            is_probe: 是否为探测请求
            **kwargs: 其他参数

        Returns:
            LLMResponse 响应对象
        """
        # 使用 adaptor 转换消息
        converted = self._adaptor.convert_messages_to_provider(messages)
        openai_messages = converted["messages"]

        # 构建请求参数
        request_params = {
            "model": self.config.model,
            "messages": openai_messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "stream": False,
        }

        # 音频模型参数
        if _is_audio_model(self.config.model):
            request_params["modalities"] = ["text", "audio"]
            request_params["audio"] = {
                "voice": kwargs.get("audio_voice", "alloy"),
                "format": kwargs.get("audio_format", "wav"),
            }

        # System prompt
        if system:
            if isinstance(system, list):
                system_text = "\n".join(
                    block.get("text", "") for block in system if block.get("type") == "text"
                )
                request_params["messages"].insert(0, {"role": "system", "content": system_text})
            elif isinstance(system, dict):
                system_text = (
                    system.get("text", "") if system.get("type") == "text" else str(system)
                )
                request_params["messages"].insert(0, {"role": "system", "content": system_text})
            else:
                request_params["messages"].insert(0, {"role": "system", "content": str(system)})

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

        logger.debug(f"📤 OpenAI 请求: model={self.config.model}, messages={len(openai_messages)}")

        if LLM_DEBUG_VERBOSE:
            logger.info("=" * 80)
            logger.info("🔍 [DEBUG-ASYNC] 完整 request_params:")
            logger.info(f"   model: {request_params.get('model')}")
            logger.info(f"   messages: {len(request_params.get('messages', []))}")
            logger.info("=" * 80)

        # API 调用
        try:
            response = await self.client.chat.completions.create(**request_params)
        except Exception as e:
            if not is_probe:
                logger.error(f"OpenAI API 调用失败: {e}")
            raise

        # 转换响应（含音频输出处理）
        return self._parse_response(response)

    async def create_message_stream(
        self,
        messages: List[Message],
        system: Optional[Union[str, List[Dict[str, Any]]]] = None,
        tools: Optional[List[Union[ToolType, str, Dict]]] = None,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_content: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[Dict], None]] = None,
        **kwargs,
    ) -> AsyncIterator[LLMResponse]:
        """
        创建消息（流式）

        Args:
            messages: 消息列表
            system: 系统提示词
            tools: 工具列表
            on_thinking: thinking 回调（推理模型通过 reasoning_content 返回）
            on_content: content 回调
            on_tool_call: tool_call 回调
            **kwargs: 其他参数

        Yields:
            LLMResponse 片段
        """
        # 使用 adaptor 转换消息
        converted = self._adaptor.convert_messages_to_provider(messages)
        openai_messages = converted["messages"]

        # 构建请求参数
        request_params = {
            "model": self.config.model,
            "messages": openai_messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        # 音频模型参数
        if _is_audio_model(self.config.model):
            request_params["modalities"] = ["text", "audio"]
            request_params["audio"] = {
                "voice": kwargs.get("audio_voice", "alloy"),
                "format": kwargs.get("audio_format", "wav"),
            }

        # System prompt
        if system:
            if isinstance(system, list):
                system_text = "\n".join(
                    block.get("text", "") for block in system if block.get("type") == "text"
                )
                request_params["messages"].insert(0, {"role": "system", "content": system_text})
            elif isinstance(system, dict):
                system_text = (
                    system.get("text", "") if system.get("type") == "text" else str(system)
                )
                request_params["messages"].insert(0, {"role": "system", "content": system_text})
            else:
                # 字符串格式
                request_params["messages"].insert(0, {"role": "system", "content": str(system)})

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

        logger.info(
            f"📤 OpenAI 流式请求: model={self.config.model}, messages={len(openai_messages)}"
        )

        # 累积变量
        accumulated_content = ""
        accumulated_thinking = ""
        accumulated_audio_data = ""
        tool_calls = []
        stop_reason = None
        usage = {}

        try:
            stream = await self.client.chat.completions.create(**request_params)

            async for chunk in stream:
                if not chunk.choices:
                    # 最后一个 chunk（包含 usage）
                    if chunk.usage:
                        usage = {
                            "input_tokens": chunk.usage.prompt_tokens,
                            "output_tokens": chunk.usage.completion_tokens,
                        }
                        # 提取 reasoning tokens（如果有）
                        if hasattr(chunk.usage, "completion_tokens_details"):
                            details = chunk.usage.completion_tokens_details
                            reasoning_tokens = getattr(details, "reasoning_tokens", 0) if details else 0
                            if reasoning_tokens:
                                usage["thinking_tokens"] = reasoning_tokens
                        logger.info(
                            f"📊 Token 使用: input={usage['input_tokens']:,}, "
                            f"output={usage['output_tokens']:,}"
                        )
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                # 处理思考内容（OpenAI 推理模型通过 reasoning_content 返回）
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

                # 处理普通内容
                if delta.content:
                    accumulated_content += delta.content
                    if on_content:
                        on_content(delta.content)
                    yield LLMResponse(
                        content=delta.content, model=self.config.model, is_stream=True
                    )

                # 处理音频输出（OpenAI 音频模型通过 delta.audio 返回流式音频）
                if hasattr(delta, "audio") and delta.audio:
                    audio_chunk = getattr(delta.audio, "data", None)
                    if audio_chunk:
                        accumulated_audio_data += audio_chunk

                    audio_transcript = getattr(delta.audio, "transcript", None)
                    if audio_transcript:
                        accumulated_content += audio_transcript
                        if on_content:
                            on_content(audio_transcript)
                        yield LLMResponse(
                            content=audio_transcript, model=self.config.model, is_stream=True
                        )

                # 处理工具调用
                if delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        index = tool_call.index

                        # 确保 tool_calls 列表足够长
                        while len(tool_calls) <= index:
                            tool_calls.append(
                                {"id": "", "name": "", "arguments": "", "type": "function"}
                            )

                        # 累积字段
                        if tool_call.id:
                            tool_calls[index]["id"] = tool_call.id

                            # 🆕 Tool Use Start 事件（流式）
                            yield LLMResponse(
                                content="",
                                model=self.config.model,
                                is_stream=True,
                                tool_use_start={
                                    "type": "tool_use",
                                    "id": tool_call.id,
                                    "name": tool_call.function.name if tool_call.function else "",
                                },
                            )

                        if tool_call.function:
                            if tool_call.function.name:
                                tool_calls[index]["name"] = tool_call.function.name
                            if tool_call.function.arguments:
                                tool_calls[index]["arguments"] += tool_call.function.arguments

                                # 🆕 Input Delta 事件（流式）
                                yield LLMResponse(
                                    content="",
                                    model=self.config.model,
                                    is_stream=True,
                                    input_delta=tool_call.function.arguments,
                                )

                        # 回调
                        if on_tool_call:
                            on_tool_call(
                                {
                                    "id": tool_call.id,
                                    "name": tool_call.function.name if tool_call.function else "",
                                    "arguments": (
                                        tool_call.function.arguments if tool_call.function else ""
                                    ),
                                }
                            )

                # 停止原因
                if choice.finish_reason:
                    stop_reason = choice.finish_reason

            # 处理累积的工具调用
            formatted_tool_calls = []
            for tc in tool_calls:
                if tc.get("name"):
                    try:
                        input_dict = (
                            json.loads(tc["arguments"], strict=False) if tc["arguments"] else {}
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

            # 构建 raw_content
            raw_content = []
            if accumulated_thinking:
                raw_content.append({"type": "thinking", "thinking": accumulated_thinking})
            if accumulated_content:
                raw_content.append({"type": "text", "text": accumulated_content})
            for tc in formatted_tool_calls:
                raw_content.append(
                    {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["input"]}
                )

            logger.info(f"📥 OpenAI 响应: stop_reason={stop_reason or 'stop'}")

            if stop_reason == "tool_calls" or (formatted_tool_calls and stop_reason == "stop"):
                stop_reason = "tool_use"

            # 构建音频输出数据
            audio_data = None
            if accumulated_audio_data:
                audio_data = {
                    "data": accumulated_audio_data,
                    "transcript": accumulated_content,
                    "format": "wav",
                }
                logger.info(
                    f"🎵 OpenAI 音频输出: data_len={len(accumulated_audio_data)}"
                )

            # 返回最终响应
            yield LLMResponse(
                content=accumulated_content,
                thinking=accumulated_thinking if accumulated_thinking else None,
                tool_calls=formatted_tool_calls if formatted_tool_calls else None,
                stop_reason=stop_reason or "stop",
                usage=usage if usage else None,
                model=self.config.model,
                raw_content=raw_content,
                audio_data=audio_data,
                is_stream=False,
            )

        except Exception as e:
            logger.error(f"OpenAI 流式传输错误: {e}")
            raise

    def count_tokens(self, text: str) -> int:
        """
        计算 token 数量

        TODO: OpenAI 可以使用 tiktoken 精确计算（已在父类实现）
        - tiktoken 是 OpenAI 官方的 tokenizer
        - cl100k_base 适用于 GPT-4 系列

        当前使用父类的 tiktoken 实现。

        Args:
            text: 要计算的文本

        Returns:
            token 数量
        """
        # OpenAI 直接使用 tiktoken（父类实现）即可
        return super().count_tokens(text)

    def _parse_response(self, response) -> LLMResponse:
        """
        解析 OpenAI 响应为统一格式
        """
        choice = response.choices[0]
        message = choice.message

        content_text = message.content or ""

        # 提取思考内容（OpenAI 推理模型通过 reasoning_content 返回）
        thinking_text = getattr(message, "reasoning_content", None)

        # 提取音频输出（音频模型通过 message.audio 返回）
        audio_data = None
        if hasattr(message, "audio") and message.audio:
            audio_data = {
                "data": getattr(message.audio, "data", ""),
                "transcript": getattr(message.audio, "transcript", ""),
                "format": getattr(message.audio, "format", "wav"),
                "id": getattr(message.audio, "id", ""),
                "expires_at": getattr(message.audio, "expires_at", None),
            }
            if audio_data["transcript"] and not content_text:
                content_text = audio_data["transcript"]
            logger.info(
                f"🎵 收到音频输出: format={audio_data['format']}, "
                f"transcript_len={len(audio_data.get('transcript', ''))}"
            )

        # 提取工具调用
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                input_dict = json.loads(tc.function.arguments) if tc.function.arguments else {}
                tool_calls.append(
                    {"id": tc.id, "name": tc.function.name, "input": input_dict, "type": "tool_use"}
                )

        # Usage 信息
        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }
            if hasattr(response.usage, "completion_tokens_details"):
                details = response.usage.completion_tokens_details
                reasoning_tokens = getattr(details, "reasoning_tokens", 0) if details else 0
                if reasoning_tokens:
                    usage["thinking_tokens"] = reasoning_tokens
            logger.info(
                f"📊 Token 使用: input={usage['input_tokens']:,}, "
                f"output={usage['output_tokens']:,}"
            )

        stop_reason = choice.finish_reason
        if stop_reason == "tool_calls" or (tool_calls and stop_reason == "stop"):
            stop_reason = "tool_use"

        # 构建 raw_content
        raw_content = []
        if thinking_text:
            raw_content.append({"type": "thinking", "thinking": thinking_text})
        if content_text:
            raw_content.append({"type": "text", "text": content_text})
        for tc in tool_calls:
            raw_content.append(
                {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["input"]}
            )

        llm_response = LLMResponse(
            content=content_text,
            thinking=thinking_text,
            tool_calls=tool_calls if tool_calls else None,
            stop_reason=stop_reason,
            usage=usage,
            model=self.config.model,
            raw_content=raw_content,
        )

        if audio_data:
            llm_response.audio_data = audio_data

        return llm_response


# ============================================================
# 注册到 LLMRegistry
# ============================================================


def _register_openai():
    """延迟注册 OpenAI Provider（避免循环导入）"""
    from .defaults import get_default_model
    from .registry import LLMRegistry

    LLMRegistry.register(
        name="openai",
        service_class=OpenAILLMService,
        adaptor_class=OpenAIAdaptor,
        default_model=get_default_model("openai"),
        api_key_env="OPENAI_API_KEY",
        display_name="OpenAI",
        description="OpenAI GPT 系列模型",
        supported_features=[
            "streaming",
            "tool_calling",
            "function_calling",
            "thinking",
        ],
    )

    LLMRegistry.register(
        name="kimi",
        service_class=OpenAILLMService,
        adaptor_class=OpenAIAdaptor,
        default_model=get_default_model("kimi"),
        api_key_env="MOONSHOT_API_KEY",
        display_name="Kimi (Moonshot)",
        description="Moonshot AI Kimi 系列模型（OpenAI 兼容）",
        supported_features=[
            "streaming",
            "tool_calling",
            "thinking",
        ],
    )


# 模块加载时注册
_register_openai()

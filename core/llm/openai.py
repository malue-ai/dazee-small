"""
OpenAI LLM 服务实现

双通道架构：
- Reasoning 模型（GPT-5.x / o-series）→ Responses API（/v1/responses）
- 其他模型（GPT-4o 等）及兼容提供商（Kimi）→ Chat Completions API

参考文档：
- https://developers.openai.com/api/docs/guides/text
- https://developers.openai.com/api/docs/guides/function-calling
- https://developers.openai.com/api/docs/guides/streaming-responses
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

LLM_DEBUG_VERBOSE = os.getenv("LLM_DEBUG_VERBOSE", "").lower() in ("1", "true", "yes")

OPENAI_AUDIO_MODELS = {
    "gpt-audio",
    "gpt-4o-audio-preview",
    "gpt-4o-audio-preview-2024-12-17",
}

_REASONING_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")

_OPENAI_OFFICIAL_HOSTS = ("api.openai.com",)


def _is_audio_model(model: str) -> bool:
    return any(m in model for m in OPENAI_AUDIO_MODELS)


def _is_reasoning_model(model: str) -> bool:
    return any(model.startswith(p) for p in _REASONING_MODEL_PREFIXES)


def _thinking_budget_to_effort(budget: int) -> str:
    """Map internal thinking budget to OpenAI reasoning effort.

    GPT-5.4 supports: none, low, medium, high, xhigh.
    """
    if budget <= 0:
        return "none"
    if budget <= 3000:
        return "low"
    if budget <= 8000:
        return "medium"
    if budget <= 20000:
        return "high"
    return "xhigh"


# keep old name for backward compat (used by llm_profiles)
_supports_reasoning_effort = _is_reasoning_model


# ============================================================
# OpenAI LLM 服务
# ============================================================


class OpenAILLMService(BaseLLMService):
    """
    OpenAI LLM 服务（双通道：Responses API + Chat Completions）

    Reasoning 模型自动走 Responses API 获得更好的推理性能，
    其他模型和 OpenAI 兼容提供商（Kimi 等）走 Chat Completions。
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self._adaptor = OpenAIAdaptor()

        api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OpenAI API Key 未设置。请设置 OPENAI_API_KEY 环境变量或传入 api_key 参数"
            )

        base_url = self.config.base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        self._base_url = base_url

        timeout = getattr(self.config, "timeout", 120.0)
        max_retries = getattr(self.config, "max_retries", 3)

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

        self._custom_tools: List[Dict[str, Any]] = []

        api_mode = "Responses" if self._use_responses_api() else "Chat Completions"
        logger.info(
            f"✅ OpenAI 服务初始化成功: model={self.config.model}, "
            f"api={api_mode}, base_url={base_url}"
        )

    # ============================================================
    # API 通道选择
    # ============================================================

    def _use_responses_api(self) -> bool:
        """Reasoning 模型 + OpenAI 官方端点 → Responses API"""
        if not _is_reasoning_model(self.config.model):
            return False
        return any(h in self._base_url for h in _OPENAI_OFFICIAL_HOSTS)

    # ============================================================
    # 自定义工具管理
    # ============================================================

    def add_custom_tool(self, name: str, description: str, input_schema: Dict[str, Any]) -> None:
        for i, tool in enumerate(self._custom_tools):
            if tool["name"] == name:
                self._custom_tools[i] = {
                    "name": name, "description": description, "input_schema": input_schema,
                }
                return
        self._custom_tools.append(
            {"name": name, "description": description, "input_schema": input_schema}
        )

    def remove_custom_tool(self, name: str) -> bool:
        for i, tool in enumerate(self._custom_tools):
            if tool["name"] == name:
                self._custom_tools.pop(i)
                return True
        return False

    def get_custom_tools(self) -> List[Dict[str, Any]]:
        return self._custom_tools.copy()

    def clear_custom_tools(self) -> None:
        self._custom_tools.clear()

    # ============================================================
    # 工具格式转换
    # ============================================================

    def _format_tools_chat(self, tools: List[Union[ToolType, str, Dict]]) -> List[Dict[str, Any]]:
        """格式化工具 → Chat Completions 格式 (嵌套 function 字段)"""
        formatted = []
        for tool in tools:
            if isinstance(tool, ToolType):
                continue
            elif isinstance(tool, str):
                for ct in self._custom_tools:
                    if ct.get("name") == tool:
                        formatted.append(self._to_chat_tool(ct))
                        break
            elif isinstance(tool, dict):
                formatted.append(self._to_chat_tool(tool))
        return formatted

    @staticmethod
    def _to_chat_tool(tool: Dict[str, Any]) -> Dict[str, Any]:
        if tool.get("type") == "function" and "function" in tool:
            return tool
        return {
            "type": "function",
            "function": {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema") or tool.get("parameters", {}),
            },
        }

    @staticmethod
    def _to_responses_tool(tool: Dict[str, Any]) -> Dict[str, Any]:
        """转换工具 → Responses API 格式 (扁平 name/parameters)"""
        if tool.get("type") == "function" and "function" in tool:
            func = tool["function"]
            return {
                "type": "function",
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "parameters": func.get("parameters", {}),
            }
        return {
            "type": "function",
            "name": tool.get("name", ""),
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema") or tool.get("parameters", {}),
        }

    @staticmethod
    def _normalize_tool_choice(tool_choice: Any) -> Any:
        if isinstance(tool_choice, str):
            return tool_choice
        if isinstance(tool_choice, dict) and tool_choice.get("type") == "tool":
            return {"type": "function", "function": {"name": tool_choice["name"]}}
        return tool_choice

    def _collect_tools(
        self, tools: Optional[List[Union[ToolType, str, Dict]]], for_responses: bool = False,
    ) -> List[Dict[str, Any]]:
        """收集并去重所有工具（外部 + 自定义），按目标 API 格式化。"""
        converter = self._to_responses_tool if for_responses else self._to_chat_tool
        all_tools: List[Dict[str, Any]] = []
        seen: set = set()

        if tools:
            raw = self._format_tools_chat(tools) if not for_responses else []
            if for_responses:
                for t in tools:
                    if isinstance(t, ToolType):
                        continue
                    elif isinstance(t, str):
                        for ct in self._custom_tools:
                            if ct.get("name") == t:
                                raw.append(converter(ct))
                                break
                    elif isinstance(t, dict):
                        raw.append(converter(t))
            for item in raw:
                name = (
                    item.get("name", "")
                    or item.get("function", {}).get("name", "")
                )
                if name and name not in seen:
                    all_tools.append(item)
                    seen.add(name)

        for ct in self._custom_tools:
            name = ct.get("name", "")
            if name and name not in seen:
                all_tools.append(converter(ct))
                seen.add(name)

        return all_tools

    # ============================================================
    # 系统提示词提取
    # ============================================================

    @staticmethod
    def _extract_system_text(system: Optional[Union[str, List[Dict[str, Any]], Dict]]) -> str:
        if not system:
            return ""
        if isinstance(system, list):
            return "\n".join(
                b.get("text", "") for b in system if b.get("type") == "text"
            )
        if isinstance(system, dict):
            return system.get("text", "") if system.get("type") == "text" else str(system)
        return str(system)

    # ============================================================
    # Chat Completions → Responses API 消息格式转换
    # ============================================================

    @staticmethod
    def _chat_messages_to_responses_input(
        messages: List[Dict[str, Any]],
    ) -> tuple:
        """Convert Chat Completions messages to Responses API input + instructions.

        Maps system/developer → instructions, user/assistant/tool → input items.
        Converts Chat content parts (text/image_url) to Responses format (input_text/input_image).

        Returns:
            (instructions: str, input_items: list)
        """
        instructions = ""
        items: List[Dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "")

            if role in ("system", "developer"):
                text = msg.get("content", "")
                if text:
                    instructions = (instructions + "\n" + text).strip() if instructions else text

            elif role == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = OpenAILLMService._convert_content_to_responses(content)
                items.append({"role": "user", "content": content})

            elif role == "assistant":
                content = msg.get("content")
                if content:
                    if isinstance(content, str):
                        items.append({"role": "assistant", "content": content})
                    elif isinstance(content, list):
                        text = "\n".join(
                            p.get("text", "") for p in content
                            if isinstance(p, dict) and p.get("type") == "text" and p.get("text")
                        )
                        if text:
                            items.append({"role": "assistant", "content": text})

                for tc in msg.get("tool_calls", []):
                    func = tc.get("function", {})
                    items.append({
                        "type": "function_call",
                        "call_id": tc.get("id", ""),
                        "name": func.get("name", ""),
                        "arguments": func.get("arguments", "{}"),
                    })

            elif role == "tool":
                items.append({
                    "type": "function_call_output",
                    "call_id": msg.get("tool_call_id", ""),
                    "output": msg.get("content", ""),
                })

        return instructions, items

    @staticmethod
    def _convert_content_to_responses(parts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert Chat Completions content parts to Responses API format.

        Chat: text/image_url → Responses: input_text/input_image
        """
        result = []
        for part in parts:
            ptype = part.get("type", "")

            if ptype == "text":
                result.append({"type": "input_text", "text": part.get("text", "")})

            elif ptype == "image_url":
                url = ""
                img = part.get("image_url")
                if isinstance(img, dict):
                    url = img.get("url", "")
                elif isinstance(img, str):
                    url = img
                result.append({"type": "input_image", "image_url": url})

            elif ptype == "input_audio":
                result.append(part)

            else:
                result.append({"type": "input_text", "text": str(part)})

        return result

    # ============================================================
    # 核心 API — 路由入口
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
        converted = self._adaptor.convert_messages_to_provider(messages)
        openai_messages = converted["messages"]

        if self._use_responses_api():
            return await self._create_via_responses(openai_messages, system, tools, is_probe, **kwargs)
        return await self._create_via_chat(openai_messages, system, tools, is_probe, **kwargs)

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
        converted = self._adaptor.convert_messages_to_provider(messages)
        openai_messages = converted["messages"]

        if self._use_responses_api():
            async for resp in self._stream_via_responses(
                openai_messages, system, tools, on_thinking, on_content, on_tool_call, **kwargs
            ):
                yield resp
        else:
            async for resp in self._stream_via_chat(
                openai_messages, system, tools, on_thinking, on_content, on_tool_call, **kwargs
            ):
                yield resp

    # ============================================================
    # 通道 A: Chat Completions API（GPT-4o / 兼容提供商）
    # ============================================================

    async def _create_via_chat(
        self, openai_messages, system, tools, is_probe, **kwargs,
    ) -> LLMResponse:
        _max = kwargs.get("max_tokens", self.config.max_tokens)
        _is_reasoning = _is_reasoning_model(self.config.model)

        request_params: Dict[str, Any] = {
            "model": self.config.model,
            "messages": openai_messages,
            "stream": False,
        }

        if _is_reasoning:
            request_params["max_completion_tokens"] = _max
            effort = kwargs.get("reasoning_effort")
            if effort:
                request_params["reasoning_effort"] = effort
            elif self.config.enable_thinking:
                request_params["reasoning_effort"] = _thinking_budget_to_effort(
                    self.config.thinking_budget
                )
        else:
            request_params["max_tokens"] = _max
            request_params["temperature"] = kwargs.get("temperature", self.config.temperature)

        if _is_audio_model(self.config.model):
            request_params["modalities"] = ["text", "audio"]
            request_params["audio"] = {
                "voice": kwargs.get("audio_voice", "alloy"),
                "format": kwargs.get("audio_format", "wav"),
            }

        sys_text = self._extract_system_text(system)
        if sys_text:
            request_params["messages"].insert(0, {"role": "system", "content": sys_text})

        all_tools = self._collect_tools(tools, for_responses=False)
        if all_tools:
            request_params["tools"] = all_tools
            request_params["tool_choice"] = self._normalize_tool_choice(
                kwargs.get("tool_choice", "auto")
            )

        logger.debug(f"📤 [Chat] 请求: model={self.config.model}, messages={len(openai_messages)}")

        try:
            response = await self.client.chat.completions.create(**request_params)
        except Exception as e:
            if not is_probe:
                logger.error(f"OpenAI Chat API 调用失败: {e}")
            raise

        return self._parse_chat_response(response)

    async def _stream_via_chat(
        self, openai_messages, system, tools, on_thinking, on_content, on_tool_call, **kwargs,
    ) -> AsyncIterator[LLMResponse]:
        _max = kwargs.get("max_tokens", self.config.max_tokens)
        _is_reasoning = _is_reasoning_model(self.config.model)

        request_params: Dict[str, Any] = {
            "model": self.config.model,
            "messages": openai_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if _is_reasoning:
            request_params["max_completion_tokens"] = _max
            effort = kwargs.get("reasoning_effort")
            if effort:
                request_params["reasoning_effort"] = effort
            elif self.config.enable_thinking:
                request_params["reasoning_effort"] = _thinking_budget_to_effort(
                    self.config.thinking_budget
                )
        else:
            request_params["max_tokens"] = _max
            request_params["temperature"] = kwargs.get("temperature", self.config.temperature)

        if _is_audio_model(self.config.model):
            request_params["modalities"] = ["text", "audio"]
            request_params["audio"] = {
                "voice": kwargs.get("audio_voice", "alloy"),
                "format": kwargs.get("audio_format", "wav"),
            }

        sys_text = self._extract_system_text(system)
        if sys_text:
            request_params["messages"].insert(0, {"role": "system", "content": sys_text})

        all_tools = self._collect_tools(tools, for_responses=False)
        if all_tools:
            request_params["tools"] = all_tools
            request_params["tool_choice"] = self._normalize_tool_choice(
                kwargs.get("tool_choice", "auto")
            )

        logger.info(f"📤 [Chat] 流式请求: model={self.config.model}, messages={len(openai_messages)}")

        accumulated_content = ""
        accumulated_thinking = ""
        accumulated_audio_data = ""
        tool_calls: List[Dict] = []
        stop_reason = None
        usage: Dict = {}

        try:
            stream = await self.client.chat.completions.create(**request_params)

            async for chunk in stream:
                if not chunk.choices:
                    if chunk.usage:
                        usage = {
                            "input_tokens": chunk.usage.prompt_tokens,
                            "output_tokens": chunk.usage.completion_tokens,
                        }
                        if hasattr(chunk.usage, "completion_tokens_details"):
                            details = chunk.usage.completion_tokens_details
                            rt = getattr(details, "reasoning_tokens", 0) if details else 0
                            if rt:
                                usage["thinking_tokens"] = rt
                        logger.info(
                            f"📊 Token 使用: input={usage['input_tokens']:,}, "
                            f"output={usage['output_tokens']:,}"
                        )
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    accumulated_thinking += delta.reasoning_content
                    if on_thinking:
                        on_thinking(delta.reasoning_content)
                    yield LLMResponse(
                        content="", thinking=delta.reasoning_content,
                        model=self.config.model, is_stream=True,
                    )

                if delta.content:
                    accumulated_content += delta.content
                    if on_content:
                        on_content(delta.content)
                    yield LLMResponse(
                        content=delta.content, model=self.config.model, is_stream=True,
                    )

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
                            content=audio_transcript, model=self.config.model, is_stream=True,
                        )

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        while len(tool_calls) <= idx:
                            tool_calls.append({"id": "", "name": "", "arguments": "", "type": "function"})
                        if tc.id:
                            tool_calls[idx]["id"] = tc.id
                            yield LLMResponse(
                                content="", model=self.config.model, is_stream=True,
                                tool_use_start={
                                    "type": "tool_use", "id": tc.id,
                                    "name": tc.function.name if tc.function else "",
                                },
                            )
                        if tc.function:
                            if tc.function.name:
                                tool_calls[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls[idx]["arguments"] += tc.function.arguments
                                yield LLMResponse(
                                    content="", model=self.config.model, is_stream=True,
                                    input_delta=tc.function.arguments,
                                )
                        if on_tool_call:
                            on_tool_call({
                                "id": tc.id,
                                "name": tc.function.name if tc.function else "",
                                "arguments": tc.function.arguments if tc.function else "",
                            })

                if choice.finish_reason:
                    stop_reason = choice.finish_reason

            formatted_tc = self._finalize_tool_calls(tool_calls)
            raw_content = self._build_raw_content(accumulated_thinking, accumulated_content, formatted_tc)

            if stop_reason == "tool_calls" or (formatted_tc and stop_reason == "stop"):
                stop_reason = "tool_use"

            audio_data = None
            if accumulated_audio_data:
                audio_data = {
                    "data": accumulated_audio_data,
                    "transcript": accumulated_content,
                    "format": "wav",
                }

            yield LLMResponse(
                content=accumulated_content,
                thinking=accumulated_thinking or None,
                tool_calls=formatted_tc or None,
                stop_reason=stop_reason or "stop",
                usage=usage or None,
                model=self.config.model,
                raw_content=raw_content,
                audio_data=audio_data,
                is_stream=False,
            )

        except Exception as e:
            logger.error(f"OpenAI Chat 流式传输错误: {e}")
            raise

    # ============================================================
    # 通道 B: Responses API（GPT-5.x / o-series）
    # ============================================================

    async def _create_via_responses(
        self, openai_messages, system, tools, is_probe, **kwargs,
    ) -> LLMResponse:
        sys_text = self._extract_system_text(system)
        if sys_text:
            openai_messages.insert(0, {"role": "developer", "content": sys_text})

        instructions, input_items = self._chat_messages_to_responses_input(openai_messages)
        _max = kwargs.get("max_tokens", self.config.max_tokens)

        request_params: Dict[str, Any] = {
            "model": self.config.model,
            "input": input_items,
            "stream": False,
        }
        if instructions:
            request_params["instructions"] = instructions
        if _max:
            request_params["max_output_tokens"] = _max

        reasoning_params: Dict[str, str] = {}
        effort = kwargs.get("reasoning_effort")
        if effort:
            reasoning_params["effort"] = effort
        elif self.config.enable_thinking:
            reasoning_params["effort"] = _thinking_budget_to_effort(self.config.thinking_budget)
        if self.config.enable_thinking:
            reasoning_params["summary"] = "auto"
        if reasoning_params:
            request_params["reasoning"] = reasoning_params

        all_tools = self._collect_tools(tools, for_responses=True)
        if all_tools:
            request_params["tools"] = all_tools
            tc = self._normalize_tool_choice(kwargs.get("tool_choice", "auto"))
            if tc and tc != "auto":
                request_params["tool_choice"] = tc

        logger.debug(
            f"📤 [Responses] 请求: model={self.config.model}, "
            f"input_items={len(input_items)}"
        )

        try:
            response = await self.client.responses.create(**request_params)
        except Exception as e:
            if not is_probe:
                logger.error(f"OpenAI Responses API 调用失败: {e}")
            raise

        return self._parse_responses_output(response)

    async def _stream_via_responses(
        self, openai_messages, system, tools,
        on_thinking, on_content, on_tool_call, **kwargs,
    ) -> AsyncIterator[LLMResponse]:
        sys_text = self._extract_system_text(system)
        if sys_text:
            openai_messages.insert(0, {"role": "developer", "content": sys_text})

        instructions, input_items = self._chat_messages_to_responses_input(openai_messages)
        _max = kwargs.get("max_tokens", self.config.max_tokens)

        request_params: Dict[str, Any] = {
            "model": self.config.model,
            "input": input_items,
            "stream": True,
        }
        if instructions:
            request_params["instructions"] = instructions
        if _max:
            request_params["max_output_tokens"] = _max

        reasoning_params: Dict[str, str] = {}
        effort = kwargs.get("reasoning_effort")
        if effort:
            reasoning_params["effort"] = effort
        elif self.config.enable_thinking:
            reasoning_params["effort"] = _thinking_budget_to_effort(self.config.thinking_budget)
        if self.config.enable_thinking:
            reasoning_params["summary"] = "auto"
        if reasoning_params:
            request_params["reasoning"] = reasoning_params

        all_tools = self._collect_tools(tools, for_responses=True)
        if all_tools:
            request_params["tools"] = all_tools
            tc = self._normalize_tool_choice(kwargs.get("tool_choice", "auto"))
            if tc and tc != "auto":
                request_params["tool_choice"] = tc

        logger.info(
            f"📤 [Responses] 流式请求: model={self.config.model}, "
            f"input_items={len(input_items)}"
        )

        accumulated_content = ""
        accumulated_thinking = ""
        func_calls: Dict[int, Dict[str, str]] = {}
        usage: Dict = {}

        try:
            stream = await self.client.responses.create(**request_params)

            async for event in stream:
                etype = event.type

                # --- 文本 delta ---
                if etype == "response.output_text.delta":
                    text = event.delta
                    accumulated_content += text
                    if on_content:
                        on_content(text)
                    yield LLMResponse(
                        content=text, model=self.config.model, is_stream=True,
                    )

                elif etype in (
                    "response.reasoning_summary_text.delta",
                    "response.reasoning_summary_part.delta",
                    "response.reasoning.delta",
                ):
                    text = getattr(event, "delta", "") or getattr(event, "text", "")
                    if text:
                        accumulated_thinking += text
                        if on_thinking:
                            on_thinking(text)
                        yield LLMResponse(
                            content="", thinking=text,
                            model=self.config.model, is_stream=True,
                        )

                # --- Function call: 新增 output item ---
                elif etype == "response.output_item.added":
                    item = event.item
                    if getattr(item, "type", "") == "function_call":
                        idx = event.output_index
                        call_id = getattr(item, "call_id", "") or ""
                        name = getattr(item, "name", "") or ""
                        func_calls[idx] = {
                            "call_id": call_id, "name": name, "arguments": "",
                        }
                        yield LLMResponse(
                            content="", model=self.config.model, is_stream=True,
                            tool_use_start={
                                "type": "tool_use", "id": call_id, "name": name,
                            },
                        )

                # --- Function call: 参数 delta ---
                elif etype == "response.function_call_arguments.delta":
                    idx = event.output_index
                    delta_text = event.delta
                    if idx in func_calls:
                        func_calls[idx]["arguments"] += delta_text
                    yield LLMResponse(
                        content="", model=self.config.model, is_stream=True,
                        input_delta=delta_text,
                    )
                    if on_tool_call:
                        fc = func_calls.get(idx, {})
                        on_tool_call({
                            "id": fc.get("call_id", ""),
                            "name": fc.get("name", ""),
                            "arguments": delta_text,
                        })

                # --- Function call: 完成 ---
                elif etype == "response.function_call_arguments.done":
                    pass

                elif etype == "response.completed":
                    resp_obj = event.response
                    if hasattr(resp_obj, "usage") and resp_obj.usage:
                        u = resp_obj.usage
                        usage = {
                            "input_tokens": getattr(u, "input_tokens", 0),
                            "output_tokens": getattr(u, "output_tokens", 0),
                        }
                        out_details = getattr(u, "output_tokens_details", None)
                        rt = getattr(out_details, "reasoning_tokens", 0) if out_details else 0
                        if not rt:
                            rt = getattr(u, "reasoning_tokens", 0)
                        if rt:
                            usage["thinking_tokens"] = rt
                        logger.info(
                            f"📊 Token 使用: input={usage.get('input_tokens', 0):,}, "
                            f"output={usage.get('output_tokens', 0):,}"
                        )
                    break

            formatted_tc = []
            for fc in func_calls.values():
                if fc.get("name"):
                    try:
                        input_dict = json.loads(fc["arguments"], strict=False) if fc["arguments"] else {}
                        formatted_tc.append({
                            "id": fc["call_id"], "name": fc["name"],
                            "input": input_dict, "type": "tool_use",
                        })
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ Responses API 工具参数解析失败: {e}")

            raw_content = self._build_raw_content(accumulated_thinking, accumulated_content, formatted_tc)
            stop_reason = "tool_use" if formatted_tc else "stop"

            yield LLMResponse(
                content=accumulated_content,
                thinking=accumulated_thinking or None,
                tool_calls=formatted_tc or None,
                stop_reason=stop_reason,
                usage=usage or None,
                model=self.config.model,
                raw_content=raw_content,
                is_stream=False,
            )

        except Exception as e:
            logger.error(f"OpenAI Responses API 流式错误: {e}")
            raise

    # ============================================================
    # 响应解析
    # ============================================================

    def _parse_chat_response(self, response) -> LLMResponse:
        """解析 Chat Completions API 响应"""
        choice = response.choices[0]
        message = choice.message

        content_text = message.content or ""
        thinking_text = getattr(message, "reasoning_content", None)

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

        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                input_dict = json.loads(tc.function.arguments) if tc.function.arguments else {}
                tool_calls.append(
                    {"id": tc.id, "name": tc.function.name, "input": input_dict, "type": "tool_use"}
                )

        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }
            if hasattr(response.usage, "completion_tokens_details"):
                details = response.usage.completion_tokens_details
                rt = getattr(details, "reasoning_tokens", 0) if details else 0
                if rt:
                    usage["thinking_tokens"] = rt
            logger.info(
                f"📊 Token 使用: input={usage['input_tokens']:,}, "
                f"output={usage['output_tokens']:,}"
            )

        stop_reason = choice.finish_reason
        if stop_reason == "tool_calls" or (tool_calls and stop_reason == "stop"):
            stop_reason = "tool_use"

        raw_content = self._build_raw_content(thinking_text, content_text, tool_calls)

        llm_resp = LLMResponse(
            content=content_text, thinking=thinking_text,
            tool_calls=tool_calls or None,
            stop_reason=stop_reason, usage=usage,
            model=self.config.model, raw_content=raw_content,
        )
        if audio_data:
            llm_resp.audio_data = audio_data
        return llm_resp

    def _parse_responses_output(self, response) -> LLMResponse:
        """解析 Responses API 响应"""
        content_text = getattr(response, "output_text", "") or ""
        thinking_text = ""
        tool_calls = []

        for item in response.output:
            item_type = getattr(item, "type", "")

            if item_type == "reasoning":
                summary = getattr(item, "summary", None)
                if summary:
                    for part in summary:
                        t = getattr(part, "text", "")
                        if t:
                            thinking_text += t

            elif item_type == "function_call":
                call_id = getattr(item, "call_id", "")
                name = getattr(item, "name", "")
                args_str = getattr(item, "arguments", "{}")
                try:
                    input_dict = json.loads(args_str, strict=False) if args_str else {}
                except json.JSONDecodeError:
                    input_dict = {}
                tool_calls.append({
                    "id": call_id, "name": name,
                    "input": input_dict, "type": "tool_use",
                })

            elif item_type == "message":
                for part in getattr(item, "content", []):
                    if getattr(part, "type", "") == "output_text":
                        t = getattr(part, "text", "")
                        if t and not content_text:
                            content_text = t

        usage = {}
        if hasattr(response, "usage") and response.usage:
            u = response.usage
            usage = {
                "input_tokens": getattr(u, "input_tokens", 0),
                "output_tokens": getattr(u, "output_tokens", 0),
            }
            out_details = getattr(u, "output_tokens_details", None)
            rt = getattr(out_details, "reasoning_tokens", 0) if out_details else 0
            if not rt:
                rt = getattr(u, "reasoning_tokens", 0)
            if rt:
                usage["thinking_tokens"] = rt
            logger.info(
                f"📊 Token 使用: input={usage['input_tokens']:,}, "
                f"output={usage['output_tokens']:,}"
            )

        stop_reason = "tool_use" if tool_calls else "stop"
        raw_content = self._build_raw_content(thinking_text, content_text, tool_calls)

        return LLMResponse(
            content=content_text,
            thinking=thinking_text or None,
            tool_calls=tool_calls or None,
            stop_reason=stop_reason,
            usage=usage,
            model=self.config.model,
            raw_content=raw_content,
        )

    # ============================================================
    # 通用工具方法
    # ============================================================

    @staticmethod
    def _finalize_tool_calls(tool_calls: List[Dict]) -> List[Dict[str, Any]]:
        result = []
        for tc in tool_calls:
            if tc.get("name"):
                try:
                    input_dict = json.loads(tc["arguments"], strict=False) if tc["arguments"] else {}
                    result.append({
                        "id": tc["id"], "name": tc["name"],
                        "input": input_dict, "type": "tool_use",
                    })
                except json.JSONDecodeError as e:
                    logger.error(f"❌ 工具调用参数解析失败: {e}")
        return result

    @staticmethod
    def _build_raw_content(
        thinking: Optional[str], content: str, tool_calls: List[Dict],
    ) -> List[Dict[str, Any]]:
        raw: List[Dict[str, Any]] = []
        if thinking:
            raw.append({"type": "thinking", "thinking": thinking})
        if content:
            raw.append({"type": "text", "text": content})
        for tc in tool_calls:
            raw.append({
                "type": "tool_use", "id": tc["id"],
                "name": tc["name"], "input": tc["input"],
            })
        return raw

    def count_tokens(self, text: str) -> int:
        return super().count_tokens(text)


# ============================================================
# 注册到 LLMRegistry
# ============================================================


def _register_openai():
    from .defaults import get_default_model
    from .registry import LLMRegistry

    LLMRegistry.register(
        name="openai",
        service_class=OpenAILLMService,
        adaptor_class=OpenAIAdaptor,
        default_model=get_default_model("openai"),
        api_key_env="OPENAI_API_KEY",
        display_name="OpenAI",
        description="OpenAI GPT 系列模型（Reasoning 模型自动使用 Responses API）",
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
        description="Moonshot AI Kimi 系列模型（OpenAI 兼容，走 Chat Completions）",
        supported_features=[
            "streaming",
            "tool_calling",
            "thinking",
        ],
    )


_register_openai()

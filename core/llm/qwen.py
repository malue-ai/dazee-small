"""
Qwen LLM 服务实现（DashScope SDK）
"""

import asyncio
import os
import threading
from typing import Dict, Any, Optional, List, Union, AsyncIterator, Callable

import dashscope

from logger import get_logger
from .base import (
    BaseLLMService,
    LLMConfig,
    LLMResponse,
    Message,
    ToolType,
)
from .adaptor import OpenAIAdaptor
from .tool_call_utils import normalize_tool_calls

logger = get_logger("llm.qwen")


class QwenLLMService(BaseLLMService):
    """
    Qwen LLM 服务（DashScope SDK）
    """
    
    def __init__(self, config: LLMConfig):
        """
        初始化 Qwen 服务
        
        Args:
            config: LLM 配置
        """
        if not config.api_key:
            config.api_key = dashscope.api_key or None
        if not config.api_key:
            config.api_key = os.getenv("DASHSCOPE_API_KEY")
        self.config = config
        self._adaptor = OpenAIAdaptor()
        self._custom_tools: List[Dict[str, Any]] = []
        self.base_url = config.base_url
        
        if config.api_key:
            dashscope.api_key = config.api_key
        if config.base_url:
            dashscope.base_http_api_url = self._normalize_dashscope_base_url(config.base_url)
    
    def _normalize_dashscope_base_url(self, base_url: str) -> str:
        """
        规范化 DashScope SDK base_url
        
        Args:
            base_url: 原始 base_url
            
        Returns:
            SDK 可用的 base_url（/api/v1）
        """
        normalized = base_url.rstrip("/")
        if "compatible-mode" in normalized:
            normalized = normalized.replace("/compatible-mode/v1", "/api/v1")
        elif normalized.endswith("/v1") and not normalized.endswith("/api/v1"):
            normalized = normalized[:-3] + "/api/v1"
        return normalized

    def _supports_thinking_model(self, model_name: str) -> bool:
        """
        判断模型是否支持思考模式（Qwen3/Qwen3-VL）

        Args:
            model_name: 模型名称

        Returns:
            是否支持思考模式
        """
        if not model_name:
            return False
        return "qwen3" in model_name.lower()
    
    def add_custom_tool(self, name: str, description: str, input_schema: Dict[str, Any]) -> None:
        """
        注册自定义工具（OpenAI-Compatible）
        """
        self._custom_tools.append({
            "name": name,
            "description": description,
            "input_schema": input_schema
        })
    
    def _build_payload(
        self,
        messages: List[Message],
        system: Optional[str],
        tools: Optional[List[Union[ToolType, str, Dict]]],
        **kwargs
    ) -> Dict[str, Any]:
        """
        构建 DashScope 请求参数
        """
        payload = self._adaptor.convert_messages_to_provider(messages, system)
        params: Dict[str, Any] = {
            "model": self.config.model,
            "messages": payload.get("messages", []),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "result_format": kwargs.get("result_format", self.config.result_format or "message"),
        }
        
        top_p = kwargs.get("top_p", self.config.top_p)
        if top_p is not None:
            params["top_p"] = top_p
        frequency_penalty = kwargs.get("frequency_penalty", self.config.frequency_penalty)
        if frequency_penalty is not None:
            params["frequency_penalty"] = frequency_penalty
        presence_penalty = kwargs.get("presence_penalty", self.config.presence_penalty)
        if presence_penalty is not None:
            params["presence_penalty"] = presence_penalty
        repetition_penalty = kwargs.get("repetition_penalty", self.config.repetition_penalty)
        if repetition_penalty is not None:
            params["repetition_penalty"] = repetition_penalty
        tool_choice = kwargs.get("tool_choice", self.config.tool_choice)
        if tool_choice is not None:
            params["tool_choice"] = tool_choice
        parallel_tool_calls = kwargs.get("parallel_tool_calls", self.config.parallel_tool_calls)
        if parallel_tool_calls is not None:
            params["parallel_tool_calls"] = parallel_tool_calls

        # Qwen 额外参数（按需透传）
        enable_thinking = kwargs.get("enable_thinking")
        if enable_thinking is None and self._supports_thinking_model(self.config.model):
            enable_thinking = getattr(self.config, "enable_thinking", None)
        if enable_thinking is not None and self._supports_thinking_model(self.config.model):
            params["enable_thinking"] = enable_thinking
            if enable_thinking:
                thinking_budget = kwargs.get("thinking_budget", getattr(self.config, "thinking_budget", None))
                if thinking_budget is not None:
                    params["thinking_budget"] = thinking_budget

        optional_params = [
            "top_k",
            "seed",
            "stop",
            "n",
            "response_format",
            "logprobs",
            "top_logprobs",
            "enable_search",
            "search_options",
            "incremental_output",
            "vl_high_resolution_images",
            "vl_enable_image_hw_output",
            "enable_code_interpreter",
        ]
        for key in optional_params:
            value = kwargs.get(key, getattr(self.config, key, None))
            if value is not None:
                params[key] = value

        if "search_options" in params and "enable_search" not in params:
            params["enable_search"] = True
        
        merged_tools = self._filter_tools(tools) + self._custom_tools
        if merged_tools:
            params["tools"] = self._adaptor.convert_tools_to_provider(merged_tools)
            if params.get("result_format") != "message":
                logger.warning("检测到工具调用，已强制将 result_format 设为 message")
                params["result_format"] = "message"
            if params.get("n") not in (None, 1):
                logger.warning("检测到工具调用，已强制将 n 设为 1")
                params["n"] = 1
        
        return params
    
    def _filter_tools(self, tools: Optional[List[Union[ToolType, str, Dict]]]) -> List[Dict[str, Any]]:
        """
        过滤工具列表，仅保留 dict 类型
        """
        if not tools:
            return []
        return [tool for tool in tools if isinstance(tool, dict)]
    
    def _get_value(self, obj: Any, key: str, default: Any = None) -> Any:
        """
        兼容 dict / 对象访问
        """
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)
    
    def _parse_response(self, response: Any) -> LLMResponse:
        """
        解析 DashScope 响应
        """
        status_code = self._get_value(response, "status_code")
        if status_code and status_code != 200:
            error_message = self._get_value(response, "message", "DashScope 调用失败")
            raise RuntimeError(f"DashScope 调用失败: {status_code} {error_message}")
        
        output = self._get_value(response, "output", {})
        choices = self._get_value(output, "choices", []) or []
        choice = choices[0] if choices else {}
        message = self._get_value(choice, "message", {}) or {}
        
        content = self._get_value(message, "content", "")
        thinking = self._get_value(message, "reasoning_content", "")
        tool_calls = self._get_value(message, "tool_calls")
        normalized_tool_calls = normalize_tool_calls(tool_calls)
        stop_reason = (
            self._get_value(choice, "finish_reason") or
            self._get_value(choice, "stop_reason") or
            "end_turn"
        )
        
        usage = self._get_value(response, "usage")
        usage_dict = None
        if usage:
            usage_dict = {
                "input_tokens": self._get_value(usage, "input_tokens", 0),
                "output_tokens": self._get_value(usage, "output_tokens", 0),
                "total_tokens": self._get_value(usage, "total_tokens", 0),
            }
        
        raw_content = []
        if thinking:
            raw_content.append({"type": "thinking", "thinking": thinking})
        if content:
            raw_content.append({"type": "text", "text": content})
        if normalized_tool_calls:
            for tc in normalized_tool_calls:
                raw_content.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": tc.get("name", ""),
                    "input": tc.get("input", {})
                })
        
        return LLMResponse(
            content=content or "",
            thinking=thinking or None,
            tool_calls=normalized_tool_calls,
            stop_reason=stop_reason,
            usage=usage_dict,
            raw_content=raw_content or None
        )
    
    async def create_message_async(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        tools: Optional[List[Union[ToolType, str, Dict]]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        创建消息（异步）
        """
        params = self._build_payload(messages, system, tools, **kwargs)
        
        def _call():
            return dashscope.Generation.call(**params)
        
        response = await asyncio.to_thread(_call)
        return self._parse_response(response)
    
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
        """
        创建消息（流式）
        """
        params = self._build_payload(messages, system, tools, **kwargs)
        params["stream"] = True
        if "incremental_output" not in params:
            params["incremental_output"] = True
        incremental_output = params.get("incremental_output", True)
        
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        
        def _run_stream():
            try:
                for chunk in dashscope.Generation.call(**params):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, e)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)
        
        thread = threading.Thread(target=_run_stream, daemon=True)
        thread.start()
        
        accumulated_content = ""
        accumulated_thinking = ""
        last_tool_calls: Optional[List[Dict[str, Any]]] = None
        last_stop_reason = "end_turn"
        usage_dict: Optional[Dict[str, int]] = None
        has_chunk = False
        
        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            
            has_chunk = True
            
            output = self._get_value(item, "output", {})
            choices = self._get_value(output, "choices", []) or []
            choice = choices[0] if choices else {}
            message = self._get_value(choice, "message", {}) or {}
            
            content = self._get_value(message, "content", "")
            thinking = self._get_value(message, "reasoning_content", "")
            tool_calls = self._get_value(message, "tool_calls")
            normalized_tool_calls = normalize_tool_calls(tool_calls)
            stop_reason = (
                self._get_value(choice, "finish_reason") or
                self._get_value(choice, "stop_reason") or
                "end_turn"
            )
            last_stop_reason = stop_reason or last_stop_reason
            
            usage = self._get_value(item, "usage")
            if usage:
                usage_dict = {
                    "input_tokens": self._get_value(usage, "input_tokens", 0),
                    "output_tokens": self._get_value(usage, "output_tokens", 0),
                    "total_tokens": self._get_value(usage, "total_tokens", 0),
                }
            
            delta_content = ""
            if content:
                if incremental_output:
                    delta_content = content
                    accumulated_content += content
                else:
                    delta_content = (
                        content[len(accumulated_content):]
                        if content.startswith(accumulated_content)
                        else content
                    )
                    accumulated_content = content
            
            delta_thinking = ""
            if thinking:
                if incremental_output:
                    delta_thinking = thinking
                    accumulated_thinking += thinking
                else:
                    delta_thinking = (
                        thinking[len(accumulated_thinking):]
                        if thinking.startswith(accumulated_thinking)
                        else thinking
                    )
                    accumulated_thinking = thinking
            
            if delta_thinking and on_thinking:
                on_thinking(delta_thinking)
            if delta_content and on_content:
                on_content(delta_content)
            if normalized_tool_calls and on_tool_call:
                on_tool_call({"tool_calls": normalized_tool_calls})
            if normalized_tool_calls:
                last_tool_calls = normalized_tool_calls
            
            if delta_content or delta_thinking or normalized_tool_calls:
                yield LLMResponse(
                    content=delta_content or "",
                    thinking=delta_thinking or None,
                    tool_calls=normalized_tool_calls,
                    stop_reason=stop_reason,
                    is_stream=True
                )
        
        if has_chunk:
            raw_content = []
            if accumulated_thinking:
                raw_content.append({"type": "thinking", "thinking": accumulated_thinking})
            if accumulated_content:
                raw_content.append({"type": "text", "text": accumulated_content})
            if last_tool_calls:
                for tc in last_tool_calls:
                    raw_content.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": tc.get("name", ""),
                        "input": tc.get("input", {})
                    })
            
            yield LLMResponse(
                content=accumulated_content or "",
                thinking=accumulated_thinking or None,
                tool_calls=last_tool_calls,
                stop_reason=last_stop_reason,
                usage=usage_dict,
                raw_content=raw_content or None
            )
    
    def count_tokens(self, text: str) -> int:
        """
        计算 token 数量（粗略估计）
        """
        if not text:
            return 0
        return max(1, len(text) // 4)

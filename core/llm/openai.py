"""
OpenAI 兼容 LLM 服务实现

支持 OpenAI / OpenAI-Compatible 接口（用于 Qwen/DeepSeek 等兼容端点）

参考：
- https://platform.openai.com/docs/api-reference/chat
"""

from typing import Dict, Any, Optional, List, Union, AsyncIterator, Callable
import json
import os
import time

import httpx

from logger import get_logger
from .base import (
    BaseLLMService,
    LLMConfig,
    LLMResponse,
    Message,
    LLMProvider,
    ToolType
)
from .adaptor import OpenAIAdaptor

logger = get_logger("llm.openai")


class OpenAILLMService(BaseLLMService):
    """
    OpenAI 兼容 LLM 服务
    
    支持：
    - Chat Completions
    - Function Calling
    - Streaming
    """
    
    def __init__(self, config: LLMConfig):
        """
        初始化 OpenAI 服务
        
        Args:
            config: LLM 配置
        """
        self.config = config
        self._adaptor = OpenAIAdaptor()
        self._custom_tools: List[Dict[str, Any]] = []
        
        # 兼容端点（默认 OpenAI，可通过 compat/provider 调整）
        base_url = config.base_url or self._get_default_base_url()
        self.base_url = self._normalize_base_url(base_url)
        
        # HTTP 客户端
        timeout = getattr(config, "timeout", 120.0)
        self._client = httpx.AsyncClient(timeout=timeout)

    def _get_default_base_url(self) -> str:
        """
        获取默认 base_url（支持 OpenAI-Compatible）
        """
        compat = (self.config.compat or "").lower()
        provider = getattr(self.config, "provider", None)
        
        if compat == "qwen" or provider == LLMProvider.QWEN:
            return os.getenv("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
        
        if compat == "deepseek":
            return os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        
        return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    
    def _normalize_base_url(self, base_url: str) -> str:
        """
        规范化 base_url，确保以 /v1 结尾
        
        Args:
            base_url: 原始地址
            
        Returns:
            规范化地址
        """
        if not base_url:
            return "https://api.openai.com/v1"
        base_url = base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return base_url
    
    def _build_headers(self) -> Dict[str, str]:
        """
        构建请求头
        
        Returns:
            请求头
        """
        api_key = self.config.api_key or ""
        headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers
    
    def _filter_tools(self, tools: Optional[List[Union[ToolType, str, Dict]]]) -> List[Dict[str, Any]]:
        """
        过滤工具列表，仅保留 dict 类型
        
        Args:
            tools: 原始工具列表
            
        Returns:
            过滤后的工具列表
        """
        if not tools:
            return []
        return [tool for tool in tools if isinstance(tool, dict)]
    
    def add_custom_tool(self, name: str, description: str, input_schema: Dict[str, Any]) -> None:
        """
        注册自定义工具（OpenAI 兼容）
        
        Args:
            name: 工具名称
            description: 工具描述
            input_schema: 输入参数 Schema
        """
        self._custom_tools.append({
            "name": name,
            "description": description,
            "input_schema": input_schema
        })
    
    async def create_message_async(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        tools: Optional[List[Union[ToolType, str, Dict]]] = None,
        **kwargs
    ) -> LLMResponse:
        """
        创建消息（异步）
        
        Args:
            messages: 消息列表
            system: 系统提示词
            tools: 工具列表
            **kwargs: 其他参数
            
        Returns:
            LLMResponse
        """
        payload = self._adaptor.convert_messages_to_provider(messages, system)
        payload["model"] = self.config.model
        payload["max_tokens"] = kwargs.get("max_tokens", self.config.max_tokens)
        payload["temperature"] = kwargs.get("temperature", self.config.temperature)
        top_p = kwargs.get("top_p", getattr(self.config, "top_p", None))
        if top_p is not None:
            payload["top_p"] = top_p
        frequency_penalty = kwargs.get("frequency_penalty", getattr(self.config, "frequency_penalty", None))
        if frequency_penalty is not None:
            payload["frequency_penalty"] = frequency_penalty
        presence_penalty = kwargs.get("presence_penalty", getattr(self.config, "presence_penalty", None))
        if presence_penalty is not None:
            payload["presence_penalty"] = presence_penalty
        tool_choice = kwargs.get("tool_choice", getattr(self.config, "tool_choice", None))
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        parallel_tool_calls = kwargs.get("parallel_tool_calls", getattr(self.config, "parallel_tool_calls", None))
        if parallel_tool_calls is not None:
            payload["parallel_tool_calls"] = parallel_tool_calls
        
        merged_tools = self._filter_tools(tools) + self._custom_tools
        if merged_tools:
            payload["tools"] = self._adaptor.convert_tools_to_provider(merged_tools)
        
        # 透传部分参数
        for key in ["tool_choice", "top_p", "frequency_penalty", "presence_penalty"]:
            if key in kwargs:
                payload[key] = kwargs[key]
        
        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()
        
        response = await self._client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"OpenAI 调用失败: {response.status_code} {response.text}")
        
        return self._adaptor.convert_response_to_claude(response.json())
    
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
        
        Args:
            messages: 消息列表
            system: 系统提示词
            tools: 工具列表
            on_thinking: thinking 回调（不支持）
            on_content: content 回调
            on_tool_call: tool_call 回调
            **kwargs: 其他参数
            
        Yields:
            LLMResponse 片段
        """
        payload = self._adaptor.convert_messages_to_provider(messages, system)
        payload["model"] = self.config.model
        payload["max_tokens"] = kwargs.get("max_tokens", self.config.max_tokens)
        payload["temperature"] = kwargs.get("temperature", self.config.temperature)
        payload["stream"] = True
        
        merged_tools = self._filter_tools(tools) + self._custom_tools
        if merged_tools:
            payload["tools"] = self._adaptor.convert_tools_to_provider(merged_tools)
        
        url = f"{self.base_url}/chat/completions"
        headers = self._build_headers()
        
        accumulated_content = ""
        tool_call_buffers: Dict[int, Dict[str, Any]] = {}
        tool_call_started: set = set()
        finish_reason = None
        
        async with self._client.stream("POST", url, headers=headers, json=payload) as response:
            if response.status_code >= 400:
                text = await response.aread()
                raise RuntimeError(f"OpenAI 流式调用失败: {response.status_code} {text.decode('utf-8')}")
            
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                
                data = line.replace("data:", "", 1).strip()
                if data == "[DONE]":
                    break
                
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                
                choice = (chunk.get("choices") or [{}])[0]
                delta = choice.get("delta", {})
                finish_reason = choice.get("finish_reason") or finish_reason
                
                # 内容增量
                if "content" in delta and delta["content"]:
                    text = delta["content"]
                    accumulated_content += text
                    if on_content:
                        on_content(text)
                    yield LLMResponse(content=text, is_stream=True)
                
                # 工具调用增量
                tool_calls = delta.get("tool_calls") or []
                for tc in tool_calls:
                    index = tc.get("index", 0)
                    buffer = tool_call_buffers.setdefault(index, {
                        "id": tc.get("id", ""),
                        "name": "",
                        "arguments": ""
                    })
                    
                    if tc.get("id"):
                        buffer["id"] = tc.get("id")
                    
                    function = tc.get("function") or {}
                    if function.get("name"):
                        buffer["name"] = function.get("name")
                    
                    if buffer["id"] and buffer["name"] and buffer["id"] not in tool_call_started:
                        tool_call_started.add(buffer["id"])
                        if on_tool_call:
                            on_tool_call({"id": buffer["id"], "name": buffer["name"]})
                        yield LLMResponse(
                            content="",
                            is_stream=True,
                            tool_use_start={
                                "id": buffer["id"],
                                "name": buffer["name"],
                                "type": "tool_use"
                            }
                        )
                    
                    if function.get("arguments"):
                        buffer["arguments"] += function.get("arguments")
                        yield LLMResponse(
                            content="",
                            is_stream=True,
                            input_delta=function.get("arguments")
                        )
        
        # 构建最终响应
        tool_calls_payload = []
        raw_content = []
        
        if accumulated_content:
            raw_content.append({"type": "text", "text": accumulated_content})
        
        for buffer in tool_call_buffers.values():
            tool_input = {}
            if buffer.get("arguments"):
                try:
                    tool_input = json.loads(buffer["arguments"])
                except json.JSONDecodeError:
                    tool_input = {}
            
            tool_calls_payload.append({
                "id": buffer.get("id", f"tool_{int(time.time())}"),
                "name": buffer.get("name", ""),
                "input": tool_input,
                "type": "tool_use"
            })
            
            raw_content.append({
                "type": "tool_use",
                "id": tool_calls_payload[-1]["id"],
                "name": tool_calls_payload[-1]["name"],
                "input": tool_input
            })
        
        stop_reason_map = {
            "stop": "end_turn",
            "tool_calls": "tool_use",
            "length": "max_tokens"
        }
        stop_reason = stop_reason_map.get(finish_reason, "end_turn")
        
        yield LLMResponse(
            content=accumulated_content,
            tool_calls=tool_calls_payload or None,
            stop_reason=stop_reason,
            raw_content=raw_content or None,
            is_stream=False
        )
    
    def count_tokens(self, text: str) -> int:
        """
        计算 token 数量（粗略估算）
        
        Args:
            text: 文本内容
            
        Returns:
            token 数量
        """
        if not text:
            return 0
        return max(1, len(text) // 4)


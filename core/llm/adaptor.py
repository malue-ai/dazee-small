"""
格式适配器模块

负责不同 LLM 格式之间的转换，以 Claude 格式为内部标准。

设计参考：
- one-api / new-api 的 Adaptor 设计
- 统一使用 Claude 格式作为内部存储格式

格式对比：
┌─────────────┬──────────────────────────────────────────────┐
│   Provider  │              消息格式                         │
├─────────────┼──────────────────────────────────────────────┤
│   Claude    │ content: str | List[ContentBlock]           │
│             │ ContentBlock: {type, text/thinking/tool_use}│
├─────────────┼──────────────────────────────────────────────┤
│   OpenAI    │ content: str | List[ContentPart]            │
│             │ ContentPart: {type, text/image_url}         │
│             │ tool_calls: List[{id, type, function}]      │
├─────────────┼──────────────────────────────────────────────┤
│   Gemini    │ parts: List[Part]                           │
│             │ Part: {text} | {inline_data} | {function_call}│
└─────────────┴──────────────────────────────────────────────┘
"""

from typing import Dict, Any, List, Optional, Union
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .base import Message, LLMResponse, ToolType


# ============================================================
# 格式转换器基类
# ============================================================

class BaseAdaptor(ABC):
    """
    格式适配器基类
    
    职责：
    1. 将统一格式（Claude）转换为特定 Provider 格式
    2. 将特定 Provider 响应转换为统一格式（Claude）
    """
    
    @abstractmethod
    def convert_messages_to_provider(
        self,
        messages: List[Message],
        system: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        将 Claude 格式消息转换为 Provider 格式
        
        Args:
            messages: Claude 格式的消息列表
            system: 系统提示词
            
        Returns:
            Provider 格式的请求参数
        """
        pass
    
    @abstractmethod
    def convert_response_to_claude(
        self,
        response: Any
    ) -> LLMResponse:
        """
        将 Provider 响应转换为 Claude 格式
        
        Args:
            response: Provider 的原始响应
            
        Returns:
            Claude 格式的 LLMResponse
        """
        pass
    
    @abstractmethod
    def convert_tools_to_provider(
        self,
        tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        将 Claude 格式工具定义转换为 Provider 格式
        
        Args:
            tools: Claude 格式的工具定义
            
        Returns:
            Provider 格式的工具定义
        """
        pass


# ============================================================
# Claude 适配器（原生，无需转换）
# ============================================================

class ClaudeAdaptor(BaseAdaptor):
    """
    Claude 适配器
    
    Claude 是内部标准格式，基本无需转换
    """
    
    def convert_messages_to_provider(
        self,
        messages: List[Message],
        system: Optional[str] = None
    ) -> Dict[str, Any]:
        """Claude 格式 → Claude API（原生）"""
        result = {
            "messages": [{"role": m.role, "content": m.content} for m in messages]
        }
        if system:
            result["system"] = system
        return result
    
    def convert_response_to_claude(self, response: Any) -> LLMResponse:
        """Claude 响应 → LLMResponse（原生）"""
        # 已经是 Claude 格式，直接返回
        if isinstance(response, LLMResponse):
            return response
        raise ValueError("Expected LLMResponse for Claude adaptor")
    
    def convert_tools_to_provider(
        self,
        tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Claude 格式工具 → Claude API（原生）"""
        return tools


# ============================================================
# OpenAI 适配器
# ============================================================

class OpenAIAdaptor(BaseAdaptor):
    """
    OpenAI 适配器
    
    转换规则：
    - Claude content blocks → OpenAI content + tool_calls
    - Claude tool_use → OpenAI function calling
    - Claude thinking → OpenAI 不支持（存为 metadata）
    """
    
    def convert_messages_to_provider(
        self,
        messages: List[Message],
        system: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Claude 格式 → OpenAI 格式
        
        转换规则：
        - system prompt → messages[0] with role="system"
        - content blocks → 展开为 content 字符串
        - tool_result → role="tool" 消息
        """
        openai_messages = []
        
        # System prompt 作为第一条消息
        if system:
            openai_messages.append({
                "role": "system",
                "content": system
            })
        
        for msg in messages:
            converted = self._convert_message(msg)
            if isinstance(converted, list):
                openai_messages.extend(converted)
            else:
                openai_messages.append(converted)
        
        return {"messages": openai_messages}
    
    def _convert_message(self, msg: Message) -> Union[Dict, List[Dict]]:
        """转换单条消息"""
        content = msg.content
        
        # 简单字符串
        if isinstance(content, str):
            return {"role": msg.role, "content": content}
        
        # Content blocks
        if isinstance(content, list):
            text_parts = []
            tool_calls = []
            tool_results = []
            
            for block in content:
                block_type = block.get("type", "")
                
                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                    
                elif block_type == "thinking":
                    # OpenAI 不支持 thinking，跳过或存为注释
                    pass
                    
                elif block_type == "tool_use":
                    tool_calls.append({
                        "id": block.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": self._serialize_json(block.get("input", {}))
                        }
                    })
                    
                elif block_type == "tool_result":
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content": self._get_tool_result_content(block)
                    })
            
            # 构建消息
            result = []
            
            if msg.role == "assistant":
                assistant_msg = {"role": "assistant"}
                if text_parts:
                    assistant_msg["content"] = "\n".join(text_parts)
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                result.append(assistant_msg)
            elif msg.role == "user":
                if text_parts:
                    result.append({
                        "role": "user",
                        "content": "\n".join(text_parts)
                    })
            
            # Tool results 作为独立消息
            result.extend(tool_results)
            
            return result if len(result) > 1 else result[0] if result else {"role": msg.role, "content": ""}
        
        return {"role": msg.role, "content": str(content)}
    
    def _serialize_json(self, obj: Any) -> str:
        """序列化为 JSON 字符串"""
        import json
        return json.dumps(obj, ensure_ascii=False)
    
    def _get_tool_result_content(self, block: Dict) -> str:
        """获取 tool_result 的内容"""
        content = block.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            # 提取文本部分
            texts = [p.get("text", "") for p in content if p.get("type") == "text"]
            return "\n".join(texts)
        return str(content)
    
    def convert_response_to_claude(self, response: Any) -> LLMResponse:
        """
        OpenAI 响应 → Claude 格式
        
        转换规则：
        - choices[0].message.content → content
        - choices[0].message.tool_calls → tool_calls
        - finish_reason → stop_reason
        """
        # 假设 response 是 OpenAI 的响应对象或字典
        if isinstance(response, dict):
            return self._convert_dict_response(response)
        
        # OpenAI SDK 响应对象
        choice = response.choices[0] if response.choices else None
        if not choice:
            return LLMResponse(content="", stop_reason="end_turn")
        
        message = choice.message
        content = message.content or ""
        tool_calls = None
        raw_content = []
        
        # 添加文本内容
        if content:
            raw_content.append({"type": "text", "text": content})
        
        # 转换 tool_calls
        if hasattr(message, 'tool_calls') and message.tool_calls:
            tool_calls = []
            for tc in message.tool_calls:
                import json
                tool_call = {
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": json.loads(tc.function.arguments) if tc.function.arguments else {}
                }
                tool_calls.append(tool_call)
                raw_content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": tool_call["input"]
                })
        
        # 转换 stop_reason
        stop_reason_map = {
            "stop": "end_turn",
            "tool_calls": "tool_use",
            "length": "max_tokens",
            "content_filter": "end_turn"
        }
        stop_reason = stop_reason_map.get(choice.finish_reason, "end_turn")
        
        # Usage
        usage = {}
        if hasattr(response, 'usage') and response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens
            }
        
        return LLMResponse(
            content=content,
            thinking=None,  # OpenAI 不支持 thinking
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
            raw_content=raw_content
        )
    
    def _convert_dict_response(self, response: Dict) -> LLMResponse:
        """转换字典格式的响应"""
        choices = response.get("choices", [])
        if not choices:
            return LLMResponse(content="", stop_reason="end_turn")
        
        choice = choices[0]
        message = choice.get("message", {})
        content = message.get("content", "") or ""
        tool_calls = None
        raw_content = []
        
        if content:
            raw_content.append({"type": "text", "text": content})
        
        if message.get("tool_calls"):
            import json
            tool_calls = []
            for tc in message["tool_calls"]:
                func = tc.get("function", {})
                tool_call = {
                    "id": tc.get("id", ""),
                    "name": func.get("name", ""),
                    "input": json.loads(func.get("arguments", "{}"))
                }
                tool_calls.append(tool_call)
                raw_content.append({
                    "type": "tool_use",
                    "id": tool_call["id"],
                    "name": tool_call["name"],
                    "input": tool_call["input"]
                })
        
        stop_reason_map = {
            "stop": "end_turn",
            "tool_calls": "tool_use",
            "length": "max_tokens"
        }
        stop_reason = stop_reason_map.get(choice.get("finish_reason", ""), "end_turn")
        
        usage = {}
        if response.get("usage"):
            usage = {
                "input_tokens": response["usage"].get("prompt_tokens", 0),
                "output_tokens": response["usage"].get("completion_tokens", 0)
            }
        
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
            raw_content=raw_content
        )
    
    def convert_tools_to_provider(
        self,
        tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Claude 格式工具 → OpenAI 格式
        
        转换规则：
        - name → function.name
        - description → function.description
        - input_schema → function.parameters
        """
        openai_tools = []
        
        for tool in tools:
            # 跳过 Claude 原生工具（如 web_search_20250305）
            if "type" in tool and tool["type"] != "function":
                continue
            
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {
                        "type": "object",
                        "properties": {},
                        "required": []
                    })
                }
            }
            openai_tools.append(openai_tool)
        
        return openai_tools


# ============================================================
# Gemini 适配器
# ============================================================

class GeminiAdaptor(BaseAdaptor):
    """
    Gemini 适配器
    
    转换规则：
    - Claude content → Gemini parts
    - Claude tool_use → Gemini function_call
    """
    
    def convert_messages_to_provider(
        self,
        messages: List[Message],
        system: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Claude 格式 → Gemini 格式
        
        Gemini 格式：
        {
            "contents": [
                {"role": "user", "parts": [{"text": "..."}]},
                {"role": "model", "parts": [{"text": "..."}]}
            ],
            "system_instruction": {"parts": [{"text": "..."}]}
        }
        """
        gemini_contents = []
        
        for msg in messages:
            # Gemini 使用 "model" 而不是 "assistant"
            role = "model" if msg.role == "assistant" else msg.role
            parts = self._convert_content_to_parts(msg.content)
            
            gemini_contents.append({
                "role": role,
                "parts": parts
            })
        
        result = {"contents": gemini_contents}
        
        if system:
            result["system_instruction"] = {
                "parts": [{"text": system}]
            }
        
        return result
    
    def _convert_content_to_parts(
        self,
        content: Union[str, List[Dict]]
    ) -> List[Dict[str, Any]]:
        """将 Claude content 转换为 Gemini parts"""
        if isinstance(content, str):
            return [{"text": content}]
        
        parts = []
        for block in content:
            block_type = block.get("type", "")
            
            if block_type == "text":
                parts.append({"text": block.get("text", "")})
                
            elif block_type == "thinking":
                # Gemini 不支持 thinking，跳过
                pass
                
            elif block_type == "tool_use":
                parts.append({
                    "function_call": {
                        "name": block.get("name", ""),
                        "args": block.get("input", {})
                    }
                })
                
            elif block_type == "tool_result":
                parts.append({
                    "function_response": {
                        "name": block.get("name", ""),
                        "response": {"result": block.get("content", "")}
                    }
                })
        
        return parts if parts else [{"text": ""}]
    
    def convert_response_to_claude(self, response: Any) -> LLMResponse:
        """
        Gemini 响应 → Claude 格式
        
        Gemini 响应格式：
        {
            "candidates": [{
                "content": {"parts": [{"text": "..."}]},
                "finishReason": "STOP"
            }]
        }
        """
        if isinstance(response, dict):
            return self._convert_dict_response(response)
        
        # Gemini SDK 响应对象
        candidate = response.candidates[0] if response.candidates else None
        if not candidate:
            return LLMResponse(content="", stop_reason="end_turn")
        
        content_parts = candidate.content.parts if candidate.content else []
        
        text_content = ""
        tool_calls = []
        raw_content = []
        
        for part in content_parts:
            if hasattr(part, 'text') and part.text:
                text_content += part.text
                raw_content.append({"type": "text", "text": part.text})
                
            elif hasattr(part, 'function_call') and part.function_call:
                fc = part.function_call
                tool_call = {
                    "id": f"gemini_{fc.name}",  # Gemini 没有 id，生成一个
                    "name": fc.name,
                    "input": dict(fc.args) if fc.args else {}
                }
                tool_calls.append(tool_call)
                raw_content.append({
                    "type": "tool_use",
                    "id": tool_call["id"],
                    "name": tool_call["name"],
                    "input": tool_call["input"]
                })
        
        # 转换 finish_reason
        stop_reason_map = {
            "STOP": "end_turn",
            "MAX_TOKENS": "max_tokens",
            "SAFETY": "end_turn",
            "RECITATION": "end_turn",
            "OTHER": "end_turn"
        }
        finish_reason = getattr(candidate, 'finish_reason', None)
        stop_reason = stop_reason_map.get(str(finish_reason), "end_turn")
        
        # Usage
        usage = {}
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage = {
                "input_tokens": response.usage_metadata.prompt_token_count,
                "output_tokens": response.usage_metadata.candidates_token_count
            }
        
        return LLMResponse(
            content=text_content,
            thinking=None,
            tool_calls=tool_calls if tool_calls else None,
            stop_reason=stop_reason,
            usage=usage,
            raw_content=raw_content
        )
    
    def _convert_dict_response(self, response: Dict) -> LLMResponse:
        """转换字典格式的响应"""
        candidates = response.get("candidates", [])
        if not candidates:
            return LLMResponse(content="", stop_reason="end_turn")
        
        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])
        
        text_content = ""
        tool_calls = []
        raw_content = []
        
        for part in parts:
            if "text" in part:
                text_content += part["text"]
                raw_content.append({"type": "text", "text": part["text"]})
                
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_call = {
                    "id": f"gemini_{fc.get('name', '')}",
                    "name": fc.get("name", ""),
                    "input": fc.get("args", {})
                }
                tool_calls.append(tool_call)
                raw_content.append({
                    "type": "tool_use",
                    "id": tool_call["id"],
                    "name": tool_call["name"],
                    "input": tool_call["input"]
                })
        
        stop_reason_map = {
            "STOP": "end_turn",
            "MAX_TOKENS": "max_tokens"
        }
        stop_reason = stop_reason_map.get(candidate.get("finishReason", ""), "end_turn")
        
        usage = {}
        if response.get("usageMetadata"):
            usage = {
                "input_tokens": response["usageMetadata"].get("promptTokenCount", 0),
                "output_tokens": response["usageMetadata"].get("candidatesTokenCount", 0)
            }
        
        return LLMResponse(
            content=text_content,
            tool_calls=tool_calls if tool_calls else None,
            stop_reason=stop_reason,
            usage=usage,
            raw_content=raw_content
        )
    
    def convert_tools_to_provider(
        self,
        tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Claude 格式工具 → Gemini 格式
        
        Gemini 工具格式：
        {
            "function_declarations": [{
                "name": "...",
                "description": "...",
                "parameters": {...}
            }]
        }
        """
        function_declarations = []
        
        for tool in tools:
            # 跳过 Claude 原生工具
            if "type" in tool and tool["type"] != "function":
                continue
            
            declaration = {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {
                    "type": "object",
                    "properties": {},
                    "required": []
                })
            }
            function_declarations.append(declaration)
        
        return [{"function_declarations": function_declarations}] if function_declarations else []


# ============================================================
# 工厂函数
# ============================================================

def get_adaptor(provider: str) -> BaseAdaptor:
    """
    获取对应 Provider 的适配器
    
    Args:
        provider: 提供商名称 (claude, openai, gemini)
        
    Returns:
        对应的适配器实例
    """
    adaptors = {
        "claude": ClaudeAdaptor,
        "openai": OpenAIAdaptor,
        "gemini": GeminiAdaptor,
    }
    
    adaptor_class = adaptors.get(provider.lower())
    if not adaptor_class:
        raise ValueError(f"Unknown provider: {provider}")
    
    return adaptor_class()


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
import json
from typing import Dict, Any, List, Optional, Union
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .base import Message, LLMResponse, ToolType
from logger import get_logger

logger = get_logger("adaptor")

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
# Claude 适配器
# ============================================================

class ClaudeAdaptor(BaseAdaptor):
    """
    Claude 适配器
    
    职责：
    1. 加载历史消息时：清理 thinking/index，分离 tool_result
    2. 发送 API 前：确保消息格式符合 Claude API 要求
    
    Claude API 消息格式规范：
    - assistant 消息可包含：text, thinking, tool_use
    - user 消息可包含：text, tool_result
    - tool_result 必须在 user 消息中，且紧跟对应的 tool_use
    """
    
    # ==================== 加载历史消息 ====================
    
    @staticmethod
    def prepare_messages_from_db(db_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        从数据库加载的消息 → LLM 格式
        
        处理逻辑：
        1. 按 index 字段排序内容块
        2. 清理 thinking, redacted_thinking 块
        3. 去重 tool_use 和 tool_result
        4. 移除 index 字段
        5. **交错分离**：遇到 tool_result 时立即创建 user 消息
           - 数据库: assistant [text, tool_use, tool_result, tool_use, tool_result]
           - 输出: assistant [text, tool_use] → user [tool_result] → assistant [tool_use] → user [tool_result]
        6. 确保 tool_use/tool_result 配对
        
        Args:
            db_messages: 数据库消息列表 [{"role": "...", "content": [...]}]
            
        Returns:
            符合 Claude API 格式的消息列表
        """

        logger.info(f"📥 prepare_messages_from_db: 输入 {len(db_messages)} 条消息")
        
        result = []
        
        # 用于全局去重：记录已添加的 tool_use id 和 tool_result tool_use_id
        seen_tool_use_ids: set = set()
        seen_tool_result_ids: set = set()
        
        for msg in db_messages:
            role = msg.get("role", "")
            content = msg.get("content", [])
            
            # 如果 content 是字符串，直接添加
            if isinstance(content, str):
                result.append({"role": role, "content": content})
                continue
            
            # 如果不是列表，跳过
            if not isinstance(content, list):
                continue
            
            # 按 index 字段排序（确保顺序正确）
            sorted_content = sorted(
                content,
                key=lambda b: b.get("index", 999) if isinstance(b, dict) else 999
            )
            
            if role == "assistant":
                # 🔧 关键改进：交错分离 tool_result
                # 遍历内容块，遇到 tool_result 时立即创建 user 消息
                current_assistant_blocks = []
                
                for block in sorted_content:
                    if not isinstance(block, dict):
                        current_assistant_blocks.append(block)
                        continue
                    
                    block_type = block.get("type", "")
                    
                    # 跳过 thinking 块
                    if block_type in ("thinking", "redacted_thinking"):
                        continue
                    
                    # 移除 index 字段
                    clean_block = {k: v for k, v in block.items() if k != "index"}
                    
                    # tool_use 去重检查
                    if block_type == "tool_use":
                        tool_id = block.get("id")
                        if tool_id in seen_tool_use_ids:
                            continue  # 跳过重复的 tool_use
                        seen_tool_use_ids.add(tool_id)
                        current_assistant_blocks.append(clean_block)
                    
                    # tool_result：先保存当前 assistant 块，然后创建 user 消息
                    elif block_type == "tool_result":
                        tool_use_id = block.get("tool_use_id")
                        if tool_use_id in seen_tool_result_ids:
                            continue  # 跳过重复的 tool_result
                        seen_tool_result_ids.add(tool_use_id)
                        
                        # 先保存当前累积的 assistant 块
                        if current_assistant_blocks:
                            result.append({"role": "assistant", "content": current_assistant_blocks})
                            current_assistant_blocks = []
                        
                        # tool_result 作为独立的 user 消息
                        result.append({"role": "user", "content": [clean_block]})
                    
                    else:
                        # text 等其他类型
                        current_assistant_blocks.append(clean_block)
                
                # 保存最后累积的 assistant 块
                if current_assistant_blocks:
                    result.append({"role": "assistant", "content": current_assistant_blocks})
            
            else:
                # user/system 消息：过滤并保留
                filtered_blocks = []
                for block in sorted_content:
                    if not isinstance(block, dict):
                        continue
                    
                    block_type = block.get("type", "")
                    
                    # 跳过 thinking 块
                    if block_type in ("thinking", "redacted_thinking"):
                        continue
                    
                    # 移除 index 字段
                    clean_block = {k: v for k, v in block.items() if k != "index"}
                    
                    # tool_result 去重
                    if block_type == "tool_result":
                        tool_use_id = block.get("tool_use_id")
                        if tool_use_id in seen_tool_result_ids:
                            continue
                        seen_tool_result_ids.add(tool_use_id)
                    
                    filtered_blocks.append(clean_block)
                
                if filtered_blocks:
                    result.append({"role": role, "content": filtered_blocks})
        
        # 统计 tool_use 和 tool_result 数量
        pre_tool_use_ids = set()
        pre_tool_result_ids = set()
        for msg in result:
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_use":
                            pre_tool_use_ids.add(block.get("id"))
                        elif block.get("type") == "tool_result":
                            pre_tool_result_ids.add(block.get("tool_use_id"))
        
        logger.info(f"📊 交错分离后: {len(result)} 条消息, tool_use={len(pre_tool_use_ids)}, tool_result={len(pre_tool_result_ids)}")
        
        if pre_tool_use_ids - pre_tool_result_ids:
            logger.warning(f"⚠️ 检测到未配对的 tool_use: {pre_tool_use_ids - pre_tool_result_ids}")
        
        # 确保 tool_use/tool_result 配对
        result = ClaudeAdaptor.ensure_tool_pairs(result)
        
        logger.info(f"📤 prepare_messages_from_db: 输出 {len(result)} 条消息")
        
        return result
    
    @staticmethod
    def ensure_tool_pairs(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        确保 tool_use 和 tool_result 成对出现（同时去重）
        
        Claude API 要求：
        - 每个 tool_use 后面必须紧跟对应的 tool_result（在下一个 user 消息中）
        - 如果 tool_use 没有对应的 tool_result，需要移除
        - 如果 tool_result 没有对应的 tool_use，也需要移除
        - 🆕 每个 tool_use_id 只能有一个 tool_result（去重）
        
        Args:
            messages: 消息列表
            
        Returns:
            清理后的消息列表（只保留配对且不重复的 tool_use/tool_result）
        """
        if not messages:
            return messages
        
        # 1. 收集所有 tool_use ID 和 tool_result 对应的 tool_use_id
        tool_use_ids: set = set()
        tool_result_ids: set = set()
        
        for msg in messages:
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "tool_use":
                    tool_use_ids.add(block.get("id"))
                elif block_type == "tool_result":
                    tool_result_ids.add(block.get("tool_use_id"))
        
        # 2. 找出配对的 tool_use（既有 tool_use 又有对应的 tool_result）
        paired_ids = tool_use_ids & tool_result_ids
        unpaired_tool_use = tool_use_ids - tool_result_ids
        unpaired_tool_result = tool_result_ids - tool_use_ids
        
        if unpaired_tool_use:
            logger.warning(f"⚠️ 发现 {len(unpaired_tool_use)} 个未配对的 tool_use，将移除: {unpaired_tool_use}")
        if unpaired_tool_result:
            logger.warning(f"⚠️ 发现 {len(unpaired_tool_result)} 个未配对的 tool_result，将移除: {unpaired_tool_result}")
        
        # 3. 🆕 过滤消息，移除未配对的 tool_use 和 tool_result，同时去重
        # 记录已添加的 tool_use 和 tool_result ID（用于去重）
        added_tool_use_ids: set = set()
        added_tool_result_ids: set = set()
        
        cleaned_messages = []
        
        for msg in messages:
            content = msg.get("content", [])
            role = msg.get("role", "user")
            
            if isinstance(content, list):
                # 过滤未配对的块 + 去重
                filtered_content = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    
                    block_type = block.get("type")
                    
                    if block_type == "tool_use":
                        tool_id = block.get("id")
                        if tool_id in paired_ids:
                            # 🆕 检查是否已添加过（去重）
                            if tool_id in added_tool_use_ids:
                                logger.warning(f"🧹 移除重复的 tool_use: {tool_id}")
                                continue
                            added_tool_use_ids.add(tool_id)
                            filtered_content.append(block)
                        else:
                            logger.debug(f"🧹 移除未配对的 tool_use: {tool_id}")
                    elif block_type == "tool_result":
                        tool_use_id = block.get("tool_use_id")
                        if tool_use_id in paired_ids:
                            # 🆕 检查是否已添加过（去重）
                            if tool_use_id in added_tool_result_ids:
                                logger.warning(f"🧹 移除重复的 tool_result: {tool_use_id}")
                                continue
                            added_tool_result_ids.add(tool_use_id)
                            filtered_content.append(block)
                        else:
                            logger.debug(f"🧹 移除未配对的 tool_result: {tool_use_id}")
                    else:
                        filtered_content.append(block)
                
                # 只添加有内容的消息
                if filtered_content:
                    cleaned_messages.append({
                        "role": role,
                        "content": filtered_content
                    })
            else:
                # 纯文本消息，直接保留
                if content:
                    cleaned_messages.append(msg)
        
        # 🆕 统计去重信息
        duplicate_tool_use = len(tool_use_ids) - len(added_tool_use_ids)
        duplicate_tool_result = len(tool_result_ids) - len(added_tool_result_ids)
        if duplicate_tool_use > 0 or duplicate_tool_result > 0:
            logger.warning(f"🧹 去重: 移除 {duplicate_tool_use} 个重复 tool_use, {duplicate_tool_result} 个重复 tool_result")
        
        logger.info(f"✅ ensure_tool_pairs: {len(messages)} → {len(cleaned_messages)} 条消息")
        return cleaned_messages
    
    @staticmethod
    def clean_content_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        清理 content blocks
        
        处理：
        - 移除 thinking, redacted_thinking 块
        - 移除 index 字段
        
        Args:
            blocks: content blocks 列表
            
        Returns:
            清理后的 blocks
        """
        result = []
        for block in blocks:
            if not isinstance(block, dict):
                result.append(block)
                continue
            
            block_type = block.get("type", "")
            
            # 跳过 thinking 块
            if block_type in ("thinking", "redacted_thinking"):
                continue
            
            # 移除 index 字段
            clean_block = {k: v for k, v in block.items() if k != "index"}
            result.append(clean_block)
        
        return result
    
    # ==================== 发送 API 前 ====================
    
    def convert_messages_to_provider(
        self,
        messages: List[Message],
        system: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Message → Claude API 格式
        
        兜底检查：确保 tool_result 在 user 消息中
        """
        converted_messages = []
        
        for msg in messages:
            content = msg.content
            
            # 字符串内容直接添加
            if isinstance(content, str):
                converted_messages.append({"role": msg.role, "content": content})
                continue
            
            # 列表内容需要检查 tool_result
            if isinstance(content, list) and msg.role == "assistant":
                assistant_blocks = []
                tool_result_blocks = []
                
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_result_blocks.append(block)
                    else:
                        assistant_blocks.append(block)
                
                # 添加 assistant 消息（不含 tool_result）
                if assistant_blocks:
                    converted_messages.append({
                        "role": "assistant",
                        "content": assistant_blocks
                    })
                
                # tool_result 分离到 user 消息
                if tool_result_blocks:
                    converted_messages.append({
                        "role": "user",
                        "content": tool_result_blocks
                    })
            else:
                # 其他情况直接添加
                converted_messages.append({
                    "role": msg.role,
                    "content": content
                })
        
        # 🔧 关键：确保 tool_use/tool_result 配对（移除未配对的 tool_use）
        # 这是发送给 Claude API 前的最后一道防线
        converted_messages = ClaudeAdaptor.ensure_tool_pairs(converted_messages)
        
        result = {"messages": converted_messages}
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


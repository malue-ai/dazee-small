# 多格式对话交互协议

> 📅 **版本**: V1.0  
> 🎯 **目标**: 统一 Agent 输入输出格式，支持 OpenAI ChatML / Claude 原生格式

---

## 📋 目录

- [格式选型](#格式选型)
- [统一消息格式](#统一消息格式)
- [API 接口设计](#api-接口设计)
- [历史对话处理](#历史对话处理)
- [格式转换层](#格式转换层)
- [使用示例](#使用示例)

---

## 🎯 格式选型

### 推荐方案：Claude Content Blocks（内部标准）+ 多格式兼容层

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         格式兼容架构                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   外部接口层                                                                 │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                  │
│   │ OpenAI ChatML │  │ Claude Native │  │ 简化格式      │                  │
│   │ (兼容层)      │  │ (推荐)        │  │ (快捷接口)    │                  │
│   └───────┬───────┘  └───────┬───────┘  └───────┬───────┘                  │
│           │                  │                  │                           │
│           └──────────────────┼──────────────────┘                           │
│                              │                                               │
│                              ▼                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                    MessageAdaptor (格式转换层)                       │  │
│   │    • openai_to_claude()  ← OpenAI → Claude                          │  │
│   │    • claude_to_openai()  ← Claude → OpenAI                          │  │
│   │    • simple_to_claude()  ← 简化格式 → Claude                        │  │
│   └────────────────────────────────┬────────────────────────────────────┘  │
│                                    │                                        │
│                                    ▼                                        │
│   内部标准层                                                                 │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │              Claude Content Blocks Format（内部统一标准）            │  │
│   │                                                                      │  │
│   │   {                                                                  │  │
│   │     "role": "user" | "assistant",                                   │  │
│   │     "content": [                                                     │  │
│   │       {"type": "text", "text": "..."},                              │  │
│   │       {"type": "thinking", "thinking": "...", "signature": "..."},  │  │
│   │       {"type": "tool_use", "id": "...", "name": "...", "input": {}},│  │
│   │       {"type": "tool_result", "tool_use_id": "...", "content": "..."}│  │
│   │     ]                                                                │  │
│   │   }                                                                  │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                         SimpleAgent (Core)                           │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 为什么选择 Claude Content Blocks？

| 特性 | Claude Content Blocks | OpenAI ChatML | 说明 |
|-----|----------------------|---------------|------|
| **Thinking 支持** | ✅ 原生支持 | ❌ 不支持 | 关键差异 |
| **Tool Use** | ✅ 统一在 content | ⚠️ 单独字段 | Claude 更简洁 |
| **多模态** | ✅ 原生支持 | ✅ 支持 | 都支持 |
| **流式输出** | ✅ 完整支持 | ✅ 支持 | 都支持 |
| **无损转换** | ✅ → OpenAI | ⚠️ → Claude | Claude 信息更完整 |

---

## 📦 统一消息格式

### 1. 统一消息结构 (UnifiedMessage)

```python
from typing import Union, List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime

# ============================================================
# Content Block 类型定义
# ============================================================

class TextBlock(BaseModel):
    """文本内容块"""
    type: Literal["text"] = "text"
    text: str


class ThinkingBlock(BaseModel):
    """思考过程块（Claude 特有）"""
    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: Optional[str] = None  # 用于流式延续


class ToolUseBlock(BaseModel):
    """工具调用块"""
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: Dict[str, Any]


class ToolResultBlock(BaseModel):
    """工具结果块"""
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: Union[str, List[Dict[str, Any]]]
    is_error: bool = False


class ImageBlock(BaseModel):
    """图片内容块"""
    type: Literal["image"] = "image"
    source: Dict[str, Any]  # {"type": "base64", "media_type": "...", "data": "..."}


# 内容块联合类型
ContentBlock = Union[TextBlock, ThinkingBlock, ToolUseBlock, ToolResultBlock, ImageBlock]


# ============================================================
# 统一消息格式
# ============================================================

class UnifiedMessage(BaseModel):
    """
    统一消息格式（内部标准）
    
    采用 Claude Content Blocks 格式作为内部统一标准
    """
    role: Literal["user", "assistant", "system"]
    content: Union[str, List[ContentBlock]]
    
    # 元数据（可选）
    id: Optional[str] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        json_schema_extra = {
            "examples": [
                # 简单文本消息
                {
                    "role": "user",
                    "content": "帮我生成一个 PPT"
                },
                # 带 thinking 的 assistant 消息
                {
                    "role": "assistant", 
                    "content": [
                        {"type": "thinking", "thinking": "用户需要生成 PPT，我应该..."},
                        {"type": "text", "text": "好的，我来帮你生成 PPT"},
                        {"type": "tool_use", "id": "toolu_xxx", "name": "slidespeak", "input": {"title": "..."}}
                    ]
                }
            ]
        }
```

### 2. 对话历史格式

```python
class ConversationHistory(BaseModel):
    """
    对话历史
    
    用于端到端交互时传入历史上下文
    """
    conversation_id: Optional[str] = None
    messages: List[UnifiedMessage] = Field(default_factory=list)
    
    # 压缩选项
    max_tokens: Optional[int] = None  # 最大 token 限制
    compression_strategy: Optional[str] = "truncate"  # truncate | summarize | sliding_window
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "conversation_id": "conv_123",
                    "messages": [
                        {"role": "user", "content": "你好"},
                        {"role": "assistant", "content": "你好！有什么可以帮助你的？"},
                        {"role": "user", "content": "帮我生成一个 PPT"}
                    ]
                }
            ]
        }
```

---

## 🔌 API 接口设计

### 1. 端到端聊天接口

```python
# models/api_formats.py

from pydantic import BaseModel, Field
from typing import Union, List, Dict, Any, Optional, Literal


class E2EChatRequest(BaseModel):
    """
    端到端聊天请求
    
    支持三种输入格式：
    1. 简化格式：只传 message 字符串
    2. Claude 格式：传 messages 数组（Content Blocks）
    3. OpenAI 格式：传 messages 数组（ChatML）
    """
    
    # ===== 格式标识 =====
    format: Literal["simple", "claude", "openai"] = Field(
        default="simple",
        description="消息格式：simple（简化）| claude（原生）| openai（ChatML）"
    )
    
    # ===== 简化格式（推荐新用户使用）=====
    message: Optional[str] = Field(
        None,
        description="用户消息（简化格式使用）"
    )
    
    # ===== 完整消息格式（Claude/OpenAI）=====
    messages: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="消息历史（Claude 或 OpenAI 格式）"
    )
    
    # ===== 通用参数 =====
    conversation_id: Optional[str] = Field(
        None,
        description="对话 ID（用于延续历史对话）"
    )
    user_id: Optional[str] = Field(
        None,
        description="用户 ID"
    )
    stream: bool = Field(
        True,
        description="是否流式输出"
    )
    
    # ===== 高级选项 =====
    system_prompt: Optional[str] = Field(
        None,
        description="自定义系统提示词（覆盖默认）"
    )
    max_tokens: Optional[int] = Field(
        None,
        description="最大输出 token"
    )
    temperature: Optional[float] = Field(
        None,
        description="温度参数"
    )
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                # 示例 1：简化格式
                {
                    "format": "simple",
                    "message": "帮我生成一个关于 AI 的 PPT",
                    "conversation_id": "conv_123"
                },
                # 示例 2：Claude 格式
                {
                    "format": "claude",
                    "messages": [
                        {"role": "user", "content": "你好"},
                        {"role": "assistant", "content": [
                            {"type": "text", "text": "你好！"}
                        ]},
                        {"role": "user", "content": "帮我生成 PPT"}
                    ]
                },
                # 示例 3：OpenAI ChatML 格式
                {
                    "format": "openai",
                    "messages": [
                        {"role": "system", "content": "你是一个助手"},
                        {"role": "user", "content": "你好"},
                        {"role": "assistant", "content": "你好！"},
                        {"role": "user", "content": "帮我生成 PPT"}
                    ]
                }
            ]
        }
    }


class E2EChatResponse(BaseModel):
    """
    端到端聊天响应
    
    输出格式与请求格式一致（format 字段决定）
    """
    
    # ===== 基本信息 =====
    conversation_id: str = Field(..., description="对话 ID")
    session_id: str = Field(..., description="会话 ID")
    
    # ===== 响应内容 =====
    message: Dict[str, Any] = Field(
        ...,
        description="Agent 响应消息（格式与请求一致）"
    )
    
    # ===== 执行详情 =====
    status: Literal["success", "failed", "incomplete"] = Field(..., description="状态")
    turns: int = Field(..., description="执行轮次")
    
    # ===== 可选详情 =====
    thinking: Optional[str] = Field(None, description="思考过程（如果有）")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(None, description="工具调用记录")
    plan: Optional[Dict[str, Any]] = Field(None, description="执行计划")
    
    # ===== 性能指标 =====
    usage: Optional[Dict[str, int]] = Field(
        None,
        description="Token 使用统计"
    )
    latency_ms: Optional[int] = Field(
        None,
        description="响应延迟（毫秒）"
    )
```

### 2. 路由实现

```python
# routers/chat_e2e.py

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import json

from models.api_formats import E2EChatRequest, E2EChatResponse
from core.llm.adaptor import get_adaptor, OpenAIAdaptor
from services import get_chat_service

router = APIRouter(prefix="/api/v2", tags=["e2e-chat"])


@router.post("/chat", response_model=E2EChatResponse)
async def e2e_chat(request: E2EChatRequest):
    """
    端到端聊天接口
    
    支持多种输入格式，统一处理后返回对应格式的响应
    """
    chat_service = get_chat_service()
    
    # 1. 格式转换：将输入转换为内部统一格式（Claude）
    unified_messages = convert_to_unified(request)
    
    # 2. 调用 Agent
    if request.stream:
        return StreamingResponse(
            stream_chat(unified_messages, request),
            media_type="text/event-stream"
        )
    else:
        result = await chat_service.chat(
            messages=unified_messages,
            conversation_id=request.conversation_id,
            user_id=request.user_id
        )
        
        # 3. 格式转换：将输出转换为请求格式
        response_message = convert_from_unified(
            result["message"],
            target_format=request.format
        )
        
        return E2EChatResponse(
            conversation_id=result["conversation_id"],
            session_id=result["session_id"],
            message=response_message,
            status=result["status"],
            turns=result["turns"],
            thinking=result.get("thinking"),
            tool_calls=result.get("tool_calls"),
            usage=result.get("usage")
        )


def convert_to_unified(request: E2EChatRequest) -> List[Dict[str, Any]]:
    """
    将请求转换为统一的 Claude 格式
    """
    if request.format == "simple":
        # 简化格式：直接构建单条消息
        return [{"role": "user", "content": request.message}]
    
    elif request.format == "openai":
        # OpenAI ChatML → Claude
        adaptor = OpenAIAdaptor()
        return adaptor.convert_to_claude_messages(request.messages)
    
    elif request.format == "claude":
        # 已经是 Claude 格式，直接返回
        return request.messages
    
    else:
        raise HTTPException(400, f"不支持的格式: {request.format}")


def convert_from_unified(
    message: Dict[str, Any],
    target_format: str
) -> Dict[str, Any]:
    """
    将 Claude 格式响应转换为目标格式
    """
    if target_format == "simple":
        # 提取纯文本
        content = message.get("content", "")
        if isinstance(content, list):
            texts = [b.get("text", "") for b in content if b.get("type") == "text"]
            content = "\n".join(texts)
        return {"role": "assistant", "content": content}
    
    elif target_format == "openai":
        # Claude → OpenAI ChatML
        adaptor = OpenAIAdaptor()
        return adaptor.convert_message_to_openai(message)
    
    elif target_format == "claude":
        # 直接返回
        return message
    
    else:
        return message
```

---

## 📜 历史对话处理

### 1. 历史加载策略

```python
# core/context/history_loader.py

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class CompressionStrategy(Enum):
    """历史压缩策略"""
    NONE = "none"              # 不压缩
    TRUNCATE = "truncate"      # 截断旧消息
    SLIDING_WINDOW = "sliding" # 滑动窗口
    SUMMARIZE = "summarize"    # 总结旧消息


@dataclass
class HistoryConfig:
    """历史加载配置"""
    max_tokens: int = 100000           # 最大 token（Claude 支持 200K）
    max_messages: int = 100            # 最大消息数
    compression: CompressionStrategy = CompressionStrategy.SLIDING_WINDOW
    keep_system: bool = True           # 始终保留 system 消息
    keep_recent: int = 10              # 至少保留最近 N 条


class HistoryLoader:
    """
    历史对话加载器
    
    负责：
    1. 从数据库加载对话历史
    2. 压缩历史以适应 context window
    3. 合并新消息
    """
    
    def __init__(self, config: HistoryConfig = None):
        self.config = config or HistoryConfig()
    
    async def load_and_merge(
        self,
        conversation_id: str,
        new_messages: List[Dict[str, Any]],
        db_session = None
    ) -> List[Dict[str, Any]]:
        """
        加载历史并合并新消息
        
        Args:
            conversation_id: 对话 ID
            new_messages: 新消息列表
            db_session: 数据库会话
            
        Returns:
            合并后的完整消息列表
        """
        # 1. 从数据库加载历史
        history = await self._load_from_db(conversation_id, db_session)
        
        # 2. 压缩历史
        compressed = self._compress(history)
        
        # 3. 合并新消息
        merged = compressed + new_messages
        
        return merged
    
    def _compress(
        self,
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """根据策略压缩消息"""
        
        if self.config.compression == CompressionStrategy.NONE:
            return messages
        
        elif self.config.compression == CompressionStrategy.TRUNCATE:
            # 简单截断：保留最后 N 条
            return messages[-self.config.max_messages:]
        
        elif self.config.compression == CompressionStrategy.SLIDING_WINDOW:
            # 滑动窗口：保留 system + 最近 N 条
            system_msgs = [m for m in messages if m.get("role") == "system"]
            other_msgs = [m for m in messages if m.get("role") != "system"]
            
            # 保留最近的消息
            recent = other_msgs[-self.config.keep_recent:]
            
            return system_msgs + recent
        
        elif self.config.compression == CompressionStrategy.SUMMARIZE:
            # 总结策略：将旧消息压缩为摘要（需要调用 LLM）
            return self._summarize_old_messages(messages)
        
        return messages
    
    async def _load_from_db(
        self,
        conversation_id: str,
        db_session
    ) -> List[Dict[str, Any]]:
        """从数据库加载历史"""
        # 使用现有的 conversation 服务
        from services import get_conversation_service
        conv_service = get_conversation_service()
        
        messages = await conv_service.get_messages(
            conversation_id=conversation_id,
            limit=self.config.max_messages
        )
        
        return messages
```

### 2. 对话持久化

```python
# core/context/history_saver.py

from typing import List, Dict, Any
import json


class HistorySaver:
    """
    历史对话保存器
    
    职责：
    1. 将 Agent 响应保存到数据库
    2. 处理 Content Blocks 格式的存储
    3. 提取和保存 thinking（可选）
    """
    
    async def save_turn(
        self,
        conversation_id: str,
        user_message: Dict[str, Any],
        assistant_message: Dict[str, Any],
        metadata: Dict[str, Any] = None
    ):
        """
        保存一轮对话
        
        Args:
            conversation_id: 对话 ID
            user_message: 用户消息
            assistant_message: 助手响应（Claude 格式）
            metadata: 元数据（tool_calls, thinking 等）
        """
        from services import get_conversation_service
        conv_service = get_conversation_service()
        
        # 保存用户消息
        await conv_service.add_message(
            conversation_id=conversation_id,
            role="user",
            content=self._serialize_content(user_message.get("content"))
        )
        
        # 保存助手消息
        assistant_content = assistant_message.get("content", [])
        
        # 提取 thinking（如果需要单独存储）
        thinking = None
        if isinstance(assistant_content, list):
            for block in assistant_content:
                if block.get("type") == "thinking":
                    thinking = block.get("thinking")
                    break
        
        await conv_service.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=self._serialize_content(assistant_content),
            status=json.dumps({
                "has_thinking": thinking is not None,
                "tool_calls": metadata.get("tool_calls", []) if metadata else []
            })
        )
    
    def _serialize_content(self, content: Any) -> str:
        """序列化 content 为 JSON 字符串"""
        if isinstance(content, str):
            return json.dumps([{"type": "text", "text": content}])
        elif isinstance(content, list):
            return json.dumps(content)
        else:
            return json.dumps([{"type": "text", "text": str(content)}])
```

---

## 🔄 格式转换层

### 增强 adaptor.py

```python
# core/llm/adaptor.py（增强版）

class OpenAIAdaptor(BaseAdaptor):
    """
    OpenAI 适配器（增强版）
    
    新增：
    - convert_to_claude_messages(): ChatML → Claude
    - convert_message_to_openai(): 单条消息转换
    """
    
    def convert_to_claude_messages(
        self,
        openai_messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        OpenAI ChatML → Claude 格式
        
        转换规则：
        - system 消息：提取出来作为 system prompt（返回时单独处理）
        - tool_calls：转换为 tool_use content block
        - tool 消息：转换为 tool_result content block
        """
        claude_messages = []
        system_prompt = None
        
        for msg in openai_messages:
            role = msg.get("role")
            content = msg.get("content", "")
            
            if role == "system":
                # System 消息：合并为 system prompt
                if system_prompt:
                    system_prompt += "\n\n" + content
                else:
                    system_prompt = content
                continue
            
            elif role == "user":
                claude_messages.append({
                    "role": "user",
                    "content": content if isinstance(content, str) else self._convert_openai_content(content)
                })
            
            elif role == "assistant":
                claude_content = []
                
                # 添加文本内容
                if content:
                    claude_content.append({"type": "text", "text": content})
                
                # 转换 tool_calls
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        claude_content.append({
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": tc["function"]["name"],
                            "input": json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"]
                        })
                
                claude_messages.append({
                    "role": "assistant",
                    "content": claude_content if claude_content else ""
                })
            
            elif role == "tool":
                # Tool 结果：需要添加到前一个 assistant 消息后面，或创建 user 消息
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": content
                }
                
                # 如果最后一条是 assistant 消息，追加 tool_result
                if claude_messages and claude_messages[-1]["role"] == "assistant":
                    last_content = claude_messages[-1]["content"]
                    if isinstance(last_content, list):
                        # 创建新的 user 消息包含 tool_result
                        claude_messages.append({
                            "role": "user",
                            "content": [tool_result]
                        })
                    else:
                        claude_messages.append({
                            "role": "user", 
                            "content": [tool_result]
                        })
                else:
                    claude_messages.append({
                        "role": "user",
                        "content": [tool_result]
                    })
        
        return claude_messages, system_prompt
    
    def _convert_openai_content(
        self,
        content: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """转换 OpenAI 的 content parts 为 Claude content blocks"""
        claude_blocks = []
        
        for part in content:
            part_type = part.get("type")
            
            if part_type == "text":
                claude_blocks.append({
                    "type": "text",
                    "text": part.get("text", "")
                })
            
            elif part_type == "image_url":
                # 转换图片格式
                url = part.get("image_url", {}).get("url", "")
                if url.startswith("data:"):
                    # Base64 图片
                    media_type, data = self._parse_data_url(url)
                    claude_blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": data
                        }
                    })
                else:
                    # URL 图片（Claude 需要转为 base64）
                    claude_blocks.append({
                        "type": "image",
                        "source": {
                            "type": "url",
                            "url": url
                        }
                    })
        
        return claude_blocks
    
    def convert_message_to_openai(
        self,
        claude_message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Claude 单条消息 → OpenAI 格式
        """
        role = claude_message.get("role")
        content = claude_message.get("content")
        
        if isinstance(content, str):
            return {"role": role, "content": content}
        
        # Content blocks
        text_parts = []
        tool_calls = []
        
        for block in content:
            block_type = block.get("type")
            
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            
            elif block_type == "thinking":
                # OpenAI 不支持 thinking，可以忽略或添加注释
                pass
            
            elif block_type == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {}), ensure_ascii=False)
                    }
                })
        
        result = {
            "role": role,
            "content": "\n".join(text_parts) if text_parts else None
        }
        
        if tool_calls:
            result["tool_calls"] = tool_calls
        
        return result
```

---

## 💡 使用示例

### 1. 简化格式（推荐新用户）

```bash
# 最简单的调用方式
curl -X POST http://localhost:8000/api/v2/chat \
  -H "Content-Type: application/json" \
  -d '{
    "format": "simple",
    "message": "帮我生成一个关于 AI 的 PPT",
    "conversation_id": "conv_123"
  }'
```

**响应**：
```json
{
  "conversation_id": "conv_123",
  "session_id": "sess_xxx",
  "message": {
    "role": "assistant",
    "content": "好的，我已经为你生成了一个关于 AI 的 PPT...\n下载链接: https://..."
  },
  "status": "success",
  "turns": 3
}
```

### 2. Claude 原生格式（推荐高级用户）

```bash
curl -X POST http://localhost:8000/api/v2/chat \
  -H "Content-Type: application/json" \
  -d '{
    "format": "claude",
    "messages": [
      {"role": "user", "content": "你好"},
      {"role": "assistant", "content": [
        {"type": "text", "text": "你好！有什么可以帮助你的？"}
      ]},
      {"role": "user", "content": "帮我分析一下这张图片"},
      {"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}}
      ]}
    ]
  }'
```

**响应**（保留完整 Content Blocks）：
```json
{
  "conversation_id": "conv_456",
  "session_id": "sess_yyy",
  "message": {
    "role": "assistant",
    "content": [
      {"type": "thinking", "thinking": "用户上传了一张图片，让我分析..."},
      {"type": "text", "text": "这张图片展示的是..."},
      {"type": "tool_use", "id": "toolu_xxx", "name": "image_analysis", "input": {...}}
    ]
  },
  "status": "success",
  "turns": 2,
  "thinking": "用户上传了一张图片，让我分析..."
}
```

### 3. OpenAI ChatML 格式（兼容现有系统）

```bash
curl -X POST http://localhost:8000/api/v2/chat \
  -H "Content-Type: application/json" \
  -d '{
    "format": "openai",
    "messages": [
      {"role": "system", "content": "你是一个专业的 PPT 生成助手"},
      {"role": "user", "content": "你好"},
      {"role": "assistant", "content": "你好！"},
      {"role": "user", "content": "帮我生成 PPT"}
    ]
  }'
```

**响应（转换为 OpenAI 格式）**：
```json
{
  "conversation_id": "conv_789",
  "session_id": "sess_zzz", 
  "message": {
    "role": "assistant",
    "content": "好的，我来帮你生成 PPT...",
    "tool_calls": [
      {
        "id": "call_xxx",
        "type": "function",
        "function": {
          "name": "slidespeak",
          "arguments": "{\"title\": \"...\"}"
        }
      }
    ]
  },
  "status": "success",
  "turns": 2
}
```

### 4. Python SDK 示例

```python
# 使用 Python 调用

import httpx
from typing import List, Dict, Any

class ZenFluxClient:
    """ZenFlux Agent 客户端"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient()
    
    async def chat(
        self,
        message: str,
        conversation_id: str = None,
        history: List[Dict[str, Any]] = None,
        format: str = "simple"
    ) -> Dict[str, Any]:
        """
        发送聊天请求
        
        Args:
            message: 用户消息
            conversation_id: 对话 ID（延续历史）
            history: 消息历史（可选，覆盖数据库历史）
            format: 格式（simple/claude/openai）
        """
        payload = {
            "format": format,
            "conversation_id": conversation_id,
            "stream": False
        }
        
        if format == "simple":
            payload["message"] = message
        else:
            if history:
                payload["messages"] = history + [{"role": "user", "content": message}]
            else:
                payload["messages"] = [{"role": "user", "content": message}]
        
        response = await self.client.post(
            f"{self.base_url}/api/v2/chat",
            json=payload
        )
        
        return response.json()
    
    async def chat_stream(
        self,
        message: str,
        conversation_id: str = None
    ):
        """流式聊天"""
        async with self.client.stream(
            "POST",
            f"{self.base_url}/api/v2/chat",
            json={
                "format": "simple",
                "message": message,
                "conversation_id": conversation_id,
                "stream": True
            }
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    yield json.loads(line[6:])


# 使用示例
async def main():
    client = ZenFluxClient()
    
    # 简单对话
    result = await client.chat("帮我生成一个 PPT")
    print(result["message"]["content"])
    
    # 延续对话
    result2 = await client.chat(
        "把标题改成 AI 技术分享",
        conversation_id=result["conversation_id"]
    )
    
    # 流式输出
    async for event in client.chat_stream("分析市场趋势"):
        if event["type"] == "content_delta":
            print(event["data"]["text"], end="", flush=True)
```

---

## 📊 格式对比总览

| 特性 | Simple | Claude | OpenAI |
|-----|--------|--------|--------|
| **适用场景** | 快速测试、新用户 | 高级功能、完整控制 | 兼容现有系统 |
| **Thinking 支持** | ❌ 返回时过滤 | ✅ 完整保留 | ❌ 不支持 |
| **Tool Use** | ❌ 返回时过滤 | ✅ 完整保留 | ✅ 转换为 tool_calls |
| **多模态** | ❌ 不支持 | ✅ 支持 | ✅ 支持 |
| **历史格式** | 字符串列表 | Content Blocks | ChatML |
| **System Prompt** | 默认使用 | 可自定义 | messages[0] |

---

## 🔗 相关文档

| 文档 | 说明 |
|------|------|
| [00-ARCHITECTURE-V4.md](./00-ARCHITECTURE-V4.md) | V4 架构总览 |
| [06-CONVERSATION-HISTORY.md](./06-CONVERSATION-HISTORY.md) | 对话历史管理 |
| [03-EVENT-PROTOCOL.md](./03-EVENT-PROTOCOL.md) | SSE 事件协议 |


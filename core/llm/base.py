"""
LLM 服务基础模块

包含：
- 枚举定义（LLMProvider, ToolType, InvocationType）
- 数据类（LLMConfig, LLMResponse, Message）
- 抽象基类（BaseLLMService）

设计原则：
1. 只提供异步接口
2. 统一的数据格式（兼容 Claude API 格式，用于数据库存储）
3. 易于扩展（支持 Claude、OpenAI、Gemini 等）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List, Union, AsyncIterator, Callable


# ============================================================
# 枚举定义
# ============================================================

class LLMProvider(Enum):
    """LLM 提供商"""
    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"


class ToolType(Enum):
    """
    工具类型（统一抽象）
    
    Claude Server Tools (服务端执行):
    - CODE_EXECUTION: 代码执行（Skills 功能需要）
    - TOOL_SEARCH: 工具搜索 (Beta)
    
    Claude Client Tools (客户端执行):
    - BASH: Shell 命令
    - TEXT_EDITOR: 文本编辑器
    - COMPUTER_USE: 计算机使用 (Beta)
    
    自定义工具:
    - CUSTOM: 用户自定义工具
    
    注：web_search/web_fetch/memory 已移除，改用客户端工具（tavily_search, exa_search, Mem0）
    """
    # Server Tools（仅保留 code_execution 用于 Skills）
    # 🆕 web_search/web_fetch/memory 已移除，改用客户端工具
    CODE_EXECUTION = "code_execution"
    TOOL_SEARCH = "tool_search"
    
    # Client Tools
    BASH = "bash"
    TEXT_EDITOR = "text_editor"
    COMPUTER_USE = "computer_use"
    
    # Custom
    CUSTOM = "custom"


class InvocationType(Enum):
    """
    调用方式类型
    
    - DIRECT: 标准工具调用
    - CODE_EXECUTION: 代码执行
    - PROGRAMMATIC: 程序化工具调用
    - STREAMING: 细粒度流式
    - TOOL_SEARCH: 工具搜索
    """
    DIRECT = "direct"
    CODE_EXECUTION = "code_execution"
    PROGRAMMATIC = "programmatic"
    STREAMING = "streaming"
    TOOL_SEARCH = "tool_search"


# ============================================================
# 数据类
# ============================================================

@dataclass
class LLMConfig:
    """
    LLM 配置
    
    Attributes:
        provider: LLM 提供商
        model: 模型名称
        api_key: API 密钥
        enable_thinking: 启用 Extended Thinking（Claude 特有）
        thinking_budget: Thinking token 预算
        enable_caching: 启用 Prompt Caching
        enable_streaming: 启用流式输出
        temperature: 温度参数
        max_tokens: 最大输出 token 数
        tools: 工具列表
        timeout: 请求超时时间（秒）
        max_retries: 最大重试次数
    """
    provider: LLMProvider
    model: str
    api_key: str
    
    # Core capabilities
    enable_thinking: bool = True
    thinking_budget: int = 10000
    enable_caching: bool = False
    enable_streaming: bool = False
    
    # 基础参数
    temperature: float = 1.0
    max_tokens: int = 64000  # Claude Sonnet 4.5 最大支持 64K output tokens
    
    # Tools
    tools: List[Dict[str, Any]] = field(default_factory=list)
    
    # 高级功能
    enable_context_editing: bool = False
    enable_structured_output: bool = False
    
    # 网络配置
    timeout: float = 120.0  # 请求超时（秒），默认 2 分钟
    max_retries: int = 3    # 最大重试次数


@dataclass
class Message:
    """
    统一的消息格式（兼容 Claude API 格式）
    
    Attributes:
        role: 角色 ("user" | "assistant")
        content: 消息内容（字符串或 content blocks 列表）
    
    Content Blocks 格式（用于复杂消息）：
    ```python
    [
        {"type": "text", "text": "..."},
        {"type": "thinking", "thinking": "...", "signature": "..."},
        {"type": "tool_use", "id": "...", "name": "...", "input": {...}},
        {"type": "tool_result", "tool_use_id": "...", "content": "..."}
    ]
    ```
    """
    role: str
    content: Union[str, List[Dict[str, Any]]]


@dataclass
class LLMResponse:
    """
    统一的 LLM 响应格式（兼容 Claude API 格式）
    
    Attributes:
        content: 文本内容
        thinking: Extended Thinking 内容（Claude 特有）
        tool_calls: 工具调用列表
        stop_reason: 停止原因 (end_turn, tool_use, max_tokens, etc.)
        usage: Token 使用统计
        raw_content: 原始 content blocks（用于消息续传）
        is_stream: 是否为流式响应
        cache_read_tokens: 缓存读取 tokens（Claude 特有）
        cache_creation_tokens: 缓存创建 tokens（Claude 特有）
        
    🆕 流式工具调用：
        tool_use_start: 工具调用开始 {id, name}
        input_delta: 工具参数增量（JSON 片段）
    """
    content: str
    thinking: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    stop_reason: str = "end_turn"
    usage: Optional[Dict[str, int]] = None
    
    # 原始 content 块（用于 tool_use 响应的消息续传）
    raw_content: Optional[List[Any]] = None
    
    # 流式相关
    is_stream: bool = False
    
    # 🆕 流式工具调用
    tool_use_start: Optional[Dict[str, str]] = None  # {id, name}
    input_delta: Optional[str] = None  # JSON 片段
    
    # Claude 特有
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


# ============================================================
# 抽象基类
# ============================================================

class BaseLLMService(ABC):
    """
    LLM 服务抽象基类
    
    所有 LLM 实现必须继承此类并实现以下方法：
    - create_message_async: 异步创建消息
    - create_message_stream: 流式创建消息
    - count_tokens: 计算 token 数量
    
    使用示例：
    ```python
    # 异步调用
    response = await llm.create_message_async(
        messages=[Message(role="user", content="Hello")],
        system="You are a helpful assistant"
    )
    
    # 流式调用
    async for chunk in llm.create_message_stream(messages, system):
        print(chunk.content, end="")
    ```
    """
    
    @abstractmethod
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
            LLMResponse 响应对象
        """
        pass
    
    @abstractmethod
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
            on_thinking: thinking 回调
            on_content: content 回调
            on_tool_call: tool_call 回调
            **kwargs: 其他参数
            
        Yields:
            LLMResponse 片段
        """
        pass
    
    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """
        计算 token 数量
        
        Args:
            text: 要计算的文本
            
        Returns:
            token 数量
        """
        pass
    
    def convert_to_tool_schema(self, capability: Dict[str, Any]) -> Dict[str, Any]:
        """
        将能力定义转换为工具 schema（可被子类覆盖）
        
        Args:
            capability: 能力定义（来自 capabilities.yaml）
            
        Returns:
            工具 schema
        """
        name = capability.get("name", "")
        input_schema = capability.get("input_schema", {
            "type": "object",
            "properties": {},
            "required": []
        })
        description = capability.get("metadata", {}).get("description", f"Tool: {name}")
        
        return {
            "name": name,
            "description": description,
            "input_schema": input_schema
        }


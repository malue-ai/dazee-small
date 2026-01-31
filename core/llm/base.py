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
    QWEN = "qwen"


class ToolType(Enum):
    """
    工具类型（统一抽象）
    
    Claude Server Tools (服务端执行):
    - WEB_SEARCH: 网页搜索
    - WEB_FETCH: 网页获取 (Beta)
    - CODE_EXECUTION: 代码执行 (Beta)
    - MEMORY: 记忆工具 (Beta)
    - TOOL_SEARCH: 工具搜索 (Beta)
    
    Claude Client Tools (客户端执行):
    - BASH: Shell 命令
    - TEXT_EDITOR: 文本编辑器
    - COMPUTER_USE: 计算机使用 (Beta)
    
    自定义工具:
    - CUSTOM: 用户自定义工具
    """
    # Server Tools
    WEB_SEARCH = "web_search"
    WEB_FETCH = "web_fetch"
    CODE_EXECUTION = "code_execution"
    MEMORY = "memory"
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
        base_url: API 基础地址（OpenAI 兼容厂商）
        api_key_env: API Key 环境变量名称（可选）
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
    base_url: Optional[str] = None
    compat: Optional[str] = None
    api_key_env: Optional[str] = None
    
    # Core capabilities
    enable_thinking: bool = True
    thinking_budget: int = 10000
    enable_caching: bool = False
    enable_streaming: bool = False
    
    # 基础参数
    temperature: float = 1.0
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    repetition_penalty: Optional[float] = None
    max_tokens: int = 64000  # Claude Sonnet 4.5 最大支持 64K output tokens
    
    # Tools
    tools: List[Dict[str, Any]] = field(default_factory=list)
    
    # 高级功能
    enable_context_editing: bool = False
    enable_structured_output: bool = False
    result_format: Optional[str] = None
    tool_choice: Optional[str] = None
    parallel_tool_calls: Optional[bool] = None

    # Qwen 扩展参数（未设置时不透传）
    top_k: Optional[int] = None
    seed: Optional[int] = None
    stop: Optional[Union[str, List[str]]] = None
    n: Optional[int] = None
    response_format: Optional[Dict[str, Any]] = None
    logprobs: Optional[bool] = None
    top_logprobs: Optional[int] = None
    enable_search: Optional[bool] = None
    search_options: Optional[Dict[str, Any]] = None
    incremental_output: Optional[bool] = None
    vl_high_resolution_images: Optional[bool] = None
    vl_enable_image_hw_output: Optional[bool] = None
    enable_code_interpreter: Optional[bool] = None
    
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

    def supports_native_tools(self) -> bool:
        """
        是否支持 Claude 原生工具（bash/text_editor/web_search）
        
        Returns:
            是否支持原生工具
        """
        return False

    def supports_skills(self) -> bool:
        """
        是否支持 Claude Skills 容器
        
        Returns:
            是否支持 Skills
        """
        return False

    async def probe(
        self,
        max_retries: int = 3,
        message: str = "ping",
        **kwargs
    ) -> Dict[str, Any]:
        """
        服务存活探针（默认实现）
        
        Args:
            max_retries: 最大重试次数
            message: 探针消息内容
        
        Returns:
            探针结果
        """
        from infra.resilience.retry import retry_async
        
        config = getattr(self, "config", None)
        provider = getattr(config, "provider", None)
        provider_value = provider.value if provider else "unknown"
        model = getattr(config, "model", "unknown")
        target = {
            "name": f"{provider_value}:{model}",
            "provider": provider_value,
            "model": model
        }
        
        async def _call():
            return await self.create_message_async(
                messages=[Message(role="user", content=message)],
                system=None,
                tools=None,
                max_tokens=1,
                temperature=0.0,
                enable_thinking=False,
                enable_caching=False,
            )
        
        if provider == LLMProvider.CLAUDE:
            await _call()
        else:
            await retry_async(_call, max_retries=max_retries)
        
        return {
            "primary": target,
            "selected": target,
            "switched": False,
            "errors": []
        }
    
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


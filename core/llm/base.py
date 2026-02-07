"""
LLM 服务基础模块

包含：
- 枚举定义（LLMProvider, ToolType, InvocationType）
- 数据类（LLMConfig, LLMResponse, Message）
- 抽象基类（BaseLLMService）
- 统一的 token 计算函数（tiktoken）

设计原则：
1. 只提供异步接口
2. 统一的数据格式（兼容 Claude API 格式，用于数据库存储）
3. 易于扩展（支持 Claude、OpenAI、Gemini 等）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

import tiktoken

# ============================================================
# 统一的 Token 计算（使用 tiktoken cl100k_base）
# ============================================================

# 全局 tokenizer 缓存
_tiktoken_encoder = None


def _get_tiktoken_encoder():
    """
    获取 tiktoken encoder（延迟初始化，全局缓存）

    PyInstaller 打包后 importlib.metadata.entry_points() 无法发现
    tiktoken 的编码插件，需要手动导入并注册。
    """
    global _tiktoken_encoder
    if _tiktoken_encoder is None:
        try:
            _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
        except ValueError:
            # PyInstaller 打包环境：手动注册 tiktoken 编码插件
            import importlib
            mod = importlib.import_module("tiktoken_ext.openai_public")
            constructors = mod.ENCODING_CONSTRUCTORS()
            # 将编码构造器注册到 tiktoken 内部注册表
            for enc_name, constructor_fn in constructors.items():
                tiktoken.registry.ENCODING_CONSTRUCTORS[enc_name] = constructor_fn
            _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
    return _tiktoken_encoder


def count_tokens(text: str) -> int:
    """
    计算文本的 token 数量（使用 tiktoken cl100k_base）

    这是多模型项目的统一 token 计算方案。
    cl100k_base 编码适用于 GPT-4/Claude 等主流模型的近似计算。

    Args:
        text: 要计算的文本

    Returns:
        token 数量
    """
    if not text:
        return 0
    encoder = _get_tiktoken_encoder()
    return len(encoder.encode(text))


def _extract_message_text(content: Any) -> str:
    """
    递归提取消息中的所有文本内容

    支持的内容格式：
    - 字符串
    - 列表（包含多个 block）
    - 字典（text/tool_result/tool_use/thinking block）
    """
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        return " ".join(_extract_message_text(item) for item in content)
    elif isinstance(content, dict):
        block_type = content.get("type", "")
        if block_type == "text":
            return content.get("text", "")
        elif block_type == "tool_result":
            return _extract_message_text(content.get("content", ""))
        elif block_type == "tool_use":
            tool_name = content.get("name", "")
            tool_input = content.get("input", {})
            return f"{tool_name}: {str(tool_input)}"
        elif block_type == "thinking":
            return content.get("thinking", "")
        else:
            return str(content.get("text", "") or content.get("content", ""))
    return str(content)


def count_message_tokens(msg: Dict[str, Any]) -> int:
    """
    计算单条消息的 token 数

    Args:
        msg: 消息字典（包含 role 和 content）

    Returns:
        token 数量
    """
    role = msg.get("role", "")
    content = msg.get("content", "")
    text = f"{role}: {_extract_message_text(content)}"
    return count_tokens(text)


def count_messages_tokens(messages: List[Dict[str, Any]], system_prompt: str = "") -> int:
    """
    计算消息列表的 token 数

    Args:
        messages: 消息列表
        system_prompt: 系统提示词

    Returns:
        token 数量
    """
    all_text = system_prompt or ""

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        msg_text = f"{role}: {_extract_message_text(content)}"
        all_text += "\n" + msg_text

    return count_tokens(all_text)


def count_tools_tokens(tools: List[Dict[str, Any]]) -> int:
    """
    计算工具定义的 token 数

    Args:
        tools: 工具定义列表（Claude API 格式）

    Returns:
        token 数量
    """
    if not tools:
        return 0

    import json

    try:
        tools_json = json.dumps(tools, ensure_ascii=False)
        return count_tokens(tools_json)
    except Exception:
        # 保守估计：每个工具 1000 tokens
        return len(tools) * 1000


def count_request_tokens(
    messages: List[Dict[str, Any]], system_prompt: str = "", tools: List[Dict[str, Any]] = None
) -> int:
    """
    计算完整 LLM 请求的 token 数（消息 + 系统提示 + 工具）

    Args:
        messages: 消息列表
        system_prompt: 系统提示词
        tools: 工具定义列表（可选）

    Returns:
        总 token 数
    """
    message_tokens = count_messages_tokens(messages, system_prompt)
    tools_tokens = count_tools_tokens(tools) if tools else 0
    return message_tokens + tools_tokens


# ============================================================
# 枚举定义
# ============================================================


class LLMProvider(Enum):
    """LLM 提供商"""

    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"
    QWEN = "qwen"  # 🆕 通义千问（阿里云）


class ToolType(Enum):
    """
    工具类型（统一抽象）

    Claude Client Tools (客户端执行):
    - BASH: Shell 命令
    - TEXT_EDITOR: 文本编辑器
    - COMPUTER_USE: 计算机使用 (Beta)

    自定义工具:
    - CUSTOM: 用户自定义工具

    注：所有服务器工具已移除，搜索通过 Skills 提供
    """

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
    - PROGRAMMATIC: 程序化工具调用
    - STREAMING: 细粒度流式
    """

    DIRECT = "direct"
    PROGRAMMATIC = "programmatic"
    STREAMING = "streaming"


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
        base_url: API 基础 URL（可选，用于自定义 endpoint 或代理）
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
    max_tokens: int = 32768

    # Tools
    tools: List[Dict[str, Any]] = field(default_factory=list)

    # 高级功能
    enable_context_editing: bool = False
    enable_structured_output: bool = False

    # 网络配置
    base_url: Optional[str] = None  # API 基础 URL（可选，用于自定义 endpoint）
    timeout: float = 120.0  # 请求超时（秒），默认 2 分钟
    max_retries: int = 3  # 最大重试次数


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
        model: 实际使用的模型名称（用于准确计费）🆕
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

    # 🆕 实际使用的模型名称（用于准确计费，尤其在容灾切换时）
    model: Optional[str] = None

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
        **kwargs,
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
        **kwargs,
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

    def count_tokens(self, text: str) -> int:
        """
        计算 token 数量（使用 tiktoken cl100k_base）

        TODO: 各 LLM 服务可以重写此方法，使用官方 API 获取精确值
        - Claude: client.messages.count_tokens()
        - OpenAI: tiktoken 精确计算
        - Qwen/Gemini: 官方 tokenizer

        Args:
            text: 要计算的文本

        Returns:
            token 数量
        """
        return count_tokens(text)

    def convert_to_tool_schema(self, capability: Dict[str, Any]) -> Dict[str, Any]:
        """
        将能力定义转换为工具 schema（可被子类覆盖）

        Args:
            capability: 能力定义（来自 capabilities.yaml）

        Returns:
            工具 schema
        """
        name = capability.get("name", "")
        input_schema = capability.get(
            "input_schema", {"type": "object", "properties": {}, "required": []}
        )
        description = capability.get("metadata", {}).get("description", f"Tool: {name}")

        return {"name": name, "description": description, "input_schema": input_schema}

"""
LLM 服务模块

提供统一的 LLM 服务接口，支持多种 LLM 提供商。

模块结构：
- base.py: 基础类和数据模型
- claude.py: Claude 实现
- openai.py: OpenAI 实现（占位）
- gemini.py: Gemini 实现（占位）

使用示例：
```python
from core.llm import create_llm_service, LLMProvider, Message

# 创建 Claude 服务
llm = create_llm_service(provider=LLMProvider.CLAUDE)

# 异步调用
response = await llm.create_message_async(
    messages=[Message(role="user", content="Hello")],
    system="You are helpful"
)

# 流式调用
async for chunk in llm.create_message_stream(messages, system):
    print(chunk.content, end="")
```
"""

import os
from typing import Optional, Union

# 基础类和数据模型
from .base import (
    # 枚举
    LLMProvider,
    ToolType,
    InvocationType,
    # 数据类
    LLMConfig,
    LLMResponse,
    Message,
    # 抽象基类
    BaseLLMService,
)

# Claude 实现
from .claude import (
    ClaudeLLMService,
    create_claude_service,
)

# OpenAI 实现（占位）
from .openai import OpenAILLMService

# Gemini 实现（占位）
from .gemini import GeminiLLMService

# 格式适配器
from .adaptor import (
    BaseAdaptor,
    ClaudeAdaptor,
    OpenAIAdaptor,
    GeminiAdaptor,
    get_adaptor,
)


# ============================================================
# 工厂函数
# ============================================================

def create_llm_service(
    provider: Union[LLMProvider, str] = LLMProvider.CLAUDE,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    **kwargs
) -> BaseLLMService:
    """
    工厂函数：创建 LLM 服务
    
    Args:
        provider: LLM 提供商 (claude, openai, gemini)
        model: 模型名称（默认根据 provider 选择）
        api_key: API 密钥（默认从环境变量读取）
        **kwargs: 其他配置参数
        
    Returns:
        LLM 服务实例
        
    Example:
    ```python
    # Claude（默认）
    llm = create_llm_service()
    
    # 指定模型
    llm = create_llm_service(
        provider=LLMProvider.CLAUDE,
        model="claude-sonnet-4-5-20250929",
        enable_thinking=True
    )
    
    # OpenAI（待实现）
    llm = create_llm_service(provider=LLMProvider.OPENAI)
    ```
    """
    # 字符串转枚举
    if isinstance(provider, str):
        provider = LLMProvider(provider)
    
    # 默认模型
    default_models = {
        LLMProvider.CLAUDE: "claude-sonnet-4-5-20250929",
        LLMProvider.OPENAI: "gpt-4o",
        LLMProvider.GEMINI: "gemini-pro",
    }
    
    if model is None:
        model = default_models.get(provider, "claude-sonnet-4-5-20250929")
    
    # 默认 API Key
    if api_key is None:
        env_keys = {
            LLMProvider.CLAUDE: "ANTHROPIC_API_KEY",
            LLMProvider.OPENAI: "OPENAI_API_KEY",
            LLMProvider.GEMINI: "GOOGLE_API_KEY",
        }
        api_key = os.getenv(env_keys.get(provider, "ANTHROPIC_API_KEY"))
    
    # 创建配置
    config = LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        **kwargs
    )
    
    # 根据 provider 创建服务
    if provider == LLMProvider.CLAUDE:
        return ClaudeLLMService(config)
    elif provider == LLMProvider.OPENAI:
        return OpenAILLMService(config)
    elif provider == LLMProvider.GEMINI:
        return GeminiLLMService(config)
    else:
        raise ValueError(f"Unknown provider: {provider}")


# ============================================================
# 导出
# ============================================================

__all__ = [
    # 枚举
    "LLMProvider",
    "ToolType",
    "InvocationType",
    
    # 数据类
    "LLMConfig",
    "LLMResponse",
    "Message",
    
    # 基类
    "BaseLLMService",
    
    # 实现类
    "ClaudeLLMService",
    "OpenAILLMService",
    "GeminiLLMService",
    
    # 适配器
    "BaseAdaptor",
    "ClaudeAdaptor",
    "OpenAIAdaptor",
    "GeminiAdaptor",
    "get_adaptor",
    
    # 工厂函数
    "create_llm_service",
    "create_claude_service",
]


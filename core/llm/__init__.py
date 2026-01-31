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
from typing import Optional, Union, Dict, Any, List

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

# Qwen 实现（DashScope SDK）
from .qwen import QwenLLMService

# 格式适配器
from .adaptor import (
    BaseAdaptor,
    ClaudeAdaptor,
    OpenAIAdaptor,
    GeminiAdaptor,
    get_adaptor,
)

# 路由器
from .router import ModelRouter, RouteTarget


# ============================================================
# 工厂函数
# ============================================================

def _normalize_provider(provider: Union[LLMProvider, str]) -> LLMProvider:
    """
    规范化 provider 类型
    
    Args:
        provider: provider 输入
        
    Returns:
        LLMProvider
    """
    if isinstance(provider, str):
        return LLMProvider(provider)
    return provider


def _build_target_name(
    provider: LLMProvider,
    model: str,
    base_url: Optional[str] = None,
    prefix: Optional[str] = None
) -> str:
    """
    构建路由目标名称（支持多 Provider 来源）
    """
    base_part = f"{provider.value}:{model}"
    if base_url:
        base_part = f"{base_part}@{base_url}"
    if prefix:
        return f"{prefix}:{base_part}"
    return base_part


def create_base_llm_service(
    provider: Union[LLMProvider, str] = LLMProvider.CLAUDE,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    **kwargs
) -> BaseLLMService:
    """
    创建基础 LLM 服务（不启用路由）
    
    Args:
        provider: LLM 提供商
        model: 模型名称
        api_key: API Key
        **kwargs: 其他参数
        
    Returns:
        LLM 服务实例
    """
    api_key_env = kwargs.pop("api_key_env", None)
    if api_key is None and api_key_env:
        api_key = os.getenv(api_key_env)
    
    provider = _normalize_provider(provider)
    
    # 默认模型
    default_models = {
        LLMProvider.CLAUDE: "claude-sonnet-4-5-20250929",
        LLMProvider.OPENAI: "gpt-4o",
        LLMProvider.GEMINI: "gemini-pro",
        LLMProvider.QWEN: "qwen-max",
    }
    
    if model is None:
        model = default_models.get(provider, "claude-sonnet-4-5-20250929")
    
    # 默认 API Key
    if api_key is None:
        env_keys = {
            LLMProvider.CLAUDE: "ANTHROPIC_API_KEY",
            LLMProvider.OPENAI: "OPENAI_API_KEY",
            LLMProvider.GEMINI: "GOOGLE_API_KEY",
            LLMProvider.QWEN: "QWEN_API_KEY",
        }
        api_key = os.getenv(env_keys.get(provider, "ANTHROPIC_API_KEY"))
        if provider == LLMProvider.QWEN and not api_key:
            api_key = os.getenv("DASHSCOPE_API_KEY")
    
    # 默认 compat/base_url（Qwen 优先使用 QWEN_BASE_URL）
    if provider == LLMProvider.QWEN and not kwargs.get("compat"):
        kwargs["compat"] = "qwen"
    if provider == LLMProvider.QWEN and not kwargs.get("base_url"):
        qwen_base_url = os.getenv("QWEN_BASE_URL")
        if qwen_base_url:
            kwargs["base_url"] = qwen_base_url
    
    config = LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        **kwargs
    )
    
    if provider == LLMProvider.CLAUDE:
        return ClaudeLLMService(config)
    if provider == LLMProvider.OPENAI:
        return OpenAILLMService(config)
    if provider == LLMProvider.GEMINI:
        return GeminiLLMService(config)
    if provider == LLMProvider.QWEN:
        return QwenLLMService(config)
    
    raise ValueError(f"Unknown provider: {provider}")


def create_llm_service(
    provider: Union[LLMProvider, str] = LLMProvider.CLAUDE,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    fallbacks: Optional[List[Dict[str, Any]]] = None,
    policy: Optional[Dict[str, Any]] = None,
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
    # 兼容 fallbacks / policy 从 kwargs 传入
    fallbacks = fallbacks or kwargs.pop("fallbacks", None)
    policy = policy or kwargs.pop("policy", None)
    
    # API Key 环境变量覆盖
    api_key_env = kwargs.pop("api_key_env", None)
    if api_key is None and api_key_env:
        api_key = os.getenv(api_key_env)
    
    provider = _normalize_provider(provider)
    
    # 主服务
    primary_service = create_base_llm_service(
        provider=provider,
        model=model,
        api_key=api_key,
        **kwargs
    )
    
    if not fallbacks:
        return primary_service
    
    # 构建路由目标
    primary_target = RouteTarget(
        service=primary_service,
        provider=provider,
        model=primary_service.config.model,
        name=_build_target_name(
            provider=provider,
            model=primary_service.config.model,
            base_url=primary_service.config.base_url
        )
    )
    
    fallback_targets = []
    for idx, fb in enumerate(fallbacks):
        if not isinstance(fb, dict):
            continue
        
        fb_provider = _normalize_provider(fb.get("provider", provider))
        fb_model = fb.get("model")
        fb_api_key = fb.get("api_key")
        fb_api_key_env = fb.get("api_key_env")
        if fb_api_key is None and fb_api_key_env:
            fb_api_key = os.getenv(fb_api_key_env)
        
        fb_kwargs = fb.copy()
        for key in ["provider", "model", "api_key", "api_key_env"]:
            fb_kwargs.pop(key, None)
        
        fb_service = create_base_llm_service(
            provider=fb_provider,
            model=fb_model,
            api_key=fb_api_key,
            **fb_kwargs
        )
        
        fallback_targets.append(RouteTarget(
            service=fb_service,
            provider=fb_provider,
            model=fb_service.config.model,
            name=_build_target_name(
                provider=fb_provider,
                model=fb_service.config.model,
                base_url=fb_service.config.base_url,
                prefix=f"fallback_{idx}"
            )
        ))
    
    return ModelRouter(primary=primary_target, fallbacks=fallback_targets, policy=policy)


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
    "QwenLLMService",
    
    # 适配器
    "BaseAdaptor",
    "ClaudeAdaptor",
    "OpenAIAdaptor",
    "GeminiAdaptor",
    "get_adaptor",
    "ModelRouter",
    
    # 工厂函数
    "create_llm_service",
    "create_base_llm_service",
    "create_claude_service",
]


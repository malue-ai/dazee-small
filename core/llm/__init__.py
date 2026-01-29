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

# 多模型路由器（🆕 V7.10）
from .router import (
    ModelRouter,
    RouteTarget,
    RouterPolicy,
)

# 健康监控器（🆕 V7.10）
from .health_monitor import (
    LLMHealthMonitor,
    HealthPolicy,
    get_llm_health_monitor,
)

# 工具调用工具（🆕 V7.10）
from .tool_call_utils import normalize_tool_calls


# ============================================================
# 工厂函数
# ============================================================

def _create_single_llm_service(
    provider: Union[LLMProvider, str],
    model: str,
    api_key: Optional[str] = None,
    **kwargs
) -> BaseLLMService:
    """
    创建单个 LLM 服务（内部函数）
    
    Args:
        provider: LLM 提供商
        model: 模型名称
        api_key: API 密钥
        **kwargs: 其他配置参数
        
    Returns:
        LLM 服务实例
    """
    # 字符串转枚举
    if isinstance(provider, str):
        provider = LLMProvider(provider)
    
    # 创建配置（过滤掉 ModelRouter 专有参数）
    router_keys = {"fallbacks", "policy", "api_key_env"}
    filtered_kwargs = {k: v for k, v in kwargs.items() if k not in router_keys}
    
    config = LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        **filtered_kwargs
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


def create_llm_service(
    provider: Union[LLMProvider, str] = LLMProvider.CLAUDE,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    **kwargs
) -> BaseLLMService:
    """
    工厂函数：创建 LLM 服务（支持多模型容灾）
    
    Args:
        provider: LLM 提供商 (claude, openai, gemini)
        model: 模型名称（默认根据 provider 选择）
        api_key: API 密钥（默认从环境变量读取）
        **kwargs: 其他配置参数
            - fallbacks: 备选模型列表（🆕 V7.10）
            - policy: 路由策略（🆕 V7.10）
            - api_key_env: API Key 环境变量名（🆕 V7.10）
        
    Returns:
        LLM 服务实例（可能是 ModelRouter 或单个 LLM Service）
        
    Example:
    ```python
    # 单个模型（无容灾）
    llm = create_llm_service(provider="claude", model="claude-sonnet-4-5")
    
    # 多模型容灾（自动包装为 ModelRouter）
    llm = create_llm_service(
        provider="claude",
        model="claude-sonnet-4-5",
        fallbacks=[
            {"provider": "claude", "model": "claude-sonnet-4-5", "api_key_env": "CLAUDE_API_KEY_VENDOR_A"}
        ],
        policy={"max_failures": 2, "cooldown_seconds": 600}
    )
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
    
    # 从环境变量读取 API Key（支持 api_key_env 参数）
    api_key_env = kwargs.pop("api_key_env", None)
    if api_key is None:
        if api_key_env:
            api_key = os.getenv(api_key_env)
        else:
            env_keys = {
                LLMProvider.CLAUDE: "ANTHROPIC_API_KEY",
                LLMProvider.OPENAI: "OPENAI_API_KEY",
                LLMProvider.GEMINI: "GOOGLE_API_KEY",
            }
            api_key = os.getenv(env_keys.get(provider, "ANTHROPIC_API_KEY"))
    
    # 检查是否有 fallbacks 配置（🆕 V7.10）
    fallbacks_config = kwargs.pop("fallbacks", None)
    policy_config = kwargs.pop("policy", None)
    
    if not fallbacks_config:
        # 无 fallbacks，创建单个 LLM 服务
        return _create_single_llm_service(provider, model, api_key, **kwargs)
    
    # 有 fallbacks，创建 ModelRouter（🆕 V7.10）
    from logger import get_logger
    logger = get_logger("llm.factory")
    
    # 创建 primary target
    primary_service = _create_single_llm_service(provider, model, api_key, **kwargs)
    primary = RouteTarget(
        service=primary_service,
        provider=provider,
        model=model,
        name=f"primary:{provider.value}:{model}"
    )
    
    # 创建 fallback targets
    fallbacks = []
    for idx, fb_config in enumerate(fallbacks_config):
        fb_provider = fb_config.get("provider", provider)
        fb_model = fb_config.get("model", model)
        fb_api_key_env = fb_config.get("api_key_env")
        fb_api_key = os.getenv(fb_api_key_env) if fb_api_key_env else None
        
        # 合并配置（fallback 继承 primary 的配置，但可覆盖）
        fb_kwargs = kwargs.copy()
        for key in ["base_url", "max_tokens", "temperature", "enable_thinking", 
                    "thinking_budget", "enable_caching", "timeout", "max_retries"]:
            if key in fb_config:
                fb_kwargs[key] = fb_config[key]
        
        fb_service = _create_single_llm_service(fb_provider, fb_model, fb_api_key, **fb_kwargs)
        fallbacks.append(RouteTarget(
            service=fb_service,
            provider=fb_provider if isinstance(fb_provider, LLMProvider) else LLMProvider(fb_provider),
            model=fb_model,
            name=f"fallback_{idx}:{fb_provider}:{fb_model}"
        ))
    
    # 创建 ModelRouter
    logger.info(
        f"🔀 创建 ModelRouter: primary={primary.name}, "
        f"fallbacks=[{', '.join(f.name for f in fallbacks)}]"
    )
    
    return ModelRouter(
        primary=primary,
        fallbacks=fallbacks,
        policy=policy_config,
        health_monitor=get_llm_health_monitor()
    )


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
    
    # 多模型路由器（🆕 V7.10）
    "ModelRouter",
    "RouteTarget",
    "RouterPolicy",
    
    # 健康监控器（🆕 V7.10）
    "LLMHealthMonitor",
    "HealthPolicy",
    "get_llm_health_monitor",
    
    # 工具调用工具（🆕 V7.10）
    "normalize_tool_calls",
    
    # 工厂函数
    "create_llm_service",
    "create_claude_service",
]


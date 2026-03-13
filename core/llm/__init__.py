"""
LLM 服务模块

提供统一的 LLM 服务接口，支持多种 LLM 提供商。

双层注册架构：
- LLMRegistry（Provider 层）: 定义"如何调用"（服务类 + 适配器）
- ModelRegistry（Model 层）: 定义"具体配置"（endpoint、能力、类型）

模块结构：
- registry.py: Provider 注册中心
- model_registry.py: Model 注册中心
- base.py: 基础类和数据模型
- adaptor.py: 格式适配器
- claude.py: Claude 实现
- openai.py: OpenAI 实现
- gemini.py: Gemini 实现
- qwen.py: 千问实现
- deepseek.py: DeepSeek 实现
- glm.py: GLM 实现

使用示例：
```python
from core.llm import (
    create_llm_service, LLMProvider, Message,
    LLMRegistry, ModelRegistry, ModelType
)

# 方式 1：通过 ModelRegistry 创建（推荐）
llm = ModelRegistry.create_service("gpt-4o")
embedder = ModelRegistry.create_service("bge-m3")

# 方式 2：通过 LLMRegistry 创建
llm = LLMRegistry.create_service("claude")

# 方式 3：使用工厂函数
llm = create_llm_service(provider=LLMProvider.CLAUDE)

# 查询可用模型
llm_models = ModelRegistry.list_models(model_type=ModelType.LLM)
embedding_models = ModelRegistry.list_models(model_type=ModelType.EMBEDDING)

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

# 格式适配器
from .adaptor import (
    BaseAdaptor,
    ClaudeAdaptor,
    DeepSeekAdaptor,
    GeminiAdaptor,
    OpenAIAdaptor,
    get_adaptor,
)

# 基础类和数据模型
from .base import (  # 枚举; 数据类; 抽象基类; Token 计算
    BaseLLMService,
    InvocationType,
    LLMConfig,
    LLMProvider,
    LLMResponse,
    Message,
    ToolType,
    count_message_tokens,
    count_messages_tokens,
    count_request_tokens,
    count_tokens,
    count_tools_tokens,
)

# Claude 实现
from .claude import (
    ClaudeLLMService,
    create_claude_service,
)

# Gemini 实现（占位）
from .gemini import GeminiLLMService

# 健康监控器（🆕 V7.10）
from .health_monitor import (
    HealthPolicy,
    LLMHealthMonitor,
    get_llm_health_monitor,
)

# Model 注册中心（新增）
from .model_registry import (
    AdapterType,
    ModelCapabilities,
    ModelConfig,
    ModelRegistry,
    ModelType,
)

# OpenAI 实现（占位）
from .openai import OpenAILLMService

# DeepSeek 实现
from .deepseek import (
    DeepSeekLLMService,
    create_deepseek_service,
)

# GLM 实现
from .glm import (
    GLMLLMService,
    create_glm_service,
)

# MiniMax 实现
from .minimax import (
    MiniMaxLLMService,
    create_minimax_service,
)

# 千问实现
from .qwen import (
    QwenConfig,
    QwenLLMService,
    create_qwen_service,
)

# Provider 注册中心
from .registry import LLMRegistry

# 多模型路由器（🆕 V7.10）
from .router import (
    ModelRouter,
    RouterPolicy,
    RouteTarget,
)

# 工具调用工具（🆕 V7.10）
from .tool_call_utils import normalize_tool_calls

# ============================================================
# 工厂函数
# ============================================================


def _create_single_llm_service(
    provider: Union[LLMProvider, str], model: str, api_key: Optional[str] = None, **kwargs
) -> BaseLLMService:
    """
    创建单个 LLM 服务（内部函数）

    通过 LLMRegistry 动态创建，无需硬编码 if-elif 链。
    添加新 Provider 只需：
    1. 创建 XxxLLMService 类
    2. 在文件末尾调用 LLMRegistry.register()
    3. 在配置中使用 provider: "xxx"

    Args:
        provider: LLM 提供商（字符串或枚举）
        model: 模型名称
        api_key: API 密钥
        **kwargs: 其他配置参数

    Returns:
        LLM 服务实例
    """
    # 统一转为字符串（LLMRegistry 使用字符串作为 key）
    provider_str = provider.value if isinstance(provider, LLMProvider) else provider

    # 过滤掉 ModelRouter 专有参数
    router_keys = {"fallbacks", "policy", "api_key_env"}
    filtered_kwargs = {k: v for k, v in kwargs.items() if k not in router_keys}

    # 🆕 使用 LLMRegistry 动态创建服务（自动处理 config_class）
    return LLMRegistry.create_service(
        provider=provider_str, model=model, api_key=api_key, **filtered_kwargs
    )


def create_llm_service(
    provider: Union[LLMProvider, str] = LLMProvider.CLAUDE,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    **kwargs,
) -> BaseLLMService:
    """
    工厂函数：创建 LLM 服务（支持多模型容灾）

    Args:
        provider: LLM 提供商 (claude, openai, gemini)
        model: 模型名称（默认根据 provider 选择）
        api_key: API 密钥（默认从环境变量读取）
        **kwargs: 其他配置参数
            - api_key_env: API Key 环境变量名

    Returns:
        LLM 服务实例

    Example:
    ```python
    llm = create_llm_service(provider="claude")
    ```
    """
    # 字符串转枚举
    if isinstance(provider, str):
        provider = LLMProvider(provider)

    from .defaults import DEFAULT_MODELS as _DEFAULTS
    default_models = {
        LLMProvider(k): v for k, v in _DEFAULTS.items()
        if k in {p.value for p in LLMProvider}
    }

    if model is None:
        model = default_models.get(provider)
        if model is None:
            raise ValueError(
                f"未指定模型且 provider '{provider}' 无默认模型。"
                f"请在 config.yaml 中配置 agent.provider 和 agent.model"
            )

    # 从环境变量读取 API Key（支持 api_key_env 参数）
    api_key_env = kwargs.pop("api_key_env", None)
    if api_key is None:
        if api_key_env:
            api_key = os.getenv(api_key_env)
        else:
            env_keys = {
                LLMProvider.CLAUDE: "ANTHROPIC_API_KEY",
                LLMProvider.OPENAI: "OPENAI_API_KEY",
                LLMProvider.GEMINI: "GEMINI_API_KEY",
                LLMProvider.QWEN: "DASHSCOPE_API_KEY",
                LLMProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
                LLMProvider.GLM: "ZHIPUAI_API_KEY",
                LLMProvider.MINIMAX: "MINIMAX_API_KEY",
                LLMProvider.KIMI: "MOONSHOT_API_KEY",
            }
            api_key = os.getenv(env_keys.get(provider, "ANTHROPIC_API_KEY"))

    fallbacks_config = kwargs.pop("fallbacks", None)
    policy = kwargs.pop("policy", None)

    primary_service = _create_single_llm_service(provider, model, api_key, **kwargs)

    if fallbacks_config is False:
        return primary_service

    try:
        from core.llm.router import ModelRouter, RouteTarget
        from logger import get_logger as _get_logger
        _log = _get_logger("llm.factory")

        if fallbacks_config and fallbacks_config != "auto":
            fb_list = fallbacks_config
        else:
            fb_list = _auto_discover_fallbacks(provider)

        if not fb_list:
            return primary_service

        primary_target = RouteTarget(
            name=f"{provider.value}/{model}",
            service=primary_service,
            provider=provider,
            model=model,
        )
        fallback_targets = []
        for fb in fb_list:
            fb_provider = fb.get("provider")
            fb_model = fb.get("model")
            fb_api_key = fb.get("api_key")
            fb_api_key_env = fb.get("api_key_env")
            if fb_api_key_env and not fb_api_key:
                fb_api_key = os.getenv(fb_api_key_env)
            if not fb_api_key:
                continue
            try:
                fb_service = _create_single_llm_service(
                    LLMProvider(fb_provider), fb_model, fb_api_key,
                )
                fallback_targets.append(RouteTarget(
                    name=f"{fb_provider}/{fb_model}",
                    service=fb_service,
                    provider=LLMProvider(fb_provider),
                    model=fb_model or "",
                ))
            except Exception as e:
                _log.debug(f"Fallback {fb_provider}/{fb_model} skip: {e}")

        if fallback_targets:
            _log.info(
                f"ModelRouter: primary={provider.value}/{model}, "
                f"auto-fallbacks={[t.name for t in fallback_targets]}"
            )
            return ModelRouter(
                primary=primary_target,
                fallbacks=fallback_targets,
                policy=policy,
            )
    except ImportError:
        pass

    return primary_service


def _auto_discover_fallbacks(primary_provider: LLMProvider) -> list:
    """Auto-discover fallback providers by scanning configured API Keys.

    Excludes the primary provider. Uses light-tier models to minimize cost.
    Only includes providers whose API Key is actually set in environment.
    """
    from .defaults import DEFAULT_MODELS as _DEFAULTS

    PROVIDER_FALLBACK_CANDIDATES = [
        {"provider": "openai", "model": "gpt-4o-mini", "api_key_env": "OPENAI_API_KEY"},
        {"provider": "claude", "model": "claude-haiku-4-5-20251001", "api_key_env": "ANTHROPIC_API_KEY"},
        {"provider": "qwen", "model": "qwen-plus", "api_key_env": "DASHSCOPE_API_KEY"},
        {"provider": "deepseek", "model": "deepseek-chat", "api_key_env": "DEEPSEEK_API_KEY"},  # light-tier
        {"provider": "glm", "model": "glm-4.5-flash", "api_key_env": "ZHIPUAI_API_KEY"},
        {"provider": "gemini", "model": "gemini-2.0-flash", "api_key_env": "GEMINI_API_KEY"},
    ]

    fallbacks = []
    for candidate in PROVIDER_FALLBACK_CANDIDATES:
        if candidate["provider"] == primary_provider.value:
            continue
        api_key = os.getenv(candidate["api_key_env"])
        if api_key:
            fallbacks.append(candidate)

    return fallbacks


# ============================================================
# 导出
# ============================================================

__all__ = [
    # ========== 注册中心 ==========
    # Provider 注册中心
    "LLMRegistry",
    # Model 注册中心
    "ModelRegistry",
    "ModelType",
    "AdapterType",
    "ModelConfig",
    "ModelCapabilities",
    # ========== 枚举 ==========
    "LLMProvider",
    "ToolType",
    "InvocationType",
    # ========== 数据类 ==========
    "LLMConfig",
    "LLMResponse",
    "Message",
    # ========== 基类 ==========
    "BaseLLMService",
    # ========== Token 计算 ==========
    "count_tokens",
    "count_message_tokens",
    "count_messages_tokens",
    "count_tools_tokens",
    "count_request_tokens",
    # ========== 实现类 ==========
    "ClaudeLLMService",
    "OpenAILLMService",
    "GeminiLLMService",
    "QwenLLMService",
    "QwenConfig",
    "DeepSeekLLMService",
    "GLMLLMService",
    "MiniMaxLLMService",
    # ========== 适配器 ==========
    "BaseAdaptor",
    "ClaudeAdaptor",
    "OpenAIAdaptor",
    "GeminiAdaptor",
    "DeepSeekAdaptor",
    "get_adaptor",
    # ========== 路由器（容灾）==========
    "ModelRouter",
    "RouteTarget",
    "RouterPolicy",
    # ========== 健康监控器 ==========
    "LLMHealthMonitor",
    "HealthPolicy",
    "get_llm_health_monitor",
    # ========== 工具 ==========
    "normalize_tool_calls",
    # ========== 工厂函数 ==========
    "create_llm_service",
    "create_claude_service",
    "create_qwen_service",
    "create_deepseek_service",
    "create_glm_service",
    "create_minimax_service",
]

"""
Models 路由层 - LLM 模型注册与查询

提供功能：
- 列出已注册模型
- 注册新模型
- 获取模型详情
- 删除已注册模型
- 列出已注册 Provider（含关联模型和 Key 状态）
- 验证 API Key 有效性
"""

import os
from typing import List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, status

from logger import get_logger
from core.llm.model_registry import (
    AdapterType,
    ModelCapabilities,
    ModelConfig,
    ModelPricing,
    ModelRegistry,
    ModelType,
)
from core.llm.registry import LLMRegistry
from models.llm import (
    ModelCapabilitiesResponse,
    ModelDetailResponse,
    ModelInfoResponse,
    ModelPricingResponse,
    ModelRegisterRequest,
    ProviderDetailResponse,
    ProviderInfoResponse,
    ProviderModelInfo,
    ProviderValidateKeyRequest,
    ProviderValidateKeyResponse,
)

logger = get_logger("router.models")

router = APIRouter(prefix="/api/v1/models", tags=["Models"])


# ============================================================
# 列表查询
# ============================================================


@router.get("", response_model=List[ModelInfoResponse])
async def list_models(
    type: Optional[str] = Query(None, description="模型类型过滤 (llm, vlm, embedding 等)"),
    provider: Optional[str] = Query(None, description="提供商过滤 (openai, claude, qwen 等)"),
):
    """
    获取可用模型列表

    支持按类型和提供商过滤。
    """
    model_type_enum = None
    if type:
        try:
            model_type_enum = ModelType(type)
        except ValueError:
            pass

    models = ModelRegistry.list_models(model_type=model_type_enum, provider=provider)

    return [
        ModelInfoResponse(
            model_name=m.model_name,
            display_name=m.display_name or m.model_name,
            provider=m.provider,
            model_type=m.model_type.value,
            description=m.description,
            capabilities=ModelCapabilitiesResponse(
                supports_tools=m.capabilities.supports_tools,
                supports_vision=m.capabilities.supports_vision,
                supports_thinking=m.capabilities.supports_thinking,
                supports_audio=m.capabilities.supports_audio,
                supports_streaming=m.capabilities.supports_streaming,
                max_tokens=m.capabilities.max_tokens,
                max_input_tokens=m.capabilities.max_input_tokens,
            ),
        )
        for m in models
    ]


# ============================================================
# Provider 查询（静态路由，必须在动态路由之前）
# ============================================================


@router.get(
    "/providers",
    response_model=List[ProviderInfoResponse],
    summary="列出所有 LLM Provider",
    description="获取所有已注册的 LLM Provider 列表",
)
async def list_providers():
    """
    列出所有已注册的 LLM Provider

    返回 Provider 的名称、默认模型、API Key 环境变量等信息
    """
    provider_names = LLMRegistry.list_providers()

    results = []
    for name in provider_names:
        try:
            info = LLMRegistry.get_provider_info(name)
            results.append(
                ProviderInfoResponse(
                    name=info["name"],
                    display_name=info.get("display_name"),
                    default_model=info["default_model"],
                    api_key_env=info["api_key_env"],
                    description=info.get("description"),
                    supported_features=info.get("supported_features", []),
                )
            )
        except Exception as e:
            logger.warning(f"获取 Provider '{name}' 信息失败: {e}")

    return results


# ============================================================
# Provider 支持列表（含关联模型和 Key 状态）
# ============================================================


# 所有支持的 Provider 元信息（静态定义，不依赖 LLMRegistry 注册）
SUPPORTED_PROVIDERS = {
    "claude": {
        "display_name": "Claude (Anthropic)",
        "icon": "🟠",
        "base_url": "https://api.anthropic.com",
        "api_key_env": "ANTHROPIC_API_KEY",
        "description": "Anthropic Claude 系列，支持 Extended Thinking 和 Prompt Caching",
        "validate_url": "/v1/messages",
        "validate_method": "anthropic",
    },
    "openai": {
        "display_name": "OpenAI",
        "icon": "🟢",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "description": "OpenAI GPT 系列，支持视觉和工具调用",
        "validate_url": "/models",
        "validate_method": "openai",
    },
    "qwen": {
        "display_name": "通义千问 (Qwen)",
        "icon": "🔵",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "description": "阿里云通义千问系列，支持 Thinking 和多模态",
        "validate_url": "/models",
        "validate_method": "openai",
    },
    "deepseek": {
        "display_name": "DeepSeek",
        "icon": "🐋",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "description": "DeepSeek 系列，高性价比推理模型",
        "validate_url": "/models",
        "validate_method": "openai",
    },
    "kimi": {
        "display_name": "Kimi (Moonshot)",
        "icon": "🌙",
        "base_url": "https://api.moonshot.cn/v1",
        "api_key_env": "MOONSHOT_API_KEY",
        "description": "Moonshot AI Kimi 系列，支持超长上下文",
        "validate_url": "/models",
        "validate_method": "openai",
    },
    "minimax": {
        "display_name": "MiniMax",
        "icon": "🔶",
        "base_url": "https://api.minimax.chat/v1",
        "api_key_env": "MINIMAX_API_KEY",
        "description": "MiniMax 系列，支持超长上下文和语音",
        "validate_url": "/models",
        "validate_method": "openai",
    },
}


@router.get(
    "/providers/supported",
    response_model=List[ProviderDetailResponse],
    summary="获取支持的 Provider 列表（含模型和 Key 状态）",
    description="返回所有支持的 LLM Provider，包含关联模型列表和 API Key 配置状态",
)
async def list_supported_providers():
    """
    获取支持的 Provider 列表

    返回每个 Provider 的：
    - 基本信息（名称、图标、描述）
    - 默认 Base URL
    - API Key 环境变量名和当前配置状态
    - 该 Provider 下的所有可用模型
    """
    results = []

    for provider_name, meta in SUPPORTED_PROVIDERS.items():
        # Get models for this provider
        provider_models = ModelRegistry.list_models(provider=provider_name)
        model_infos = [
            ProviderModelInfo(
                model_name=m.model_name,
                display_name=m.display_name or m.model_name,
                description=m.description,
                supports_thinking=m.capabilities.supports_thinking,
                supports_vision=m.capabilities.supports_vision,
                max_tokens=m.capabilities.max_tokens,
            )
            for m in provider_models
        ]

        # Check if API key is configured
        api_key_env = meta["api_key_env"]
        api_key_configured = bool(os.getenv(api_key_env))

        # Get default model
        default_model = provider_models[0].model_name if provider_models else ""

        results.append(
            ProviderDetailResponse(
                name=provider_name,
                display_name=meta["display_name"],
                icon=meta["icon"],
                base_url=meta["base_url"],
                api_key_env=api_key_env,
                api_key_configured=api_key_configured,
                default_model=default_model,
                description=meta["description"],
                models=model_infos,
            )
        )

    return results


# ============================================================
# API Key 验证
# ============================================================


async def _validate_openai_compatible(base_url: str, api_key: str) -> tuple[bool, str, list[str]]:
    """
    Validate API key for OpenAI-compatible providers.

    Calls GET /models with Bearer token to check validity.

    Returns:
        (valid, message, model_names)
    """
    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers)

    if resp.status_code == 200:
        data = resp.json()
        models = [m.get("id", "") for m in data.get("data", [])]
        return True, "API Key 验证通过", models
    elif resp.status_code == 401:
        return False, "API Key 无效或已过期", []
    elif resp.status_code == 403:
        return False, "API Key 权限不足", []
    else:
        return False, f"验证失败 (HTTP {resp.status_code})", []


async def _validate_anthropic(base_url: str, api_key: str) -> tuple[bool, str, list[str]]:
    """
    Validate API key for Anthropic Claude.

    Sends a minimal messages request; 401 = invalid, 400 = valid key (bad request body is expected).
    """
    url = f"{base_url.rstrip('/')}/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    # Send a minimal request body — expecting 400 (bad request) if key is valid
    body = {"model": "claude-haiku-3-5-20241022", "max_tokens": 1, "messages": []}

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, headers=headers, json=body)

    if resp.status_code == 401:
        return False, "API Key 无效或已过期", []
    elif resp.status_code == 403:
        return False, "API Key 权限不足", []
    elif resp.status_code in (200, 400):
        # 400 = key valid but request body invalid (expected)
        # 200 = somehow succeeded (unlikely with empty messages)
        return True, "API Key 验证通过", []
    else:
        return False, f"验证失败 (HTTP {resp.status_code})", []


@router.post(
    "/providers/validate-key",
    response_model=ProviderValidateKeyResponse,
    summary="验证 API Key",
    description="验证指定 Provider 的 API Key 是否有效",
)
async def validate_api_key(request: ProviderValidateKeyRequest):
    """
    验证 API Key

    对指定 Provider 发起轻量级 API 调用，检查 Key 是否有效。

    支持的 Provider: claude, openai, qwen, deepseek, kimi, minimax
    """
    provider = request.provider.lower()

    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNSUPPORTED_PROVIDER",
                "message": f"不支持的 Provider '{request.provider}'",
                "supported": list(SUPPORTED_PROVIDERS.keys()),
            },
        )

    meta = SUPPORTED_PROVIDERS[provider]
    base_url = request.base_url or meta["base_url"]
    validate_method = meta["validate_method"]

    try:
        if validate_method == "anthropic":
            valid, message, models = await _validate_anthropic(base_url, request.api_key)
        else:
            valid, message, models = await _validate_openai_compatible(base_url, request.api_key)

        return ProviderValidateKeyResponse(
            valid=valid,
            provider=provider,
            message=message,
            models=models,
        )

    except httpx.TimeoutException:
        return ProviderValidateKeyResponse(
            valid=False,
            provider=provider,
            message=f"连接超时，无法访问 {base_url}",
            models=[],
        )
    except httpx.ConnectError:
        return ProviderValidateKeyResponse(
            valid=False,
            provider=provider,
            message=f"无法连接到 {base_url}，请检查网络或 Base URL",
            models=[],
        )
    except Exception as e:
        logger.error(f"验证 API Key 失败: {e}", exc_info=True)
        return ProviderValidateKeyResponse(
            valid=False,
            provider=provider,
            message=f"验证过程异常: {str(e)}",
            models=[],
        )


# ============================================================
# 注册模型
# ============================================================


@router.post(
    "",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="注册新模型",
    description="向 ModelRegistry 注册一个新的 LLM 模型",
)
async def register_model(request: ModelRegisterRequest):
    """
    注册新模型

    将模型配置注册到全局 ModelRegistry，注册后可通过
    GET /api/v1/models 查询，也可在 Agent 配置中引用。

    ## 注意
    - 如果模型名已存在，会覆盖原有配置
    - Provider 必须是已注册的（claude, openai, qwen, gemini）
    - 注册后自动持久化到 YAML，服务重启后自动恢复
    """
    # 校验 model_type
    try:
        model_type = ModelType(request.model_type)
    except ValueError:
        valid_types = [t.value for t in ModelType]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_MODEL_TYPE",
                "message": f"无效的模型类型 '{request.model_type}'，"
                           f"可选值: {', '.join(valid_types)}",
            },
        )

    # 校验 adapter
    try:
        adapter = AdapterType(request.adapter)
    except ValueError:
        valid_adapters = [a.value for a in AdapterType]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_ADAPTER",
                "message": f"无效的适配器类型 '{request.adapter}'，"
                           f"可选值: {', '.join(valid_adapters)}",
            },
        )

    # 校验 provider 是否已注册
    if not LLMRegistry.is_registered(request.provider):
        available = LLMRegistry.list_providers()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNKNOWN_PROVIDER",
                "message": f"未知的 Provider '{request.provider}'，"
                           f"可用的 Provider: {', '.join(available)}",
            },
        )

    # 构建 ModelConfig
    is_overwrite = ModelRegistry.is_registered(request.model_name)

    model_config = ModelConfig(
        model_name=request.model_name,
        model_type=model_type,
        adapter=adapter,
        base_url=request.base_url,
        api_key_env=request.api_key_env,
        provider=request.provider,
        display_name=request.display_name,
        description=request.description,
        capabilities=ModelCapabilities(
            supports_tools=request.capabilities.supports_tools,
            supports_vision=request.capabilities.supports_vision,
            supports_thinking=request.capabilities.supports_thinking,
            supports_audio=request.capabilities.supports_audio,
            supports_streaming=request.capabilities.supports_streaming,
            max_tokens=request.capabilities.max_tokens,
            max_input_tokens=request.capabilities.max_input_tokens,
        ),
        pricing=ModelPricing(
            input_per_million=request.pricing.input_per_million,
            output_per_million=request.pricing.output_per_million,
            cache_read_per_million=request.pricing.cache_read_per_million,
            cache_write_per_million=request.pricing.cache_write_per_million,
        ),
        extra_config=request.extra_config,
        is_custom=True,
    )

    # 注册到内存
    ModelRegistry.register(model_config)

    # 持久化到 YAML
    await ModelRegistry.save_custom_models()

    action = "覆盖" if is_overwrite else "注册"
    logger.info(
        f"✅ {action}模型: {request.model_name} "
        f"(provider={request.provider}, type={model_type.value})"
    )

    return {
        "success": True,
        "model_name": request.model_name,
        "action": "overwritten" if is_overwrite else "created",
        "message": f"模型 '{request.model_name}' {action}成功（已持久化）",
    }


# ============================================================
# 单个模型查询和删除（动态路由，必须在静态路由之后）
# ============================================================


@router.get(
    "/{model_name}",
    response_model=ModelDetailResponse,
    summary="获取模型详情",
    description="获取指定模型的完整配置信息",
)
async def get_model_detail(model_name: str):
    """
    获取模型详情

    返回模型的完整信息，包括能力、定价、适配器类型等。
    """
    config = ModelRegistry.get(model_name)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "MODEL_NOT_FOUND",
                "message": f"模型 '{model_name}' 未注册",
                "available_models": ModelRegistry.list_model_names(),
            },
        )

    return ModelDetailResponse(
        model_name=config.model_name,
        display_name=config.display_name or config.model_name,
        provider=config.provider,
        model_type=config.model_type.value,
        adapter=config.adapter.value,
        base_url=config.base_url,
        api_key_env=config.api_key_env,
        description=config.description,
        capabilities=ModelCapabilitiesResponse(
            supports_tools=config.capabilities.supports_tools,
            supports_vision=config.capabilities.supports_vision,
            supports_thinking=config.capabilities.supports_thinking,
            supports_audio=config.capabilities.supports_audio,
            supports_streaming=config.capabilities.supports_streaming,
            max_tokens=config.capabilities.max_tokens,
            max_input_tokens=config.capabilities.max_input_tokens,
        ),
        pricing=ModelPricingResponse(
            input_per_million=config.pricing.input_per_million,
            output_per_million=config.pricing.output_per_million,
            cache_read_per_million=config.pricing.cache_read_per_million,
            cache_write_per_million=config.pricing.cache_write_per_million,
            is_free=config.pricing.is_free,
        ),
    )


@router.delete(
    "/{model_name}",
    response_model=dict,
    summary="删除已注册模型",
    description="从 ModelRegistry 中删除指定模型",
)
async def unregister_model(model_name: str):
    """
    删除已注册模型

    从全局 ModelRegistry 中移除指定模型。

    ## 注意
    - 预置模型可以删除，但重启后会恢复
    - 自定义模型删除后同步从持久化文件移除
    - 如果有 Agent 正在使用该模型，不会立即影响运行中的会话
    """
    model_name_lower = model_name.lower()

    if not ModelRegistry.is_registered(model_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "MODEL_NOT_FOUND",
                "message": f"模型 '{model_name}' 未注册",
            },
        )

    # 检查是否是自定义模型（需要同步删除持久化）
    config = ModelRegistry.get(model_name)
    was_custom = config.is_custom if config else False

    # 从 _models 字典中移除
    ModelRegistry._models.pop(model_name_lower, None)

    # 如果是自定义模型，同步更新持久化文件
    if was_custom:
        await ModelRegistry.save_custom_models()

    logger.info(f"🗑️ 模型已删除: {model_name} (custom={was_custom})")

    return {
        "success": True,
        "model_name": model_name,
        "message": f"模型 '{model_name}' 已从注册表中移除"
                   + ("（已同步删除持久化记录）" if was_custom else "（预置模型，重启后恢复）"),
    }

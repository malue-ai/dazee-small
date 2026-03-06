"""
Models 路由层 - LLM 模型管理

两层模型：
- 支持目录（Supported）：系统知道的所有模型（preset + custom）
- 激活列表（Activated）：用户配置了 API Key 的模型，实际可用

端点概览：
- GET  /supported           → 支持的模型目录
- POST /supported           → 向目录注册自定义模型
- GET  /                    → 用户已激活的模型列表
- POST /                    → 激活模型（填 API Key）
- GET  /{model_name}        → 模型详情（含激活状态）
- DELETE /{model_name}      → 停用模型
- GET  /providers           → 已注册 Provider 列表
- GET  /providers/supported → Provider 元信息（选择器用）
- POST /providers/validate-key → 验证 API Key
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
    ActivatedModelResponse,
    ModelActivateRequest,
    ModelCapabilitiesResponse,
    ModelDetailResponse,
    ModelPricingResponse,
    ModelRegisterRequest,
    ProviderActivateRequest,
    ProviderDetailResponse,
    ProviderInfoResponse,
    ProviderModelResponse,
    ProviderValidateKeyRequest,
    ProviderValidateKeyResponse,
    SupportedModelResponse,
    ValidatedModelInfo,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/models", tags=["Models"])


# ============================================================
# Helper: build response objects from ModelConfig
# ============================================================


def _caps_response(c: ModelCapabilities) -> ModelCapabilitiesResponse:
    return ModelCapabilitiesResponse(
        supports_tools=c.supports_tools,
        supports_vision=c.supports_vision,
        supports_thinking=c.supports_thinking,
        supports_audio=c.supports_audio,
        supports_streaming=c.supports_streaming,
        max_tokens=c.max_tokens,
        max_input_tokens=c.max_input_tokens,
    )


def _pricing_response(p: ModelPricing) -> ModelPricingResponse:
    return ModelPricingResponse(
        input_per_million=p.input_per_million,
        output_per_million=p.output_per_million,
        cache_read_per_million=p.cache_read_per_million,
        cache_write_per_million=p.cache_write_per_million,
        long_context_threshold=p.long_context_threshold,
        long_context_input_per_million=p.long_context_input_per_million,
        long_context_output_per_million=p.long_context_output_per_million,
        long_context_cache_read_per_million=p.long_context_cache_read_per_million,
        is_free=p.is_free,
    )


# ============================================================
# 支持目录（Supported Catalog）
# ============================================================


@router.get(
    "/supported",
    response_model=List[SupportedModelResponse],
    summary="获取支持的模型目录",
    description="列出系统支持的所有模型（preset + 自定义注册），含是否已激活标记",
)
async def list_supported_models(
    type: Optional[str] = Query(None, description="模型类型过滤"),
    provider: Optional[str] = Query(None, description="提供商过滤"),
):
    """
    支持的模型目录

    返回所有系统知道的模型，每个模型标注 is_activated（用户是否已配置 API Key）。
    前端用此接口渲染「可添加的模型列表」。
    """
    model_type_enum = None
    if type:
        try:
            model_type_enum = ModelType(type)
        except ValueError:
            pass

    models = ModelRegistry.list_models(model_type=model_type_enum, provider=provider)

    return [
        SupportedModelResponse(
            model_name=m.model_name,
            display_name=m.display_name or m.model_name,
            provider=m.provider,
            model_type=m.model_type.value,
            adapter=m.adapter.value,
            base_url=m.base_url,
            api_key_env=m.api_key_env,
            description=m.description,
            is_activated=ModelRegistry.is_activated(m.model_name),
            capabilities=_caps_response(m.capabilities),
            pricing=_pricing_response(m.pricing),
        )
        for m in models
    ]


@router.post(
    "/supported",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="向目录注册自定义模型",
    description="向支持目录添加一个新的模型定义（不含 API Key，仅扩展目录）",
)
async def register_supported_model(request: ModelRegisterRequest):
    """
    向支持目录注册自定义模型

    仅扩展目录，不激活。激活需调用 POST /api/v1/models。
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

    ModelRegistry.register(model_config)
    await ModelRegistry.save_custom_models()

    action = "覆盖" if is_overwrite else "注册"
    logger.info(
        f"✅ {action}目录模型: {request.model_name} "
        f"(provider={request.provider}, type={model_type.value})"
    )

    return {
        "success": True,
        "model_name": request.model_name,
        "action": "overwritten" if is_overwrite else "created",
        "message": f"模型 '{request.model_name}' 已添加到支持目录",
    }


# ============================================================
# 已激活模型（Activated Models）
# ============================================================


@router.get(
    "",
    response_model=List[ActivatedModelResponse],
    summary="获取已激活模型列表",
    description="列出用户已配置 API Key 的模型（实际可用的模型）",
)
async def list_activated_models(
    provider: Optional[str] = Query(None, description="提供商过滤"),
):
    """
    已激活模型列表

    返回用户实际配置了 API Key 的模型。
    前端用此接口渲染「我的模型」列表。
    """
    models = ModelRegistry.list_activated(provider=provider)

    results = []
    for m in models:
        entry = ModelRegistry.get_activated_entry(m.model_name)
        results.append(
            ActivatedModelResponse(
                model_name=m.model_name,
                display_name=m.display_name or m.model_name,
                provider=m.provider,
                model_type=m.model_type.value,
                adapter=m.adapter.value,
                base_url=entry.base_url or m.base_url if entry else m.base_url,
                api_key_configured=True,
                description=m.description,
                capabilities=_caps_response(m.capabilities),
                pricing=_pricing_response(m.pricing),
                activated_at=entry.activated_at if entry else None,
            )
        )
    return results


@router.post(
    "",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="激活模型",
    description="通过提供 API Key 激活一个模型，使其可用于 Agent",
)
async def activate_model(request: ModelActivateRequest):
    """
    激活模型

    提供 API Key 来激活一个模型。

    - 如果模型在支持目录中：只需 model_name + api_key（base_url 可选覆盖）
    - 如果模型不在目录中：还需提供 provider（自动注册到目录并激活）
    """
    # 检查模型是否在目录中
    in_catalog = ModelRegistry.is_registered(request.model_name)

    # 如果不在目录中，必须提供 provider
    if not in_catalog and not request.provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "PROVIDER_REQUIRED",
                "message": f"模型 '{request.model_name}' 不在支持目录中，"
                           f"必须提供 provider 字段",
            },
        )

    # 如果提供了 provider，校验
    if request.provider and not LLMRegistry.is_registered(request.provider):
        available = LLMRegistry.list_providers()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNKNOWN_PROVIDER",
                "message": f"未知的 Provider '{request.provider}'，"
                           f"可用的 Provider: {', '.join(available)}",
            },
        )

    was_activated = ModelRegistry.is_activated(request.model_name)

    try:
        # Build capabilities/pricing dicts for custom models
        caps_dict = None
        pricing_dict = None
        if not in_catalog:
            caps_dict = {
                "supports_tools": request.capabilities.supports_tools,
                "supports_vision": request.capabilities.supports_vision,
                "supports_thinking": request.capabilities.supports_thinking,
                "supports_audio": request.capabilities.supports_audio,
                "supports_streaming": request.capabilities.supports_streaming,
                "max_tokens": request.capabilities.max_tokens,
                "max_input_tokens": request.capabilities.max_input_tokens,
            }
            pricing_dict = {
                "input_per_million": request.pricing.input_per_million,
                "output_per_million": request.pricing.output_per_million,
                "cache_read_per_million": request.pricing.cache_read_per_million,
                "cache_write_per_million": request.pricing.cache_write_per_million,
            }

        ModelRegistry.activate_model(
            model_name=request.model_name,
            api_key=request.api_key,
            base_url=request.base_url,
            provider=request.provider,
            model_type=request.model_type,
            adapter=request.adapter,
            display_name=request.display_name,
            description=request.description,
            capabilities=caps_dict,
            pricing=pricing_dict,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "ACTIVATION_ERROR", "message": str(e)},
        )

    # 持久化
    await ModelRegistry.save_activated_models()
    # 如果是自定义模型，也持久化到目录
    if not in_catalog:
        await ModelRegistry.save_custom_models()

    action = "更新" if was_activated else "激活"
    logger.info(f"✅ 模型{action}: {request.model_name}")

    # 模型激活后热重载 Agent + 清除 ChatService 缓存
    # 确保后续请求使用新激活的模型（而非启动时缓存的旧模型）
    try:
        from services.agent_registry import get_agent_registry
        registry = get_agent_registry()
        reload_result = await registry.reload_agent()
        logger.info(f"🔄 模型 '{request.model_name}' 激活后热重载 Agent: {reload_result}")
    except Exception as e:
        logger.warning(f"⚠️ 模型激活后 Agent 热重载失败（不影响激活）: {e}")

    try:
        from services.chat_service import get_chat_service
        get_chat_service().invalidate_llm_caches()
    except Exception as e:
        logger.warning(f"⚠️ 清除 ChatService 缓存失败（不影响激活）: {e}")

    return {
        "success": True,
        "model_name": request.model_name,
        "action": "updated" if was_activated else "activated",
        "message": f"模型 '{request.model_name}' {action}成功",
    }


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
    """列出所有已注册的 LLM Provider"""
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
# Provider 元信息（选择器用，不含模型列表）
# ============================================================


SUPPORTED_PROVIDERS = {
    "claude": {
        "display_name": "Claude (Anthropic)",
        "icon": "🟠",
        "base_url": "https://api.anthropic.com",
        "api_key_env": "ANTHROPIC_API_KEY",
        "api_key_url": "https://console.anthropic.com/settings/keys",
        "description": "Anthropic Claude 系列，支持 Extended Thinking 和 Prompt Caching",
        "adapter": "claude",
        "validate_method": "anthropic",
    },
    "openai": {
        "display_name": "OpenAI",
        "icon": "🟢",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "api_key_url": "https://platform.openai.com/api-keys",
        "description": "OpenAI GPT 系列，支持视觉和工具调用",
        "adapter": "openai",
        "validate_method": "openai",
    },
    "qwen": {
        "display_name": "通义千问 (Qwen)",
        "icon": "🔵",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "api_key_url": "https://dashscope.console.aliyun.com/apiKey",
        "description": "阿里云通义千问系列，支持 Thinking 和多模态",
        "adapter": "openai",
        "validate_method": "openai",
    },
    "deepseek": {
        "display_name": "DeepSeek",
        "icon": "🐋",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "api_key_url": "https://platform.deepseek.com/api_keys",
        "description": "DeepSeek 系列，高性价比推理模型",
        "adapter": "openai",
        "validate_method": "openai",
    },
    "kimi": {
        "display_name": "Kimi (Moonshot)",
        "icon": "🌙",
        "base_url": "https://api.moonshot.cn/v1",
        "api_key_env": "MOONSHOT_API_KEY",
        "api_key_url": "https://platform.moonshot.cn/console/api-keys",
        "description": "Moonshot AI Kimi 系列，支持超长上下文",
        "adapter": "openai",
        "validate_method": "openai",
    },
    "minimax": {
        "display_name": "MiniMax",
        "icon": "🔶",
        "base_url": "https://api.minimaxi.com/anthropic",
        "api_key_env": "MINIMAX_API_KEY",
        "api_key_url": "https://platform.minimaxi.com/user-center/basic-information/interface-key",
        "description": "MiniMax M2.5/M2 系列，官方 Anthropic 兼容 / 第三方 OpenAI 兼容",
        "adapter": "claude",
        "validate_method": "auto",
    },
    "glm": {
        "display_name": "智谱 GLM (Zhipu AI)",
        "icon": "🔮",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_env": "ZHIPUAI_API_KEY",
        "api_key_url": "https://open.bigmodel.cn/usercenter/apikeys",
        "description": "智谱 GLM 系列，支持 Thinking、Function Calling 和视觉",
        "adapter": "openai",
        "validate_method": "openai",
    },
    "gemini": {
        "display_name": "Gemini (Google)",
        "icon": "💎",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "api_key_env": "GEMINI_API_KEY",
        "api_key_url": "https://aistudio.google.com/apikey",
        "description": "Google Gemini 系列，支持多模态和超长上下文",
        "adapter": "gemini",
        "validate_method": "openai",
    },
}


@router.get(
    "/providers/supported",
    response_model=List[ProviderDetailResponse],
    summary="获取支持的 Provider 元信息",
    description="返回所有支持的 Provider 元信息（名称、图标、默认 URL、适配器）。用于前端表单选择器。",
)
async def list_supported_providers():
    """
    获取支持的 Provider 元信息

    纯元信息，不含模型列表。前端用此渲染 Provider 选择下拉框。
    模型列表请使用 GET /api/v1/models/supported?provider=xxx 查询。
    """
    results = []

    for provider_name, meta in SUPPORTED_PROVIDERS.items():
        api_key_env = meta["api_key_env"]
        api_key_configured = bool(os.getenv(api_key_env))

        # Get models from catalog for this provider
        provider_models = ModelRegistry.list_models(provider=provider_name)
        default_model = provider_models[0].model_name if provider_models else ""

        # Build model summaries
        model_summaries = [
            ProviderModelResponse(
                model_name=m.model_name,
                display_name=m.display_name or m.model_name,
                description=m.description,
                supports_thinking=m.capabilities.supports_thinking,
                supports_vision=m.capabilities.supports_vision,
                max_tokens=m.capabilities.max_tokens,
            )
            for m in provider_models
        ]

        results.append(
            ProviderDetailResponse(
                name=provider_name,
                display_name=meta["display_name"],
                icon=meta["icon"],
                base_url=meta["base_url"],
                api_key_env=api_key_env,
                api_key_url=meta.get("api_key_url"),
                api_key_configured=api_key_configured,
                default_model=default_model,
                description=meta["description"],
                adapter=meta["adapter"],
                models=model_summaries,
            )
        )

    return results


# ============================================================
# API Key 验证
# ============================================================


async def _validate_openai_compatible(base_url: str, api_key: str) -> tuple[bool, str, list[str]]:
    """Validate API key for OpenAI-compatible providers."""
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


async def _validate_anthropic(
    base_url: str, api_key: str, provider: str = "claude",
) -> tuple[bool, str, list[str]]:
    """Validate API key for Anthropic-compatible providers (Claude, MiniMax, etc.)."""
    base = base_url.rstrip("/")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    # Pick a lightweight probe model based on provider
    catalog_models = ModelRegistry.list_models(provider=provider)
    probe_model = catalog_models[0].model_name if catalog_models else "claude-3-5-haiku-20241022"

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Step 1: validate key via messages endpoint (empty body → expect 400)
        url = f"{base}/v1/messages"
        body = {"model": probe_model, "max_tokens": 1, "messages": []}
        resp = await client.post(url, headers=headers, json=body)

        if resp.status_code not in (200, 400):
            try:
                err_body = resp.json()
                err_msg = err_body.get("error", {}).get("message", resp.text[:200])
            except Exception:
                err_msg = resp.text[:200]
            logger.warning(
                f"Anthropic 验证失败: HTTP {resp.status_code}, body={err_msg}"
            )

            if resp.status_code == 401:
                return False, "API Key 无效或已过期", []
            elif resp.status_code == 403:
                return False, f"API Key 权限不足 ({err_msg})", []
            else:
                return False, f"验证失败 (HTTP {resp.status_code}: {err_msg})", []

        # Step 2: fetch available models so the frontend can proceed
        models: list[str] = []
        try:
            models_resp = await client.get(
                f"{base}/v1/models", headers=headers,
            )
            if models_resp.status_code == 200:
                data = models_resp.json().get("data", [])
                models = [m.get("id", "") for m in data if m.get("id")]
        except Exception:
            catalog = ModelRegistry.list_models(provider=provider)
            models = [m.model_name for m in catalog]

        if not models:
            catalog = ModelRegistry.list_models(provider=provider)
            models = [m.model_name for m in catalog]

        return True, "API Key 验证通过", models


def _build_model_details(
    api_model_names: list[str], provider: str
) -> list[ValidatedModelInfo]:
    """Match API-returned model names against catalog, return enriched details.

    For models in our catalog: return full capabilities from preset data.
    For models NOT in catalog: return basic info with defaults.
    """
    catalog_models = {
        m.model_name.lower(): m
        for m in ModelRegistry.list_models(provider=provider)
    }

    details: list[ValidatedModelInfo] = []
    seen: set[str] = set()

    for name in api_model_names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        catalog_entry = catalog_models.get(key)
        if catalog_entry:
            details.append(
                ValidatedModelInfo(
                    model_name=catalog_entry.model_name,
                    display_name=catalog_entry.display_name or catalog_entry.model_name,
                    provider=provider,
                    model_type=catalog_entry.model_type.value,
                    context_window=catalog_entry.capabilities.max_input_tokens,
                    max_output_tokens=catalog_entry.capabilities.max_tokens,
                    supports_tools=catalog_entry.capabilities.supports_tools,
                    supports_vision=catalog_entry.capabilities.supports_vision,
                    supports_thinking=catalog_entry.capabilities.supports_thinking,
                    in_catalog=True,
                )
            )
        else:
            details.append(
                ValidatedModelInfo(  # type: ignore[call-arg]
                    model_name=name,
                    display_name=name,
                    provider=provider,
                    model_type="llm",
                    in_catalog=False,
                )
            )

    # Catalog models first, then non-catalog; within each group, keep original order
    details.sort(key=lambda d: (not d.in_catalog, 0))
    return details


@router.post(
    "/providers/validate-key",
    response_model=ProviderValidateKeyResponse,
    summary="验证 API Key",
    description="验证指定 Provider 的 API Key 是否有效",
)
async def validate_api_key(request: ProviderValidateKeyRequest):
    """验证 API Key"""
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

    # "auto": 用户改了 base_url → openai 验证，否则 → anthropic 验证
    if validate_method == "auto":
        default_url = meta["base_url"].rstrip("/")
        custom_url = (request.base_url or "").rstrip("/")
        if custom_url and custom_url != default_url:
            validate_method = "openai"
        else:
            validate_method = "anthropic"

    try:
        if validate_method == "anthropic":
            valid, message, models = await _validate_anthropic(base_url, request.api_key, provider)
        else:
            valid, message, models = await _validate_openai_compatible(base_url, request.api_key)

        logger.info(
            f"API Key 验证结果: provider={provider}, valid={valid}, "
            f"message={message}, models_count={len(models)}"
        )

        # Match validated model names against catalog for rich details
        model_details = _build_model_details(models, provider) if valid else []

        return ProviderValidateKeyResponse(
            valid=valid,
            provider=provider,
            message=message,
            models=models,
            model_details=model_details,
        )

    except httpx.TimeoutException:
        return ProviderValidateKeyResponse(
            valid=False, provider=provider,
            message=f"连接超时，无法访问 {base_url}", models=[],
        )
    except httpx.ConnectError:
        return ProviderValidateKeyResponse(
            valid=False, provider=provider,
            message=f"无法连接到 {base_url}，请检查网络或 Base URL", models=[],
        )
    except Exception as e:
        logger.error(f"验证 API Key 失败: {e}", exc_info=True)
        return ProviderValidateKeyResponse(
            valid=False, provider=provider,
            message=f"验证过程异常: {str(e)}", models=[],
        )


# ============================================================
# Provider 批量激活
# ============================================================


@router.post(
    "/providers/activate",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="按 Provider 批量激活模型",
    description="提供 API Key 后，一次性激活该 Provider 目录中的所有模型",
)
async def activate_provider(request: ProviderActivateRequest):
    """
    按 Provider 批量激活模型

    验证 Key 通过后调用此接口，将该 Provider 的所有目录模型一次性激活。
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

    base_url = request.base_url or SUPPORTED_PROVIDERS[provider]["base_url"]

    activated = ModelRegistry.activate_provider_models(
        provider=provider,
        api_key=request.api_key,
        base_url=base_url,
    )

    # Persist to YAML
    await ModelRegistry.save_activated_models()

    # 模型激活后热重载 Agent，使 xiaodazi 等 agent:{} 实例
    # 能通过 ModelRegistry.list_activated() fallback 获取到新激活的模型
    #
    # 注意：首次启动时如果没有 API Key，preload_instance 会失败，
    # 导致 registry.is_loaded=False。所以这里不检查 is_loaded，
    # 无论之前是否加载成功都尝试重新加载。
    try:
        from services.agent_registry import get_agent_registry
        registry = get_agent_registry()
        reload_result = await registry.reload_agent()
        logger.info(
            f"🔄 Provider '{provider}' 激活后热重载 Agent: {reload_result}"
        )
    except Exception as e:
        logger.warning(f"⚠️ Provider 激活后 Agent 热重载失败（不影响激活）: {e}")

    # 清除 ChatService 缓存（intent_llm / routers 等）
    # 确保后续请求使用新激活的模型
    try:
        from services.chat_service import get_chat_service
        get_chat_service().invalidate_llm_caches()
    except Exception as e:
        logger.warning(f"⚠️ 清除 ChatService 缓存失败（不影响激活）: {e}")

    return {
        "success": True,
        "provider": provider,
        "activated_count": len(activated),
        "models": [e.model_name for e in activated],
        "message": f"已激活 {len(activated)} 个 {provider} 模型",
    }


# ============================================================
# 单个模型查询和停用（动态路由，必须在静态路由之后）
# ============================================================


@router.get(
    "/{model_name}",
    response_model=ModelDetailResponse,
    summary="获取模型详情",
    description="获取指定模型的完整配置（含激活状态）",
)
async def get_model_detail(model_name: str):
    """
    获取模型详情

    返回模型的完整信息，包括能力、定价、适配器类型和是否已激活。
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
        is_activated=ModelRegistry.is_activated(config.model_name),
        capabilities=_caps_response(config.capabilities),
        pricing=_pricing_response(config.pricing),
    )


@router.delete(
    "/{model_name}",
    response_model=dict,
    summary="停用模型",
    description="停用指定模型（移除 API Key 配置）",
)
async def deactivate_model(model_name: str):
    """
    停用模型

    从激活列表中移除，清除 API Key 环境变量。
    模型仍保留在支持目录中，可随时重新激活。
    """
    if not ModelRegistry.is_activated(model_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "MODEL_NOT_ACTIVATED",
                "message": f"模型 '{model_name}' 未激活",
            },
        )

    ModelRegistry.deactivate_model(model_name)
    await ModelRegistry.save_activated_models()

    logger.info(f"🗑️ 模型已停用: {model_name}")

    # 清除 ChatService 缓存（停用后框架 LLM 需切换到其他可用模型）
    try:
        from services.chat_service import get_chat_service
        get_chat_service().invalidate_llm_caches()
    except Exception as e:
        logger.warning(f"⚠️ 清除 ChatService 缓存失败（不影响停用）: {e}")

    return {
        "success": True,
        "model_name": model_name,
        "message": f"模型 '{model_name}' 已停用（API Key 已清除，可随时重新激活）",
    }

"""
LLM 配置模型

用于 LLM 超参数配置、模型目录和模型激活
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """LLM 超参数配置"""
    temperature: Optional[float] = Field(None, description="温度参数 (0-1)")
    max_tokens: Optional[int] = Field(None, description="最大输出 token 数")
    enable_thinking: Optional[bool] = Field(None, description="是否启用 Extended Thinking")
    thinking_budget: Optional[int] = Field(None, description="Thinking token 预算")
    thinking_mode: Optional[str] = Field(None, description="Thinking 模式 (simulated/native)")
    enable_caching: Optional[bool] = Field(None, description="是否启用 Prompt Caching")
    top_p: Optional[float] = Field(None, description="Top-P 核采样参数")


# ============================================================
# 共用子模型
# ============================================================


class ModelCapabilitiesRequest(BaseModel):
    """模型能力配置"""
    supports_tools: bool = Field(True, description="是否支持工具调用")
    supports_vision: bool = Field(False, description="是否支持图像输入")
    supports_thinking: bool = Field(False, description="是否支持深度思考")
    supports_audio: bool = Field(False, description="是否支持音频输入")
    supports_streaming: bool = Field(True, description="是否支持流式输出")
    max_tokens: int = Field(4096, description="最大输出 token 数")
    max_input_tokens: Optional[int] = Field(None, description="最大输入 token 数")


class ModelPricingRequest(BaseModel):
    """模型定价信息（美元 / 百万 token）"""
    input_per_million: Optional[float] = Field(None, description="输入 $/M tokens")
    output_per_million: Optional[float] = Field(None, description="输出 $/M tokens")
    cache_read_per_million: Optional[float] = Field(None, description="缓存读取 $/M tokens")
    cache_write_per_million: Optional[float] = Field(None, description="缓存写入 $/M tokens")


class ModelCapabilitiesResponse(BaseModel):
    """模型能力响应"""
    supports_tools: bool
    supports_vision: bool
    supports_thinking: bool
    supports_audio: bool
    supports_streaming: bool
    max_tokens: int
    max_input_tokens: Optional[int] = None


class ModelPricingResponse(BaseModel):
    """模型定价响应"""
    input_per_million: Optional[float] = None
    output_per_million: Optional[float] = None
    cache_read_per_million: Optional[float] = None
    cache_write_per_million: Optional[float] = None
    is_free: bool = False


# ============================================================
# 支持的模型目录（Catalog）
# ============================================================


class ModelRegisterRequest(BaseModel):
    """向支持目录注册自定义模型（扩展目录，不含 API Key）"""
    model_name: str = Field(..., description="模型名称（如 gpt-4o、qwen3-max）")
    model_type: str = Field("llm", description="模型类型：llm, vlm, embedding, rerank, tts, stt, audio")
    adapter: str = Field("openai", description="适配器类型：openai, claude, gemini")
    base_url: str = Field(..., description="API 端点 URL")
    api_key_env: str = Field(..., description="API Key 环境变量名")
    provider: str = Field(..., description="Provider 名称（如 openai, claude, qwen）")
    display_name: Optional[str] = Field(None, description="显示名称")
    description: Optional[str] = Field(None, description="模型描述")
    capabilities: ModelCapabilitiesRequest = Field(
        default_factory=ModelCapabilitiesRequest, description="模型能力配置"
    )
    pricing: ModelPricingRequest = Field(
        default_factory=ModelPricingRequest, description="定价信息"
    )
    extra_config: Dict[str, Any] = Field(default_factory=dict, description="额外配置")


class SupportedModelResponse(BaseModel):
    """支持的模型目录项（含是否已激活）"""
    model_name: str = Field(..., description="模型名称")
    display_name: str = Field(..., description="显示名称")
    provider: str = Field(..., description="Provider")
    model_type: str = Field(..., description="模型类型")
    adapter: str = Field(..., description="适配器类型")
    base_url: str = Field(..., description="默认 API 端点")
    api_key_env: str = Field(..., description="API Key 环境变量名")
    description: Optional[str] = Field(None, description="模型描述")
    is_activated: bool = Field(False, description="用户是否已激活此模型")
    capabilities: ModelCapabilitiesResponse = Field(..., description="模型能力")
    pricing: ModelPricingResponse = Field(..., description="定价信息")


# ============================================================
# 激活的模型（用户配置了 API Key 的）
# ============================================================


class ModelActivateRequest(BaseModel):
    """激活模型请求"""
    model_name: str = Field(..., description="模型名称（支持目录中的模型，或自定义模型名）")
    api_key: str = Field(..., description="API Key（实际的密钥值）")
    base_url: Optional[str] = Field(None, description="自定义 API 端点（不填则用目录默认值）")

    # 以下字段仅用于目录中不存在的自定义模型
    model_type: str = Field("llm", description="模型类型（自定义模型必填）")
    adapter: str = Field("openai", description="适配器类型（自定义模型必填）")
    provider: Optional[str] = Field(None, description="Provider 名称（自定义模型必填）")
    display_name: Optional[str] = Field(None, description="显示名称")
    description: Optional[str] = Field(None, description="模型描述")
    capabilities: ModelCapabilitiesRequest = Field(
        default_factory=ModelCapabilitiesRequest, description="模型能力（自定义模型可配置）"
    )
    pricing: ModelPricingRequest = Field(
        default_factory=ModelPricingRequest, description="定价信息"
    )


class ActivatedModelResponse(BaseModel):
    """已激活模型响应"""
    model_name: str = Field(..., description="模型名称")
    display_name: str = Field(..., description="显示名称")
    provider: str = Field(..., description="Provider")
    model_type: str = Field(..., description="模型类型")
    adapter: str = Field(..., description="适配器类型")
    base_url: str = Field(..., description="API 端点（用户可能覆盖了默认值）")
    api_key_configured: bool = Field(True, description="API Key 已配置")
    description: Optional[str] = Field(None, description="模型描述")
    capabilities: ModelCapabilitiesResponse = Field(..., description="模型能力")
    pricing: ModelPricingResponse = Field(..., description="定价信息")
    activated_at: Optional[str] = Field(None, description="激活时间（ISO 格式）")


class ModelDetailResponse(BaseModel):
    """模型详情响应（支持目录 + 激活状态）"""
    model_name: str
    display_name: str
    provider: str
    model_type: str
    adapter: str
    base_url: str
    api_key_env: str
    description: Optional[str] = None
    is_activated: bool = False
    capabilities: ModelCapabilitiesResponse
    pricing: ModelPricingResponse


# ============================================================
# Provider 相关模型
# ============================================================


class ProviderInfoResponse(BaseModel):
    """Provider 信息响应"""
    name: str
    display_name: Optional[str] = None
    default_model: str
    api_key_env: str
    description: Optional[str] = None
    supported_features: List[str] = Field(default_factory=list)


class ProviderModelResponse(BaseModel):
    """Provider 下的模型摘要"""
    model_name: str = Field(..., description="模型标识符")
    display_name: str = Field(..., description="显示名称")
    description: Optional[str] = Field(None, description="模型描述")
    supports_thinking: bool = Field(False, description="是否支持深度思考")
    supports_vision: bool = Field(False, description="是否支持视觉")
    max_tokens: int = Field(0, description="最大输出 token 数")


class ProviderDetailResponse(BaseModel):
    """Provider 详情响应（含关联模型列表）"""
    name: str = Field(..., description="Provider 标识符")
    display_name: str = Field(..., description="显示名称")
    icon: str = Field("🤖", description="图标（emoji 或 URL）")
    base_url: str = Field(..., description="默认 API Base URL")
    api_key_env: str = Field(..., description="API Key 环境变量名")
    api_key_url: Optional[str] = Field(None, description="获取 API Key 的平台链接")
    api_key_configured: bool = Field(False, description="API Key 是否已配置")
    default_model: str = Field(..., description="默认模型")
    description: Optional[str] = Field(None, description="Provider 描述")
    adapter: str = Field("openai", description="该 Provider 使用的适配器类型")
    models: List[ProviderModelResponse] = Field(default_factory=list, description="该 Provider 支持的模型列表")


class ProviderActivateRequest(BaseModel):
    """按 Provider 批量激活模型请求"""
    provider: str = Field(..., description="Provider 名称（claude, openai, qwen, deepseek, kimi, minimax）")
    api_key: str = Field(..., description="API Key")
    base_url: Optional[str] = Field(None, description="自定义 Base URL（可选，不填用默认）")


class ProviderValidateKeyRequest(BaseModel):
    """验证 API Key 请求"""
    provider: str = Field(..., description="Provider 名称（claude, openai, qwen, deepseek, kimi, minimax）")
    api_key: str = Field(..., description="待验证的 API Key")
    base_url: Optional[str] = Field(None, description="自定义 Base URL（可选，不填用默认）")


class ValidatedModelInfo(BaseModel):
    """验证通过后的模型详情（匹配目录）"""
    model_name: str = Field(..., description="模型标识符")
    display_name: str = Field(..., description="显示名称")
    provider: str = Field(..., description="Provider 名称")
    model_type: str = Field("llm", description="模型类型")
    context_window: Optional[int] = Field(None, description="上下文窗口大小（max_input_tokens）")
    max_output_tokens: int = Field(4096, description="最大输出 token 数")
    supports_tools: bool = Field(True, description="是否支持工具调用")
    supports_vision: bool = Field(False, description="是否支持视觉")
    supports_thinking: bool = Field(False, description="是否支持深度思考")
    in_catalog: bool = Field(False, description="是否在预设目录中")


class ProviderValidateKeyResponse(BaseModel):
    """验证 API Key 响应"""
    valid: bool = Field(..., description="Key 是否有效")
    provider: str = Field(..., description="Provider 名称")
    message: str = Field(..., description="验证结果描述")
    models: List[str] = Field(default_factory=list, description="该 Key 可用的模型列表（模型名字符串）")
    model_details: List[ValidatedModelInfo] = Field(
        default_factory=list,
        description="匹配目录后的模型详情（含能力、上下文窗口）",
    )

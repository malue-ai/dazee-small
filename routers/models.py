from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from core.llm.model_registry import ModelRegistry, ModelType

router = APIRouter(prefix="/api/v1/models", tags=["Models"])


class ModelCapabilitiesResponse(BaseModel):
    supports_tools: bool
    supports_vision: bool
    supports_thinking: bool
    supports_audio: bool
    supports_streaming: bool
    max_tokens: int
    max_input_tokens: Optional[int] = None


class ModelInfoResponse(BaseModel):
    model_name: str
    display_name: str
    provider: str
    model_type: str
    description: Optional[str] = None
    capabilities: ModelCapabilitiesResponse


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
            pass  # 忽略无效类型，或者可以抛出 400 错误

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

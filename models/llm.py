"""
LLM 配置模型

用于 LLM 超参数配置
"""

from typing import Optional
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

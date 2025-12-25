from typing import Optional, List, Dict, Any, Generic, TypeVar
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

# 定义泛型类型变量
T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """标准 API 响应格式"""
    code: int = Field(..., description="状态码")
    message: str = Field(..., description="消息")
    data: Optional[T] = Field(None, description="数据")


"""
Mem0 数据模型

用于用户记忆管理的请求/响应模型
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


# ==================== 请求模型 ====================

class MemorySearchRequest(BaseModel):
    """记忆搜索请求"""
    user_id: str = Field(..., description="用户 ID")
    query: str = Field(..., description="搜索查询")
    limit: int = Field(10, ge=1, le=50, description="返回数量限制")


class MemoryAddRequest(BaseModel):
    """添加记忆请求"""
    user_id: str = Field(..., description="用户 ID")
    messages: List[Dict[str, str]] = Field(..., description="消息列表")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class BatchUpdateRequest(BaseModel):
    """批量更新请求"""
    since_hours: int = Field(24, ge=1, le=168, description="处理过去多少小时的会话")
    max_concurrent: int = Field(5, ge=1, le=20, description="最大并发数")


# ==================== 响应模型 ====================

class MemoryItem(BaseModel):
    """记忆项"""
    id: str = Field(..., description="记忆 ID")
    memory: str = Field(..., description="记忆内容")
    score: Optional[float] = Field(None, description="相关性分数")
    user_id: Optional[str] = Field(None, description="用户 ID")
    created_at: Optional[str] = Field(None, description="创建时间")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class UpdateResult(BaseModel):
    """单用户更新结果"""
    user_id: str = Field(..., description="用户 ID")
    success: bool = Field(..., description="是否成功")
    memories_added: int = Field(0, description="新增记忆数")
    error: Optional[str] = Field(None, description="错误信息")
    duration_ms: int = Field(0, description="耗时（毫秒）")


class BatchUpdateResult(BaseModel):
    """批量更新结果"""
    total_users: int = Field(..., description="总用户数")
    successful: int = Field(..., description="成功数")
    failed: int = Field(..., description="失败数")
    duration_seconds: float = Field(..., description="总耗时（秒）")
    results: List[UpdateResult] = Field(default_factory=list, description="详细结果")


class HealthCheckResult(BaseModel):
    """健康检查结果"""
    service: str = Field("mem0", description="服务名称")
    status: str = Field(..., description="服务状态")
    pool: Optional[Dict[str, Any]] = Field(None, description="Pool 状态")
    error: Optional[str] = Field(None, description="错误信息")


class MemoryAddResult(BaseModel):
    """添加记忆结果"""
    memories_added: int = Field(..., description="新增记忆数")
    results: List[Dict[str, Any]] = Field(default_factory=list, description="详细结果")


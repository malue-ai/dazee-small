"""
Mem0 路由层 - 用户记忆管理接口

职责：
- 用户记忆搜索
- 批量更新触发
- 健康检查

设计原则：
- 只处理 HTTP 协议
- 🆕 复用 BackgroundTaskService（不重复造轮子）
- 支持定时任务调用
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks
from logger import get_logger

from models.api import APIResponse
from utils.background_tasks import (
    get_background_task_service,
    Mem0UpdateResult,
    Mem0BatchUpdateResult
)

logger = get_logger("mem0_router")

# 创建路由器
router = APIRouter(
    prefix="/api/v1/mem0",
    tags=["mem0"],
    responses={404: {"description": "Not found"}},
)


# ==================== 请求/响应模型 ====================

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


class MemoryItem(BaseModel):
    """记忆项"""
    id: str
    memory: str
    score: Optional[float] = None
    user_id: Optional[str] = None
    created_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class UpdateResultResponse(BaseModel):
    """更新结果响应"""
    user_id: str
    success: bool
    memories_added: int = 0
    error: Optional[str] = None
    duration_ms: int = 0


class BatchUpdateResultResponse(BaseModel):
    """批量更新结果响应"""
    total_users: int
    successful: int
    failed: int
    duration_seconds: float
    results: List[UpdateResultResponse] = []


class HealthCheckResponse(BaseModel):
    """健康检查响应"""
    service: str
    status: str
    pool: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ==================== 记忆搜索 ====================

@router.post("/search", response_model=APIResponse[List[MemoryItem]])
async def search_memories(request: MemorySearchRequest):
    """
    搜索用户相关记忆
    
    ## 参数
    - **user_id**: 用户 ID（必填）
    - **query**: 搜索查询（必填）
    - **limit**: 返回数量限制（可选，默认 10）
    
    ## 返回
    ```json
    {
      "code": 200,
      "message": "success",
      "data": [
        {
          "id": "mem_uuid",
          "memory": "用户偏好使用 Python 开发",
          "score": 0.92,
          "user_id": "user_123",
          "created_at": "2024-01-01T10:00:00"
        }
      ]
    }
    ```
    """
    try:
        from core.memory.mem0 import get_mem0_pool
        
        pool = get_mem0_pool()
        memories = pool.search(
            user_id=request.user_id,
            query=request.query,
            limit=request.limit
        )
        
        # 转换为响应模型
        items = [
            MemoryItem(
                id=m.get("id", ""),
                memory=m.get("memory", ""),
                score=m.get("score"),
                user_id=m.get("user_id"),
                created_at=m.get("created_at"),
                metadata=m.get("metadata")
            )
            for m in memories
        ]
        
        logger.info(f"🔍 记忆搜索: user_id={request.user_id}, 结果数={len(items)}")
        
        return APIResponse(
            code=200,
            message="success",
            data=items
        )
        
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="mem0 模块未安装"
        )
    except Exception as e:
        logger.error(f"记忆搜索失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/user/{user_id}", response_model=APIResponse[List[MemoryItem]])
async def get_user_memories(
    user_id: str,
    limit: int = Query(50, ge=1, le=200, description="返回数量限制")
):
    """
    获取用户所有记忆
    
    ## 参数
    - **user_id**: 用户 ID（路径参数）
    - **limit**: 返回数量限制（可选，默认 50）
    
    ## 返回
    用户的所有记忆列表
    """
    try:
        from core.memory.mem0 import get_mem0_pool
        
        pool = get_mem0_pool()
        memories = pool.get_all(user_id=user_id, limit=limit)
        
        items = [
            MemoryItem(
                id=m.get("id", ""),
                memory=m.get("memory", ""),
                score=m.get("score"),
                user_id=m.get("user_id"),
                created_at=m.get("created_at"),
                metadata=m.get("metadata")
            )
            for m in memories
        ]
        
        logger.info(f"📋 获取用户记忆: user_id={user_id}, 数量={len(items)}")
        
        return APIResponse(
            code=200,
            message="success",
            data=items
        )
        
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="mem0 模块未安装"
        )
    except Exception as e:
        logger.error(f"获取用户记忆失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ==================== 添加记忆 ====================

@router.post("/add", response_model=APIResponse[Dict[str, Any]])
async def add_memories(request: MemoryAddRequest):
    """
    添加用户记忆
    
    ## 参数
    - **user_id**: 用户 ID（必填）
    - **messages**: 消息列表（必填）
    - **metadata**: 元数据（可选）
    
    ## 消息格式
    ```json
    {
      "messages": [
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "..."}
      ]
    }
    ```
    
    ## 返回
    添加结果，包含新增记忆数量
    """
    try:
        from core.memory.mem0 import get_mem0_pool
        
        pool = get_mem0_pool()
        result = pool.add(
            user_id=request.user_id,
            messages=request.messages,
            metadata=request.metadata
        )
        
        memories_added = len(result.get("results", []))
        logger.info(f"➕ 添加记忆: user_id={request.user_id}, 新增={memories_added}")
        
        return APIResponse(
            code=200,
            message="success",
            data={
                "memories_added": memories_added,
                "results": result.get("results", [])
            }
        )
        
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="mem0 模块未安装"
        )
    except Exception as e:
        logger.error(f"添加记忆失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ==================== 批量更新 ====================

@router.post("/batch-update", response_model=APIResponse[BatchUpdateResultResponse])
async def batch_update_memories(
    request: BatchUpdateRequest,
    background_tasks: BackgroundTasks
):
    """
    触发批量更新用户记忆
    
    ## 参数
    - **since_hours**: 处理过去多少小时的会话（默认 24）
    - **max_concurrent**: 最大并发数（默认 5）
    
    ## 说明
    - 此接口会从数据库获取指定时间范围内的所有用户会话
    - 通过 BackgroundTaskService 执行（复用统一的后台任务机制）
    - 适合定时任务调用（如凌晨批量更新）
    
    ## 返回
    批量更新结果统计
    """
    try:
        service = get_background_task_service()
        
        logger.info(
            f"🚀 触发批量更新: since={request.since_hours}h, max_concurrent={request.max_concurrent}"
        )
        
        # 🆕 复用 BackgroundTaskService
        result = await service.batch_update_all_memories(
            since_hours=request.since_hours,
            max_concurrent=request.max_concurrent
        )
        
        # 转换为响应模型
        response = BatchUpdateResultResponse(
            total_users=result.total_users,
            successful=result.successful,
            failed=result.failed,
            duration_seconds=result.duration_seconds,
            results=[
                UpdateResultResponse(
                    user_id=r.user_id,
                    success=r.success,
                    memories_added=r.memories_added,
                    error=r.error,
                    duration_ms=r.duration_ms
                )
                for r in result.results
            ]
        )
        
        return APIResponse(
            code=200,
            message="success",
            data=response
        )
        
    except Exception as e:
        logger.error(f"批量更新失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/user/{user_id}/update", response_model=APIResponse[UpdateResultResponse])
async def update_user_memories(
    user_id: str,
    since_hours: int = Query(24, ge=1, le=168, description="处理过去多少小时的会话")
):
    """
    更新单个用户的记忆
    
    ## 参数
    - **user_id**: 用户 ID（路径参数）
    - **since_hours**: 处理过去多少小时的会话（默认 24）
    
    ## 说明
    从数据库获取该用户在指定时间范围内的会话，提取记忆并更新
    """
    try:
        service = get_background_task_service()
        
        # 🆕 复用 BackgroundTaskService
        result = await service.update_user_memories(
            user_id=user_id,
            since_hours=since_hours
        )
        
        return APIResponse(
            code=200,
            message="success" if result.success else "failed",
            data=UpdateResultResponse(
                user_id=result.user_id,
                success=result.success,
                memories_added=result.memories_added,
                error=result.error,
                duration_ms=result.duration_ms
            )
        )
        
    except Exception as e:
        logger.error(f"更新用户记忆失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ==================== 删除记忆 ====================

@router.delete("/memory/{memory_id}", response_model=APIResponse[Dict[str, bool]])
async def delete_memory(memory_id: str):
    """
    删除单条记忆
    
    ## 参数
    - **memory_id**: 记忆 ID（路径参数）
    """
    try:
        from core.memory.mem0 import get_mem0_pool
        
        pool = get_mem0_pool()
        success = pool.delete(memory_id=memory_id)
        
        logger.info(f"🗑️ 删除记忆: memory_id={memory_id}, success={success}")
        
        return APIResponse(
            code=200,
            message="success" if success else "failed",
            data={"deleted": success}
        )
        
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="mem0 模块未安装"
        )
    except Exception as e:
        logger.error(f"删除记忆失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/user/{user_id}", response_model=APIResponse[Dict[str, bool]])
async def reset_user_memories(user_id: str):
    """
    重置用户所有记忆
    
    ## 参数
    - **user_id**: 用户 ID（路径参数）
    
    ## ⚠️ 警告
    此操作不可逆，将删除用户的所有记忆
    """
    try:
        from core.memory.mem0 import get_mem0_pool
        
        pool = get_mem0_pool()
        success = pool.reset_user(user_id=user_id)
        
        logger.warning(f"🗑️ 重置用户记忆: user_id={user_id}, success={success}")
        
        return APIResponse(
            code=200,
            message="success" if success else "failed",
            data={"reset": success}
        )
        
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="mem0 模块未安装"
        )
    except Exception as e:
        logger.error(f"重置用户记忆失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ==================== 健康检查 ====================

@router.get("/health", response_model=APIResponse[HealthCheckResponse])
async def health_check():
    """
    Mem0 服务健康检查
    
    ## 返回
    服务健康状态，包含：
    - 服务状态
    - Mem0 Pool 状态
    - 向量存储连接状态
    """
    try:
        service = get_mem0_update_service()
        result = await service.health_check()
        
        return APIResponse(
            code=200,
            message="success",
            data=HealthCheckResponse(**result)
        )
        
    except Exception as e:
        return APIResponse(
            code=503,
            message="unhealthy",
            data=HealthCheckResponse(
                service="mem0",
                status="unhealthy",
                error=str(e)
            )
        )


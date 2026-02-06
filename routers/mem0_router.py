"""
Mem0 路由层 - 用户记忆管理接口

职责：
- HTTP 协议处理
- 请求/响应转换
- 错误码映射

设计原则：
- 只处理 HTTP 协议，业务逻辑委托给 Service
- 统一的错误处理
"""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query, status

from logger import get_logger
from models.api import APIResponse
from models.mem0 import (
    BatchUpdateRequest,
    BatchUpdateResult,
    HealthCheckResult,
    MemoryAddRequest,
    MemoryAddResult,
    MemoryItem,
    MemorySearchRequest,
    UpdateResult,
)
from services.mem0_service import (
    Mem0NotInstalledError,
    Mem0ServiceError,
    get_mem0_service,
)

logger = get_logger("mem0_router")

# 创建路由器
router = APIRouter(
    prefix="/api/v1/mem0",
    tags=["mem0"],
    responses={404: {"description": "Not found"}},
)


# ==================== 错误处理 ====================


def handle_mem0_error(e: Exception):
    """统一的 Mem0 错误处理"""
    if isinstance(e, Mem0NotInstalledError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="mem0 模块未安装"
        )
    elif isinstance(e, Mem0ServiceError):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    else:
        logger.error(f"未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


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
        service = get_mem0_service()
        items = await service.search(
            user_id=request.user_id, query=request.query, limit=request.limit
        )

        return APIResponse(code=200, message="success", data=items)

    except Exception as e:
        handle_mem0_error(e)


@router.get("/user/{user_id}", response_model=APIResponse[List[MemoryItem]])
async def get_user_memories(
    user_id: str, limit: int = Query(50, ge=1, le=200, description="返回数量限制")
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
        service = get_mem0_service()
        items = await service.get_all(user_id=user_id, limit=limit)

        return APIResponse(code=200, message="success", data=items)

    except Exception as e:
        handle_mem0_error(e)


# ==================== 添加记忆 ====================


@router.post("/add", response_model=APIResponse[MemoryAddResult])
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
        service = get_mem0_service()
        result = await service.add(
            user_id=request.user_id, messages=request.messages, metadata=request.metadata
        )

        return APIResponse(code=200, message="success", data=result)

    except Exception as e:
        handle_mem0_error(e)


# ==================== 批量更新 ====================


@router.post("/batch-update", response_model=APIResponse[BatchUpdateResult])
async def batch_update_memories(request: BatchUpdateRequest):
    """
    触发批量更新用户记忆

    ## 参数
    - **since_hours**: 处理过去多少小时的会话（默认 24）
    - **max_concurrent**: 最大并发数（默认 5）

    ## 说明
    - 此接口会从数据库获取指定时间范围内的所有用户会话
    - 通过 BackgroundTaskService 执行
    - 适合定时任务调用（如凌晨批量更新）

    ## 返回
    批量更新结果统计
    """
    try:
        service = get_mem0_service()
        result = await service.batch_update(
            since_hours=request.since_hours, max_concurrent=request.max_concurrent
        )

        return APIResponse(code=200, message="success", data=result)

    except Exception as e:
        handle_mem0_error(e)


@router.post("/user/{user_id}/update", response_model=APIResponse[UpdateResult])
async def update_user_memories(
    user_id: str, since_hours: int = Query(24, ge=1, le=168, description="处理过去多少小时的会话")
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
        service = get_mem0_service()
        result = await service.update_user(user_id=user_id, since_hours=since_hours)

        return APIResponse(code=200, message="success" if result.success else "failed", data=result)

    except Exception as e:
        handle_mem0_error(e)


# ==================== 删除记忆 ====================


@router.delete("/memory/{memory_id}", response_model=APIResponse[Dict[str, bool]])
async def delete_memory(memory_id: str):
    """
    删除单条记忆

    ## 参数
    - **memory_id**: 记忆 ID（路径参数）
    """
    try:
        service = get_mem0_service()
        success = await service.delete(memory_id=memory_id)

        return APIResponse(
            code=200, message="success" if success else "failed", data={"deleted": success}
        )

    except Exception as e:
        handle_mem0_error(e)


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
        service = get_mem0_service()
        success = await service.reset_user(user_id=user_id)

        return APIResponse(
            code=200, message="success" if success else "failed", data={"reset": success}
        )

    except Exception as e:
        handle_mem0_error(e)


# ==================== 健康检查 ====================


@router.get("/health", response_model=APIResponse[HealthCheckResult])
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
        service = get_mem0_service()
        result = await service.health_check()

        return APIResponse(
            code=200 if result.status == "healthy" else 503,
            message="success" if result.status == "healthy" else "unhealthy",
            data=result,
        )

    except Exception as e:
        return APIResponse(
            code=503,
            message="unhealthy",
            data=HealthCheckResult(service="mem0", status="unhealthy", error=str(e)),
        )

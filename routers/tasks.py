"""
任务路由层 - Tasks Router

提供后台任务管理 API：
- 获取任务列表
- 手动触发任务
- 触发批量任务（定时任务场景）
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

from logger import get_logger
from models.api import APIResponse
from services.task_service import get_task_service, TaskStatus
from utils.background_tasks import get_scheduler

logger = get_logger("tasks_router")

router = APIRouter(
    prefix="/api/v1/tasks",
    tags=["tasks"],
    responses={404: {"description": "Not found"}},
)

task_service = get_task_service()


# ==================== 请求/响应模型 ====================

class RunTaskRequest(BaseModel):
    """手动触发任务请求"""
    user_id: Optional[str] = Field(None, description="用户 ID（部分任务需要）")
    conversation_id: Optional[str] = Field(None, description="对话 ID（部分任务需要）")
    session_id: Optional[str] = Field(None, description="Session ID（用于 SSE 推送进度）")
    params: Optional[Dict[str, Any]] = Field(None, description="额外参数")
    wait: bool = Field(False, description="是否等待任务完成")


class RunBatchTaskRequest(BaseModel):
    """触发批量任务请求"""
    since_hours: int = Field(24, ge=1, le=168, description="处理过去多少小时的数据")
    max_concurrent: int = Field(5, ge=1, le=20, description="最大并发数")
    params: Optional[Dict[str, Any]] = Field(None, description="额外参数")


class TaskInfoResponse(BaseModel):
    """任务信息响应"""
    name: str
    description: str
    supports_scheduled: bool
    schedule_config: Optional[Dict[str, Any]] = None


class TaskRunResponse(BaseModel):
    """任务执行响应"""
    task_name: str
    status: str
    trigger_type: str
    started_at: str
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


# ==================== API 端点 ====================

@router.get("", response_model=APIResponse)
async def list_tasks(
    scheduled_only: bool = Query(False, description="只返回支持定时执行的任务")
):
    """
    获取已注册的后台任务列表
    
    返回所有可用的后台任务及其配置信息
    """
    try:
        tasks = task_service.list_tasks(include_scheduled_only=scheduled_only)
        
        return APIResponse(
            success=True,
            data={
                "tasks": tasks,
                "total": len(tasks),
            },
            message=f"获取到 {len(tasks)} 个任务"
        )
    
    except Exception as e:
        logger.error(f"❌ 获取任务列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")


@router.get("/{task_name}", response_model=APIResponse)
async def get_task(task_name: str):
    """
    获取单个任务详情
    
    Args:
        task_name: 任务名称
    """
    try:
        task = task_service.get_task(task_name)
        
        if not task:
            raise HTTPException(
                status_code=404,
                detail=f"任务不存在: {task_name}"
            )
        
        return APIResponse(
            success=True,
            data=task,
            message=f"获取任务详情: {task_name}"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取任务详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取任务详情失败: {str(e)}")


@router.post("/{task_name}/run", response_model=APIResponse)
async def run_task(task_name: str, request: RunTaskRequest):
    """
    手动触发任务
    
    可用于：
    - 测试任务
    - 手动补偿执行
    - API 集成
    
    Args:
        task_name: 任务名称
        request: 任务参数
    """
    try:
        result = await task_service.run_task(
            task_name=task_name,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            session_id=request.session_id,
            extra_params=request.params,
            wait=request.wait
        )
        
        if result.status == TaskStatus.FAILED:
            return APIResponse(
                success=False,
                data=result.to_dict(),
                message=result.error or "任务执行失败"
            )
        
        return APIResponse(
            success=True,
            data=result.to_dict(),
            message=f"任务 {task_name} 已{'完成' if result.status == TaskStatus.COMPLETED else '启动'}"
        )
    
    except Exception as e:
        logger.error(f"❌ 手动触发任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"触发任务失败: {str(e)}")


@router.post("/{task_name}/batch", response_model=APIResponse)
async def run_batch_task(task_name: str, request: RunBatchTaskRequest):
    """
    触发批量任务（用于定时任务场景）
    
    如：批量更新所有用户的 Mem0 记忆
    
    Args:
        task_name: 任务名称
        request: 批量任务参数
    """
    try:
        # 检查任务是否支持批量执行
        task = task_service.get_task(task_name)
        if not task or not task.get("supports_scheduled"):
            raise HTTPException(
                status_code=400,
                detail=f"任务 {task_name} 不支持批量执行"
            )
        
        params = request.params or {}
        params["since_hours"] = request.since_hours
        params["max_concurrent"] = request.max_concurrent
        
        result = await task_service.run_batch_task(
            task_name=task_name,
            params=params
        )
        
        if result.status == TaskStatus.FAILED:
            return APIResponse(
                success=False,
                data=result.to_dict(),
                message=result.error or "批量任务执行失败"
            )
        
        return APIResponse(
            success=True,
            data=result.to_dict(),
            message=f"批量任务 {task_name} 执行完成"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 批量任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"批量任务失败: {str(e)}")


# ==================== 定时任务配置 API ====================

@router.get("/scheduled/config", response_model=APIResponse)
async def get_scheduled_config():
    """
    获取所有支持定时执行的任务及其配置
    
    用于：
    - 前端展示定时任务配置
    - 外部调度器（如 Celery Beat）读取配置
    """
    try:
        tasks = task_service.list_tasks(include_scheduled_only=True)
        
        return APIResponse(
            success=True,
            data={
                "tasks": tasks,
                "total": len(tasks),
                "hint": "可通过 POST /api/v1/tasks/{task_name}/batch 触发定时任务"
            },
            message=f"获取到 {len(tasks)} 个可定时执行的任务"
        )
    
    except Exception as e:
        logger.error(f"❌ 获取定时任务配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")


@router.get("/scheduled/status", response_model=APIResponse)
async def get_scheduler_status():
    """
    获取定时任务调度器状态
    
    返回：
    - 调度器是否在运行
    - 当前注册的定时任务列表
    - 各任务的下次执行时间
    """
    try:
        scheduler = get_scheduler()
        
        return APIResponse(
            success=True,
            data={
                "running": scheduler.is_running(),
                "jobs": scheduler.get_jobs(),
                "total_jobs": len(scheduler.get_jobs()),
            },
            message="调度器运行中" if scheduler.is_running() else "调度器未运行"
        )
    
    except Exception as e:
        logger.error(f"❌ 获取调度器状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")


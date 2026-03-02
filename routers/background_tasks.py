"""
Background Tasks REST API

后台任务查询和管理接口，供前端 BackgroundTasksView 调用。
任务本身由 PipelineTool 通过 BackgroundTaskManager 提交。
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/background-tasks", tags=["Background Tasks"])


# ============================================================
# Response Models
# ============================================================


class BackgroundTaskResponse(BaseModel):
    task_id: str
    name: str
    description: str = ""
    status: str
    progress: float = 0.0
    progress_message: str = ""
    result_preview: Optional[str] = None
    error: Optional[str] = None
    elapsed_ms: int = 0
    created_at: str


class BackgroundTaskListResponse(BaseModel):
    tasks: list[BackgroundTaskResponse]
    total: int


# ============================================================
# Singleton accessor
# ============================================================

_manager = None


def get_manager():
    """获取全局 BackgroundTaskManager 单例"""
    global _manager
    if _manager is None:
        from core.orchestration.background import create_background_task_manager

        async def on_notify(task):
            """完成后发送系统通知"""
            try:
                from tools.nodes_tool import NodesTool
                nodes = NodesTool()
                title = "后台任务完成" if task.status.value == "completed" else "后台任务失败"
                message = f"{task.name}\n耗时 {task.elapsed_ms // 1000}s"
                if task.error:
                    message += f"\n错误: {task.error[:100]}"
                await nodes.execute({
                    "action": "notify",
                    "title": title,
                    "message": message,
                })
            except Exception as e:
                logger.debug(f"发送通知失败: {e}")

        _manager = create_background_task_manager(on_notify=on_notify)
    return _manager


def set_manager(manager):
    """外部注入 BackgroundTaskManager（如 ChatService 初始化时）"""
    global _manager
    _manager = manager


# ============================================================
# Endpoints
# ============================================================


@router.get(
    "",
    response_model=BackgroundTaskListResponse,
    summary="List background tasks",
)
async def list_tasks(
    user_id: str = Query(default="local", description="User ID"),
    task_status: Optional[str] = Query(default=None, alias="status"),
):
    manager = get_manager()
    from core.orchestration.background import TaskStatus

    status_enum = None
    if task_status:
        try:
            status_enum = TaskStatus(task_status)
        except ValueError:
            pass

    tasks = manager.get_user_tasks(user_id, status=status_enum)
    return BackgroundTaskListResponse(
        tasks=[BackgroundTaskResponse(**t.to_dict()) for t in tasks],
        total=len(tasks),
    )


@router.get(
    "/{task_id}",
    response_model=BackgroundTaskResponse,
    summary="Get task detail",
)
async def get_task(task_id: str):
    manager = get_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return BackgroundTaskResponse(**task.to_dict())


@router.post(
    "/{task_id}/cancel",
    summary="Cancel a running task",
)
async def cancel_task(task_id: str):
    manager = get_manager()
    success = await manager.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="任务无法取消（可能已完成或不存在）")
    return {"success": True, "message": f"任务 {task_id} 已取消"}


@router.delete(
    "/{task_id}",
    summary="Remove task from list",
)
async def remove_task(task_id: str):
    manager = get_manager()
    task = manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    if task.status.value in ("queued", "running"):
        raise HTTPException(status_code=400, detail="运行中的任务请先取消")
    manager._tasks.pop(task_id, None)
    return {"success": True, "message": f"任务 {task_id} 已删除"}


@router.post(
    "/cleanup",
    summary="Cleanup completed tasks older than max_age_seconds",
)
async def cleanup_tasks(max_age_seconds: int = Query(default=3600)):
    manager = get_manager()
    removed = manager.cleanup_completed(max_age_seconds)
    return {"success": True, "removed": removed}

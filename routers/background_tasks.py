"""
Background Tasks REST API

后台任务查询、管理和提交接口，供前端 BackgroundTasksView 调用。
支持两种提交来源：
1. PipelineTool 通过 BackgroundTaskManager 内部提交
2. 前端通过 POST /submit 主动提交（用户发起的后台任务）
"""

from typing import Any, Dict, List, Optional

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


class SubmitBackgroundTaskRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=5000, description="任务内容")
    user_id: str = Field(default="local")
    files: Optional[List[Dict[str, Any]]] = None


class SubmitBackgroundTaskResponse(BaseModel):
    task_id: str
    conversation_id: str


# ============================================================
# Singleton accessor
# ============================================================

def get_manager():
    """获取全局 BackgroundTaskManager 单例（委托 core 层统一管理）"""
    from core.orchestration.background import get_global_bg_manager, init_global_bg_manager

    mgr = get_global_bg_manager()
    if mgr is not None:
        return mgr

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

    return init_global_bg_manager(on_notify=on_notify)


# ============================================================
# Endpoints
# ============================================================


@router.post(
    "/submit",
    response_model=SubmitBackgroundTaskResponse,
    summary="Submit a new background task from frontend",
)
async def submit_background_task(req: SubmitBackgroundTaskRequest):
    """
    前端主动提交后台任务。

    创建新对话 → 包装为 BackgroundTask → 后台执行 Agent chat。
    立即返回 task_id 和 conversation_id，前端可通过列表接口轮询进度。
    """
    from services.chat_service import get_chat_service
    from services.conversation_service import get_conversation_service

    manager = get_manager()
    conv_service = get_conversation_service()
    chat_svc = get_chat_service()

    conv = await conv_service.create_conversation(
        user_id=req.user_id, title=req.prompt[:30]
    )
    conversation_id = conv.id

    task_name = req.prompt[:50]
    if len(req.prompt) > 50:
        task_name += "..."

    async def _run_chat(
        task: "BackgroundTask", mgr: "BackgroundTaskManager"
    ) -> Any:
        await mgr.update_progress(task.task_id, 0.05, "Agent 开始处理...")
        result = await chat_svc.chat(
            message=req.prompt,
            user_id=req.user_id,
            conversation_id=conversation_id,
            stream=False,
            files=req.files,
        )
        await mgr.update_progress(task.task_id, 1.0, "完成")
        return result

    bg_task = manager.submit(
        name=task_name,
        fn=_run_chat,
        user_id=req.user_id,
        conversation_id=conversation_id,
        description=req.prompt,
    )

    logger.info(
        f"前端提交后台任务: task_id={bg_task.task_id}, "
        f"conversation_id={conversation_id}"
    )

    return SubmitBackgroundTaskResponse(
        task_id=bg_task.task_id,
        conversation_id=conversation_id,
    )


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

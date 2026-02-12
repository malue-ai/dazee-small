"""
Scheduled Tasks REST API

Provides endpoints for managing user scheduled tasks:
- List / detail
- Pause / resume
- Cancel / delete
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from logger import get_logger
from models.scheduled_task import (
    ScheduledTaskListResponse,
    ScheduledTaskResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/scheduled-tasks", tags=["Scheduled Tasks"])


# ============================================================
# List & Detail
# ============================================================


@router.get(
    "",
    response_model=ScheduledTaskListResponse,
    summary="List scheduled tasks",
    description="Get paginated list of user's scheduled tasks, optionally filtered by status.",
)
async def list_tasks(
    user_id: str = Query(default="local", description="User ID"),
    task_status: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by status: active / paused / completed / cancelled",
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=100, description="Page size"),
):
    """List user's scheduled tasks with optional status filtering."""
    from services.scheduled_task_service import list_tasks as svc_list

    task_dicts, total = await svc_list(
        user_id=user_id, status=task_status, page=page, page_size=page_size
    )

    return ScheduledTaskListResponse(
        tasks=[ScheduledTaskResponse(**t) for t in task_dicts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{task_id}",
    response_model=ScheduledTaskResponse,
    summary="Get task detail",
    description="Get a single scheduled task by ID.",
)
async def get_task(
    task_id: str,
    user_id: str = Query(default="local", description="User ID"),
):
    """Get scheduled task detail."""
    from services.scheduled_task_service import get_task as svc_get

    result = await svc_get(task_id=task_id, user_id=user_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TASK_NOT_FOUND", "message": f"Task not found: {task_id}"},
        )

    return ScheduledTaskResponse(**result)


# ============================================================
# State transitions
# ============================================================


@router.post(
    "/{task_id}/pause",
    response_model=ScheduledTaskResponse,
    summary="Pause a task",
    description="Pause an active task. Removes it from the scheduler.",
)
async def pause_task(
    task_id: str,
    user_id: str = Query(default="local", description="User ID"),
):
    """Pause an active scheduled task."""
    from services.scheduled_task_service import pause_task as svc_pause

    result = await svc_pause(task_id=task_id, user_id=user_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "PAUSE_FAILED",
                "message": f"Cannot pause task: {task_id} (not found, not owned, or not active)",
            },
        )

    return ScheduledTaskResponse(**result)


@router.post(
    "/{task_id}/resume",
    response_model=ScheduledTaskResponse,
    summary="Resume a task",
    description="Resume a paused task. Re-registers it in the scheduler.",
)
async def resume_task(
    task_id: str,
    user_id: str = Query(default="local", description="User ID"),
):
    """Resume a paused scheduled task."""
    from services.scheduled_task_service import resume_task as svc_resume

    result = await svc_resume(task_id=task_id, user_id=user_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "RESUME_FAILED",
                "message": f"Cannot resume task: {task_id} (not found, not owned, or not paused)",
            },
        )

    return ScheduledTaskResponse(**result)


@router.post(
    "/{task_id}/cancel",
    response_model=dict,
    summary="Cancel a task",
    description="Cancel a task (soft delete). Sets status to cancelled.",
)
async def cancel_task(
    task_id: str,
    user_id: str = Query(default="local", description="User ID"),
):
    """Cancel a scheduled task (soft delete)."""
    from services.scheduled_task_service import cancel_task as svc_cancel

    success = await svc_cancel(task_id=task_id, user_id=user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "CANCEL_FAILED",
                "message": f"Cannot cancel task: {task_id} (not found or not owned)",
            },
        )

    return {"success": True, "message": f"Task cancelled: {task_id}"}


# ============================================================
# Delete
# ============================================================


@router.delete(
    "/{task_id}",
    response_model=dict,
    summary="Delete a task",
    description="Permanently delete a task from the database.",
)
async def delete_task(
    task_id: str,
    user_id: str = Query(default="local", description="User ID"),
):
    """Delete a scheduled task (hard delete)."""
    from services.scheduled_task_service import delete_task as svc_delete

    success = await svc_delete(task_id=task_id, user_id=user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "DELETE_FAILED",
                "message": f"Cannot delete task: {task_id} (not found or not owned)",
            },
        )

    return {"success": True, "message": f"Task deleted: {task_id}"}

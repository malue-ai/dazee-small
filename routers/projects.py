"""
Projects REST API.

Endpoints:
  GET    /api/v1/projects/templates       — list available templates
  GET    /api/v1/projects                  — list user projects
  POST   /api/v1/projects                  — create project from template
  GET    /api/v1/projects/{project_id}     — get single project
  PATCH  /api/v1/projects/{project_id}     — update project
  DELETE /api/v1/projects/{project_id}     — delete project
  POST   /api/v1/projects/{project_id}/activate — switch active project
  GET    /api/v1/projects/active           — get current active project
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from core.project.manager import ProjectManager
from core.project.models import (
    ProjectCreate,
    ProjectInfo,
    ProjectUpdate,
    TemplateInfo,
)
from logger import get_logger

logger = get_logger("router.projects")

router = APIRouter(prefix="/api/v1/projects", tags=["项目管理"])

# Singleton — injected at startup via configure()
_manager: Optional[ProjectManager] = None

DEFAULT_USER_ID = "default-user"


def configure(manager: ProjectManager) -> None:
    """Called at app startup to inject the ProjectManager singleton."""
    global _manager
    _manager = manager
    logger.info("Projects router configured")


def _mgr() -> ProjectManager:
    if _manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="项目管理未启用",
        )
    return _manager


# ================================================================
# Templates
# ================================================================


@router.get("/templates", response_model=List[TemplateInfo])
async def list_templates() -> List[TemplateInfo]:
    """List all available project templates."""
    return _mgr().get_templates()


# ================================================================
# CRUD
# ================================================================


@router.get("", response_model=List[ProjectInfo])
async def list_projects(
    user_id: str = Query(default=DEFAULT_USER_ID),
) -> List[ProjectInfo]:
    """List all projects for the user."""
    return await _mgr().list_projects(user_id)


@router.post("", response_model=ProjectInfo, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user_id: str = Query(default=DEFAULT_USER_ID),
) -> ProjectInfo:
    """Create a new project from a template."""
    return await _mgr().create_project(user_id, body)


@router.get("/active", response_model=Optional[ProjectInfo])
async def get_active_project(
    user_id: str = Query(default=DEFAULT_USER_ID),
) -> Optional[ProjectInfo]:
    """Get the currently active project."""
    return await _mgr().get_active_project(user_id)


@router.get("/{project_id}", response_model=ProjectInfo)
async def get_project(
    project_id: str,
    user_id: str = Query(default=DEFAULT_USER_ID),
) -> ProjectInfo:
    """Get a single project by ID."""
    info = await _mgr().get_project(user_id, project_id)
    if not info:
        raise HTTPException(status_code=404, detail="项目不存在")
    return info


@router.patch("/{project_id}", response_model=ProjectInfo)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    user_id: str = Query(default=DEFAULT_USER_ID),
) -> ProjectInfo:
    """Update project fields."""
    info = await _mgr().update_project(user_id, project_id, body)
    if not info:
        raise HTTPException(status_code=404, detail="项目不存在")
    return info


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    user_id: str = Query(default=DEFAULT_USER_ID),
) -> None:
    """Delete a project and its isolated directory."""
    ok = await _mgr().delete_project(user_id, project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="项目不存在")


@router.post("/{project_id}/activate", response_model=ProjectInfo)
async def activate_project(
    project_id: str,
    user_id: str = Query(default=DEFAULT_USER_ID),
) -> ProjectInfo:
    """Switch the active project."""
    info = await _mgr().switch_project(user_id, project_id)
    if not info:
        raise HTTPException(status_code=404, detail="项目不存在")
    return info

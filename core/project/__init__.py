"""
项目管理模块

项目隔离：独立 context、knowledge、playbook、skills_config。
"""

from core.project.manager import ProjectManager
from core.project.models import (
    LocalProject,
    ProjectCreate,
    ProjectInfo,
    ProjectTemplate,
    ProjectUpdate,
    TemplateInfo,
)

__all__ = [
    "ProjectManager",
    "ProjectTemplate",
    "ProjectInfo",
    "ProjectCreate",
    "ProjectUpdate",
    "TemplateInfo",
    "LocalProject",
]

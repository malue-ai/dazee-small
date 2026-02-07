"""
ProjectManager — project CRUD, template instantiation, directory isolation.

Design:
- Templates are immutable, loaded from config.yaml project_templates
- Projects are persisted in SQLite (LocalProject)
- Each project has an isolated directory: {projects_root}/{project_id}/
  containing knowledge/, playbook/, state/
- Only ONE project can be active per user at a time
"""

import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from logger import get_logger

from .models import (
    LocalProject,
    ProjectCreate,
    ProjectInfo,
    ProjectTemplate,
    ProjectUpdate,
    TemplateInfo,
)

logger = get_logger(__name__)

# Default built-in templates (used when config.yaml has none)
_BUILTIN_TEMPLATES: List[ProjectTemplate] = [
    ProjectTemplate(
        id="writing",
        name="写稿搭子",
        icon="✍️",
        description="公众号、视频脚本、文案创作",
        default_skills=["summarize", "writing-assistant", "canvas"],
        memory_focus="style",
        ui_template="content-creation",
    ),
    ProjectTemplate(
        id="data",
        name="表格搭子",
        icon="📊",
        description="Excel 处理、数据分析、图表生成",
        default_skills=["excel-analyzer", "chart-generator", "nano-pdf"],
        memory_focus="format",
        ui_template="data-dashboard",
    ),
    ProjectTemplate(
        id="research",
        name="研究搭子",
        icon="📚",
        description="论文、文献管理、学术写作",
        default_skills=["pdf-reader", "citation-extractor", "academic-writer"],
        memory_focus="domain",
        ui_template="research-workspace",
    ),
    ProjectTemplate(
        id="office",
        name="办公搭子",
        icon="💼",
        description="PPT、邮件、会议纪要",
        default_skills=["ppt-generator", "email-drafter", "meeting-notes"],
        memory_focus="workflow",
        ui_template="office-assistant",
    ),
    ProjectTemplate(
        id="custom",
        name="自定义项目",
        icon="⚙️",
        description="包含所有可用技能，按需裁剪",
        default_skills=["__all__"],
        memory_focus="general",
        ui_template="default",
    ),
]

# Sentinel: when default_skills contains this, expand to all available skills at creation time
_ALL_SKILLS_SENTINEL = "__all__"

# Subdirectories created inside each project
_PROJECT_SUBDIRS = ["knowledge", "playbook", "state", "state/snapshots"]


class ProjectManager:
    """
    Project lifecycle management.

    Usage:
        mgr = ProjectManager(projects_root=Path("~/.xiaodazi/projects"))
        mgr.load_templates(config_templates_list)

        project = await mgr.create_project("default-user", ProjectCreate(name="My Project", template_id="writing"))
        projects = await mgr.list_projects("default-user")
        await mgr.switch_project("default-user", project.id)
        await mgr.delete_project("default-user", project.id)
    """

    def __init__(
        self,
        projects_root: Optional[Path] = None,
        templates: Optional[List[ProjectTemplate]] = None,
        all_skill_names: Optional[List[str]] = None,
    ) -> None:
        if projects_root is None:
            from utils.app_paths import get_user_data_dir
            projects_root = get_user_data_dir() / "projects"
        self._root = Path(projects_root).expanduser()
        self._root.mkdir(parents=True, exist_ok=True)

        # Template registry (id → template)
        self._templates: Dict[str, ProjectTemplate] = {}
        self.load_templates(templates or _BUILTIN_TEMPLATES)

        # Full skill list for __all__ expansion (set externally after SkillsLoader.load())
        self._all_skill_names: List[str] = list(all_skill_names or [])

        logger.info(
            f"ProjectManager 初始化: root={self._root}, "
            f"templates={list(self._templates.keys())}"
        )

    # ================================================================
    # Templates
    # ================================================================

    def load_templates(self, templates: List[ProjectTemplate]) -> None:
        """Replace template registry with given templates."""
        self._templates = {t.id: t for t in templates}
        # Ensure "custom" always exists
        if "custom" not in self._templates:
            custom = [t for t in _BUILTIN_TEMPLATES if t.id == "custom"]
            if custom:
                self._templates["custom"] = custom[0]

    def load_templates_from_config(self, raw_list: List[Dict[str, Any]]) -> None:
        """Parse config.yaml project_templates list and load."""
        templates = [ProjectTemplate.from_dict(d) for d in raw_list if isinstance(d, dict)]
        if templates:
            self.load_templates(templates)
            logger.info(f"从配置加载 {len(templates)} 个项目模板")

    def set_all_skill_names(self, names: List[str]) -> None:
        """Set the full skill list for __all__ expansion (called after SkillsLoader.load())."""
        self._all_skill_names = list(names)
        logger.debug(f"设置全量 Skill 列表: {len(names)} 个")

    def get_templates(self) -> List[TemplateInfo]:
        """Return all available templates as API models."""
        result: List[TemplateInfo] = []
        for t in self._templates.values():
            # __all__ → show the expanded list to frontend
            skills = list(t.default_skills)
            if _ALL_SKILLS_SENTINEL in skills and self._all_skill_names:
                skills = list(self._all_skill_names)
            result.append(
                TemplateInfo(
                    id=t.id,
                    name=t.name,
                    icon=t.icon,
                    description=t.description,
                    default_skills=skills,
                    memory_focus=t.memory_focus,
                    ui_template=t.ui_template,
                )
            )
        return result

    def get_template(self, template_id: str) -> Optional[ProjectTemplate]:
        """Get a single template by ID."""
        return self._templates.get(template_id)

    # ================================================================
    # CRUD
    # ================================================================

    async def create_project(
        self, user_id: str, req: ProjectCreate
    ) -> ProjectInfo:
        """
        Create a new project from a template.

        1. Resolve template (fallback to custom)
        2. Create LocalProject row
        3. Create project directory with subdirs
        """
        template = self._templates.get(req.template_id) or self._templates.get("custom")
        if template is None:
            template = _BUILTIN_TEMPLATES[-1]  # custom fallback

        project_id = uuid.uuid4().hex[:16]

        from infra.local_store.workspace import get_workspace
        ws = get_workspace()

        async with ws.session() as session:
            project = LocalProject(
                id=project_id,
                user_id=user_id,
                name=req.name,
                template_id=template.id,
                icon=req.icon or template.icon,
                description=req.description or template.description,
                memory_focus=template.memory_focus,
                ui_template=template.ui_template,
                is_active=0,
            )
            # __all__ → expand to all available skill names
            skills = list(template.default_skills)
            if _ALL_SKILLS_SENTINEL in skills:
                skills = list(self._all_skill_names) if self._all_skill_names else []
            project.skills = skills
            session.add(project)
            await session.commit()
            await session.refresh(project)
            info = project.to_info()

        # Create isolated directory
        self._ensure_project_dirs(project_id)

        logger.info(
            f"项目已创建: id={project_id}, name={req.name}, "
            f"template={template.id}"
        )
        return info

    async def list_projects(self, user_id: str) -> List[ProjectInfo]:
        """List all projects for a user, ordered by updated_at desc."""
        from infra.local_store.workspace import get_workspace
        from sqlalchemy import select

        ws = get_workspace()
        async with ws.session() as session:
            stmt = (
                select(LocalProject)
                .where(LocalProject.user_id == user_id)
                .order_by(LocalProject.updated_at.desc())
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [r.to_info() for r in rows]

    async def get_project(self, user_id: str, project_id: str) -> Optional[ProjectInfo]:
        """Get a single project."""
        row = await self._get_row(user_id, project_id)
        return row.to_info() if row else None

    async def update_project(
        self, user_id: str, project_id: str, req: ProjectUpdate
    ) -> Optional[ProjectInfo]:
        """Update mutable project fields."""
        from infra.local_store.workspace import get_workspace

        ws = get_workspace()
        async with ws.session() as session:
            row = await self._get_row_in_session(session, user_id, project_id)
            if not row:
                return None
            if req.name is not None:
                row.name = req.name
            if req.description is not None:
                row.description = req.description
            if req.icon is not None:
                row.icon = req.icon
            if req.skills is not None:
                row.skills = req.skills
            await session.commit()
            await session.refresh(row)
            return row.to_info()

    async def delete_project(self, user_id: str, project_id: str) -> bool:
        """Delete project row and its isolated directory."""
        from infra.local_store.workspace import get_workspace

        ws = get_workspace()
        async with ws.session() as session:
            row = await self._get_row_in_session(session, user_id, project_id)
            if not row:
                return False
            await session.delete(row)
            await session.commit()

        # Remove directory
        project_dir = self._root / project_id
        if project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)
            logger.info(f"项目目录已删除: {project_dir}")

        logger.info(f"项目已删除: id={project_id}")
        return True

    async def switch_project(self, user_id: str, project_id: str) -> Optional[ProjectInfo]:
        """
        Set a project as active (deactivate all others for the user).
        """
        from infra.local_store.workspace import get_workspace
        from sqlalchemy import select, update

        ws = get_workspace()
        async with ws.session() as session:
            # Deactivate all
            await session.execute(
                update(LocalProject)
                .where(LocalProject.user_id == user_id)
                .values(is_active=0)
            )
            # Activate target
            row = await self._get_row_in_session(session, user_id, project_id)
            if not row:
                await session.rollback()
                return None
            row.is_active = 1
            await session.commit()
            await session.refresh(row)
            info = row.to_info()

        logger.info(f"项目已切换: id={project_id}, name={info.name}")
        return info

    async def get_active_project(self, user_id: str) -> Optional[ProjectInfo]:
        """Get the currently active project for a user."""
        from infra.local_store.workspace import get_workspace
        from sqlalchemy import select

        ws = get_workspace()
        async with ws.session() as session:
            stmt = (
                select(LocalProject)
                .where(LocalProject.user_id == user_id, LocalProject.is_active == 1)
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return row.to_info() if row else None

    # ================================================================
    # Directory isolation
    # ================================================================

    def get_project_dir(self, project_id: str) -> Path:
        """Return the isolated directory for a project."""
        return self._root / project_id

    def _ensure_project_dirs(self, project_id: str) -> Path:
        """Create the isolated directory structure."""
        project_dir = self._root / project_id
        for sub in _PROJECT_SUBDIRS:
            (project_dir / sub).mkdir(parents=True, exist_ok=True)
        return project_dir

    # ================================================================
    # Internal helpers
    # ================================================================

    async def _get_row(self, user_id: str, project_id: str) -> Optional[LocalProject]:
        from infra.local_store.workspace import get_workspace
        from sqlalchemy import select

        ws = get_workspace()
        async with ws.session() as session:
            stmt = select(LocalProject).where(
                LocalProject.id == project_id,
                LocalProject.user_id == user_id,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    @staticmethod
    async def _get_row_in_session(session: Any, user_id: str, project_id: str) -> Optional[LocalProject]:
        from sqlalchemy import select

        stmt = select(LocalProject).where(
            LocalProject.id == project_id,
            LocalProject.user_id == user_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

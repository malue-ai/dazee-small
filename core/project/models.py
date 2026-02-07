"""
Project data models.

- ProjectTemplate: immutable template loaded from config.yaml
- ProjectInfo: Pydantic API model
- LocalProject: SQLite ORM model
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from infra.local_store.models import LocalBase, _from_json, _to_json

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


# ================================================================
# Template (immutable, from config.yaml)
# ================================================================


@dataclass(frozen=True)
class ProjectTemplate:
    """Immutable project template loaded from config.yaml."""

    id: str
    name: str
    icon: str = ""
    description: str = ""
    default_skills: List[str] = field(default_factory=list)
    memory_focus: str = "general"  # style / format / domain / workflow / general
    ui_template: str = "default"

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectTemplate":
        return cls(
            id=data.get("id", "custom"),
            name=data.get("name", ""),
            icon=data.get("icon", ""),
            description=data.get("description", ""),
            default_skills=data.get("default_skills") or [],
            memory_focus=data.get("memory_focus", "general"),
            ui_template=data.get("ui_template", "default"),
        )


# ================================================================
# Pydantic API models
# ================================================================


class ProjectInfo(BaseModel):
    """Project info returned by API."""

    id: str = Field(description="Project unique ID")
    name: str = Field(description="User-visible name")
    template_id: str = Field(default="custom", description="Template used to create this project")
    icon: str = Field(default="")
    description: str = Field(default="")
    memory_focus: str = Field(default="general")
    ui_template: str = Field(default="default")
    skills: List[str] = Field(default_factory=list, description="Enabled skill names")
    is_active: bool = Field(default=False, description="Whether this is the current project")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectCreate(BaseModel):
    """Request body for creating a project."""

    name: str = Field(min_length=1, max_length=128)
    template_id: str = Field(default="custom")
    description: str = Field(default="")
    icon: str = Field(default="")


class ProjectUpdate(BaseModel):
    """Request body for updating a project."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = None
    icon: Optional[str] = None
    skills: Optional[List[str]] = None


class TemplateInfo(BaseModel):
    """Template info returned by API."""

    id: str
    name: str
    icon: str = ""
    description: str = ""
    default_skills: List[str] = Field(default_factory=list)
    memory_focus: str = "general"
    ui_template: str = "default"


# ================================================================
# SQLite ORM model
# ================================================================


class LocalProject(LocalBase):
    """
    Project table.

    Each project has isolated context, knowledge, playbook, and skills config.
    """

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: uuid.uuid4().hex[:16]
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    template_id: Mapped[str] = mapped_column(String(64), nullable=False, default="custom")
    icon: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Isolation settings (JSON)
    memory_focus: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    ui_template: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    skills_json: Mapped[str] = mapped_column("skills", Text, nullable=False, default="[]")
    settings_json: Mapped[str] = mapped_column("settings", Text, nullable=False, default="{}")

    # State
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    __table_args__ = (
        Index("idx_project_user_active", "user_id", "is_active"),
        Index("idx_project_user_updated", "user_id", "updated_at"),
    )

    @property
    def skills(self) -> List[str]:
        result = _from_json(self.skills_json, [])
        return result if isinstance(result, list) else []

    @skills.setter
    def skills(self, value: List[str]) -> None:
        self.skills_json = _to_json(value)

    @property
    def settings(self) -> Dict[str, Any]:
        return _from_json(self.settings_json, {})

    @settings.setter
    def settings(self, value: Dict[str, Any]) -> None:
        self.settings_json = _to_json(value)

    def to_info(self) -> ProjectInfo:
        """Convert ORM model to API model."""
        return ProjectInfo(
            id=self.id,
            name=self.name,
            template_id=self.template_id,
            icon=self.icon,
            description=self.description,
            memory_focus=self.memory_focus,
            ui_template=self.ui_template,
            skills=self.skills,
            is_active=bool(self.is_active),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def __repr__(self) -> str:
        return f"<LocalProject(id={self.id}, name={self.name}, template={self.template_id})>"

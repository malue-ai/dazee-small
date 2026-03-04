"""
云端任务本地存储模型

继承 LocalBase，由 init_local_database 自动建表。
任务状态在本地管理，不依赖云端提供 task 管理能力。
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from infra.local_store.models import LocalBase


class LocalCloudTask(LocalBase):
    """
    云端委托任务的本地记录

    状态机: created -> streaming -> completed / failed / canceled
    """

    __tablename__ = "cloud_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="created", index=True,
    )
    task_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cloud_conversation_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    progress_steps_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_cloud_tasks_status_created", "status", "created_at"),
    )

    # --- JSON property helpers ---

    @property
    def progress_steps(self) -> List[Dict[str, Any]]:
        try:
            return json.loads(self.progress_steps_json) if self.progress_steps_json else []
        except (json.JSONDecodeError, TypeError):
            return []

    @progress_steps.setter
    def progress_steps(self, value: List[Dict[str, Any]]) -> None:
        self.progress_steps_json = json.dumps(value, ensure_ascii=False)

    def add_progress_step(self, step: Dict[str, Any]) -> None:
        steps = self.progress_steps
        steps.append(step)
        self.progress_steps = steps

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.id,
            "status": self.status,
            "task_description": self.task_description,
            "cloud_conversation_id": self.cloud_conversation_id,
            "progress_steps": self.progress_steps,
            "result_summary": self.result_summary,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

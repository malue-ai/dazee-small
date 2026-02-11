"""
Scheduled Task API Models

Pydantic models for scheduled task REST API.
Aligned with LocalScheduledTask ORM model in infra/local_store/models.py.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ==================== Enums ====================


class TaskTriggerType(str, Enum):
    """Task trigger type (matches DB: once / cron / interval)"""
    ONCE = "once"
    CRON = "cron"
    INTERVAL = "interval"


class TaskActionType(str, Enum):
    """Task action type (matches DB action JSON: type field)"""
    SEND_MESSAGE = "send_message"
    AGENT_TASK = "agent_task"


class TaskStatus(str, Enum):
    """Task status (matches DB: active / paused / completed / cancelled)"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ==================== Response Models ====================


class ScheduledTaskResponse(BaseModel):
    """Single scheduled task response — full detail"""
    id: str
    user_id: str
    title: str
    description: Optional[str] = None

    # Trigger
    trigger_type: str
    run_at: Optional[datetime] = None
    cron_expr: Optional[str] = None
    interval_seconds: Optional[int] = None

    # Action (raw JSON dict)
    action: Dict[str, Any] = Field(default_factory=dict)

    # Status & execution
    status: str
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    run_count: int = 0

    # Metadata
    created_at: datetime
    updated_at: Optional[datetime] = None
    conversation_id: Optional[str] = None

    model_config = {"from_attributes": True}


class ScheduledTaskListResponse(BaseModel):
    """Paginated task list response"""
    tasks: List[ScheduledTaskResponse]
    total: int
    page: int = 1
    page_size: int = 50

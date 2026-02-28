"""
ACP data models for local-side use.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ACPTask:
    """Represents a task delegated to the cloud agent."""

    task_id: str
    status: str = "submitted"
    session_id: str = ""
    result_summary: Optional[str] = None


@dataclass
class ACPEvent:
    """A single event received from the ACP SSE stream."""

    type: str
    data: Dict[str, Any] = field(default_factory=dict)
    seq: int = 0

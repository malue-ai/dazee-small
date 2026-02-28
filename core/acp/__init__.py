"""
ACP (Agent Collaboration Protocol) — local-side client module.

Minimal implementation for Forward ACP: local agent delegates tasks to cloud.
"""

from core.acp.client import ACPClient
from core.acp.models import ACPEvent, ACPTask

__all__ = ["ACPClient", "ACPTask", "ACPEvent"]

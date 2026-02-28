"""
Cloud collaboration module — direct call to cloud agent's existing API.

Phase 0.5: Call /api/v1/chat/stream directly, zero cloud-side changes.
"""

from core.cloud.client import CloudClient, get_cloud_client

__all__ = ["CloudClient", "get_cloud_client"]

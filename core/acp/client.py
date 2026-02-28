"""
ACPClient — minimal HTTP + SSE client for Forward ACP.

Connects to the cloud agent's /acp/* endpoints.
Phase 1: hardcoded URL from env, no token management (auth added later).
"""

import json
import os
from typing import Any, AsyncGenerator, Dict, Optional

import httpx

from core.acp.models import ACPEvent, ACPTask
from logger import get_logger

logger = get_logger("acp_client")

ACP_CLOUD_URL = os.getenv("ACP_CLOUD_URL", "http://127.0.0.1:8001")
ACP_TIMEOUT = int(os.getenv("ACP_TIMEOUT", "120"))


class ACPClient:
    """
    Minimal ACP client for task delegation.

    Usage:
        client = ACPClient()
        task = await client.create_task("research AI agents")
        async for event in client.stream_events(task.task_id):
            print(event.type, event.data)
    """

    def __init__(self, cloud_url: Optional[str] = None, acp_token: Optional[str] = None):
        self._cloud_url = (cloud_url or ACP_CLOUD_URL).rstrip("/")
        self._acp_token = acp_token or os.getenv("ACP_TOKEN", "")

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._acp_token:
            headers["Authorization"] = f"Bearer {self._acp_token}"
        return headers

    async def create_task(
        self, task: str, context: Optional[Dict[str, Any]] = None
    ) -> ACPTask:
        """POST /acp/tasks — create and start a cloud task."""
        url = f"{self._cloud_url}/acp/tasks"
        body: Dict[str, Any] = {"task": task}
        if context:
            body["context"] = context

        async with httpx.AsyncClient(timeout=ACP_TIMEOUT) as http:
            resp = await http.post(url, json=body, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()

        logger.info(f"ACP task created: {data.get('task_id')}")
        return ACPTask(
            task_id=data["task_id"],
            status=data.get("status", "submitted"),
            session_id=data.get("session_id", ""),
        )

    async def get_task(self, task_id: str) -> ACPTask:
        """GET /acp/tasks/{task_id} — poll task status."""
        url = f"{self._cloud_url}/acp/tasks/{task_id}"
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()

        return ACPTask(
            task_id=data["task_id"],
            status=data.get("status", "unknown"),
            session_id=data.get("session_id", ""),
            result_summary=data.get("result_summary"),
        )

    async def stream_events(
        self, task_id: str, last_seq: int = 0
    ) -> AsyncGenerator[ACPEvent, None]:
        """
        GET /acp/tasks/{task_id}/stream — consume SSE event stream.

        Yields ACPEvent objects until the task completes or fails.
        """
        url = f"{self._cloud_url}/acp/tasks/{task_id}/stream"
        params = {"last_seq": last_seq} if last_seq else {}

        async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as http:
            async with http.stream(
                "GET", url, headers=self._headers(), params=params
            ) as response:
                response.raise_for_status()
                buffer = ""

                async for chunk in response.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        raw_event, buffer = buffer.split("\n\n", 1)
                        event = self._parse_sse_event(raw_event)
                        if event:
                            yield event
                            if event.type in (
                                "acp_task_completed",
                                "acp_task_failed",
                                "acp_error",
                            ):
                                return

    async def control_task(self, task_id: str, action: str) -> Dict[str, Any]:
        """PATCH /acp/tasks/{task_id}/state — pause/resume/cancel."""
        url = f"{self._cloud_url}/acp/tasks/{task_id}/state"
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.patch(
                url, json={"action": action}, headers=self._headers()
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _parse_sse_event(raw: str) -> Optional[ACPEvent]:
        """Parse a single SSE data line into an ACPEvent."""
        for line in raw.strip().split("\n"):
            if line.startswith("data:"):
                json_str = line[5:].strip()
                if not json_str:
                    continue
                try:
                    data = json.loads(json_str)
                    return ACPEvent(
                        type=data.get("type", "unknown"),
                        data=data.get("data", data),
                        seq=data.get("seq", 0),
                    )
                except json.JSONDecodeError:
                    continue
        return None


_acp_client: Optional[ACPClient] = None


def get_acp_client() -> ACPClient:
    """Get or create the global ACPClient singleton."""
    global _acp_client
    if _acp_client is None:
        _acp_client = ACPClient()
    return _acp_client

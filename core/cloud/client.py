"""
CloudClient — calls the cloud agent's existing /api/v1/chat/stream endpoint.

No custom ACP protocol. Just HTTP POST + SSE consumption.
The cloud returns events in the same zenflux format the local agent uses.

Usage:
    client = get_cloud_client()
    async for event in client.chat_stream("Research AI agents"):
        print(event["type"], event.get("data"))
"""

import json
import os
import time
from typing import Any, AsyncGenerator, Dict, Optional

import httpx

from logger import get_logger

logger = get_logger("cloud_client")

CLOUD_URL = os.getenv("CLOUD_URL", "http://127.0.0.1:8001")
CLOUD_USERNAME = os.getenv("CLOUD_USERNAME", "")
CLOUD_PASSWORD = os.getenv("CLOUD_PASSWORD", "")
CLOUD_TIMEOUT = int(os.getenv("CLOUD_TIMEOUT", "180"))


class CloudClient:
    """
    Calls the cloud agent's existing chat API.

    Auth: same as the cloud's web frontend (username/password -> JWT).
    Chat: POST /api/v1/chat/stream -> SSE event stream.
    """

    def __init__(
        self,
        cloud_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self._cloud_url = (cloud_url or CLOUD_URL).rstrip("/")
        self._username = username or CLOUD_USERNAME
        self._password = password or CLOUD_PASSWORD
        self._token: Optional[str] = None
        self._token_time: float = 0
        self._token_ttl: float = 23 * 3600  # refresh before 24h expiry

    async def _ensure_token(self) -> str:
        """Login if no token or token is expiring."""
        if self._token and (time.time() - self._token_time) < self._token_ttl:
            return self._token

        if not self._username or not self._password:
            raise RuntimeError(
                "Cloud credentials not configured. "
                "Set CLOUD_URL, CLOUD_USERNAME, CLOUD_PASSWORD env vars "
                "or bind via settings page."
            )

        self._token = await self.login(self._username, self._password)
        self._token_time = time.time()
        return self._token

    async def login(self, username: str, password: str) -> str:
        """POST /api/v1/auth/login -> JWT token."""
        url = f"{self._cloud_url}/api/v1/auth/login"
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(url, json={"username": username, "password": password})
            resp.raise_for_status()
            data = resp.json()
        token = data.get("token", "")
        if not token:
            raise RuntimeError(f"Login failed: no token in response. keys={list(data.keys())}")
        logger.info(f"Cloud login OK: user={username}")
        return token

    async def chat_stream(
        self,
        message: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        files: Optional[list] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        POST /api/v1/chat/stream -> consume SSE events.

        Yields dicts with the same zenflux event format the local agent uses:
        {type, data, seq, ...}
        """
        token = await self._ensure_token()
        url = f"{self._cloud_url}/api/v1/chat/stream"

        body: Dict[str, Any] = {
            "message": message,
            "userId": user_id or self._username or "cloud_skill_user",
            "stream": True,
        }
        if conversation_id:
            body["conversationId"] = conversation_id
        if files:
            body["files"] = files

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(CLOUD_TIMEOUT)) as http:
            async with http.stream("POST", url, json=body, headers=headers) as response:
                if response.status_code == 401:
                    self._token = None
                    raise RuntimeError("Cloud auth expired, will retry on next call")
                response.raise_for_status()

                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        raw_event, buffer = buffer.split("\n\n", 1)
                        event = _parse_sse_line(raw_event)
                        if event:
                            yield event
                            if event.get("type") in ("message_stop", "session_end"):
                                return

    @property
    def is_configured(self) -> bool:
        return bool(self._cloud_url and self._username and self._password)


def _parse_sse_line(raw: str) -> Optional[Dict[str, Any]]:
    """Parse SSE data lines into a dict."""
    for line in raw.strip().split("\n"):
        if line.startswith("data:"):
            json_str = line[5:].strip()
            if not json_str or json_str == "{}":
                continue
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue
        if line.startswith("event:") and "done" in line:
            return {"type": "message_stop", "data": {}}
    return None


_cloud_client: Optional[CloudClient] = None


def get_cloud_client() -> CloudClient:
    """Get or create the global CloudClient singleton."""
    global _cloud_client
    if _cloud_client is None:
        _cloud_client = CloudClient()
    return _cloud_client

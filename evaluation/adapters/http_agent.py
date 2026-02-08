"""
HTTP API adapter for E2E evaluation.

Calls ZenFlux FastAPI: POST /api/v1/chat (stream=false), poll session, fetch messages,
then normalizes to harness format (messages, tool_calls, token_usage, metadata).
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from evaluation.models import Message, TokenUsage, ToolCall

logger = logging.getLogger(__name__)


class HttpAgentAdapter:
    """
    Adapter that talks to ZenFlux HTTP API and returns a dict compatible with
    EvaluationHarness._execute_agent (messages, tool_calls, token_usage, metadata).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        user_id: str = "eval_e2e_user",
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        poll_interval_seconds: float = 2.0,
        poll_max_wait_seconds: float = 300.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.agent_id = agent_id
        self.conversation_id = conversation_id
        self.poll_interval = poll_interval_seconds
        self.poll_max_wait = poll_max_wait_seconds

    async def chat(
        self,
        user_query: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        files: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Send one message to the chat API, wait for completion, fetch messages,
        and return a harness-compatible result.

        Args:
            user_query: User message text.
            conversation_history: Optional list of prior messages (role/content).
            files: Optional list of file refs for API, e.g. [{"file_id": "..."}].

        Returns:
            Dict with keys: messages, tool_calls, token_usage, metadata.
        """
        payload: Dict[str, Any] = {
            "message": user_query,
            "user_id": self.user_id,
            "stream": False,
        }
        if self.conversation_id is not None:
            payload["conversation_id"] = self.conversation_id
        if self.agent_id is not None:
            payload["agent_id"] = self.agent_id
        if files:
            payload["files"] = files

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/chat",
                json=payload,
            )
            if resp.status_code >= 400:
                try:
                    err_body = resp.text
                    if len(err_body) > 500:
                        err_body = err_body[:500] + "..."
                except Exception:
                    err_body = ""
                raise RuntimeError(
                    f"POST /api/v1/chat returned {resp.status_code}: {err_body}"
                ) from None
            body = resp.json()
        data = body.get("data") or body
        task_id = data.get("task_id")
        conversation_id = data.get("conversation_id")
        if not task_id:
            raise ValueError("Chat response missing task_id")

        await self._poll_until_done(task_id)

        messages_data, tool_calls_list, token_usage = await self._fetch_and_parse_messages(
            conversation_id or self.conversation_id
        )

        return {
            "messages": messages_data,
            "tool_calls": tool_calls_list,
            "token_usage": token_usage,
            "metadata": {
                "task_id": task_id,
                "conversation_id": conversation_id,
            },
        }

    async def _poll_until_done(self, task_id: str) -> None:
        elapsed = 0.0
        while elapsed < self.poll_max_wait:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self.base_url}/api/v1/session/{task_id}",
                )
                resp.raise_for_status()
                body = resp.json()
            data = body.get("data") or body
            active = data.get("active", True)
            if not active:
                return
            await asyncio.sleep(self.poll_interval)
            elapsed += self.poll_interval
        raise TimeoutError(
            f"Session {task_id} did not finish within {self.poll_max_wait}s"
        )

    async def _fetch_and_parse_messages(
        self, conversation_id: str
    ) -> tuple[List[Dict[str, Any]], List[ToolCall], TokenUsage]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/conversations/{conversation_id}/messages",
                params={"limit": 200, "order": "asc"},
            )
            resp.raise_for_status()
            body = resp.json()
        data = body.get("data") or body
        raw_messages = data.get("messages") or []

        messages_out: List[Dict[str, Any]] = []
        tool_calls_list: List[ToolCall] = []
        input_tokens = 0
        output_tokens = 0
        thinking_tokens = 0
        cache_read_tokens = 0
        cache_write_tokens = 0

        for raw in raw_messages:
            role = raw.get("role", "user")
            content_str = raw.get("content", "[]")
            if isinstance(content_str, list):
                content_blocks = content_str
            else:
                try:
                    content_blocks = json.loads(content_str) if content_str else []
                except json.JSONDecodeError:
                    content_blocks = [{"type": "text", "text": str(content_str)}]
            if not isinstance(content_blocks, list):
                content_blocks = [content_blocks] if isinstance(content_blocks, dict) else []

            text_parts = []
            msg_tool_calls: List[ToolCall] = []
            for blk in content_blocks:
                if not isinstance(blk, dict):
                    continue
                t = blk.get("type")
                if t == "text":
                    text_parts.append(blk.get("text", ""))
                elif t == "tool_use":
                    msg_tool_calls.append(
                        ToolCall(
                            name=blk.get("name", ""),
                            arguments=blk.get("input") or {},
                        )
                    )
                    tool_calls_list.append(
                        ToolCall(
                            name=blk.get("name", ""),
                            arguments=blk.get("input") or {},
                        )
                    )
                elif t == "tool_result":
                    pass
                elif t in ("thinking", "redacted_thinking"):
                    pass

            content_str_out = "\n".join(text_parts) if text_parts else ""
            messages_out.append(
                {
                    "role": role,
                    "content": content_str_out,
                    "tool_calls": msg_tool_calls,
                }
            )

            usage = (raw.get("metadata") or {}).get("usage")
            if isinstance(usage, dict):
                input_tokens += usage.get("input_tokens", 0) or usage.get("total_input_tokens", 0)
                output_tokens += usage.get("output_tokens", 0) or usage.get("total_output_tokens", 0)
                thinking_tokens += usage.get("total_thinking_tokens", 0) or usage.get("thinking_tokens", 0)
                cache_read_tokens += usage.get("cache_read_tokens", 0) or usage.get("total_cache_read_tokens", 0)
                cache_write_tokens += usage.get("cache_write_tokens", 0) or usage.get("cache_creation_tokens", 0) or usage.get("total_cache_creation_tokens", 0)

        token_usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )

        eval_messages: List[Message] = [
            Message(role=m["role"], content=m["content"], tool_calls=m.get("tool_calls") or [])
            for m in messages_out
        ]
        return (eval_messages, tool_calls_list, token_usage)

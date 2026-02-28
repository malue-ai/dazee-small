"""
CloudAgentTool — delegates tasks to the cloud agent via its existing chat API.

Phase 0.5: Direct call to /api/v1/chat/stream. No custom ACP protocol.
The cloud agent runs its own intent/plan/tool loop internally — transparent to us.
"""

import logging
from typing import Any, Dict, Optional

from core.cloud.client import get_cloud_client
from core.tool.types import ToolContext
from tools.base import BaseTool

logger = logging.getLogger(__name__)


class CloudAgentTool(BaseTool):
    """
    Delegate a task to the cloud agent for execution.

    The cloud agent is a full independent agent (intent, plan, tools, etc.)
    — all transparent to the local side. We just send a message and stream
    back the response.
    """

    @property
    def name(self) -> str:
        return "cloud_agent"

    @property
    def description(self) -> str:
        return (
            "Delegate a task to the cloud agent. Use when the task needs: "
            "(1) persistent execution that survives laptop shutdown, "
            "(2) sandbox code execution / project build / app publishing, or "
            "(3) mobile/IM reachability for progress tracking."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Task description to delegate to cloud agent",
                },
                "context": {
                    "type": "string",
                    "description": "Optional context (local analysis results, user preferences, etc.)",
                },
            },
            "required": ["task"],
        }

    async def execute(
        self, params: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        task_desc = params.get("task", "")
        if not task_desc:
            return {"success": False, "error": "task description is required"}

        extra_context = params.get("context", "")
        message = task_desc
        if extra_context:
            message = f"{task_desc}\n\n{extra_context}"

        client = get_cloud_client()
        if not client.is_configured:
            return {
                "success": False,
                "error": "Cloud agent not configured. Set CLOUD_URL, CLOUD_USERNAME, CLOUD_PASSWORD.",
            }

        final_text = ""
        event_count = 0

        try:
            async for event in client.chat_stream(message=message):
                event_count += 1
                etype = event.get("type", "")

                if etype == "content_delta":
                    data = event.get("data", {})
                    delta = data.get("delta", "")
                    if isinstance(delta, str):
                        final_text += delta
                    elif isinstance(delta, dict):
                        text = delta.get("text", "")
                        if text:
                            final_text += text

                elif etype == "content_start":
                    block = event.get("data", {}).get("content_block", {})
                    if block.get("type") == "tool_use":
                        await self._emit_progress(
                            context,
                            phase="tool_call",
                            tool=block.get("name", "unknown"),
                            status="running",
                        )
                    elif block.get("type") == "thinking":
                        await self._emit_progress(context, phase="thinking")

                elif etype == "content_stop":
                    data = event.get("data", {})
                    block_type = data.get("content_block", {}).get("type", "")
                    if block_type == "tool_use":
                        await self._emit_progress(
                            context,
                            phase="tool_call",
                            tool="",
                            status="done",
                        )

                elif etype in ("message_stop", "session_end"):
                    break

        except Exception as e:
            logger.error(f"Cloud chat stream error: {e}", exc_info=True)
            if final_text:
                return {
                    "success": True,
                    "result": final_text,
                    "warning": f"Stream interrupted: {e}",
                }
            return {"success": False, "error": f"Cloud agent call failed: {e}"}

        logger.info(f"Cloud task done: events={event_count}, result_len={len(final_text)}")
        return {
            "success": True,
            "result": final_text or "(cloud agent completed with no text output)",
        }

    async def _emit_progress(
        self, context: Optional[ToolContext], **progress: Any
    ) -> None:
        """Bridge cloud events to local message_delta {type: cloud_progress}."""
        if not context or not context.event_manager:
            return
        try:
            await context.event_manager.message.emit_message_delta(
                session_id=context.session_id,
                conversation_id=context.conversation_id,
                delta={"type": "cloud_progress", "content": progress},
            )
        except Exception as e:
            logger.debug(f"Failed to emit cloud_progress: {e}")

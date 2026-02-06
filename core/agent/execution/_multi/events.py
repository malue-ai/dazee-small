"""
多智能体事件发送层

V10.2 拆分自 orchestrator.py
V10.3 从 Mixin 转为独立类 EventEmitter

职责：
- 发送 Orchestrator 开始/结束事件
- 发送任务分解事件
- 发送子任务开始/结束事件
- 发送摘要事件
- 发送错误事件
"""

import json
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from logger import get_logger

logger = get_logger(__name__)


class EventEmitter:
    """
    独立的事件发送器

    管理自己的状态（content_index、tool_ids），不依赖宿主类。

    使用方式：
        emitter = EventEmitter(broadcaster=broadcaster)
        await emitter.emit_orchestrator_start(session_id, mode, ...)
    """

    def __init__(self, broadcaster=None):
        self.broadcaster = broadcaster
        self._content_index: int = 0
        self._orchestrator_tool_id: Optional[str] = None
        self._subtask_tool_ids: Dict[str, Tuple[int, str]] = {}

    def _next_content_index(self) -> int:
        idx = self._content_index
        self._content_index += 1
        return idx

    async def emit_orchestrator_start(
        self, session_id: str, mode: str, agent_count: int, lead_agent_enabled: bool
    ) -> None:
        if not self.broadcaster:
            return
        self._orchestrator_tool_id = f"orch_{session_id[:8]}_{uuid4().hex[:6]}"
        index = self._next_content_index()
        await self.broadcaster.emit_content_start(
            session_id=session_id,
            index=index,
            content_block={
                "type": "tool_use",
                "id": self._orchestrator_tool_id,
                "name": "multi_agent_orchestrator",
                "input": {
                    "mode": mode,
                    "agent_count": agent_count,
                    "lead_agent_enabled": lead_agent_enabled,
                },
            },
        )

    async def emit_decomposition(
        self, session_id: str, plan_id: str, subtasks_count: int,
        execution_mode: str, reasoning: str,
    ) -> None:
        if not self.broadcaster:
            return
        index = self._next_content_index()
        tool_id = f"decomp_{plan_id[:8] if plan_id else 'unknown'}"
        await self.broadcaster.emit_content_start(
            session_id=session_id,
            index=index,
            content_block={
                "type": "tool_use",
                "id": tool_id,
                "name": "multi_agent_decomposition",
                "input": {
                    "plan_id": plan_id,
                    "subtasks_count": subtasks_count,
                    "execution_mode": execution_mode,
                    "reasoning": reasoning[:200] if reasoning else "",
                },
            },
        )
        await self.broadcaster.emit_content_stop(session_id=session_id, index=index)
        result_index = self._next_content_index()
        await self.broadcaster.emit_content_start(
            session_id=session_id,
            index=result_index,
            content_block={
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": f"任务分解完成，共 {subtasks_count} 个子任务",
                "is_error": False,
            },
        )
        await self.broadcaster.emit_content_stop(session_id=session_id, index=result_index)

    async def emit_subtask_start(
        self, session_id: str, subtask_id: str, title: str, role: str,
        execute_by_lead: bool = False, context_dependency: str = "low",
    ) -> None:
        if not self.broadcaster:
            return
        index = self._next_content_index()
        tool_use_id = f"subtask_{subtask_id[:12] if subtask_id else uuid4().hex[:12]}"
        self._subtask_tool_ids[subtask_id] = (index, tool_use_id)
        await self.broadcaster.emit_content_start(
            session_id=session_id,
            index=index,
            content_block={
                "type": "tool_use",
                "id": tool_use_id,
                "name": "multi_agent_subtask",
                "input": {
                    "subtask_id": subtask_id,
                    "title": title,
                    "role": role,
                    "execute_by_lead": execute_by_lead,
                    "context_dependency": context_dependency,
                },
            },
        )

    async def emit_subtask_end(
        self, session_id: str, subtask_id: str, output: str, success: bool,
        executed_by_lead: bool = False, stream_chunk_size: int = 40,
    ) -> None:
        if not self.broadcaster:
            return
        tool_info = self._subtask_tool_ids.get(subtask_id)
        if tool_info:
            tool_use_index, tool_use_id = tool_info
            await self.broadcaster.emit_content_stop(session_id=session_id, index=tool_use_index)
        else:
            tool_use_id = f"subtask_{subtask_id[:12] if subtask_id else 'unknown'}"

        result_index = self._next_content_index()
        content = output or "执行完成"

        # tool_result 流式发送：content 为空进入流式模式，通过 delta 逐块推送
        await self.broadcaster.emit_content_start(
            session_id=session_id,
            index=result_index,
            content_block={
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": "",
                "is_error": not success,
            },
        )
        for i in range(0, len(content), stream_chunk_size):
            await self.broadcaster.emit_content_delta(
                session_id=session_id,
                index=result_index,
                delta=content[i:i + stream_chunk_size],
            )
        await self.broadcaster.emit_content_stop(session_id=session_id, index=result_index)

    async def emit_orchestrator_summary(self, session_id: str, summary: str) -> None:
        if not self.broadcaster or not summary:
            return
        index = self._next_content_index()
        await self.broadcaster.emit_content_start(
            session_id=session_id, index=index, content_block={"type": "text", "text": ""}
        )
        await self.broadcaster.emit_content_delta(
            session_id=session_id, index=index, delta=summary
        )
        await self.broadcaster.emit_content_stop(session_id=session_id, index=index)

    async def emit_orchestrator_end(
        self, session_id: str, status: str, duration_ms: int, agent_results_count: int
    ) -> None:
        if not self.broadcaster:
            return
        index = self._next_content_index()
        await self.broadcaster.emit_content_start(
            session_id=session_id,
            index=index,
            content_block={
                "type": "tool_result",
                "tool_use_id": self._orchestrator_tool_id or "orch_unknown",
                "content": json.dumps(
                    {
                        "status": status,
                        "duration_ms": duration_ms,
                        "agent_results": agent_results_count,
                    },
                    ensure_ascii=False,
                ),
                "is_error": status == "failed",
            },
        )
        await self.broadcaster.emit_content_stop(session_id=session_id, index=index)

    async def emit_orchestrator_error(
        self, session_id: str, error: str, checkpoint_saved: bool = False
    ) -> None:
        if not self.broadcaster:
            return
        index = self._next_content_index()
        await self.broadcaster.emit_content_start(
            session_id=session_id,
            index=index,
            content_block={
                "type": "tool_result",
                "tool_use_id": self._orchestrator_tool_id or "orch_error",
                "content": json.dumps(
                    {
                        "error": error[:500] if error else "未知错误",
                        "checkpoint_saved": checkpoint_saved,
                    },
                    ensure_ascii=False,
                ),
                "is_error": True,
            },
        )
        await self.broadcaster.emit_content_stop(session_id=session_id, index=index)

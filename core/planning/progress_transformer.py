"""
进度转换器 - ProgressTransformer（V12.0 架构 3.5.4）

核心原则：内部复杂，外部简单
- 内部保留完整的规划和回溯能力（PlanTool CRUD）
- 对用户只暴露简化的进度反馈（"正在分析..." / "快好了..."）

Config 驱动：
- 从 planning.implicit.progress_messages 读取友好消息模板
- 根据 planning.implicit.ui_mode 决定展示方式
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from logger import get_logger

if TYPE_CHECKING:
    from core.events.broadcaster import EventBroadcaster

logger = get_logger(__name__)


# Default progress messages (fallback when config not provided)
DEFAULT_PROGRESS_MESSAGES = {
    "analyzing": "正在分析...",
    "fixing": "检测到问题，自动修复中...",
    "processing": "处理中...",
    "almost_done": "快好了...",
    "done": "搞定！",
}


@dataclass
class ProgressUpdate:
    """User-friendly progress update."""

    step_id: str
    message: str
    percent: Optional[float] = None
    show_details: bool = False
    metadata: Optional[Dict[str, Any]] = None


class ProgressTransformer:
    """
    将技术性 plan_todo 步骤转换为用户友好的进度消息（架构 3.5.4）

    Usage:
        transformer = ProgressTransformer(
            broadcaster=event_broadcaster,
            config=planning_config.get("implicit", {}),
        )
        await transformer.transform_and_emit(plan_step, session_id)
    """

    def __init__(
        self,
        broadcaster: Optional["EventBroadcaster"] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Args:
            broadcaster: EventBroadcaster for SSE progress events
            config: planning.implicit config section
        """
        self._broadcaster = broadcaster
        config = config or {}

        self._ui_mode = config.get("ui_mode", "progress_bar")
        self._progress_style = config.get("progress_style", "friendly")
        self._progress_messages = {
            **DEFAULT_PROGRESS_MESSAGES,
            **(config.get("progress_messages") or {}),
        }

    def transform(
        self,
        plan_step: Any,
        completed: int = 0,
        total: int = 0,
    ) -> ProgressUpdate:
        """
        Transform a plan_todo step into a user-friendly ProgressUpdate.

        Args:
            plan_step: PlanStep dict or object with id/title/status fields
            completed: Number of completed steps
            total: Total number of steps

        Returns:
            ProgressUpdate with friendly message and percentage
        """
        # Extract fields from plan_step
        if isinstance(plan_step, dict):
            step_id = plan_step.get("id", "")
            title = plan_step.get("title", "")
            status = plan_step.get("status", "pending")
        else:
            step_id = getattr(plan_step, "id", "")
            title = getattr(plan_step, "title", "") or getattr(
                plan_step, "description", ""
            )
            status = getattr(plan_step, "status", "pending")

        # Calculate percentage
        percent = None
        if total > 0:
            percent = round(completed / total * 100, 1)

        # Generate friendly message based on progress stage
        if self._progress_style == "friendly":
            message = self._generate_friendly_message(
                title, status, percent
            )
        else:
            # technical mode: use title as-is
            message = title or "处理中..."

        # show_details based on ui_mode
        show_details = self._ui_mode == "steps"

        return ProgressUpdate(
            step_id=str(step_id),
            message=message,
            percent=percent,
            show_details=show_details,
            metadata={"title": title, "status": status},
        )

    def _generate_friendly_message(
        self,
        title: str,
        status: str,
        percent: Optional[float],
    ) -> str:
        """
        Generate user-friendly progress message (架构 3.5.4 message_map).

        Strategy: LLM-First friendly messages based on progress stage,
        not keyword matching on title.
        """
        if status == "completed":
            if percent and percent >= 100:
                return self._progress_messages.get("done", "搞定！")
            return f"✓ {title}" if title else "已完成"

        if status == "failed":
            return f"遇到问题，正在尝试其他方法..."

        # In-progress: choose message based on percentage
        if percent is not None:
            if percent >= 80:
                return self._progress_messages.get("almost_done", "快好了...")
            if percent >= 40:
                return self._progress_messages.get("processing", "处理中...")

        # Default: analyzing
        return self._progress_messages.get("analyzing", "正在分析...")

    async def transform_and_emit(
        self,
        plan_step: Any,
        session_id: str,
        completed: int = 0,
        total: int = 0,
    ) -> ProgressUpdate:
        """
        Transform and emit progress event via EventBroadcaster.

        Args:
            plan_step: PlanStep dict or object
            session_id: Session ID for event routing
            completed: Number of completed steps
            total: Total number of steps

        Returns:
            ProgressUpdate
        """
        update = self.transform(plan_step, completed, total)

        if self._broadcaster:
            try:
                await self._broadcaster.emit_progress_update(
                    session_id=session_id,
                    step_id=update.step_id,
                    message=update.message,
                    percent=update.percent,
                )
            except Exception as e:
                logger.warning(f"发送进度事件失败: {e}", exc_info=True)

        return update

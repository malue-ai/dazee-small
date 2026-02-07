"""
进度转换器 - ProgressTransformer

将技术性 plan_todo 步骤转为用户友好进度消息，
并通过 EventBroadcaster 发出 progress_update 事件。
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional

from logger import get_logger

if TYPE_CHECKING:
    from core.events.broadcaster import EventBroadcaster

logger = get_logger(__name__)


@dataclass
class ProgressUpdate:
    """用户友好进度更新"""

    step_id: str
    message: str
    percent: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class ProgressTransformer:
    """
    进度转换器

    将 Plan 步骤描述转为非技术用户可读的进度文案，
    可选通过 EventBroadcaster 发出 progress_update 事件。
    """

    def __init__(self, broadcaster: Optional["EventBroadcaster"] = None):
        """
        Args:
            broadcaster: 可选事件广播器（有值时 transform_and_emit 会发出事件）
        """
        self._broadcaster = broadcaster

    def transform(self, plan_step: Any) -> ProgressUpdate:
        """
        将技术性 plan_todo 步骤转为 ProgressUpdate

        Args:
            plan_step: PlanStep 或含 id、description 的字典

        Returns:
            ProgressUpdate
        """
        step_id = getattr(plan_step, "id", None) or (
            plan_step.get("id") if isinstance(plan_step, dict) else ""
        )
        desc = getattr(plan_step, "description", None) or (
            plan_step.get("description", "") if isinstance(plan_step, dict) else ""
        )
        message = desc if isinstance(desc, str) else str(desc)
        return ProgressUpdate(step_id=step_id or "", message=message or "处理中…")

    async def transform_and_emit(
        self, plan_step: Any, session_id: str
    ) -> ProgressUpdate:
        """
        转换 plan_step 并通过事件系统发出 progress_update

        Args:
            plan_step: PlanStep 或含 id、description 的字典
            session_id: 会话 ID（事件路由用）

        Returns:
            ProgressUpdate
        """
        update = self.transform(plan_step)

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

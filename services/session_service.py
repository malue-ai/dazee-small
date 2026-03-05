"""
Session 服务层 - Session Management Service（异步版本）

职责：
1. Session 生命周期管理（创建、获取、结束、清理）
2. Session 状态查询
3. Session 事件管理
4. 前后端连接管理（SSE session_id、心跳、超时）

设计原则：
- 单一职责：只管理 Session 状态，不涉及 Agent
- Session 状态存储在本地内存（LocalSessionStore）
- 支持多用户并发 Session
- 所有方法都是异步的，避免阻塞事件循环

注意：Agent 的创建和管理由 ChatService 负责
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.events import create_event_manager
from infra.local_store.session_store import LocalSessionStore, get_local_session_store
from logger import get_logger

logger = get_logger(__name__)


def extract_message_text(message: List[Dict[str, str]]) -> str:
    """
    从消息中提取文本内容（用于日志和预览）

    Args:
        message: 消息（Claude API 格式 [{"type": "text", "text": "..."}]）

    Returns:
        提取的文本内容
    """
    text_parts = [
        block.get("text", "")
        for block in message
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return " ".join(text_parts) if text_parts else ""


class SessionServiceError(Exception):
    """Session 服务异常基类"""

    pass


class SessionNotFoundError(SessionServiceError):
    """会话不存在异常"""

    pass


class SessionService:
    """
    Session 服务（异步版本）

    职责：管理前后端连接（Session 状态、事件流）
    注意：不负责 Agent 创建和管理
    """

    def __init__(self):
        """
        初始化 Session 服务
        """
        # 本地 Session 存储
        self.store: LocalSessionStore = get_local_session_store()

        # 事件管理器
        self.events = create_event_manager(self.store)

        # 停止事件（内存级）
        self._stop_events: Dict[str, asyncio.Event] = {}

        # V11: 状态一致性管理器（按 session_id 注册，供回滚 API 使用）
        self._state_managers: Dict[str, Any] = {}

        # V11: 长任务确认（用户选择 continue/background 后 set，执行器 await）
        self._long_run_confirm_events: Dict[str, asyncio.Event] = {}
        self._long_run_confirm_results: Dict[str, str] = {}  # "continue" / "background"

        # V11.1: HITL 危险操作确认（用户 approve/reject 后 set，执行器 await）
        self._hitl_confirm_events: Dict[str, asyncio.Event] = {}
        self._hitl_confirm_results: Dict[str, str] = {}  # "approve" / "reject"

        # V12: 回溯耗尽确认（用户选择 retry/rollback/stop）
        self._backtrack_confirm_events: Dict[str, asyncio.Event] = {}
        self._backtrack_confirm_results: Dict[str, str] = {}

        # V12: 费用确认（用户选择 continue/stop）
        self._cost_confirm_events: Dict[str, asyncio.Event] = {}
        self._cost_confirm_results: Dict[str, str] = {}

        # V12: 意图澄清（用户输入澄清文本）
        self._intent_clarify_events: Dict[str, asyncio.Event] = {}
        self._intent_clarify_results: Dict[str, str] = {}

        # V12.2: 同工具循环确认（用户选择 continue/stop）
        self._tool_loop_confirm_events: Dict[str, asyncio.Event] = {}
        self._tool_loop_confirm_results: Dict[str, str] = {}

    # ==================== Session 生命周期 ====================

    async def create_session(
        self,
        user_id: str,
        message: List[Dict[str, str]],
        conversation_id: str,
        message_id: Optional[str] = None,
    ) -> str:
        """
        创建 Session（只管理连接状态，不创建 Agent）

        Args:
            user_id: 用户 ID
            message: 用户消息（Claude API 格式 [{"type": "text", "text": "..."}]）
            conversation_id: 对话 ID（必填，ChatService 会确保在调用前已创建）
            message_id: 消息 ID（可选）

        Returns:
            session_id: 会话 ID
        """
        # 1️⃣ 生成 session_id
        session_id = str(uuid4())

        logger.info(
            f"🔨 创建新的 Session: session_id={session_id}, conversation_id={conversation_id}"
        )

        # 2️⃣ 提取消息文本用于预览
        message_text = extract_message_text(message)

        # 3️⃣ 创建 Session 状态
        await self.store.create_session(
            session_id=session_id,
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            message_preview=message_text[:100],
        )

        logger.info(
            f"✅ Session 创建完成: session_id={session_id}, "
            f"conversation_id={conversation_id}, user_id={user_id}"
        )

        return session_id

    async def end_session(self, session_id: str, status: str = "completed") -> Dict[str, Any]:
        """
        结束 Session

        Args:
            session_id: Session ID
            status: 最终状态（completed/failed/stopped）

        Returns:
            Session 摘要
        """ 
        # 更新 Session 状态为完成
        await self.store.complete_session(session_id, status=status)

        logger.info(f"✅ Session 已结束: session_id={session_id}, status={status}")

        return {"session_id": session_id, "status": status, "end_time": datetime.now().isoformat()}

    # ==================== 停止控制（内存级）====================

    def get_stop_event(self, session_id: str) -> asyncio.Event:
        """
        获取 session 的停止事件（如果不存在则创建）

        Args:
            session_id: Session ID

        Returns:
            asyncio.Event 实例
        """
        if session_id not in self._stop_events:
            self._stop_events[session_id] = asyncio.Event()
        return self._stop_events[session_id]

    def is_stopped(self, session_id: str) -> bool:
        """
        检查 session 是否已被请求停止（内存检查，无 IO）

        Args:
            session_id: Session ID

        Returns:
            是否已停止
        """
        event = self._stop_events.get(session_id)
        return event.is_set() if event else False

    def clear_stop_event(self, session_id: str) -> None:
        """
        清理 session 的停止事件（session 结束时调用）

        Args:
            session_id: Session ID
        """
        self._stop_events.pop(session_id, None)

    # ==================== 状态一致性（V11 回滚）====================

    def register_state_manager(self, session_id: str, manager: Any) -> None:
        """
        注册 session 的状态一致性管理器（供回滚 API 使用）

        Args:
            session_id: Session ID
            manager: StateConsistencyManager 实例
        """
        self._state_managers[session_id] = manager
        logger.debug(f"已注册 state_manager: session_id={session_id}")

    def get_state_manager(self, session_id: str) -> Optional[Any]:
        """获取 session 的状态一致性管理器"""
        return self._state_managers.get(session_id)

    def unregister_state_manager(self, session_id: str) -> None:
        """注销 session 的状态一致性管理器"""
        self._state_managers.pop(session_id, None)
        logger.debug(f"已注销 state_manager: session_id={session_id}")

    # ==================== 长任务确认（V11）====================

    def get_long_run_confirm_event(self, session_id: str) -> asyncio.Event:
        """获取或创建长任务确认事件（执行器 await 此事件）"""
        if session_id not in self._long_run_confirm_events:
            self._long_run_confirm_events[session_id] = asyncio.Event()
        return self._long_run_confirm_events[session_id]

    def confirm_long_running(self, session_id: str, action: str = "continue") -> None:
        """
        用户确认长任务处理方式（前端调用后 set 事件，执行器继续）

        Args:
            session_id: Session ID
            action: "continue"（前台继续） 或 "background"（转后台执行）
        """
        self._long_run_confirm_results[session_id] = action
        ev = self._long_run_confirm_events.get(session_id)
        if ev:
            ev.set()
            logger.debug(f"长任务已确认: session_id={session_id}, action={action}")

    async def wait_long_run_confirm(
        self, session_id: str, timeout: float = 300.0
    ) -> str:
        """
        等待用户确认长任务处理方式（执行器在 yield long_running_confirm 后调用）

        Returns:
            "continue" 前台继续, "background" 转后台, "timeout" 超时
        """
        ev = self.get_long_run_confirm_event(session_id)
        try:
            await asyncio.wait_for(ev.wait(), timeout=timeout)
            return self._long_run_confirm_results.pop(session_id, "continue")
        except asyncio.TimeoutError:
            logger.warning(f"长任务确认超时: session_id={session_id}")
            return "timeout"
        finally:
            ev.clear()
            self._long_run_confirm_events.pop(session_id, None)

    # ==================== HITL 危险操作确认（V11.1）====================

    def get_hitl_confirm_event(self, session_id: str) -> asyncio.Event:
        """获取或创建 HITL 确认事件"""
        if session_id not in self._hitl_confirm_events:
            self._hitl_confirm_events[session_id] = asyncio.Event()
        return self._hitl_confirm_events[session_id]

    def submit_hitl_confirm(self, session_id: str, approved: bool) -> None:
        """
        用户提交 HITL 确认结果（前端调用后 set 事件，执行器继续）

        Args:
            session_id: Session ID
            approved: True=批准执行 / False=拒绝执行
        """
        self._hitl_confirm_results[session_id] = "approve" if approved else "reject"
        ev = self._hitl_confirm_events.get(session_id)
        if ev:
            ev.set()
            logger.info(
                f"HITL 确认已提交: session_id={session_id}, "
                f"approved={approved}"
            )

    async def wait_hitl_confirm(
        self, session_id: str, timeout: float = 300.0
    ) -> str:
        """
        等待用户 HITL 确认（执行器在 yield hitl_confirm 后调用）

        Args:
            session_id: Session ID
            timeout: 超时秒数（默认 5 分钟）

        Returns:
            "approve" 表示用户批准执行，"reject" 表示拒绝
        """
        ev = self.get_hitl_confirm_event(session_id)
        try:
            await asyncio.wait_for(ev.wait(), timeout=timeout)
            return self._hitl_confirm_results.get(session_id, "reject")
        except asyncio.TimeoutError:
            logger.warning(f"HITL 确认超时（默认拒绝）: session_id={session_id}")
            return "reject"
        finally:
            ev.clear()
            self._hitl_confirm_events.pop(session_id, None)
            self._hitl_confirm_results.pop(session_id, None)

    # ==================== V12: 回溯耗尽确认 ====================

    def submit_backtrack_confirm(self, session_id: str, choice: str) -> None:
        """
        User submits backtrack-exhausted choice (retry / rollback / stop).

        Args:
            session_id: Session ID
            choice: "retry" / "rollback" / "stop"
        """
        self._backtrack_confirm_results[session_id] = choice
        ev = self._backtrack_confirm_events.get(session_id)
        if ev:
            ev.set()
            logger.info(
                f"回溯确认已提交: session_id={session_id}, choice={choice}"
            )

    async def wait_backtrack_confirm(
        self, session_id: str, timeout: float = 300.0
    ) -> str:
        """
        Wait for user backtrack-exhausted choice (executor awaits after yield).

        Returns:
            "retry" / "rollback" / "stop"; defaults to "stop" on timeout.
        """
        if session_id not in self._backtrack_confirm_events:
            self._backtrack_confirm_events[session_id] = asyncio.Event()
        ev = self._backtrack_confirm_events[session_id]
        try:
            await asyncio.wait_for(ev.wait(), timeout=timeout)
            return self._backtrack_confirm_results.get(session_id, "stop")
        except asyncio.TimeoutError:
            logger.warning(f"回溯确认超时（默认停止）: session_id={session_id}")
            return "stop"
        finally:
            ev.clear()
            self._backtrack_confirm_events.pop(session_id, None)
            self._backtrack_confirm_results.pop(session_id, None)

    # ==================== V12: 费用确认 ====================

    def submit_cost_confirm(self, session_id: str, choice: str) -> None:
        """
        User submits cost-limit choice (continue / stop).

        Args:
            session_id: Session ID
            choice: "continue" / "stop"
        """
        self._cost_confirm_results[session_id] = choice
        ev = self._cost_confirm_events.get(session_id)
        if ev:
            ev.set()
            logger.info(
                f"费用确认已提交: session_id={session_id}, choice={choice}"
            )

    async def wait_cost_confirm(
        self, session_id: str, timeout: float = 300.0
    ) -> str:
        """
        Wait for user cost-limit choice (executor awaits after yield).

        Returns:
            "continue" / "stop"; defaults to "stop" on timeout.
        """
        if session_id not in self._cost_confirm_events:
            self._cost_confirm_events[session_id] = asyncio.Event()
        ev = self._cost_confirm_events[session_id]
        try:
            await asyncio.wait_for(ev.wait(), timeout=timeout)
            return self._cost_confirm_results.get(session_id, "stop")
        except asyncio.TimeoutError:
            logger.warning(f"费用确认超时（默认停止）: session_id={session_id}")
            return "stop"
        finally:
            ev.clear()
            self._cost_confirm_events.pop(session_id, None)
            self._cost_confirm_results.pop(session_id, None)

    # ==================== V12: 意图澄清 ====================

    def submit_intent_clarify(self, session_id: str, text: str) -> None:
        """
        User submits clarification text for ambiguous intent.

        Args:
            session_id: Session ID
            text: User clarification text
        """
        self._intent_clarify_results[session_id] = text
        ev = self._intent_clarify_events.get(session_id)
        if ev:
            ev.set()
            logger.info(
                f"意图澄清已提交: session_id={session_id}, "
                f"text={text[:50]}..."
            )

    async def wait_intent_clarify(
        self, session_id: str, timeout: float = 300.0
    ) -> str:
        """
        Wait for user intent clarification (executor awaits after yield).

        Returns:
            User clarification text; defaults to empty string on timeout.
        """
        if session_id not in self._intent_clarify_events:
            self._intent_clarify_events[session_id] = asyncio.Event()
        ev = self._intent_clarify_events[session_id]
        try:
            await asyncio.wait_for(ev.wait(), timeout=timeout)
            return self._intent_clarify_results.get(session_id, "")
        except asyncio.TimeoutError:
            logger.warning(f"意图澄清超时: session_id={session_id}")
            return ""
        finally:
            ev.clear()
            self._intent_clarify_events.pop(session_id, None)
            self._intent_clarify_results.pop(session_id, None)

    # ==================== V12.2: 同工具循环确认 ====================

    def submit_tool_loop_confirm(self, session_id: str, choice: str) -> None:
        """
        User submits tool-loop choice (continue / stop).

        Args:
            session_id: Session ID
            choice: "continue" / "stop"
        """
        self._tool_loop_confirm_results[session_id] = choice
        ev = self._tool_loop_confirm_events.get(session_id)
        if ev:
            ev.set()
            logger.info(
                f"同工具循环确认已提交: session_id={session_id}, choice={choice}"
            )

    async def wait_tool_loop_confirm(
        self, session_id: str, timeout: float = 300.0
    ) -> str:
        """
        Wait for user tool-loop choice (executor awaits after yield).

        Returns:
            "continue" / "stop"; defaults to "stop" on timeout.
        """
        if session_id not in self._tool_loop_confirm_events:
            self._tool_loop_confirm_events[session_id] = asyncio.Event()
        ev = self._tool_loop_confirm_events[session_id]
        try:
            await asyncio.wait_for(ev.wait(), timeout=timeout)
            return self._tool_loop_confirm_results.get(session_id, "stop")
        except asyncio.TimeoutError:
            logger.warning(f"同工具循环确认超时（默认停止）: session_id={session_id}")
            return "stop"
        finally:
            ev.clear()
            self._tool_loop_confirm_events.pop(session_id, None)
            self._tool_loop_confirm_results.pop(session_id, None)

    async def stop_session(self, session_id: str) -> Dict[str, Any]:
        """
        停止正在运行的 Session（用户主动中断）

        流程：
        1. 设置内存级停止事件（立即生效）
        2. 立即标记为 stopped 并从活跃列表移除
        3. chat_service 事件循环检测到事件后会发送相关事件

        Args:
            session_id: Session ID

        Returns:
            停止结果

        Raises:
            SessionNotFoundError: Session 不存在
        """
        # 检查 Session 是否存在
        status = await self.store.get_session_status(session_id)
        if not status:
            raise SessionNotFoundError(f"Session 不存在或已过期: session_id={session_id}")

        # 设置内存级停止事件（立即生效，chat_service 会检测并处理）
        stop_event = self.get_stop_event(session_id)
        stop_event.set()

        # 立即调用 end_session 完成清理（更新状态、从活跃列表移除）
        await self.end_session(session_id, status="stopped")

        logger.info(f"🛑 已停止 Session 并完成清理: session_id={session_id}")

        return {
            "session_id": session_id,
            "status": "stopped",
            "stopped_at": datetime.now().isoformat(),
        }

    async def cleanup_inactive_sessions(self) -> int:
        """
        清理不活跃的 Session

        Returns:
            清理的 Session 数量，-1 表示未获取到锁
        """
        # 清理不活跃 Session
        result = await self.store.cleanup_with_lock()

        if result > 0:
            logger.info(f"🧹 清理了 {result} 个超时的 Session")
        elif result == -1:
            logger.debug("⏭️ 清理任务已在运行中，跳过")

        return result

    # ==================== Session 状态查询 ====================

    async def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """
        获取 Session 状态

        Args:
            session_id: Session ID

        Returns:
            Session 状态

        Raises:
            SessionNotFoundError: Session 不存在或已过期
        """
        status = await self.store.get_session_status(session_id)

        if not status:
            raise SessionNotFoundError(f"Session 不存在或已过期: session_id={session_id}")

        return status

    async def get_session_info(self, session_id: str) -> Dict[str, Any]:
        """
        获取 Session 信息

        Args:
            session_id: Session ID

        Returns:
            Session 信息

        Raises:
            SessionNotFoundError: Session 不存在
        """
        return await self.get_session_status(session_id)

    async def list_sessions(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出活跃 Session

        Args:
            user_id: 用户 ID（可选，不提供则返回所有）

        Returns:
            Session 列表
        """
        if user_id:
            return await self.store.get_user_sessions_detail(user_id)
        else:
            # 获取所有活跃 Session
            return await self.store.list_active_sessions()

    # ==================== Session 事件管理 ====================

    async def get_session_events(
        self, session_id: str, after_id: Optional[int] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取 Session 的事件列表（用于断线重连）

        Args:
            session_id: Session ID
            after_id: 从哪个 event_id 之后开始（可选）
            limit: 最多返回多少个事件

        Returns:
            事件列表

        Raises:
            SessionNotFoundError: Session 不存在
        """
        # 检查 Session 是否存在
        if not await self.store.get_session_status(session_id):
            raise SessionNotFoundError(f"Session 不存在: session_id={session_id}")

        # 获取事件
        events = await self.store.get_events(session_id=session_id, after_id=after_id, limit=limit)

        return events

    async def get_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取用户的所有活跃 Session

        Args:
            user_id: 用户 ID

        Returns:
            Session 列表（包含详细信息）
        """
        return await self.store.get_user_sessions_detail(user_id)

    # ==================== 辅助方法 ====================

    async def log_session_status(
        self, session_id: str, conversation_id: Optional[str] = None
    ) -> None:
        """
        输出 Session 状态信息

        Args:
            session_id: Session ID
            conversation_id: Conversation ID（可选）
        """
        try:
            status = await self.store.get_session_status(session_id)

            if status:
                logger.info(
                    f"📊 Session 状态: session_id={session_id}, conversation_id={conversation_id}, "
                    f"status={status.get('status', 'unknown')}"
                )
            else:
                logger.warning(f"⚠️ Session 不存在: session_id={session_id}")
        except SessionNotFoundError:
            logger.warning(f"⚠️ Session 不存在: session_id={session_id}")


# ==================== 便捷函数 ====================

_default_service: Optional[SessionService] = None


def get_session_service() -> SessionService:
    """获取默认 Session 服务单例"""
    global _default_service
    if _default_service is None:
        _default_service = SessionService()
    return _default_service

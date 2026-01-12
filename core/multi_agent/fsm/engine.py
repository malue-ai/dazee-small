"""
FSM 状态机引擎

职责：
- 管理 Multi-Agent 任务生命周期
- 验证状态转换合法性
- 持久化状态到 PlanMemory（检查点）
- 发布状态变更事件

设计原则：
- 复用 EventManager 发布事件
- 复用 PlanMemory 持久化状态
- 支持检查点恢复
"""

import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass

from logger import get_logger
from .states import TaskState, TaskStatus, SubTaskState, SubTaskStatus
from .transitions import (
    is_valid_transition, 
    get_next_status, 
    get_valid_events,
    is_terminal_status,
    get_transition_description
)

logger = get_logger("fsm_engine")


class InvalidTransitionError(Exception):
    """非法状态转换错误"""
    
    def __init__(self, from_status: TaskStatus, event: str, valid_events: set):
        self.from_status = from_status
        self.event = event
        self.valid_events = valid_events
        super().__init__(
            f"非法状态转换: {from_status.value} + {event}. "
            f"合法事件: {valid_events}"
        )


class TaskNotFoundError(Exception):
    """任务不存在错误"""
    pass


@dataclass
class TransitionResult:
    """状态转换结果"""
    success: bool
    from_status: TaskStatus
    to_status: TaskStatus
    event: str
    task_state: TaskState
    error: Optional[str] = None


class FSMEngine:
    """
    有限状态机引擎
    
    管理 Multi-Agent 任务的完整生命周期
    
    特性：
    - 严格的状态转换验证
    - 自动持久化（检查点）
    - 事件发布（与 EventManager 集成）
    - 检查点恢复
    
    使用示例：
        engine = FSMEngine(
            state_store=memory_manager.plan,
            event_manager=event_manager
        )
        
        # 创建任务
        state = await engine.create_task(
            task_id="task-123",
            session_id="sess-456",
            user_query="重构代码并补充测试"
        )
        
        # 状态转换
        result = await engine.transition(
            task_id="task-123",
            event="start"
        )
    """
    
    def __init__(
        self,
        state_store=None,           # PlanMemory 实例（用于持久化）
        event_manager=None,         # EventManager 实例（用于事件发布）
        auto_checkpoint: bool = True,
        checkpoint_interval: int = 1  # 每隔几次转换保存一次检查点
    ):
        """
        初始化 FSM 引擎
        
        Args:
            state_store: PlanMemory 实例，用于持久化状态
            event_manager: EventManager 实例，用于发布事件
            auto_checkpoint: 是否自动保存检查点
            checkpoint_interval: 检查点保存间隔
        """
        self.state_store = state_store
        self.event_manager = event_manager
        self.auto_checkpoint = auto_checkpoint
        self.checkpoint_interval = checkpoint_interval
        
        # 内存缓存（热数据）
        self._task_cache: Dict[str, TaskState] = {}
        
        # 转换计数（用于检查点间隔）
        self._transition_counts: Dict[str, int] = {}
        
        # 状态变更回调
        self._on_transition_callbacks: list = []
        
        logger.info("✅ FSMEngine 初始化完成")
    
    # ==================== 任务生命周期管理 ====================
    
    async def create_task(
        self,
        task_id: str,
        session_id: str,
        user_query: str
    ) -> TaskState:
        """
        创建新任务
        
        Args:
            task_id: 任务 ID
            session_id: 会话 ID
            user_query: 用户原始请求
            
        Returns:
            初始化的 TaskState
        """
        state = TaskState(
            task_id=task_id,
            session_id=session_id,
            user_query=user_query,
            status=TaskStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # 缓存
        self._task_cache[task_id] = state
        self._transition_counts[task_id] = 0
        
        # 持久化
        if self.state_store:
            await self._save_to_store(state)
        
        # 发布事件
        await self._emit_task_event("task.created", state)
        
        logger.info(f"FSM 任务创建: task_id={task_id}, session_id={session_id}")
        
        return state
    
    async def get_task(self, task_id: str) -> Optional[TaskState]:
        """
        获取任务状态
        
        优先从缓存读取，缓存未命中则从存储读取
        """
        # 先查缓存
        if task_id in self._task_cache:
            return self._task_cache[task_id]
        
        # 从存储读取
        if self.state_store:
            state = await self._load_from_store(task_id)
            if state:
                self._task_cache[task_id] = state
                return state
        
        return None
    
    async def transition(
        self,
        task_id: str,
        event: str,
        data: Dict[str, Any] = None
    ) -> TransitionResult:
        """
        执行状态转换
        
        Args:
            task_id: 任务 ID
            event: 触发事件（如 start, decompose_complete）
            data: 转换附带数据
            
        Returns:
            TransitionResult
            
        Raises:
            TaskNotFoundError: 任务不存在
            InvalidTransitionError: 非法状态转换
        """
        # 1. 获取当前状态
        state = await self.get_task(task_id)
        if not state:
            raise TaskNotFoundError(f"任务不存在: {task_id}")
        
        from_status = state.status
        
        # 2. 验证转换合法性
        if not is_valid_transition(from_status, event):
            valid_events = get_valid_events(from_status)
            raise InvalidTransitionError(from_status, event, valid_events)
        
        # 3. 获取目标状态
        to_status = get_next_status(from_status, event)
        
        # 4. 执行转换
        state.status = to_status
        state.updated_at = datetime.now()
        state.current_phase = get_transition_description(event)
        
        # 更新进度
        state.progress = state.calculate_progress()
        
        # 更新时间戳
        if to_status == TaskStatus.DECOMPOSING:
            state.started_at = datetime.now()
        elif is_terminal_status(to_status):
            state.completed_at = datetime.now()
        
        # 处理附带数据
        if data:
            self._apply_transition_data(state, event, data)
        
        # 5. 更新缓存
        self._task_cache[task_id] = state
        
        # 6. 增量检查点
        self._transition_counts[task_id] = self._transition_counts.get(task_id, 0) + 1
        if self.auto_checkpoint and self._should_checkpoint(task_id):
            await self._save_checkpoint(state)
        
        # 7. 发布事件
        await self._emit_transition_event(state, from_status, to_status, event)
        
        # 8. 执行回调
        await self._execute_callbacks(state, from_status, to_status, event)
        
        logger.info(
            f"FSM 状态转换: {from_status.value} → {to_status.value} "
            f"(event={event}, task_id={task_id})"
        )
        
        return TransitionResult(
            success=True,
            from_status=from_status,
            to_status=to_status,
            event=event,
            task_state=state
        )
    
    # ==================== 子任务管理 ====================
    
    async def add_sub_tasks(
        self,
        task_id: str,
        sub_tasks: list[SubTaskState]
    ) -> TaskState:
        """
        添加子任务
        
        在 DECOMPOSING → PLANNING 转换时调用
        """
        state = await self.get_task(task_id)
        if not state:
            raise TaskNotFoundError(f"任务不存在: {task_id}")
        
        state.sub_tasks = sub_tasks
        state.updated_at = datetime.now()
        
        self._task_cache[task_id] = state
        
        logger.info(f"FSM 添加 {len(sub_tasks)} 个子任务: task_id={task_id}")
        
        return state
    
    async def update_sub_task(
        self,
        task_id: str,
        sub_task_id: str,
        status: SubTaskStatus = None,
        result: Dict[str, Any] = None,
        error: str = None,
        worker_id: str = None
    ) -> TaskState:
        """
        更新子任务状态
        """
        state = await self.get_task(task_id)
        if not state:
            raise TaskNotFoundError(f"任务不存在: {task_id}")
        
        sub_task = state.get_sub_task(sub_task_id)
        if not sub_task:
            raise ValueError(f"子任务不存在: {sub_task_id}")
        
        # 更新字段
        if status:
            sub_task.status = status
            if status == SubTaskStatus.RUNNING:
                sub_task.started_at = datetime.now()
            elif status in {SubTaskStatus.COMPLETED, SubTaskStatus.FAILED}:
                sub_task.completed_at = datetime.now()
        
        if result is not None:
            sub_task.result = result
        
        if error is not None:
            sub_task.error = error
            sub_task.attempt_count += 1
        
        if worker_id is not None:
            sub_task.worker_id = worker_id
        
        state.updated_at = datetime.now()
        state.progress = state.calculate_progress()
        
        self._task_cache[task_id] = state
        
        # 发布子任务事件
        await self._emit_sub_task_event(state, sub_task)
        
        return state
    
    # ==================== 检查点恢复 ====================
    
    async def restore_from_checkpoint(self, task_id: str) -> Optional[TaskState]:
        """
        从检查点恢复任务状态
        
        用于服务重启后恢复长任务
        """
        if not self.state_store:
            logger.warning("无法恢复检查点：未配置 state_store")
            return None
        
        state = await self._load_from_store(task_id)
        if state:
            self._task_cache[task_id] = state
            logger.info(
                f"FSM 检查点恢复: task_id={task_id}, "
                f"status={state.status.value}, "
                f"checkpoint_version={state.checkpoint_version}"
            )
            return state
        
        return None
    
    async def list_recoverable_tasks(self, session_id: str = None) -> list[TaskState]:
        """
        列出可恢复的任务（非终态）
        """
        if not self.state_store:
            return []
        
        # 从存储中查询非终态任务
        # 这需要 PlanMemory 支持列表查询
        # TODO: 实现具体查询逻辑
        return []
    
    # ==================== 内部方法 ====================
    
    def _apply_transition_data(
        self,
        state: TaskState,
        event: str,
        data: Dict[str, Any]
    ):
        """应用转换附带数据"""
        if event == "decompose_complete":
            state.decomposition_reasoning = data.get("reasoning", "")
            state.parallelizable_groups = data.get("parallelizable_groups", [])
        
        elif event in {"aggregate_complete", "validation_pass"}:
            state.final_result = data.get("result")
        
        elif event in {"decompose_error", "execution_error", "aggregate_error"}:
            state.final_error = data.get("error")
    
    def _should_checkpoint(self, task_id: str) -> bool:
        """判断是否应该保存检查点"""
        count = self._transition_counts.get(task_id, 0)
        return count % self.checkpoint_interval == 0
    
    async def _save_checkpoint(self, state: TaskState):
        """保存检查点"""
        state.checkpoint_version += 1
        state.last_checkpoint_at = datetime.now()
        
        if self.state_store:
            await self._save_to_store(state)
            logger.debug(
                f"FSM 检查点已保存: task_id={state.task_id}, "
                f"version={state.checkpoint_version}"
            )
    
    async def _save_to_store(self, state: TaskState):
        """保存到存储"""
        if self.state_store:
            # 使用 PlanMemory 的接口
            # 格式：将 TaskState 序列化为 plan 格式
            # 注意：PlanMemory.save_plan() 是同步函数，不能 await
            self.state_store.save_plan(
                task_id=state.task_id,  # ✅ 修正参数名：task_id（与 PlanMemory 接口一致）
                goal=state.user_query,
                steps=[sub_task.__dict__ for sub_task in state.sub_tasks],
                user_query=state.user_query,
                metadata={
                    "type": "multi_agent_task",
                    "state": state.to_dict()
                }
            )
    
    async def _load_from_store(self, task_id: str) -> Optional[TaskState]:
        """从存储加载"""
        if not self.state_store:
            return None
        
        plan_data = await self.state_store.load_plan(task_id)
        if plan_data and plan_data.get("type") == "multi_agent_task":
            return TaskState.from_dict(plan_data["state"])
        
        return None
    
    async def _emit_task_event(self, event_type: str, state: TaskState):
        """发布任务事件"""
        if not self.event_manager:
            return
        
        try:
            # 🔧 V6.0: 使用 emit_conversation_delta 而非 emit_plan_update
            await self.event_manager.conversation.emit_conversation_delta(
                session_id=state.session_id,
                conversation_id=state.session_id,  # Multi-Agent 场景使用 session_id 作为 conversation_id
                delta={"plan": state.to_plan_event()}
            )
        except Exception as e:
            logger.warning(f"发布任务事件失败: {e}")
    
    async def _emit_transition_event(
        self,
        state: TaskState,
        from_status: TaskStatus,
        to_status: TaskStatus,
        event: str
    ):
        """发布状态转换事件"""
        if not self.event_manager:
            return
        
        try:
            # 🔧 V6.0: 使用 emit_conversation_delta 而非 emit_plan_update
            await self.event_manager.conversation.emit_conversation_delta(
                session_id=state.session_id,
                conversation_id=state.session_id,  # Multi-Agent 场景使用 session_id 作为 conversation_id
                delta={
                    "plan": {
                        **state.to_plan_event(),
                        "transition": {
                            "from": from_status.value,
                            "to": to_status.value,
                            "event": event,
                            "description": get_transition_description(event)
                        }
                    }
                }
            )
        except Exception as e:
            logger.warning(f"发布转换事件失败: {e}")
    
    async def _emit_sub_task_event(self, state: TaskState, sub_task: SubTaskState):
        """发布子任务事件"""
        if not self.event_manager:
            return
        
        try:
            # 🔧 V6.0: 使用 emit_conversation_delta 而非 emit_plan_update
            await self.event_manager.conversation.emit_conversation_delta(
                session_id=state.session_id,
                conversation_id=state.session_id,  # Multi-Agent 场景使用 session_id 作为 conversation_id
                delta={
                    "plan": {
                        "task_id": state.task_id,
                        "sub_task_update": sub_task.to_dict(),
                        "progress": state.progress
                    }
                }
            )
        except Exception as e:
            logger.warning(f"发布子任务事件失败: {e}")
    
    async def _execute_callbacks(
        self,
        state: TaskState,
        from_status: TaskStatus,
        to_status: TaskStatus,
        event: str
    ):
        """执行状态变更回调"""
        for callback in self._on_transition_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(state, from_status, to_status, event)
                else:
                    callback(state, from_status, to_status, event)
            except Exception as e:
                logger.error(f"状态转换回调执行失败: {e}")
    
    # ==================== 回调注册 ====================
    
    def on_transition(
        self,
        callback: Callable[[TaskState, TaskStatus, TaskStatus, str], Awaitable[None]]
    ):
        """
        注册状态转换回调
        
        Args:
            callback: 回调函数，签名 (state, from_status, to_status, event) -> None
        """
        self._on_transition_callbacks.append(callback)


def create_fsm_engine(
    state_store=None,
    event_manager=None,
    **kwargs
) -> FSMEngine:
    """
    创建 FSM 引擎实例
    
    工厂函数，便于依赖注入
    """
    return FSMEngine(
        state_store=state_store,
        event_manager=event_manager,
        **kwargs
    )

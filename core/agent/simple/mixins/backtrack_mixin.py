"""
回溯能力 Mixin

V8.0 新增

职责：
- 提供业务逻辑层错误的回溯能力
- 可被任何 Agent 类型混入使用

回溯类型：
- PLAN_REPLAN: Plan 重规划
- TOOL_REPLACE: 工具替换
- PARAM_ADJUST: 参数调整
- CONTEXT_ENRICH: 上下文补充
- INTENT_CLARIFY: 意图澄清

依赖的属性（由具体 Agent 类提供）：
- llm: LLMService
- tool_executor: ToolExecutor
- tool_selector: ToolSelector（可选）
- context_engineering: ContextEngineeringManager
- broadcaster: EventBroadcaster
- _plan_cache: dict
"""

import json
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, AsyncGenerator, TYPE_CHECKING

from core.agent.backtrack import (
    ErrorClassifier,
    BacktrackManager,
    BacktrackContext,
    BacktrackDecision,
    BacktrackResult,
    BacktrackType,
    ClassifiedError,
    get_error_classifier,
    get_backtrack_manager,
)
from core.agent.simple.errors import record_tool_error
from utils.message_utils import (
    dict_list_to_messages,
    append_assistant_message,
    append_user_message
)
from logger import get_logger

if TYPE_CHECKING:
    from core.context.runtime import RuntimeContext

logger = get_logger(__name__)


@dataclass
class RVRBState:
    """RVR-B 循环状态"""
    session_id: str
    turn: int = 0
    max_turns: int = 10
    backtrack_count: int = 0
    max_backtracks: int = 3
    
    # 执行历史
    execution_history: List[Dict[str, Any]] = field(default_factory=list)
    
    # 失败记录
    failed_tools: List[str] = field(default_factory=list)
    failed_strategies: List[str] = field(default_factory=list)
    
    # Plan 相关
    current_plan: Optional[Dict[str, Any]] = None
    current_step_index: int = 0
    
    # 最近的错误
    last_error: Optional[ClassifiedError] = None
    
    def record_execution(
        self,
        action: str,
        success: bool,
        result: Any = None,
        error: Optional[Exception] = None
    ):
        """记录执行历史"""
        self.execution_history.append({
            "turn": self.turn,
            "action": action,
            "success": success,
            "result": str(result)[:200] if result else None,
            "error": str(error) if error else None,
        })
        
        if len(self.execution_history) > 50:
            self.execution_history = self.execution_history[-50:]
    
    def record_tool_failure(self, tool_name: str):
        """记录工具失败"""
        if tool_name not in self.failed_tools:
            self.failed_tools.append(tool_name)
    
    def increment_backtrack(self):
        """增加回溯计数"""
        self.backtrack_count += 1
    
    def can_backtrack(self) -> bool:
        """是否还可以回溯"""
        return self.backtrack_count < self.max_backtracks
    
    def to_backtrack_context(self, error: ClassifiedError) -> BacktrackContext:
        """转换为 BacktrackContext"""
        return BacktrackContext(
            session_id=self.session_id,
            turn=self.turn,
            max_turns=self.max_turns,
            error=error,
            execution_history=self.execution_history,
            backtrack_count=self.backtrack_count,
            max_backtracks=self.max_backtracks,
            current_plan=self.current_plan,
            current_step_index=self.current_step_index,
            failed_tools=self.failed_tools.copy(),
            failed_strategies=self.failed_strategies.copy(),
        )


class BacktrackMixin:
    """
    回溯能力 Mixin
    
    为 Agent 提供业务逻辑层错误的回溯恢复能力。
    
    使用方式：
        class RVRBAgent(SimpleAgent, BacktrackMixin):
            def __init__(self, max_backtracks=3, **kwargs):
                SimpleAgent.__init__(self, **kwargs)
                BacktrackMixin.__init__(self, max_backtracks)
    
    提供的方法：
    - _init_backtrack(): 初始化回溯组件
    - _get_rvrb_state(): 获取/创建状态
    - _evaluate_backtrack(): 评估是否需要回溯
    - _handle_tool_error_with_backtrack(): 带回溯的工具错误处理
    - _try_alternative_tool(): 尝试替代工具
    - _run_rvr_loop_with_backtrack(): RVR-B 主循环
    """
    
    def _init_backtrack(self, max_backtracks: int = 3):
        """
        初始化回溯组件
        
        Args:
            max_backtracks: 最大回溯次数
        """
        self._max_backtracks = max_backtracks
        self._error_classifier: Optional[ErrorClassifier] = None
        self._backtrack_manager: Optional[BacktrackManager] = None
        self._rvrb_states: Dict[str, RVRBState] = {}
        
        logger.debug(f"✅ BacktrackMixin 初始化: max_backtracks={max_backtracks}")
    
    @property
    def error_classifier(self) -> ErrorClassifier:
        """错误分类器（延迟初始化）"""
        if self._error_classifier is None:
            self._error_classifier = get_error_classifier()
        return self._error_classifier
    
    @property
    def backtrack_manager(self) -> BacktrackManager:
        """回溯管理器（延迟初始化）"""
        if self._backtrack_manager is None:
            self._backtrack_manager = get_backtrack_manager(self.llm)
        return self._backtrack_manager
    
    def _get_rvrb_state(self, session_id: str) -> RVRBState:
        """获取或创建 RVR-B 状态"""
        if session_id not in self._rvrb_states:
            self._rvrb_states[session_id] = RVRBState(
                session_id=session_id,
                max_turns=self.max_turns,
                max_backtracks=self._max_backtracks,
            )
        return self._rvrb_states[session_id]
    
    def _clear_rvrb_state(self, session_id: str):
        """清除 RVR-B 状态"""
        if session_id in self._rvrb_states:
            del self._rvrb_states[session_id]
    
    async def _evaluate_backtrack(
        self,
        error: Exception,
        tool_name: str,
        tool_input: Dict[str, Any],
        state: RVRBState
    ) -> BacktrackResult:
        """
        评估是否需要回溯
        
        Args:
            error: 异常对象
            tool_name: 工具名称
            tool_input: 工具输入
            state: RVR-B 状态
            
        Returns:
            BacktrackResult: 回溯决策
        """
        # 分类错误
        classified_error = self.error_classifier.classify_tool_error(
            error=error,
            tool_name=tool_name,
            tool_input=tool_input,
        )
        
        state.last_error = classified_error
        state.record_tool_failure(tool_name)
        
        # 基础设施层错误不需要回溯
        if classified_error.is_infrastructure_error():
            logger.info(f"📦 基础设施层错误，委托给 resilience 机制")
            return BacktrackResult(
                decision=BacktrackDecision.CONTINUE,
                backtrack_type=BacktrackType.NO_BACKTRACK,
                action={"delegate_to": "resilience"},
                reason="基础设施层错误",
                confidence=1.0,
            )
        
        # 检查是否还可以回溯
        if not state.can_backtrack():
            logger.warning(f"⚠️ 已达最大回溯次数 ({state.max_backtracks})")
            return BacktrackResult(
                decision=BacktrackDecision.FAIL_GRACEFULLY,
                backtrack_type=BacktrackType.NO_BACKTRACK,
                action={"message": "已达最大回溯次数"},
                reason=f"已尝试 {state.backtrack_count} 次回溯",
                confidence=1.0,
            )
        
        # 业务逻辑层错误，进行回溯评估
        backtrack_ctx = state.to_backtrack_context(classified_error)
        result = await self.backtrack_manager.evaluate_and_decide(
            backtrack_ctx,
            use_llm=True
        )
        
        if result.decision == BacktrackDecision.BACKTRACK:
            state.increment_backtrack()
        
        return result
    
    async def _handle_tool_error_with_backtrack(
        self,
        error: Exception,
        tool_name: str,
        tool_input: Dict[str, Any],
        state: RVRBState,
        session_id: str
    ) -> tuple[str, bool, Optional[Dict]]:
        """
        带回溯的工具错误处理
        
        Args:
            error: 异常对象
            tool_name: 工具名称
            tool_input: 工具输入
            state: RVR-B 状态
            session_id: 会话 ID
            
        Returns:
            (result_content, is_error, backtrack_event): 结果内容、是否错误、回溯事件
        """
        # 评估是否需要回溯
        backtrack_result = await self._evaluate_backtrack(
            error=error,
            tool_name=tool_name,
            tool_input=tool_input,
            state=state
        )
        
        backtrack_event = None
        
        if backtrack_result.decision == BacktrackDecision.BACKTRACK:
            logger.info(f"🔄 触发回溯: {backtrack_result.backtrack_type.value}")
            
            # 生成回溯事件
            backtrack_event = {
                "type": "backtrack",
                "data": backtrack_result.to_dict()
            }
            
            # 根据回溯类型处理
            if backtrack_result.backtrack_type == BacktrackType.TOOL_REPLACE:
                alt_result = await self._try_alternative_tool(
                    tool_name, tool_input, state
                )
                if alt_result:
                    state.record_execution(f"backtrack:tool_replace", True, alt_result)
                    return alt_result, False, backtrack_event
            
            # 其他回溯类型：返回错误信息，让 LLM 决定下一步
            result_content = json.dumps({
                "error": str(error),
                "backtrack": backtrack_result.to_dict()
            }, ensure_ascii=False)
            return result_content, True, backtrack_event
        
        # 不需要回溯，正常记录错误
        record_tool_error(self.context_engineering, tool_name, error, tool_input)
        result_content = json.dumps({"error": str(error)}, ensure_ascii=False)
        state.record_execution(f"tool:{tool_name}", False, error=error)
        
        return result_content, True, None
    
    async def _try_alternative_tool(
        self,
        failed_tool: str,
        tool_input: Dict[str, Any],
        state: RVRBState
    ) -> Optional[str]:
        """
        尝试使用替代工具
        
        Args:
            failed_tool: 失败的工具名称
            tool_input: 工具输入
            state: RVR-B 状态
            
        Returns:
            替代工具的执行结果，或 None
        """
        if not hasattr(self, 'tool_selector') or not self.tool_selector:
            return None
        
        if hasattr(self.tool_selector, 'get_alternative_tools'):
            alternatives = self.tool_selector.get_alternative_tools(failed_tool)
        else:
            return None
        
        for alt_tool in alternatives:
            if alt_tool in state.failed_tools:
                continue
            
            try:
                logger.info(f"🔄 尝试替代工具: {alt_tool}")
                result = await self.tool_executor.execute(alt_tool, tool_input)
                result_content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                logger.info(f"✅ 替代工具成功: {alt_tool}")
                return result_content
            except Exception as e:
                logger.warning(f"⚠️ 替代工具也失败: {alt_tool} - {e}")
                state.record_tool_failure(alt_tool)
                continue
        
        return None
    
    async def _run_rvr_loop_with_backtrack(
        self,
        messages: List,
        system_prompt,
        tools_for_llm: List,
        ctx: "RuntimeContext",
        session_id: str,
        intent,
        enable_stream: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        RVR-B 主循环（带回溯）
        
        在标准 RVR 循环基础上添加 Backtrack 决策点。
        
        Args:
            messages: 初始消息列表
            system_prompt: 系统提示词
            tools_for_llm: LLM 工具列表
            ctx: RuntimeContext
            session_id: 会话 ID
            intent: IntentResult
            enable_stream: 是否启用流式
            
        Yields:
            事件字典
        """
        from core.agent.content_handler import create_content_handler
        
        # 初始化 RVR-B 状态
        state = self._get_rvrb_state(session_id)
        state.current_plan = self._plan_cache.get("plan")
        
        # 转换消息
        llm_messages = dict_list_to_messages(messages)
        
        # Context Engineering
        if self.context_engineering and self._plan_cache.get("plan"):
            prepared_messages = self.context_engineering.prepare_messages_for_llm(
                messages=[{"role": m.role, "content": m.content} for m in llm_messages],
                plan=self._plan_cache.get("plan"),
                inject_plan=True,
                inject_errors=True
            )
            llm_messages = dict_list_to_messages(prepared_messages)
        
        for turn in range(self.max_turns):
            ctx.next_turn()
            state.turn = turn
            
            logger.info(f"{'='*60}")
            logger.info(f"🔄 RVR-B Turn {turn + 1}/{self.max_turns} (backtracks: {state.backtrack_count}/{state.max_backtracks})")
            logger.info(f"{'='*60}")
            
            if enable_stream:
                # 流式处理（复用父类方法）
                async for event in self._process_stream(
                    llm_messages, system_prompt, tools_for_llm, ctx, session_id
                ):
                    yield event
                
                response = ctx.last_llm_response
                if response:
                    if response.stop_reason == "tool_use" and response.tool_calls:
                        is_last_turn = (turn == self.max_turns - 1)
                        if is_last_turn:
                            async for event in self._handle_last_turn_tools(
                                response, llm_messages, system_prompt, ctx, session_id
                            ):
                                yield event
                            break
                        
                        # 处理工具调用（带回溯）
                        async for event in self._handle_tool_calls_with_backtrack_stream(
                            response, llm_messages, session_id, ctx, state
                        ):
                            yield event
                    else:
                        ctx.set_completed(response.content, response.stop_reason)
                        state.record_execution("complete", True, response.content)
                        break
            else:
                # 非流式处理
                response = await self.llm.create_message_async(
                    messages=llm_messages,
                    system=system_prompt,
                    tools=tools_for_llm
                )
                
                self.usage_tracker.accumulate(response)
                
                if response.content:
                    yield {"type": "content", "data": {"text": response.content}}
                
                if response.stop_reason != "tool_use":
                    ctx.set_completed(response.content, response.stop_reason)
                    state.record_execution("complete", True, response.content)
                    break
                
                is_last_turn = (turn == self.max_turns - 1)
                if is_last_turn:
                    async for event in self._handle_last_turn_tools_non_stream(
                        response, llm_messages, system_prompt, ctx, session_id
                    ):
                        yield event
                    break
                
                await self._handle_tool_calls_with_backtrack_non_stream(
                    response, llm_messages, session_id, ctx, state
                )
            
            if ctx.is_completed():
                break
        
        # 清理状态
        self._clear_rvrb_state(session_id)
    
    async def _handle_tool_calls_with_backtrack_stream(
        self,
        response,
        llm_messages: List,
        session_id: str,
        ctx: "RuntimeContext",
        state: RVRBState
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """处理工具调用（流式，带回溯）"""
        from core.agent.content_handler import create_content_handler
        
        client_tools = [tc for tc in response.tool_calls if tc.get("type") == "tool_use"]
        server_tools = [tc for tc in response.tool_calls if tc.get("type") == "server_tool_use"]
        
        if server_tools:
            logger.info(f"🌐 服务端工具已执行: {[t.get('name') for t in server_tools]}")
        
        tool_results = []
        content_handler = create_content_handler(self.broadcaster, ctx.block)
        
        for tool_call in client_tools:
            tool_name = tool_call['name']
            tool_input = tool_call['input'] or {}
            tool_id = tool_call['id']
            
            try:
                result = await self.tool_executor.execute(tool_name, tool_input)
                result_content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                is_error = False
                state.record_execution(f"tool:{tool_name}", True, result_content)
                
            except Exception as e:
                logger.error(f"❌ 工具执行失败: {tool_name} - {e}")
                
                # 带回溯的错误处理
                result_content, is_error, backtrack_event = await self._handle_tool_error_with_backtrack(
                    error=e,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    state=state,
                    session_id=session_id
                )
                
                # 发送回溯事件
                if backtrack_event:
                    yield backtrack_event
            
            yield await content_handler.emit_block(
                session_id=session_id,
                block_type="tool_result",
                content={
                    "tool_use_id": tool_id,
                    "content": result_content,
                    "is_error": is_error
                }
            )
            
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result_content,
                "is_error": is_error
            })
        
        append_assistant_message(llm_messages, response.raw_content)
        
        if tool_results:
            append_user_message(llm_messages, tool_results)
    
    async def _handle_tool_calls_with_backtrack_non_stream(
        self,
        response,
        llm_messages: List,
        session_id: str,
        ctx: "RuntimeContext",
        state: RVRBState
    ) -> None:
        """处理工具调用（非流式，带回溯）"""
        client_tools = [tc for tc in response.tool_calls if tc.get("type") == "tool_use"]
        
        append_assistant_message(llm_messages, response.raw_content)
        
        tool_results = []
        for tool_call in client_tools:
            tool_name = tool_call['name']
            tool_input = tool_call['input'] or {}
            tool_id = tool_call['id']
            
            try:
                result = await self.tool_executor.execute(tool_name, tool_input)
                result_content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                is_error = False
                state.record_execution(f"tool:{tool_name}", True, result_content)
                
            except Exception as e:
                logger.error(f"❌ 工具执行失败: {tool_name} - {e}")
                
                result_content, is_error, _ = await self._handle_tool_error_with_backtrack(
                    error=e,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    state=state,
                    session_id=session_id
                )
            
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result_content,
                "is_error": is_error
            })
        
        if tool_results:
            append_user_message(llm_messages, tool_results)

"""
RVRBExecutor - RVR-B 执行策略

实现 React-Validate-Reflect-Backtrack-Repeat 循环。

职责：
- 在 RVR 基础上增加回溯能力
- 工具执行失败时尝试回溯和重试
- 支持 checkpoint 和恢复

回溯类型：
- PLAN_REPLAN: Plan 重规划
- TOOL_REPLACE: 工具替换
- PARAM_ADJUST: 参数调整
- CONTEXT_ENRICH: 上下文补充
- INTENT_CLARIFY: 意图澄清

迁移自：core/agent/simple/mixins/backtrack_mixin.py
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional, Set

from core.agent.backtrack import (
    BacktrackContext,
    BacktrackDecision,
    BacktrackManager,
    BacktrackResult,
    BacktrackType,
    ClassifiedError,
    ErrorClassifier,
    get_backtrack_manager,
    get_error_classifier,
)
from core.agent.errors import record_tool_error
from core.agent.execution.protocol import (
    BaseExecutor,
    ExecutionContext,
    ExecutorConfig,
)
from core.agent.execution.rvr import RVRExecutor
from core.context import stable_json_dumps
from logger import get_logger
from utils.message_utils import (
    append_assistant_message,
    append_user_message,
    dict_list_to_messages,
    messages_to_dict_list,
)

if TYPE_CHECKING:
    from core.context.runtime import RuntimeContext

logger = get_logger(__name__)


def _extract_tool_hints(tool_results: List[Dict[str, Any]]) -> List[str]:
    """Extract _hint values from tool results for mandatory injection into LLM context.

    Checks both top-level and nested result._hint locations, since some tools
    (e.g. nodes) promote _hint to the top level while others may nest it.
    """
    import json

    hints: List[str] = []
    for tr in tool_results:
        content = tr.get("content", "")
        if not isinstance(content, str) or "_hint" not in content:
            continue
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            continue
        hint = data.get("_hint") or (
            data.get("result", {}).get("_hint") if isinstance(data.get("result"), dict) else None
        )
        if hint:
            hints.append(hint)
    return hints


async def _call_async(fn: Any) -> Any:
    """Type-safe wrapper: callable() narrows to (...)->object which isn't Awaitable."""
    return await fn()


@dataclass
class RVRBState:
    """RVR-B 循环状态（V12: 移除冗余 max_turns，统一由 ExecutorConfig 管理）"""

    session_id: str
    turn: int = 0
    backtrack_count: int = 0
    max_backtracks: int = 3

    # 执行历史
    execution_history: List[Dict[str, Any]] = field(default_factory=list)

    # 失败记录
    failed_tools: List[str] = field(default_factory=list)
    failed_strategies: List[str] = field(default_factory=list)

    # 失败路径记忆（记录"工具+参数→失败原因"，引导 LLM 避免重复犯错）
    failed_approaches: List[Dict[str, str]] = field(default_factory=list)

    # 同工具连续失败计数（比精确签名去重更宽泛，捕获参数微调后仍失败的情况）
    _tool_failure_streak: Dict[str, int] = field(default_factory=dict)
    # 因连续失败被动态裁剪的工具（从 tools_for_llm 中移除，物理阻止 LLM 调用）
    pruned_tools: Set[str] = field(default_factory=set)

    # 回溯累计 token 消耗（用于事件上报）
    total_backtrack_tokens: int = 0

    # Plan 相关
    current_plan: Optional[Dict[str, Any]] = None
    current_step_index: int = 0

    # 最近的错误
    last_error: Optional[ClassifiedError] = None

    def record_execution(
        self, action: str, success: bool, result: Any = None, error: Optional[Exception] = None
    ):
        """记录执行历史"""
        self.execution_history.append(
            {
                "turn": self.turn,
                "action": action,
                "success": success,
                "result": str(result)[:200] if result else None,
                "error": str(error) if error else None,
            }
        )

        if len(self.execution_history) > 50:
            self.execution_history = self.execution_history[-50:]

    def record_tool_failure(self, tool_name: str):
        """记录工具失败"""
        if tool_name not in self.failed_tools:
            self.failed_tools.append(tool_name)

    def record_failed_approach(self, tool_name: str, approach: str, reason: str):
        """
        记录失败的方法路径

        用于在回溯反思中注入，引导 LLM 避免重复犯错。

        Args:
            tool_name: 工具名
            approach: 简要描述尝试的方法
            reason: 失败原因
        """
        entry = {"tool": tool_name, "approach": approach, "reason": reason}
        # 避免完全重复
        if entry not in self.failed_approaches:
            self.failed_approaches.append(entry)
        # 只保留最近 10 条
        if len(self.failed_approaches) > 10:
            self.failed_approaches = self.failed_approaches[-10:]

    def increment_backtrack(self):
        """增加回溯计数"""
        self.backtrack_count += 1

    def can_backtrack(self) -> bool:
        """是否还可以回溯"""
        return self.backtrack_count < self.max_backtracks

    def record_tool_outcome(self, tool_name: str, success: bool):
        """记录工具执行结果，维护同工具连续失败计数"""
        if success:
            self._tool_failure_streak[tool_name] = 0
        else:
            self._tool_failure_streak[tool_name] = (
                self._tool_failure_streak.get(tool_name, 0) + 1
            )

    def get_tool_failure_streak(self, tool_name: str) -> int:
        """获取工具连续失败次数"""
        return self._tool_failure_streak.get(tool_name, 0)

    def to_backtrack_context(
        self, error: ClassifiedError, max_turns: int = 200
    ) -> BacktrackContext:
        """Convert to BacktrackContext (max_turns = infrastructure safety limit, not semantic)."""
        return BacktrackContext(
            session_id=self.session_id,
            turn=self.turn,
            max_turns=max_turns,
            error=error,
            execution_history=self.execution_history,
            backtrack_count=self.backtrack_count,
            max_backtracks=self.max_backtracks,
            current_plan=self.current_plan,
            current_step_index=self.current_step_index,
            failed_tools=self.failed_tools.copy(),
            failed_strategies=self.failed_strategies.copy(),
        )


class RVRBExecutor(RVRExecutor):
    """
    RVR-B 执行器

    在 RVR 基础上增加回溯（Backtrack）能力。

    回溯策略：
    1. 检测工具执行失败
    2. 分类错误（基础设施层 vs 业务逻辑层）
    3. 业务逻辑层错误进行回溯评估
    4. 根据回溯类型执行恢复策略

    使用方式：
        executor = RVRBExecutor(config=ExecutorConfig(
            enable_backtrack=True,
            max_backtrack_attempts=3
        ))

        async for event in executor.execute(
            messages=messages,
            context=ExecutionContext(llm=llm, session_id=session_id, ...)
        ):
            yield event
    """

    def __init__(self, config: Optional[ExecutorConfig] = None):
        """初始化 RVR-B 执行器"""
        super().__init__(config)

        # 确保启用回溯
        if self.config:
            self.config.enable_backtrack = True

        # 回溯组件（延迟初始化）
        self._error_classifier: Optional[ErrorClassifier] = None
        self._backtrack_manager: Optional[BacktrackManager] = None

        # 状态管理
        self._rvrb_states: Dict[str, RVRBState] = {}

    @property
    def name(self) -> str:
        return "RVRBExecutor"

    def supports_backtrack(self) -> bool:
        return True

    def _get_error_classifier(self) -> ErrorClassifier:
        """获取错误分类器（延迟初始化）"""
        if self._error_classifier is None:
            self._error_classifier = get_error_classifier()
        return self._error_classifier

    def _get_backtrack_manager(self, llm) -> BacktrackManager:
        """获取回溯管理器（延迟初始化，始终确保 LLM 已注入）"""
        if self._backtrack_manager is None:
            self._backtrack_manager = get_backtrack_manager(llm)
        elif llm and not self._backtrack_manager.llm_service:
            # 确保 LLM 服务已注入（修复首次创建时 LLM 缺失的问题）
            self._backtrack_manager.llm_service = llm
        return self._backtrack_manager

    def _get_rvrb_state(self, session_id: str) -> RVRBState:
        """获取或创建 RVR-B 状态（V12: 移除 max_turns，统一由 ExecutorConfig 管理）"""
        if session_id not in self._rvrb_states:
            self._rvrb_states[session_id] = RVRBState(
                session_id=session_id,
                max_backtracks=self.config.max_backtrack_attempts if self.config else 3,
            )
        return self._rvrb_states[session_id]

    def _clear_rvrb_state(self, session_id: str):
        """清除 RVR-B 状态"""
        if session_id in self._rvrb_states:
            del self._rvrb_states[session_id]

    async def _evaluate_backtrack(
        self, error: Exception, tool_name: str, tool_input: Dict[str, Any], state: RVRBState, llm
    ) -> BacktrackResult:
        """
        评估是否需要回溯

        Args:
            error: 异常对象
            tool_name: 工具名称
            tool_input: 工具输入
            state: RVR-B 状态
            llm: LLM 服务

        Returns:
            BacktrackResult: 回溯决策
        """
        # 分类错误
        classifier = self._get_error_classifier()
        classified_error = classifier.classify_tool_error(
            error=error,
            tool_name=tool_name,
            tool_input=tool_input,
        )

        state.last_error = classified_error
        state.record_tool_failure(tool_name)

        # 记录失败路径（用于回溯反思注入）
        approach_desc = str(tool_input)[:200] if tool_input else "default"
        state.record_failed_approach(
            tool_name=tool_name,
            approach=approach_desc,
            reason=classified_error.suggested_action[:300] if classified_error.suggested_action else str(error)[:300],
        )

        # 基础设施层错误
        if classified_error.is_infrastructure_error():
            from core.agent.backtrack.error_classifier import ErrorCategory
            if classified_error.category in (
                ErrorCategory.PERMISSION_DENIED,
                ErrorCategory.DEPENDENCY_MISSING,
            ):
                # Environment errors require user action, not resilience retry
                logger.info(
                    f"🚨 环境层错误 ({classified_error.category.value})，"
                    f"需要用户操作，升级处理"
                )
                return BacktrackResult(
                    decision=BacktrackDecision.ESCALATE,
                    backtrack_type=BacktrackType.NO_BACKTRACK,
                    action={
                        "notify_user": True,
                        "error_category": classified_error.category.value,
                        "suggested_action": classified_error.suggested_action,
                    },
                    reason=classified_error.suggested_action
                    or "需要用户操作才能继续",
                    confidence=0.95,
                )

            logger.info("📦 基础设施层错误，委托给 resilience 机制")
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
        manager = self._get_backtrack_manager(llm)
        backtrack_ctx = state.to_backtrack_context(classified_error)
        result = await manager.evaluate_and_decide(backtrack_ctx, use_llm=True)

        if result.decision == BacktrackDecision.BACKTRACK:
            state.increment_backtrack()

        return result

    async def _handle_tool_error_with_backtrack(
        self,
        error: Exception,
        tool_name: str,
        tool_input: Dict[str, Any],
        state: RVRBState,
        session_id: str,
        llm,
        tool_executor,
        context_engineering=None,
        tool_selector=None,
        runtime_ctx=None,
    ) -> tuple[str, bool, Optional[Dict]]:
        """
        带回溯的工具错误处理（V12 回溯↔终止联动）

        V12 改动：
        - 新增 runtime_ctx 参数，用于将回溯状态同步到 RuntimeContext
        - FAIL_GRACEFULLY / ESCALATE 时设置 ctx.backtracks_exhausted
        - INTENT_CLARIFY 时设置 ctx.backtrack_escalation

        Args:
            error: 异常对象
            tool_name: 工具名称
            tool_input: 工具输入
            state: RVR-B 状态
            session_id: 会话 ID
            llm: LLM 服务
            tool_executor: 工具执行器
            context_engineering: 上下文工程（可选）
            tool_selector: 工具选择器（可选）
            runtime_ctx: RuntimeContext（V12，用于回溯↔终止联动）

        Returns:
            (result_content, is_error, backtrack_event)
        """
        # 评估是否需要回溯
        backtrack_result = await self._evaluate_backtrack(
            error=error, tool_name=tool_name, tool_input=tool_input, state=state, llm=llm
        )

        backtrack_event = None

        if backtrack_result.decision == BacktrackDecision.BACKTRACK:
            logger.info(f"🔄 触发回溯: {backtrack_result.backtrack_type.value}")

            # 生成回溯事件（V12: 附带累计信息）
            backtrack_event = {
                "type": "backtrack",
                "data": {
                    **backtrack_result.to_dict(),
                    "attempt": f"{state.backtrack_count}/{state.max_backtracks}",
                    "cumulative_backtrack_tokens": state.total_backtrack_tokens
                    if hasattr(state, "total_backtrack_tokens")
                    else 0,
                },
            }

            # V12: 同步回溯计数到 RuntimeContext
            if runtime_ctx:
                runtime_ctx.total_backtracks = state.backtrack_count

            # 根据回溯类型处理
            if backtrack_result.backtrack_type == BacktrackType.TOOL_REPLACE:
                alt_result = await self._try_alternative_tool(
                    tool_name, tool_input, state, tool_executor, tool_selector
                )
                if alt_result:
                    state.record_execution("backtrack:tool_replace", True, alt_result)
                    return alt_result, False, backtrack_event
                # 替代工具查找失败（或未配置 tool_selector），
                # fall through 让 LLM 自行决策替代方案

            # 回溯信息返回给 LLM，引导其自行调整策略
            backtrack_info = backtrack_result.to_dict()
            if backtrack_result.backtrack_type == BacktrackType.TOOL_REPLACE:
                backtrack_info["hint"] = (
                    f"工具 {tool_name} 执行失败，请选择其他工具或方法完成当前任务。"
                )
            result_content = stable_json_dumps(
                {"error": str(error), "backtrack": backtrack_info}
            )
            return result_content, True, backtrack_event

        elif backtrack_result.decision in (
            BacktrackDecision.FAIL_GRACEFULLY,
            BacktrackDecision.ESCALATE,
        ):
            # V12 关键改动：回溯耗尽 / 升级 → 同步状态到 RuntimeContext
            # 这样 AdaptiveTerminator 在本轮末尾能感知到，触发 HITL 三选一
            logger.warning(
                f"⚠️ 回溯升级: decision={backtrack_result.decision.value}, "
                f"backtracks={state.backtrack_count}/{state.max_backtracks}"
            )

            if runtime_ctx:
                runtime_ctx.backtracks_exhausted = True
                runtime_ctx.total_backtracks = state.backtrack_count

                if backtrack_result.backtrack_type == BacktrackType.INTENT_CLARIFY:
                    runtime_ctx.backtrack_escalation = "intent_clarify"
                else:
                    runtime_ctx.backtrack_escalation = "escalate"

            # 生成回溯耗尽事件
            backtrack_event = {
                "type": "backtrack_exhausted",
                "data": {
                    "decision": backtrack_result.decision.value,
                    "total_attempts": state.backtrack_count,
                    "failed_tools": state.failed_tools,
                    "last_error": str(error)[:500],
                    "escalation": runtime_ctx.backtrack_escalation
                    if runtime_ctx
                    else None,
                },
            }

            # 构建包含回溯历史的错误摘要（帮助 LLM 理解状况）
            result_content = stable_json_dumps(
                {
                    "error": str(error),
                    "backtrack_exhausted": True,
                    "attempts": state.backtrack_count,
                    "failed_tools": state.failed_tools,
                    "message": f"已尝试 {state.backtrack_count} 种不同方法均失败，等待用户决定",
                }
            )
            state.record_execution(
                f"backtrack_exhausted:{tool_name}", False, error=error
            )
            return result_content, True, backtrack_event

        # CONTINUE: 不需要回溯，正常记录错误
        if context_engineering:
            record_tool_error(context_engineering, tool_name, error, tool_input)

        result_content = stable_json_dumps({"error": str(error)})
        state.record_execution(f"tool:{tool_name}", False, error=error)

        return result_content, True, None

    async def _try_alternative_tool(
        self,
        failed_tool: str,
        tool_input: Dict[str, Any],
        state: RVRBState,
        tool_executor,
        tool_selector=None,
    ) -> Optional[str]:
        """
        尝试使用替代工具（V10.1 解耦）

        Args:
            failed_tool: 失败的工具名称
            tool_input: 工具输入
            state: RVR-B 状态
            tool_executor: 工具执行器
            tool_selector: 工具选择器（可选）

        Returns:
            替代工具的执行结果，或 None
        """
        if not tool_executor:
            return None

        if not tool_selector or not hasattr(tool_selector, "get_alternative_tools"):
            logger.info(
                f"⚠️ TOOL_REPLACE 降级: tool_selector 未配置，"
                f"跳过替代工具查找，将错误信息返回给 LLM 自行决策"
            )
            return None

        alternatives = tool_selector.get_alternative_tools(failed_tool)

        for alt_tool in alternatives:
            if alt_tool in state.failed_tools:
                continue

            try:
                logger.info(f"🔄 尝试替代工具: {alt_tool}")
                result = await tool_executor.execute(alt_tool, tool_input)
                result_content = result if isinstance(result, str) else stable_json_dumps(result)
                logger.info(f"✅ 替代工具成功: {alt_tool}")
                return result_content
            except Exception as e:
                logger.warning(f"⚠️ 替代工具也失败: {alt_tool} - {e}")
                state.record_tool_failure(alt_tool)
                continue

        return None

    # ==================== Termination Reply ====================

    _TERMINATION_REASON_HINTS = {
        "max_turns": "已达到最大执行轮次。",
        "max_duration": "任务执行时间较长，已自动暂停。",
        "idle_timeout": "执行过程中等待超时。",
        "consecutive_failures": "连续多次执行失败。",
        "user_stop": "用户已请求停止。",
        "hitl_no_confirm": "有操作需要用户确认，但当前无法获取确认，已暂停。",
        "tool_loop_no_confirm": "反复使用同一工具未取得进展，已暂停。",
        "user_stop_tool_loop": "用户选择停止同工具循环尝试。",
    }

    async def _generate_termination_reply(
        self,
        llm,
        llm_messages: list,
        system_prompt,
        ctx: "RuntimeContext",
        session_id: str,
        broadcaster,
        usage_tracker,
        reason: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Terminator 终止时，让 LLM 做最后一次无工具回复。

        给 LLM 当前对话上下文 + 终止原因，让它自然地总结已完成的工作
        和终止的原因，而不是输出硬编码文案。

        关键：tools=[] 阻止 LLM 调用任何工具，防止再次进入循环。
        """
        reason_hint = self._TERMINATION_REASON_HINTS.get(reason, "任务已暂停。")

        # 注入一条 user 消息，告知 LLM 需要收尾
        from core.llm.base import Message

        termination_instruction = Message(
            role="user",
            content=(
                f"[系统提示] {reason_hint}\n"
                "请简要总结你目前完成了哪些工作、还有什么未完成，"
                "以及用户接下来可以怎么做。不要调用任何工具，直接回复用户。"
            ),
        )
        final_messages = llm_messages + [termination_instruction]

        try:
            # 调用 LLM，不传任何工具，强制纯文本回复
            async for event in self._process_stream(
                llm=llm,
                messages=final_messages,
                system_prompt=system_prompt,
                tools=[],  # 关键：无工具 → LLM 只能生成文字
                ctx=ctx,
                session_id=session_id,
                broadcaster=broadcaster,
                usage_tracker=usage_tracker,
            ):
                yield event

            # 标记完成
            final_content = (
                ctx.last_llm_response.content if ctx.last_llm_response else ""
            )
            if final_content:
                ctx.set_completed(final_content, reason)
        except Exception as e:
            # LLM 调用失败时使用硬编码 fallback
            logger.warning(f"终止回复生成失败，使用 fallback: {e}")
            _fallback = f"{reason_hint}如需继续请再次发送消息。"
            yield {"type": "content", "data": {"text": _fallback}}
            ctx.set_completed(_fallback, reason)

    # ==================== Context Pollution 清理 ====================

    def _clean_backtrack_results(
        self,
        tool_results: List[Dict[str, Any]],
        state: "RVRBState",
    ) -> List[Dict[str, Any]]:
        """
        Context Pollution 清理 + 回溯消息压缩

        回溯发生后，将失败的 tool_result 内容压缩为简短摘要，
        并额外注入一条 text 类型的反思块引导 LLM 换策略。

        策略：
        - 成功的 tool_result：保留原样
        - 失败的 tool_result：保留配对关系（tool_use_id 不变），
          但把内容压缩为简短错误摘要
        - 反思摘要：作为 text 块注入，不参与 tool 配对检查，
          确保 LLM 一定能看到

        Args:
            tool_results: 原始 tool_result 列表
            state: RVR-B 状态（含失败历史）

        Returns:
            清理后的结果列表（tool_result + text 反思块）
        """
        if not state.backtrack_count:
            return tool_results

        cleaned = []
        failed_summaries = []

        for result in tool_results:
            if not result.get("is_error"):
                cleaned.append(result)
            else:
                content = result.get("content", "")
                error_brief = content[:150] if isinstance(content, str) else str(content)[:150]
                failed_summaries.append(error_brief)

                cleaned.append({
                    "type": "tool_result",
                    "tool_use_id": result.get("tool_use_id", ""),
                    "content": f"[失败] {error_brief}",
                    "is_error": True,
                })

        if failed_summaries:
            reflection = self._build_reflection_summary(failed_summaries, state)
            cleaned.append({
                "type": "text",
                "text": reflection,
            })

        return cleaned if cleaned else tool_results

    def _build_reflection_summary(
        self,
        failed_summaries: List[str],
        state: "RVRBState",
    ) -> str:
        """
        构建 Contrastive Reflection 反思摘要

        在重试前告诉 LLM"发生了什么 + 为什么失败 + 怎么避免"，
        引导 LLM 用不同策略重试而非重复犯错。

        包含 failed_approaches 路径记忆，明确列出已尝试过的方法。
        """
        failed_tools = list(state.failed_tools) if hasattr(state, "failed_tools") else []

        parts = [
            f"[回溯反思] 已尝试 {state.backtrack_count} 次回溯。",
        ]

        if failed_tools:
            parts.append(f"失败的工具: {', '.join(failed_tools)}。")

        if len(failed_summaries) == 1:
            parts.append(f"失败原因: {failed_summaries[0]}")
        elif failed_summaries:
            parts.append(f"失败原因汇总: {'; '.join(failed_summaries[:3])}")

        # 注入失败路径记忆（让 LLM 明确知道哪些方法已试过）
        if state.failed_approaches:
            parts.append("已尝试过的方法（不要重复）:")
            for i, fa in enumerate(state.failed_approaches[-5:], 1):
                parts.append(
                    f"  {i}. {fa['tool']}: {fa['approach']} → 失败: {fa['reason']}"
                )

        parts.append("请使用完全不同的策略或工具重试。")

        return "\n".join(parts)

    @staticmethod
    def _fold_backtracked_turns(
        llm_messages: list,
        state: "RVRBState",
    ) -> None:
        """
        折叠被回溯的失败轮次消息，减少 token 膨胀。

        在回溯触发后调用。向前扫描消息找到最近包含失败 tool_result
        的 assistant+user 消息对，将其内容折叠为一行摘要。
        只折叠最近两轮失败的消息（避免过度压缩导致上下文丢失）。
        """
        if state.backtrack_count < 2:
            return

        folded_count = 0
        i = len(llm_messages) - 1
        while i >= 2 and folded_count < 2:
            msg = llm_messages[i]
            content = msg.content if hasattr(msg, "content") else msg.get("content")
            role = msg.role if hasattr(msg, "role") else msg.get("role")

            if role != "user" or not isinstance(content, list):
                i -= 1
                continue

            has_error = any(
                (isinstance(b, dict) and b.get("is_error"))
                for b in content
            )
            if not has_error:
                i -= 1
                continue

            tool_names = []
            error_briefs = []
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                    c = b.get("content", "")
                    error_briefs.append(c[:80] if isinstance(c, str) else str(c)[:80])

            prev_msg = llm_messages[i - 1]
            prev_content = prev_msg.content if hasattr(prev_msg, "content") else prev_msg.get("content")
            prev_role = prev_msg.role if hasattr(prev_msg, "role") else prev_msg.get("role")
            if prev_role == "assistant" and isinstance(prev_content, list):
                for b in prev_content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        tool_names.append(b.get("name", "?"))

            summary = (
                f"[已折叠的失败轮次] 工具: {', '.join(tool_names) or '?'} "
                f"→ 失败: {'; '.join(error_briefs[:2]) or '?'}"
            )

            from core.llm.base import Message
            llm_messages[i - 1] = Message(role="assistant", content=summary)
            llm_messages[i] = Message(role="user", content="请换一种方法继续。")
            folded_count += 1
            i -= 2

        if folded_count:
            logger.info(f"📦 折叠 {folded_count} 个失败轮次，减少 token 膨胀")

    def _build_progressive_hint(
        self,
        tool_name: str,
        error_msg: str,
        state: RVRBState,
    ) -> Optional[str]:
        """
        渐进式失败引导（Progressive Hint Escalation）

        根据同一工具连续失败次数生成不同强度的引导，对推理能力弱的模型尤其有效：
        - Level 1（首次失败）：温和引导，提示分析原因
        - Level 2（连续2次）：显式约束，列出已试方法，禁止重复
        - Level 3（连续3次+）：强制转向，工具从可用列表中动态移除
        """
        streak = state.get_tool_failure_streak(tool_name)
        if streak <= 0:
            return None

        tool_approaches = [
            fa for fa in state.failed_approaches if fa["tool"] == tool_name
        ]

        if streak == 1:
            return (
                f"[工具失败提醒] {tool_name} 执行失败: {error_msg[:500]}\n"
                "请分析失败原因，调整参数或换用其他工具。"
                "不要使用完全相同的参数重试。"
            )

        if streak == 2:
            approaches_lines = "\n".join(
                f"  - {fa['approach'][:80]} → {fa['reason'][:60]}"
                for fa in tool_approaches[-3:]
            )
            return (
                f"[系统约束] {tool_name} 已连续失败 {streak} 次。\n"
                f"已尝试过的方法（禁止重复）:\n{approaches_lines}\n"
                "要求：必须换用完全不同的工具，或使用根本不同的参数。"
                "如果没有替代方案，直接基于已有信息回答用户。"
            )

        # streak >= 3: 强制转向（副作用：由调用方负责写入 pruned_tools）
        return (
            f"[强制转向] {tool_name} 已连续失败 {streak} 次，已被禁用。\n"
            f"你无法再使用 {tool_name}。请使用其他工具完成任务，"
            "或直接告诉用户当前无法完成该操作并说明原因。"
        )

    async def execute(
        self,
        messages: List[Dict[str, Any]],
        context: ExecutionContext,
        config: Optional[ExecutorConfig] = None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 RVR-B 主循环

        Args:
            messages: 初始消息列表
            context: 执行上下文
            config: 执行配置
            **kwargs: 额外参数

        Yields:
            事件字典
        """
        cfg = config or self.config

        # V10.1: 从 context 获取依赖（解耦 agent）
        llm = context.llm
        tool_executor = context.tool_executor
        broadcaster = context.broadcaster
        ctx = context.runtime_ctx
        session_id = context.session_id
        conversation_id = context.conversation_id
        system_prompt = context.system_prompt
        tools_for_llm = context.tools_for_llm
        intent = context.intent
        plan_cache = context.plan_cache

        # 验证必需依赖
        if not llm:
            logger.error("❌ RVRBExecutor: llm 未提供")
            yield {"type": "error", "data": {"message": "执行器配置错误: llm 未提供"}}
            return

        if not ctx:
            logger.error("❌ RVRBExecutor: runtime_ctx 未提供")
            yield {"type": "error", "data": {"message": "执行器配置错误: runtime_ctx 未提供"}}
            return

        # 获取额外依赖（V10.2 ToolExecutionFlow 需要）
        usage_tracker = context.extra.get("usage_tracker")
        if not usage_tracker:
            from models.usage import UsageTracker

            usage_tracker = UsageTracker()

        context_engineering = context.extra.get("context_engineering")
        plan_todo_tool = context.extra.get("plan_todo_tool")
        event_manager = context.extra.get("event_manager")
        state_manager = context.extra.get("state_manager")

        logger.info(
            f"🚀 RVRBExecutor 开始执行 (signal-driven termination): "
            f"max_backtrack={cfg.max_backtrack_attempts}"
        )

        # 初始化 RVR-B 状态
        state = self._get_rvrb_state(session_id)
        state.current_plan = plan_cache.get("plan")

        # 转换消息
        llm_messages = dict_list_to_messages(messages)

        # Context Engineering
        def _refresh_plan_injection(_llm_messages: List, *, inject_errors: bool) -> List:
            if not context_engineering or not plan_cache.get("plan"):
                return _llm_messages
            prepared_messages = context_engineering.prepare_messages_for_llm(
                messages=messages_to_dict_list(_llm_messages),
                plan=plan_cache.get("plan"),
                inject_plan=True,
                inject_errors=inject_errors,
            )
            return dict_list_to_messages(prepared_messages)

        turn = 0
        while True:
            # 每轮调用 LLM 前刷新 Plan 注入（Plan 可能在上一轮工具调用中被更新）
            llm_messages = _refresh_plan_injection(llm_messages, inject_errors=(turn == 0))

            ctx.next_turn()
            ctx.touch_activity()  # 更新活动时间（用于 idle_timeout 检测）
            state.turn = turn

            logger.info(f"{'='*60}")
            logger.info(
                f"🔄 RVR-B Turn {turn + 1} (backtracks: {state.backtrack_count}/{state.max_backtracks})"
            )
            logger.info(f"{'='*60}")

            if cfg.enable_stream:
                # 动态工具裁剪：连续失败的工具从可用列表中移除
                effective_tools = tools_for_llm
                if state.pruned_tools and tools_for_llm:
                    candidate = [
                        t for t in tools_for_llm
                        if t.get("name") not in state.pruned_tools
                    ]
                    if candidate:
                        effective_tools = candidate
                        logger.info(f"🚫 动态裁剪工具: {state.pruned_tools}")
                    else:
                        logger.warning(
                            f"⚠️ 所有工具均已裁剪，保底保留全部工具: "
                            f"{state.pruned_tools}"
                        )

                # 流式处理（V10.1: 使用父类的 _process_stream）
                async for event in self._process_stream(
                    llm=llm,
                    messages=llm_messages,
                    system_prompt=system_prompt,
                    tools=effective_tools,
                    ctx=ctx,
                    session_id=session_id,
                    broadcaster=broadcaster,
                    usage_tracker=usage_tracker,
                ):
                    yield event

                response = ctx.last_llm_response
                if response:
                    if response.stop_reason == "tool_use" and response.tool_calls:
                        # 工具调用记录已移至 _handle_tool_calls_with_backtrack_stream
                        # 在工具执行后记录 (identity, output_fingerprint)，而非执行前只记名称

                        # V11.1: HITL 危险操作确认（执行前拦截，等待用户决策）
                        hitl_rejected = False
                        if cfg.terminator:
                            try:
                                pending_names = [
                                    t.get("name") for t in response.tool_calls if t.get("name")
                                ]
                                from core.termination.protocol import TerminationAction

                                hitl_decision = cfg.terminator.evaluate(
                                    ctx,
                                    last_stop_reason="tool_use",
                                    pending_tool_names=pending_names,
                                )
                                if (
                                    hitl_decision.action == TerminationAction.ASK_USER
                                    and "hitl_confirm" in (hitl_decision.reason or "")
                                ):
                                    # 通知前端显示确认弹窗
                                    yield {
                                        "type": "hitl_confirm",
                                        "data": {
                                            "reason": hitl_decision.reason,
                                            "tools": pending_names,
                                            "message": "危险操作需用户确认",
                                        },
                                    }

                                    # 等待用户决策（approve / reject）
                                    wait_fn = (context.extra or {}).get(
                                        "wait_hitl_confirm_async"
                                    )
                                    if callable(wait_fn):
                                        user_choice = await _call_async(wait_fn)
                                        if user_choice == "approve":
                                            logger.info(
                                                f"HITL 已批准: {pending_names}"
                                            )
                                            # 用户批准 → 继续执行工具
                                        else:
                                            # 用户拒绝 → 执行 on_rejection 策略
                                            logger.info(
                                                f"HITL 已拒绝: {pending_names}，"
                                                f"执行回退策略"
                                            )
                                            hitl_rejected = True
                                            async for evt in self._handle_hitl_rejection(
                                                context, ctx, cfg
                                            ):
                                                yield evt
                                            break
                                    else:
                                        # 无等待函数，保守停止（不执行危险操作）
                                        logger.warning(
                                            "HITL 确认: 无 wait 函数，"
                                            "保守停止（不执行危险操作）"
                                        )
                                        ctx.stop_reason = (
                                            hitl_decision.reason or "hitl_confirm"
                                        )
                                        async for evt in self._generate_termination_reply(
                                            llm=llm,
                                            llm_messages=llm_messages,
                                            system_prompt=system_prompt,
                                            ctx=ctx,
                                            session_id=session_id,
                                            broadcaster=broadcaster,
                                            usage_tracker=usage_tracker,
                                            reason="hitl_no_confirm",
                                        ):
                                            yield evt
                                        break
                            except Exception as e:
                                logger.warning(
                                    f"HITL 检查异常，继续执行: {e}",
                                    exc_info=True,
                                )

                        if hitl_rejected:
                            break

                        # 处理工具调用（带回溯，V10.2 使用 ToolExecutionFlow）
                        async for event in self._handle_tool_calls_with_backtrack_stream(
                            response,
                            llm_messages,
                            session_id,
                            conversation_id,
                            ctx,
                            state,
                            llm,
                            tool_executor,
                            broadcaster,
                            usage_tracker,
                            context_engineering=context_engineering,
                            plan_cache=plan_cache,
                            plan_todo_tool=plan_todo_tool,
                            event_manager=event_manager,
                            state_manager=state_manager,
                        ):
                            yield event
                    elif response.stop_reason == "stream_error":
                        # 🚨 LLM 流式中断（网络错误后 fallback 也失败）
                        # 不持久化不完整的 tool_use blocks，通知前端错误
                        logger.warning(
                            "流式中断: stop_reason=stream_error，"
                            "丢弃不完整 tool_use，终止本轮"
                        )
                        # Yield error event so frontend can exit
                        # "executing" state instead of hanging
                        yield {
                            "type": "error",
                            "data": {
                                "message": "网络波动导致回复中断，请重试",
                                "recoverable": True,
                            },
                        }
                        ctx.set_completed(
                            response.content or "（回复因网络中断而不完整）",
                            "stream_error",
                        )
                        state.record_execution("stream_error", False, "LLM stream interrupted")
                        break
                    else:
                        ctx.set_completed(response.content, response.stop_reason)
                        state.record_execution("complete", True, response.content)
                        break
            else:
                # 非流式处理 - 动态工具裁剪
                effective_tools_ns = tools_for_llm
                if state.pruned_tools and tools_for_llm:
                    candidate_ns = [
                        t for t in tools_for_llm
                        if t.get("name") not in state.pruned_tools
                    ]
                    if candidate_ns:
                        effective_tools_ns = candidate_ns
                        logger.info(f"🚫 动态裁剪工具(non-stream): {state.pruned_tools}")
                    else:
                        logger.warning(
                            f"⚠️ 所有工具均已裁剪(non-stream)，保底保留全部工具"
                        )
                response = await llm.create_message_async(
                    messages=llm_messages, system=system_prompt, tools=effective_tools_ns  # type: ignore[arg-type]
                )

                usage_tracker.accumulate(response)

                if response.content:
                    yield {"type": "content", "data": {"text": response.content}}

                if response.stop_reason != "tool_use":
                    ctx.set_completed(response.content, response.stop_reason)
                    state.record_execution("complete", True, response.content)
                    break

                # 工具调用记录已移至 _handle_tool_calls_with_backtrack_non_stream
                # 在工具执行后记录 (identity, output_fingerprint)，而非执行前只记名称

                # V11.1: HITL 危险操作确认（非流式，等待用户决策）
                hitl_rejected_ns = False
                if cfg.terminator and response.tool_calls:
                    try:
                        pending_names = [
                            t.get("name") for t in response.tool_calls if t.get("name")
                        ]
                        from core.termination.protocol import TerminationAction

                        hitl_decision = cfg.terminator.evaluate(
                            ctx,
                            last_stop_reason="tool_use",
                            pending_tool_names=pending_names,
                        )
                        if (
                            hitl_decision.action == TerminationAction.ASK_USER
                            and "hitl_confirm" in (hitl_decision.reason or "")
                        ):
                            yield {
                                "type": "hitl_confirm",
                                "data": {
                                    "reason": hitl_decision.reason,
                                    "tools": pending_names,
                                    "message": "危险操作需用户确认",
                                },
                            }
                            wait_fn = (context.extra or {}).get(
                                "wait_hitl_confirm_async"
                            )
                            if callable(wait_fn):
                                user_choice = await _call_async(wait_fn)
                                if user_choice == "approve":
                                    logger.info(f"HITL 已批准（非流式）: {pending_names}")
                                else:
                                    logger.info(
                                        f"HITL 已拒绝（非流式）: {pending_names}"
                                    )
                                    hitl_rejected_ns = True
                                    async for evt in self._handle_hitl_rejection(
                                        context, ctx, cfg
                                    ):
                                        yield evt
                                    break
                            else:
                                ctx.stop_reason = (
                                    hitl_decision.reason or "hitl_confirm"
                                )
                                break
                    except Exception as e:
                        logger.warning(f"HITL 检查异常，继续执行: {e}", exc_info=True)

                if hitl_rejected_ns:
                    break

                await self._handle_tool_calls_with_backtrack_non_stream(
                    response,
                    llm_messages,
                    session_id,
                    conversation_id,
                    ctx,
                    state,
                    llm,
                    tool_executor,
                    broadcaster,
                    usage_tracker,
                    context_engineering=context_engineering,
                    plan_cache=plan_cache,
                    plan_todo_tool=plan_todo_tool,
                    event_manager=event_manager,
                    state_manager=state_manager,
                )

            turn += 1

            if ctx.is_completed():
                break

            # HITL pending：工具返回 pending_user_input 后暂停执行，等待下一轮消息
            if ctx.stop_reason == "hitl_pending":
                break

            # V12: 终止策略（回溯↔终止联动，信号驱动，无硬性 max_turns）
            if cfg.terminator and not ctx.is_completed():
                try:
                    from core.termination.protocol import (
                        FinishReason,
                        TerminationAction,
                    )

                    last_reason = (
                        getattr(ctx.last_llm_response, "stop_reason", None)
                        if ctx.last_llm_response
                        else None
                    )
                    _stop_requested = (
                        context.stop_event.is_set() if context.stop_event else False
                    )

                    # V12.1: 从 UsageTracker 估算费用（基于 ModelRegistry 真实定价）
                    _current_cost = None
                    if usage_tracker:
                        _current_cost = usage_tracker.estimate_cost()

                    # 估算当前 token 总量用于窗口扩展检测
                    _current_tokens = 0
                    _window_manager = (context.extra or {}).get("window_manager")
                    if _window_manager:
                        from core.llm.base import count_request_tokens
                        try:
                            _current_tokens = count_request_tokens(
                                llm_messages,
                                self._extract_system_prompt_text(system_prompt),
                            )
                        except Exception:
                            pass

                    decision = cfg.terminator.evaluate(
                        ctx,
                        last_stop_reason=last_reason,
                        stop_requested=_stop_requested,
                        pending_tool_names=None,
                        current_cost_usd=_current_cost,
                        window_manager=_window_manager,
                        current_tokens=_current_tokens,
                    )

                    if decision.should_stop:
                        ctx.stop_reason = decision.reason or "terminator"
                        # 记录结构化终止原因到 RuntimeContext（供后续分析和前端展示）
                        if decision.finish_reason:
                            ctx.finish_reason = decision.finish_reason.value

                        # --- FinishReason 处理路由 ---
                        # COMPLETED / AGENT_DECISION / USER_STOP / USER_ABORT:
                        #   正常停止，直接 break
                        # MAX_TURNS / MAX_DURATION / IDLE_TIMEOUT:
                        #   安全兜底，直接 break
                        # HITL_CONFIRM:
                        #   已在工具执行前拦截处理（line 693-751），此处不需要额外分支
                        # CONSECUTIVE_FAILURES:
                        #   推送 ROLLBACK_OPTIONS（下方处理）
                        # BACKTRACK_EXHAUSTED / INTENT_CLARIFY / COST_LIMIT / LONG_RUNNING_CONFIRM:
                        #   ASK_USER 类型，在 should_stop=False 分支处理（下方）

                        # V11.1: 连续失败 → 推送回滚选项（事件类型对齐前端）
                        if decision.action == TerminationAction.ROLLBACK_OPTIONS:
                            _state_mgr = (context.extra or {}).get("state_manager")
                            _options = (
                                _state_mgr.get_rollback_options(session_id)
                                if _state_mgr
                                else []
                            )
                            yield {
                                "type": "rollback_options",
                                "data": {
                                    "task_id": session_id,
                                    "options": _options,
                                    "reason": decision.reason,
                                },
                            }

                        # 兜底：让 LLM 做最后一次无工具回复，总结进度
                        #
                        # 判断是否需要生成终止回复：
                        # - 如果最后一次 LLM 响应是 tool_use（文本在工具调用之前，
                        #   不算"最终回复"），必须生成总结
                        # - 如果没有任何文本内容，也必须生成总结
                        _last_was_tool_use = (
                            ctx.last_llm_response
                            and ctx.last_llm_response.stop_reason == "tool_use"
                        )
                        _has_final_text = (
                            not _last_was_tool_use
                            and ctx.last_llm_response
                            and ctx.last_llm_response.content
                            and ctx.last_llm_response.content.strip()
                        )
                        if not _has_final_text:
                            _reason = decision.reason or "unknown"
                            async for evt in self._generate_termination_reply(
                                llm=llm,
                                llm_messages=llm_messages,
                                system_prompt=system_prompt,
                                ctx=ctx,
                                session_id=session_id,
                                broadcaster=broadcaster,
                                usage_tracker=usage_tracker,
                                reason=_reason,
                            ):
                                yield evt
                        break

                    # === V12 新增：回溯耗尽 → HITL 三选一 ===
                    if (
                        decision.action == TerminationAction.ASK_USER
                        and decision.finish_reason == FinishReason.BACKTRACK_EXHAUSTED
                    ):
                        total_bt = getattr(ctx, "total_backtracks", 0)
                        yield {
                            "type": "backtrack_exhausted_confirm",
                            "data": {
                                "turn": ctx.current_turn,
                                "total_backtracks": total_bt,
                                "message": (
                                    f"小搭子已经尝试了 {total_bt} 种"
                                    f"不同的方法，但都没成功。您希望怎么做？"
                                ),
                                "options": [
                                    {"id": "retry", "label": "换个思路再试试"},
                                    {"id": "rollback", "label": "撤销已做的操作"},
                                    {"id": "stop", "label": "就这样吧，先不做了"},
                                ],
                            },
                        }
                        wait_fn = (context.extra or {}).get(
                            "wait_backtrack_confirm_async"
                        )
                        if callable(wait_fn):
                            user_choice = await _call_async(wait_fn)
                            if user_choice == "rollback":
                                _state_mgr = (context.extra or {}).get(
                                    "state_manager"
                                )
                                _options = (
                                    _state_mgr.get_rollback_options(session_id)
                                    if _state_mgr
                                    else []
                                )
                                yield {
                                    "type": "rollback_options",
                                    "data": {
                                        "task_id": session_id,
                                        "options": _options,
                                        "reason": "用户选择回滚",
                                    },
                                }
                                ctx.stop_reason = "user_rollback_after_backtrack"
                                break
                            elif user_choice == "stop":
                                ctx.stop_reason = "user_stop_after_backtrack"
                                break
                            else:
                                # retry: 重置回溯计数，允许新一轮回溯
                                state.backtrack_count = 0
                                state.pruned_tools.clear()
                                state._tool_failure_streak.clear()
                                ctx.backtracks_exhausted = False
                                ctx.backtrack_escalation = None
                                ctx.consecutive_failures = 0
                                logger.info("🔄 用户选择重试，回溯计数已重置")
                        else:
                            # 无等待函数：降级为停止
                            ctx.stop_reason = "backtrack_exhausted_no_confirm"
                            break

                    # === V12 新增：意图澄清 → HITL 询问 ===
                    elif (
                        decision.action == TerminationAction.ASK_USER
                        and decision.finish_reason == FinishReason.INTENT_CLARIFY
                    ):
                        yield {
                            "type": "intent_clarify_request",
                            "data": {
                                "message": "小搭子不太确定您的具体需求，能再描述一下吗？",
                                "context": str(state.last_error)[:500]
                                if state.last_error
                                else "",
                            },
                        }
                        wait_fn = (context.extra or {}).get(
                            "wait_intent_clarify_async"
                        )
                        if callable(wait_fn):
                            clarification = await _call_async(wait_fn)
                            append_user_message(
                                llm_messages,
                                [{"type": "text", "text": clarification}],
                            )
                            ctx.backtrack_escalation = None
                            ctx.backtracks_exhausted = False
                            logger.info("📝 用户澄清意图，继续执行")
                        else:
                            ctx.stop_reason = "intent_clarify_no_confirm"
                            break

                    # === V12.2 新增：同工具循环 → HITL 二选一 ===
                    elif (
                        decision.action == TerminationAction.ASK_USER
                        and decision.finish_reason == FinishReason.TOOL_CALL_LOOP
                    ):
                        _loop_tool = getattr(ctx, "_tool_loop_tool_name", None) or "unknown"
                        yield {
                            "type": "tool_loop_confirm",
                            "data": {
                                "turn": ctx.current_turn,
                                "tool_name": _loop_tool,
                                "message": (
                                    f"小搭子注意到一直在用 {_loop_tool} 工具"
                                    f"反复尝试，但似乎没有取得进展。"
                                    f"您希望怎么做？"
                                ),
                                "options": [
                                    {"id": "continue", "label": "没关系，继续尝试"},
                                    {"id": "stop", "label": "先停下来吧"},
                                ],
                            },
                        }
                        wait_fn = (context.extra or {}).get(
                            "wait_tool_loop_confirm_async"
                        )
                        if callable(wait_fn):
                            user_choice = await _call_async(wait_fn)
                            if user_choice == "stop":
                                ctx.stop_reason = "user_stop_tool_loop"
                                break
                            ctx.confirm_tool_loop_continue()
                            logger.info(
                                f"🔄 用户确认继续（同工具循环: {_loop_tool}）"
                            )
                        else:
                            ctx.stop_reason = "tool_loop_no_confirm"
                            break

                    # === V12.1 重构：费用确认 → HITL 阶梯式提醒 ===
                    # 所有阶梯都是 HITL 询问，智能体不会主动替用户终止任务
                    elif (
                        decision.action == TerminationAction.ASK_USER
                        and decision.finish_reason == FinishReason.COST_LIMIT
                    ):
                        cost_display = (
                            f"${_current_cost:.4f}" if _current_cost else "未知"
                        )
                        # 判断是否为紧急级别
                        is_urgent = decision.reason.startswith("cost_urgent:")
                        event_type = (
                            "cost_urgent_confirm" if is_urgent else "cost_limit_confirm"
                        )
                        message = (
                            f"费用提醒：本次任务费用已达 {cost_display}，"
                            f"{'费用较高，请确认' if is_urgent else '是否继续？'}"
                        )
                        yield {
                            "type": event_type,
                            "data": {
                                "turn": ctx.current_turn,
                                "current_cost": cost_display,
                                "is_urgent": is_urgent,
                                "message": message,
                                "options": [
                                    {"id": "continue", "label": "继续执行"},
                                    {"id": "stop", "label": "停止任务"},
                                ],
                            },
                        }
                        wait_fn = (context.extra or {}).get(
                            "wait_cost_confirm_async"
                        )
                        if callable(wait_fn):
                            user_choice = await _call_async(wait_fn)
                            if user_choice == "stop":
                                ctx.stop_reason = "user_stop_cost_limit"
                                break
                            # continue: 标记已确认，不再重复询问
                            level = "urgent" if is_urgent else "confirm"
                            cfg.terminator.confirm_cost_continue(level=level)
                            logger.info(f"用户确认继续（费用{level}级别）")
                        else:
                            ctx.stop_reason = "cost_limit_no_confirm"
                            break

                    # === 4.7 上下文窗口扩展确认 ===
                    elif (
                        decision.action == TerminationAction.ASK_USER
                        and decision.finish_reason == FinishReason.CONTEXT_WINDOW_EXPANSION
                    ):
                        _exp_info = decision.metadata.get("expansion_info")
                        if _exp_info:
                            _cur_k = _exp_info.current_tokens // 1000
                            _bud_k = _exp_info.current_budget // 1000
                            _exp_k = _exp_info.expanded_budget // 1000
                            _pct = int(_exp_info.usage_ratio * 100)
                            _std_p = _exp_info.standard_input_price or 0
                            _ext_p = _exp_info.extended_input_price or 0
                            _ratio = f"{_ext_p/_std_p:.0f}x" if _std_p else ""

                            _msg = (
                                f"上下文已使用 {_cur_k}K / {_bud_k}K ({_pct}%)，即将达到窗口上限。\n"
                                f"可扩展到 {_exp_k}K，超过 {_bud_k}K 的部分按 {_ratio} 价格计费"
                                f"（输入 ${_ext_p}/M tokens）。\n"
                                f"Prompt 缓存在扩展区间仍然有效，可节省约 90% 输入成本。"
                            )
                            yield {
                                "type": "context_expansion_confirm",
                                "data": {
                                    "turn": ctx.current_turn,
                                    "current_tokens": _exp_info.current_tokens,
                                    "current_budget": _exp_info.current_budget,
                                    "expanded_budget": _exp_info.expanded_budget,
                                    "usage_ratio": _exp_info.usage_ratio,
                                    "standard_price": _std_p,
                                    "extended_price": _ext_p,
                                    "message": _msg,
                                    "options": [
                                        {"id": "expand", "label": f"扩展到 {_exp_k}K"},
                                        {"id": "optimize", "label": "不扩展，启动上下文优化"},
                                    ],
                                },
                            }
                            _exp_wait = (context.extra or {}).get(
                                "wait_context_expansion_async"
                            )
                            if callable(_exp_wait):
                                _exp_choice = await _call_async(_exp_wait)
                                if _exp_choice == "expand":
                                    _window_manager.apply_expansion(llm_service=llm)
                                    logger.info(f"用户同意扩展: {_bud_k}K → {_exp_k}K")
                                else:
                                    _window_manager.decline_expansion()
                                    logger.info("用户拒绝扩展，启动上下文压缩")
                            else:
                                _window_manager.decline_expansion()
                                logger.warning("无 wait 函数，默认不扩展")

                    # === V12.1: 费用预警（非阻塞，仅通知前端）===
                    # 当 terminator 标记 _cost_warned 且 decision 正常继续时，发送提示
                    if (
                        _current_cost is not None
                        and getattr(cfg.terminator, "_cost_warned", False)
                        and not decision.should_stop
                        and decision.finish_reason != FinishReason.COST_LIMIT
                    ):
                        cost_display = f"${_current_cost:.4f}"
                        yield {
                            "type": "cost_warn",
                            "data": {
                                "turn": ctx.current_turn,
                                "current_cost": cost_display,
                                "message": f"本次任务费用已达 {cost_display}",
                            },
                        }

                    # 长任务确认（保持原有逻辑）
                    if (
                        decision.action == TerminationAction.ASK_USER
                        and decision.reason == "long_running_confirm"
                    ):
                        wait_fn = (context.extra or {}).get(
                            "wait_long_run_confirm_async"
                        )
                        if callable(wait_fn):
                            yield {
                                "type": "long_running_confirm",
                                "data": {
                                    "turn": ctx.current_turn,
                                    "message": f"任务已执行 {ctx.current_turn} 轮，是否继续？",
                                },
                            }
                            await _call_async(wait_fn)
                            cfg.terminator.confirm_long_running()
                except Exception as e:
                    logger.warning(
                        f"terminator.evaluate() 异常，继续执行: {e}",
                        exc_info=True,
                    )

        # ---------- P0: 最终回复兜底（与 RVRExecutor 保持一致）----------
        if not ctx.is_completed() or not (ctx.final_result and ctx.final_result.strip()):
            _last_msg = llm_messages[-1] if llm_messages else None
            _last_role = (
                getattr(_last_msg, "role", None)
                or (_last_msg.get("role") if isinstance(_last_msg, dict) else None)
            )
            _last_content = (
                getattr(_last_msg, "content", "")
                or (_last_msg.get("content", "") if isinstance(_last_msg, dict) else "")
            )
            _needs_summary = (
                _last_role != "assistant"
                or not (isinstance(_last_content, str) and _last_content.strip())
            )

            if _needs_summary and llm:
                logger.info("🔄 最终回复兜底(RVRB): 循环结束但无非空 assistant 回复，生成总结...")
                try:
                    # 注入总结指令，引导 LLM 输出最终回复
                    # 不注入时 LLM 可能返回空内容（因为它不知道需要总结）
                    from core.llm.base import Message

                    summary_instruction = Message(
                        role="user",
                        content=(
                            "[系统提示] 你已完成所有工具调用。"
                            "请直接用自然语言回复用户，简要总结你完成了什么、"
                            "结果是什么。不要调用任何工具。"
                        ),
                    )
                    summary_messages = llm_messages + [summary_instruction]

                    async for event in self._process_stream(
                        llm=llm,
                        messages=summary_messages,
                        system_prompt=system_prompt,
                        tools=[],
                        ctx=ctx,
                        session_id=session_id,
                        broadcaster=broadcaster,
                        usage_tracker=usage_tracker,
                        is_first_turn=False,
                    ):
                        yield event

                    final_resp = ctx.last_llm_response
                    if final_resp and final_resp.content:
                        ctx.set_completed(final_resp.content, final_resp.stop_reason)
                except Exception as e:
                    logger.warning(f"最终回复兜底(RVRB)失败: {e}", exc_info=True)

            # 最终保底：如果 P0 也没有产生内容（LLM 调用失败等），
            # 通过 broadcaster 发送最低限度文本，确保用户看到回复
            if not ctx.is_completed() or not (ctx.final_result and ctx.final_result.strip()):
                _fallback_text = "任务执行完毕，如有问题请继续向我提问。"
                logger.warning("⚠️ P0 兜底后仍无最终回复，发送保底消息")
                try:
                    from core.agent.content_handler import create_content_handler

                    _fb_handler = create_content_handler(
                        broadcaster, ctx.block, session_id=session_id
                    )
                    await _fb_handler.handle_text(_fallback_text)
                    await _fb_handler.stop_block(session_id)
                    ctx.set_completed(_fallback_text, "fallback")
                except Exception as fb_err:
                    logger.error(f"保底消息也失败: {fb_err}", exc_info=True)

        # 清理状态
        self._clear_rvrb_state(session_id)
        logger.info(f"✅ RVRBExecutor 执行完成: turns={ctx.current_turn}")

    async def _handle_tool_calls_with_backtrack_stream(
        self,
        response,
        llm_messages: List,
        session_id: str,
        conversation_id: str,
        ctx: "RuntimeContext",
        state: RVRBState,
        llm,
        tool_executor,
        broadcaster,
        usage_tracker,
        context_engineering=None,
        plan_cache: Optional[Dict] = None,
        plan_todo_tool=None,
        event_manager=None,
        state_manager=None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """处理工具调用（流式，带回溯，支持并行执行）"""
        import time

        from core.agent.content_handler import create_content_handler
        from core.agent.tools.flow import (
            ToolExecutionContext,
            create_tool_execution_flow,
        )
        from core.tool.registry_config import get_serial_only_tools

        client_tools = [tc for tc in response.tool_calls if tc.get("type") == "tool_use"]

        tool_context = ToolExecutionContext(
            session_id=session_id,
            conversation_id=conversation_id,
            instance_id=getattr(tool_executor.tool_context, "instance_id", None) if tool_executor else None,
            tool_executor=tool_executor,
            broadcaster=broadcaster,
            event_manager=event_manager,
            context_engineering=context_engineering,
            plan_cache=plan_cache or {},
            plan_todo_tool=plan_todo_tool,
            state_manager=state_manager,
            serial_only_tools=get_serial_only_tools(),
            allow_parallel=True,
            max_parallel=5,
        )

        flow = create_tool_execution_flow()
        content_handler = create_content_handler(broadcaster, ctx.block, session_id=session_id)
        tool_results = []
        _round_failures = []

        t0 = time.monotonic()
        batch_results = await flow.execute(client_tools, tool_context)
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            f"工具批量执行完成: {len(batch_results)} 个, 耗时 {elapsed_ms:.0f}ms"
        )

        from core.context.compaction import compress_fresh_tool_result

        for tool_call in client_tools:
            tool_name = tool_call["name"]
            tool_input = tool_call["input"] or {}
            tool_id = tool_call["id"]
            _skip_compress = False

            result_info = batch_results.get(tool_id)
            if result_info is None:
                logger.error(f"❌ 工具结果缺失: {tool_name} (id={tool_id})")
                result_content = "工具执行结果缺失"
                is_error = True
            else:
                result = result_info.result
                _skip_compress = isinstance(result, dict) and result.pop("_skip_fresh_compress", False)
                result_content = result if isinstance(result, str) else stable_json_dumps(result)
                is_error = result_info.is_error

            if not is_error:
                state.record_execution(f"tool:{tool_name}", True, result_content)
            else:
                error = Exception(
                    (result_info.error_msg if result_info else None)
                    or result_content or "工具执行失败"
                )
                logger.error(f"❌ 工具执行失败: {tool_name} - {error}")

                result_content, is_error, backtrack_event = (
                    await self._handle_tool_error_with_backtrack(
                        error=error,
                        tool_name=tool_name,
                        tool_input=tool_input,
                        state=state,
                        session_id=session_id,
                        llm=llm,
                        tool_executor=tool_executor,
                        context_engineering=context_engineering,
                        runtime_ctx=ctx,
                    )
                )

                if backtrack_event:
                    yield backtrack_event

            state.record_tool_outcome(tool_name, not is_error)
            if is_error:
                _round_failures.append((tool_name, str(result_content)[:500]))

            yield await content_handler.emit_block(
                session_id=session_id,
                block_type="tool_result",
                content={"tool_use_id": tool_id, "content": result_content, "is_error": is_error},
            )

            compressed_content = (
                result_content if _skip_compress
                else compress_fresh_tool_result(result_content)
                if isinstance(result_content, str) else result_content
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": compressed_content,
                    "is_error": is_error,
                }
            )

            ctx.record_tool_call(tool_name, tool_input)

        append_assistant_message(llm_messages, response.raw_content)

        if tool_results:
            cleaned_results = self._clean_backtrack_results(tool_results, state)
            append_user_message(llm_messages, cleaned_results)

        if state.backtrack_count >= 2:
            self._fold_backtracked_turns(llm_messages, state)

        # 渐进式失败引导：工具失败即注入（不等回溯触发），按连续失败次数升级强度
        if _round_failures:
            _progressive_hints = []
            for _tn, _err in _round_failures:
                _hint = self._build_progressive_hint(_tn, _err, state)
                if _hint:
                    _progressive_hints.append(_hint)
                    # streak >= 3 时由调用方负责写入 pruned_tools（保持 _build_progressive_hint 无副作用）
                    if state.get_tool_failure_streak(_tn) >= 3:
                        state.pruned_tools.add(_tn)
            if _progressive_hints:
                append_user_message(
                    llm_messages, "\n\n".join(_progressive_hints)
                )
                logger.info(
                    f"📊 渐进式失败引导: {len(_progressive_hints)} 条"
                    f" (pruned={state.pruned_tools or 'none'})"
                )

        # 轨迹去重：完全相同的工具调用连续 N 次 → 注入反思提示引导 LLM 换思路
        if ctx.detect_repeated_call(threshold=4):
            _dedup_hint = (
                "[系统提示] 检测到完全相同的工具调用已连续执行多次，结果不会改变。"
                "请在 Thinking 中分析原因，尝试不同的参数、换一个工具、或直接基于已有信息回答用户。"
            )
            append_user_message(llm_messages, _dedup_hint)
            logger.warning(
                f"🔁 轨迹去重: 完全相同的工具调用连续 "
                f"{ctx._consecutive_duplicate_count + 1} 次，注入反思提示"
            )

        # V12.2: 同工具循环检测 — 参数不同但反复调用同一工具（绕过精确去重）
        # 设置标志后由 AdaptiveTerminator 在本轮末尾触发 HITL
        ctx.detect_tool_loop(window=8, min_same=6)

        # HITL pending 检测：如果工具返回了 pending_user_input，暂停执行等待用户响应。
        # 防止 LLM 看到 pending 结果后再次调用 hitl（连续 2 次调用 bug）。
        for _tr in tool_results:
            _tr_content = _tr.get("content", "")
            if isinstance(_tr_content, str) and "pending_user_input" in _tr_content:
                ctx.stop_reason = "hitl_pending"
                logger.info("HITL pending 检测：工具返回 pending_user_input，暂停执行等待用户响应")
                break

        # _hint 强制注入：工具结果中含 _hint 字段时，提升为独立系统消息，
        # 确保 LLM 不会因 _hint 埋在嵌套 JSON 中而忽略它。
        _injected_hints = _extract_tool_hints(tool_results)
        if _injected_hints:
            _hint_msg = "[系统提示] " + " ".join(_injected_hints)
            append_user_message(llm_messages, _hint_msg)
            logger.info(f"🔔 _hint 强制注入（stream）: {_hint_msg[:120]}...")

        # 更新连续失败计数（供终止策略与自动回滚使用）
        if any(r.get("is_error") for r in tool_results):
            ctx.consecutive_failures += 1
        else:
            ctx.consecutive_failures = 0
        ctx.touch_activity()  # 工具执行完成，更新活动时间（idle_timeout 检测）

    async def _handle_tool_calls_with_backtrack_non_stream(
        self,
        response,
        llm_messages: List,
        session_id: str,
        conversation_id: str,
        ctx: "RuntimeContext",
        state: RVRBState,
        llm,
        tool_executor,
        broadcaster,
        usage_tracker,
        context_engineering=None,
        plan_cache: Optional[Dict] = None,
        plan_todo_tool=None,
        event_manager=None,
        state_manager=None,
    ) -> None:
        """处理工具调用（非流式，带回溯，支持并行执行）"""
        import time

        from core.agent.tools.flow import (
            ToolExecutionContext,
            create_tool_execution_flow,
        )
        from core.tool.registry_config import get_serial_only_tools

        client_tools = [tc for tc in response.tool_calls if tc.get("type") == "tool_use"]

        append_assistant_message(llm_messages, response.raw_content)

        tool_context = ToolExecutionContext(
            session_id=session_id,
            conversation_id=conversation_id,
            instance_id=getattr(tool_executor.tool_context, "instance_id", None) if tool_executor else None,
            tool_executor=tool_executor,
            broadcaster=broadcaster,
            event_manager=event_manager,
            context_engineering=context_engineering,
            plan_cache=plan_cache or {},
            plan_todo_tool=plan_todo_tool,
            state_manager=state_manager,
            serial_only_tools=get_serial_only_tools(),
            allow_parallel=True,
            max_parallel=5,
        )

        flow = create_tool_execution_flow()
        tool_results = []
        _round_failures = []

        t0 = time.monotonic()
        batch_results = await flow.execute(client_tools, tool_context)
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            f"工具批量执行完成(non-stream): {len(batch_results)} 个, 耗时 {elapsed_ms:.0f}ms"
        )

        from core.context.compaction import compress_fresh_tool_result

        for tool_call in client_tools:
            tool_name = tool_call["name"]
            tool_input = tool_call["input"] or {}
            tool_id = tool_call["id"]
            _skip_compress = False

            result_info = batch_results.get(tool_id)
            if result_info is None:
                logger.error(f"❌ 工具结果缺失: {tool_name} (id={tool_id})")
                result_content = "工具执行结果缺失"
                is_error = True
            else:
                result = result_info.result
                _skip_compress = isinstance(result, dict) and result.pop("_skip_fresh_compress", False)
                result_content = result if isinstance(result, str) else stable_json_dumps(result)
                is_error = result_info.is_error

            if not is_error:
                state.record_execution(f"tool:{tool_name}", True, result_content)
            else:
                error = Exception(
                    (result_info.error_msg if result_info else None)
                    or result_content or "工具执行失败"
                )
                logger.error(f"❌ 工具执行失败: {tool_name} - {error}")

                result_content, is_error, _ = await self._handle_tool_error_with_backtrack(
                    error=error,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    state=state,
                    session_id=session_id,
                    llm=llm,
                    tool_executor=tool_executor,
                    context_engineering=context_engineering,
                    runtime_ctx=ctx,
                )

            state.record_tool_outcome(tool_name, not is_error)
            if is_error:
                _round_failures.append((tool_name, str(result_content)[:500]))

            compressed_content = (
                result_content if _skip_compress
                else compress_fresh_tool_result(result_content)
                if isinstance(result_content, str) else result_content
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": compressed_content,
                    "is_error": is_error,
                }
            )

            ctx.record_tool_call(tool_name, tool_input)

        if tool_results:
            cleaned_results = self._clean_backtrack_results(tool_results, state)
            append_user_message(llm_messages, cleaned_results)

        if state.backtrack_count >= 2:
            self._fold_backtracked_turns(llm_messages, state)

        # 渐进式失败引导（与 stream 版本对齐）
        if _round_failures:
            _progressive_hints = []
            for _tn, _err in _round_failures:
                _hint = self._build_progressive_hint(_tn, _err, state)
                if _hint:
                    _progressive_hints.append(_hint)
                    if state.get_tool_failure_streak(_tn) >= 3:
                        state.pruned_tools.add(_tn)
            if _progressive_hints:
                append_user_message(
                    llm_messages, "\n\n".join(_progressive_hints)
                )
                logger.info(
                    f"📊 渐进式失败引导(non-stream): {len(_progressive_hints)} 条"
                    f" (pruned={state.pruned_tools or 'none'})"
                )

        # 轨迹去重：完全相同的工具调用连续 N 次 → 注入反思提示引导 LLM 换思路
        if ctx.detect_repeated_call(threshold=4):
            _dedup_hint = (
                "[系统提示] 检测到完全相同的工具调用已连续执行多次，结果不会改变。"
                "请在 Thinking 中分析原因，尝试不同的参数、换一个工具、或直接基于已有信息回答用户。"
            )
            append_user_message(llm_messages, _dedup_hint)
            logger.warning(
                f"🔁 轨迹去重: 完全相同的工具调用连续 "
                f"{ctx._consecutive_duplicate_count + 1} 次，注入反思提示"
            )

        # V12.2: 同工具循环检测（non-stream 版本，逻辑与 stream 版本一致）
        ctx.detect_tool_loop(window=8, min_same=6)

        # HITL pending 检测（non-stream 版本，逻辑与 stream 版本一致）
        for _tr in tool_results:
            _tr_content = _tr.get("content", "")
            if isinstance(_tr_content, str) and "pending_user_input" in _tr_content:
                ctx.stop_reason = "hitl_pending"
                logger.info("HITL pending 检测：工具返回 pending_user_input，暂停执行等待用户响应")
                break

        # _hint 强制注入（non-stream 版本，逻辑与 stream 版本一致）
        _injected_hints = _extract_tool_hints(tool_results)
        if _injected_hints:
            _hint_msg = "[系统提示] " + " ".join(_injected_hints)
            append_user_message(llm_messages, _hint_msg)
            logger.info(f"🔔 _hint 强制注入（non-stream）: {_hint_msg[:120]}...")

        # 更新连续失败计数（供终止策略与自动回滚使用）
        if any(r.get("is_error") for r in tool_results):
            ctx.consecutive_failures += 1
        else:
            ctx.consecutive_failures = 0
        ctx.touch_activity()  # 工具执行完成，更新活动时间（idle_timeout 检测）


def create_rvrb_executor(
    config: Optional[ExecutorConfig] = None, max_backtracks: int = 3
) -> RVRBExecutor:
    """
    创建 RVR-B 执行器

    Args:
        config: 执行配置
        max_backtracks: 最大回溯次数

    Returns:
        RVRBExecutor 实例
    """
    cfg = config or ExecutorConfig()
    cfg.enable_backtrack = True
    cfg.max_backtrack_attempts = max_backtracks
    return RVRBExecutor(config=cfg)

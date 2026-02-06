"""
Worker 执行器

V10.3 拆分自 orchestrator.py
V10.4 复用 RVRExecutor（统一执行路径）

职责：
- 单个 Worker Agent 的执行（复用 RVRExecutor）
- 工具加载（动态 + 静态）
- 共享资源初始化（工具、记忆）
- Lead Agent 高关联性任务执行
"""

import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

from core.agent.models import AgentConfig, AgentResult
from logger import get_logger

if TYPE_CHECKING:
    from core.agent.components.lead_agent import SubTask
    from core.agent.models import MultiAgentConfig, OrchestratorState
    from core.billing.tracker import EnhancedUsageTracker
    from core.events.broadcaster import EventBroadcaster
    from core.tool.executor import ToolExecutor

logger = get_logger(__name__)


class WorkerRunner:
    """
    Worker Agent 执行器

    V10.4: 复用 RVRExecutor 实现统一执行路径。
    Worker 静默执行，对主 Agent 来说就是一个工具调用——只返回最终结果。
    中间过程（thinking、tool calls）存入 metadata，不进入主 Agent 上下文。

    使用方式：
        runner = WorkerRunner(
            worker_model="claude-sonnet-4-5-20250929",
            config=multi_agent_config,
        )
        result = await runner.execute_worker(config, messages, session_id, subtask)
    """

    def __init__(
        self,
        worker_model: str = "claude-sonnet-4-5-20250929",
        config: Optional["MultiAgentConfig"] = None,
        usage_tracker: Optional["EnhancedUsageTracker"] = None,
        prompt_builder=None,
    ):
        self.worker_model = worker_model
        self.config = config
        self.usage_tracker = usage_tracker
        self._prompt_builder = prompt_builder

        # 共享资源（延迟初始化）
        self._tool_loader = None
        self._tool_executor: Optional["ToolExecutor"] = None
        self._working_memory = None
        self._mem0_client = None
        self._initialized = False

        # 事件广播器（由 Orchestrator 注入）
        self._broadcaster: Optional["EventBroadcaster"] = None

        # 上下文
        self._current_session_id: Optional[str] = None
        self._current_user_id: Optional[str] = None

        # 用于构建上下文摘要的状态引用
        self._orchestrator_state: Optional["OrchestratorState"] = None

    @property
    def tool_executor(self) -> Optional["ToolExecutor"]:
        return self._tool_executor

    @tool_executor.setter
    def tool_executor(self, value: "ToolExecutor") -> None:
        self._tool_executor = value

    @property
    def broadcaster(self) -> Optional["EventBroadcaster"]:
        return self._broadcaster

    @broadcaster.setter
    def broadcaster(self, value: "EventBroadcaster") -> None:
        self._broadcaster = value

    async def initialize_shared_resources(
        self,
        session_id: str,
        user_id: Optional[str] = None,
    ) -> None:
        """
        初始化共享资源（工具、记忆）

        在第一次 Worker 执行前调用。
        """
        if self._initialized:
            return

        self._current_session_id = session_id
        self._current_user_id = user_id

        try:
            from core.tool import create_tool_context, create_tool_executor
            from core.tool.loader import ToolLoader
            from core.tool.registry import create_capability_registry

            # 先创建注册表（ToolLoader 和 ToolExecutor 都依赖它）
            registry = create_capability_registry()

            # 工具加载器
            self._tool_loader = ToolLoader(global_registry=registry)
            logger.info("✅ 多智能体工具加载器初始化完成")

            # 工具执行器
            if self._tool_executor is None:
                tool_context = create_tool_context(
                    event_manager=None,
                    workspace_dir=None,
                    apis_config=[],
                )
                self._tool_executor = create_tool_executor(
                    registry=registry,
                    tool_context=tool_context,
                )
                logger.info("✅ 多智能体工具执行器初始化完成")

        except Exception as e:
            logger.error(f"❌ 共享资源初始化失败: {e}", exc_info=True)

        self._initialized = True

    async def load_subagent_tools(
        self,
        config: AgentConfig,
        subtask: Optional["SubTask"] = None,
    ) -> List[Dict[str, Any]]:
        """
        动态加载 Subagent 所需的工具

        根据 SubTask 的 tools_required 和 AgentConfig 的 tools 加载。
        """
        if not self._initialized:
            await self.initialize_shared_resources(
                session_id=self._current_session_id or "default"
            )

        if not self._tool_loader:
            logger.warning("⚠️ 工具加载器未初始化，返回空工具列表")
            return []

        # 确定需要的工具
        core_tools = list(config.tools) if config.tools else []
        dynamic_tools = []
        if subtask and subtask.tools_required:
            dynamic_tools = list(subtask.tools_required)

        all_required_tools = list(set(core_tools + dynamic_tools))

        # 转换为 enabled_capabilities 格式
        enabled_capabilities = {tool: True for tool in all_required_tools}

        try:
            load_result = await self._tool_loader.load_tools(
                enabled_capabilities=enabled_capabilities,
            )

            # 转换为 Anthropic 工具格式
            from core.llm.claude import ClaudeLLMService

            anthropic_tools = []
            for capability in load_result.generic_tools:
                tool_name = capability.name
                native_schema = ClaudeLLMService.NATIVE_TOOLS.get(tool_name)

                if native_schema:
                    anthropic_tools.append(native_schema)
                else:
                    tool_description = capability.metadata.get("description", f"{tool_name} 工具")
                    tool_schema = capability.input_schema or {"type": "object", "properties": {}}
                    anthropic_tools.append(
                        {
                            "name": tool_name,
                            "description": tool_description,
                            "input_schema": tool_schema,
                        }
                    )

            tool_names = [t.get("name", t.get("type", "unknown")) for t in anthropic_tools]
            logger.info(f"✅ 已加载 {len(anthropic_tools)} 个工具: {tool_names}")
            return anthropic_tools

        except Exception as e:
            logger.error(f"❌ 工具加载失败: {e}", exc_info=True)
            return []

    async def execute_worker(
        self,
        config: AgentConfig,
        messages: List[Dict[str, str]],
        previous_output: Optional[str],
        session_id: str,
        subtask: Optional["SubTask"] = None,
        build_system_prompt=None,
        build_orchestrator_summary=None,
        summarize_previous_output=None,
    ) -> AgentResult:
        """
        执行单个 Worker Agent（复用 RVRExecutor）

        V10.4: 不再手写 RVR 循环，复用和单智能体完全相同的 RVRExecutor。
        流式事件通过 broadcaster 直接推送到前端。

        Args:
            config: Agent 配置
            messages: 消息历史
            previous_output: 前一个 Agent 的输出
            session_id: 会话 ID
            subtask: 子任务定义
            build_system_prompt: 系统提示词构建函数
            build_orchestrator_summary: 编排器摘要构建函数
            summarize_previous_output: 前置输出摘要函数
        """
        start_time = time.time()
        task_description = subtask.description if subtask else f"执行 {config.role.value} 任务"

        logger.info(
            f"🤖 执行 Worker: {config.agent_id} ({config.role.value}), "
            f"model={config.model}, task={task_description[:50]}..."
        )

        try:
            # 1. 构建系统提示词
            if build_system_prompt:
                system_prompt = build_system_prompt(
                    config=config,
                    subtask=subtask,
                    orchestrator_context=(
                        build_orchestrator_summary() if build_orchestrator_summary else None
                    ),
                )
            else:
                system_prompt = f"你是 {config.role.value}，请执行任务：{task_description}"

            # 2. 创建 LLM 服务
            from config.llm_config import get_llm_profile
            from core.llm import create_llm_service

            try:
                worker_profile = await get_llm_profile("multi_agent_worker")
            except KeyError:
                logger.warning("⚠️ multi_agent_worker profile 未配置，降级使用 main_agent")
                worker_profile = await get_llm_profile("main_agent")

            if self.config and self.config.worker_config:
                worker_profile["enable_thinking"] = self.config.worker_config.enable_thinking
                worker_profile["max_tokens"] = self.config.worker_config.max_tokens
                worker_profile["thinking_budget"] = self.config.worker_config.thinking_budget

            worker_model = self.worker_model or config.model
            if worker_model and worker_model != worker_profile.get("model"):
                worker_profile["model"] = worker_model

            llm = create_llm_service(**worker_profile)

            # 3. 构建用户消息
            user_message_parts = []
            if subtask:
                user_message_parts.append(f"任务：{subtask.title}")
                user_message_parts.append(f"描述：{subtask.description}")
                if subtask.context:
                    user_message_parts.append(f"\n背景信息：\n{subtask.context}")
            else:
                user_message_parts.append(f"任务：{task_description}")

            if previous_output and summarize_previous_output:
                summary = summarize_previous_output(previous_output)
                user_message_parts.append(f"\n前置任务输出摘要：\n{summary}")

            if messages:
                original_query = self._extract_user_query(messages)
                user_message_parts.append(f"\n原始用户查询：\n{original_query}")

            user_message = "\n\n".join(user_message_parts)

            # 4. 加载工具
            tools = await self.load_subagent_tools(config, subtask)

            # 5. 复用 RVRExecutor（和单智能体完全相同的执行路径）
            result = await self._execute_with_rvr(
                llm=llm,
                system_prompt=system_prompt,
                user_message=user_message,
                tools=tools,
                session_id=session_id,
                max_turns=5,
            )

            duration_ms = int((time.time() - start_time) * 1000)
            final_content = result.get("content", "")
            turns_used = result.get("turns", 0)
            worker_metadata = result.get("metadata", {})

            logger.info(
                f"✅ Worker 执行完成: {config.agent_id}, "
                f"耗时 {duration_ms}ms, turns={turns_used}, "
                f"tool_calls={worker_metadata.get('tool_calls_count', 0)}"
            )

            return AgentResult(
                result_id=f"result_{uuid4()}",
                agent_id=config.agent_id,
                success=True,
                output=final_content,
                turns_used=turns_used,
                duration_ms=duration_ms,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                metadata={
                    "model": worker_model,
                    "has_subtask": subtask is not None,
                    "subtask_title": subtask.title if subtask else None,
                    "executor": "RVRExecutor",
                    # Worker 中间过程（对主 Agent 透明，仅存入 message metadata）
                    "worker_details": worker_metadata,
                },
            )

        except Exception as e:
            logger.error(f"❌ Worker 执行失败: {config.agent_id}, error={e}", exc_info=True)
            duration_ms = int((time.time() - start_time) * 1000)

            return AgentResult(
                result_id=f"result_{uuid4()}",
                agent_id=config.agent_id,
                success=False,
                output="",
                error=str(e),
                turns_used=0,
                duration_ms=duration_ms,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                metadata={"model": config.model, "has_subtask": subtask is not None},
            )

    async def execute_by_lead_agent(
        self,
        subtask: "SubTask",
        messages: List[Dict[str, str]],
        previous_output: Optional[str],
        session_id: str,
        lead_agent_model: str = "claude-opus-4-5-20251101",
    ) -> AgentResult:
        """
        由 Lead Agent 执行高关联性任务（复用 RVRExecutor）

        V10.4: 不再手写 LLM 调用，复用 RVRExecutor。

        与 execute_worker 的区别：
        - 使用完整对话历史（不是摘要）
        - 使用 Lead Agent 的模型（Opus）
        - max_turns 更高（支持更复杂的工具调用）
        """
        start_time = time.time()

        logger.info(
            f"🧠 Lead Agent 执行高关联性任务: {subtask.title}, "
            f"关联性原因: {subtask.context_dependency_reason}"
        )

        try:
            from prompts import load_prompt

            try:
                system_prompt = load_prompt(
                    "multi_agent/lead_agent_execution",
                    task_title=subtask.title,
                    task_description=subtask.description,
                    expected_output=subtask.expected_output or "完成任务要求",
                    success_criteria=(
                        ", ".join(subtask.success_criteria)
                        if subtask.success_criteria
                        else "完成任务要求"
                    ),
                )
            except FileNotFoundError:
                system_prompt = (
                    f"你是任务执行者。当前任务：{subtask.title}\n描述：{subtask.description}"
                )

            # 构建用户消息（包含完整上下文）
            user_message_parts = [f"请执行以下任务：\n\n{subtask.description}"]
            if previous_output:
                user_message_parts.append(f"\n\n前一个任务的输出：\n{previous_output}")
            if subtask.context:
                user_message_parts.append(f"\n\n附加上下文：\n{subtask.context}")

            # 添加对话历史摘要
            for msg in messages:
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str) and len(content) < 500:
                        user_message_parts.append(f"\n\n[对话历史] {content}")

            user_message = "\n".join(user_message_parts)

            # 加载工具
            tools = await self.load_subagent_tools(
                AgentConfig(
                    agent_id="lead_agent",
                    role="executor",
                    model=lead_agent_model,
                    tools=subtask.tools_required or [],
                ),
                subtask,
            )

            # 创建 Lead Agent 的 LLM 服务
            from config.llm_config import get_llm_profile
            from core.llm import create_llm_service

            try:
                profile = await get_llm_profile("multi_agent_orchestrator")
            except KeyError:
                profile = await get_llm_profile("main_agent")

            profile["model"] = lead_agent_model
            llm = create_llm_service(**profile)

            # 复用 RVRExecutor（和单智能体完全相同的执行路径）
            result = await self._execute_with_rvr(
                llm=llm,
                system_prompt=system_prompt,
                user_message=user_message,
                tools=tools,
                session_id=session_id,
                max_turns=10,  # Lead Agent 允许更多轮次
            )

            duration_ms = int((time.time() - start_time) * 1000)
            final_content = result.get("content", "")
            worker_metadata = result.get("metadata", {})

            logger.info(
                f"✅ Lead Agent 完成高关联性任务: {subtask.subtask_id}, "
                f"耗时 {duration_ms}ms, "
                f"tool_calls={worker_metadata.get('tool_calls_count', 0)}"
            )

            return AgentResult(
                result_id=f"result_{uuid4()}",
                agent_id=subtask.subtask_id,
                success=True,
                output=final_content,
                turns_used=result.get("turns", 0),
                duration_ms=duration_ms,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                metadata={
                    "executed_by": "lead_agent",
                    "context_dependency": subtask.context_dependency.value,
                    "context_dependency_reason": subtask.context_dependency_reason,
                    "executor": "RVRExecutor",
                    "worker_details": worker_metadata,
                },
            )

        except Exception as e:
            logger.error(f"❌ Lead Agent 执行失败: {e}", exc_info=True)
            duration_ms = int((time.time() - start_time) * 1000)

            return AgentResult(
                result_id=f"result_{uuid4()}",
                agent_id="lead_agent",
                success=False,
                output="",
                error=str(e),
                duration_ms=duration_ms,
                started_at=datetime.now(),
                completed_at=datetime.now(),
            )

    async def _execute_with_rvr(
        self,
        llm,
        system_prompt: str,
        user_message: str,
        tools: List[Dict[str, Any]],
        session_id: str,
        max_turns: int = 5,
    ) -> Dict[str, Any]:
        """
        使用 RVRExecutor 执行（统一入口）

        对主 Agent 来说，Worker 就是一个工具调用：
        - 中间过程（thinking、tool calls）静默执行，不广播
        - 只有最终回答流式推送到前端
        - 中间细节存入 metadata

        Args:
            llm: LLM 服务
            system_prompt: 系统提示词
            user_message: 用户消息
            tools: 工具定义列表
            session_id: 会话 ID
            max_turns: 最大执行轮次

        Returns:
            {"content": str, "turns": int, "metadata": dict}
        """
        from core.agent.execution.protocol import ExecutionContext, ExecutorConfig
        from core.agent.execution.rvr import RVRExecutor
        from core.context.runtime import RuntimeContext

        executor = RVRExecutor(config=ExecutorConfig(
            max_turns=max_turns,
            enable_stream=False,  # 非流式：中间过程静默
        ))

        runtime_ctx = RuntimeContext(session_id=session_id)

        exec_context = ExecutionContext(
            llm=llm,
            session_id=session_id,
            tool_executor=self._tool_executor,
            tools_for_llm=tools,
            broadcaster=None,  # 不广播中间过程
            system_prompt=system_prompt,
            runtime_ctx=runtime_ctx,
            extra={"usage_tracker": self.usage_tracker},
        )

        # 静默驱动 RVRExecutor，收集中间事件到 metadata
        worker_messages = [{"role": "user", "content": user_message}]
        tool_calls_log = []

        async for event in executor.execute(worker_messages, exec_context):
            event_type = event.get("type", "")
            if event_type == "tool_use_start":
                tool_calls_log.append({
                    "name": event.get("data", {}).get("name"),
                    "id": event.get("data", {}).get("id"),
                })
            elif event_type == "tool_result":
                content = event.get("content", {})
                if content and tool_calls_log:
                    tool_calls_log[-1]["result_preview"] = str(content)[:200]

        final_content = runtime_ctx.final_result or ""

        # 流式由 EventEmitter.emit_subtask_end 的 tool_result 流式模式负责
        # WorkerRunner 只返回结果，不直接广播

        return {
            "content": final_content,
            "turns": runtime_ctx.current_turn,
            "metadata": {
                "tool_calls": tool_calls_log,
                "tool_calls_count": len(tool_calls_log),
            },
        }

    @staticmethod
    def _extract_user_query(messages: List[Dict[str, Any]]) -> str:
        """从消息历史中提取最后一条用户查询"""
        if not messages:
            return ""

        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    texts = [
                        block.get("text", "")
                        for block in content
                        if isinstance(block, dict) and block.get("type") == "text"
                    ]
                    return " ".join(texts)
                else:
                    return content
        return ""

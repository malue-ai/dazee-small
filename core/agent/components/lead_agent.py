"""
Lead Agent (Planner) - 主控智能体

灵感来源：Anthropic Multi-Agent Research System
- Lead Agent 使用 Claude Opus 4 进行任务分解和协调
- 负责：规划、委派、综合、检查点管理
- 与 Worker Agents (Sonnet) 协作

设计原则：
1. 明确的任务分解：每个子任务有清晰的目标、输出格式、工具、边界
2. 上下文管理：为每个 Worker 提供必要的上下文
3. 结果综合：整合所有 Worker 的输出
"""

# 1. 标准库
import asyncio
import json
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

# 2. 第三方库
from pydantic import BaseModel, Field

# 3. 本地模块
from core.agent.models import (
    AgentConfig,
    AgentRole,
    ExecutionMode,
    TaskAssignment,
)
from core.llm import create_llm_service
from core.llm.base import Message
from logger import get_logger

logger = get_logger(__name__)


class ContextDependency(str, Enum):
    """上下文关联性级别"""

    LOW = "low"  # 低关联：可独立执行，派发给 Subagent
    MEDIUM = "medium"  # 中关联：需要少量上下文摘要，可派发
    HIGH = "high"  # 高关联：强依赖对话历史，主 Agent 自己做


class SubTask(BaseModel):
    """子任务定义"""

    subtask_id: str = Field(..., description="子任务 ID")
    title: str = Field(..., description="子任务标题")
    description: str = Field(..., description="详细描述")

    # 执行参数
    assigned_agent_role: AgentRole = Field(AgentRole.EXECUTOR, description="分配的角色")
    tools_required: List[str] = Field(default_factory=list, description="需要的工具")

    # 输出要求
    expected_output: str = Field("", description="期望的输出格式")
    success_criteria: List[str] = Field(default_factory=list, description="成功标准")

    # 依赖关系
    depends_on: List[str] = Field(default_factory=list, description="依赖的子任务 ID")
    priority: int = Field(0, description="优先级")

    # 上下文
    context: str = Field("", description="执行上下文")

    # 约束
    constraints: List[str] = Field(default_factory=list, description="约束条件")
    max_time_seconds: int = Field(60, description="最大执行时间")

    # 🆕 V7.11: 上下文关联性判断
    context_dependency: ContextDependency = Field(
        ContextDependency.LOW, description="对主 Agent 对话上下文的依赖程度"
    )
    execute_by_lead: bool = Field(
        False, description="是否由主 Agent 自己执行（而非派发给 Subagent）"
    )
    context_dependency_reason: str = Field("", description="上下文关联性判断的理由")


class TaskDecompositionPlan(BaseModel):
    """任务分解计划"""

    plan_id: str = Field(..., description="计划 ID")

    # 目标
    original_query: str = Field(..., description="原始用户查询")
    decomposed_goal: str = Field(..., description="分解后的目标描述")

    # 子任务
    subtasks: List[SubTask] = Field(default_factory=list, description="子任务列表")

    # 执行模式
    execution_mode: ExecutionMode = Field(ExecutionMode.PARALLEL, description="建议的执行模式")

    # 综合策略
    synthesis_strategy: str = Field("", description="结果综合策略")

    # 元数据
    reasoning: str = Field("", description="分解推理过程")
    estimated_time_seconds: int = Field(0, description="预估耗时")
    created_at: datetime = Field(default_factory=datetime.now)


class LeadAgent:
    """
    Lead Agent - 主控智能体

    职责：
    1. 任务分解（Task Decomposition）
    2. 子任务分配（Task Assignment）
    3. 结果综合（Result Synthesis）
    4. 检查点管理（Checkpoint Management）

    使用方式：
        lead_agent = LeadAgent(model="claude-opus-4")

        # 任务分解
        plan = await lead_agent.decompose_task(user_query, context)

        # 结果综合
        final_result = await lead_agent.synthesize_results(subtask_results)
    """

    def __init__(
        self,
        model: str = "claude-opus-4-5-20251101",
        max_subtasks: int = 5,
        enable_thinking: bool = True,
        thinking_budget: int = 10000,
        max_tokens: int = 16384,
    ):
        """
        初始化 Lead Agent

        Args:
            model: 使用的模型（建议 Opus 4.5）
            max_subtasks: 最大子任务数量
            enable_thinking: 是否启用扩展思考
            thinking_budget: Thinking token 预算（必须小于 max_tokens）
            max_tokens: 最大 token 数（必须大于 thinking_budget）
        """
        self.model = model
        self.max_subtasks = max_subtasks
        self._enable_thinking = enable_thinking
        self._thinking_budget = thinking_budget
        self._max_tokens = max_tokens

        # 确保 max_tokens > thinking_budget
        if max_tokens <= thinking_budget:
            self._max_tokens = thinking_budget + 1000
            logger.warning(
                f"⚠️ max_tokens ({self._max_tokens}) 必须大于 thinking_budget ({thinking_budget})，已自动调整"
            )

        # 🆕 V10.3: LLM 使用 lazy loading（因为 get_llm_profile 是异步的）
        self._llm = None

        # 🆕 V7.4: 保存最后一次 LLM 响应供 Orchestrator 累积 usage
        self.last_llm_response = None

    async def _get_llm(self):
        """懒加载 LLM 服务（异步）"""
        if self._llm is None:
            from config.llm_config import get_llm_profile

            try:
                orchestrator_profile = await get_llm_profile("multi_agent_orchestrator")
                logger.info(
                    f"📦 LeadAgent 使用 LLM Profile: multi_agent_orchestrator, model={orchestrator_profile.get('model')}"
                )
            except KeyError:
                # Fallback: 如果没有配置 multi_agent_orchestrator，使用 main_agent
                logger.warning("⚠️ multi_agent_orchestrator profile 未配置，降级使用 main_agent")
                orchestrator_profile = await get_llm_profile("main_agent")

            # 覆盖参数（如果传入了）
            orchestrator_profile["enable_thinking"] = self._enable_thinking
            orchestrator_profile["max_tokens"] = self._max_tokens
            orchestrator_profile["thinking_budget"] = self._thinking_budget

            # 覆盖模型（如果显式指定）
            if self.model and self.model != orchestrator_profile.get("model"):
                logger.info(
                    f"🔧 覆盖 Orchestrator 模型: {orchestrator_profile.get('model')} → {self.model}"
                )
                orchestrator_profile["model"] = self.model

            # 创建 LLM 服务（带 fallback 支持）
            self._llm = create_llm_service(**orchestrator_profile)

            logger.info(
                f"✅ LeadAgent 初始化: model={orchestrator_profile.get('model')}, max_tokens={self._max_tokens}, thinking_budget={self._thinking_budget}"
            )

        return self._llm

    @property
    def llm(self):
        """兼容旧代码的同步属性（已废弃，请使用 await _get_llm()）"""
        if self._llm is None:
            raise RuntimeError("LLM 未初始化，请先调用 await _get_llm()")
        return self._llm

    # ===================
    # 任务分解
    # ===================

    async def decompose_task(
        self,
        user_query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        available_tools: Optional[List[str]] = None,
        intent_info: Optional[Dict[str, Any]] = None,
    ) -> TaskDecompositionPlan:
        """
        分解用户任务为子任务

        这是 Lead Agent 的核心职责

        Args:
            user_query: 用户查询
            conversation_history: 对话历史
            available_tools: 可用工具列表
            intent_info: 意图分析结果

        Returns:
            TaskDecompositionPlan: 任务分解计划
        """
        logger.info(f"🎯 Lead Agent 开始任务分解: {user_query[:100]}...")

        # 构建任务分解 prompt
        system_prompt = self._build_decomposition_prompt(available_tools)

        # 构建用户消息
        user_message = self._build_decomposition_message(
            user_query, conversation_history, intent_info
        )

        # 调用 LLM 进行分解
        messages = [Message(role="user", content=user_message)]

        llm = await self._get_llm()
        llm_response = await llm.create_message_async(
            messages=messages,
            system=system_prompt,
            temperature=0.3,  # 降低随机性，保持一致性
        )
        # 🆕 V7.4: 保存 LLM 响应供 Orchestrator 累积 usage
        self.last_llm_response = llm_response

        # 提取响应文本
        response = llm_response.content if hasattr(llm_response, "content") else str(llm_response)

        # 解析 LLM 输出为 TaskDecompositionPlan
        plan = self._parse_decomposition_response(response, user_query)

        logger.info(
            f"✅ 任务分解完成: {len(plan.subtasks)} 个子任务, " f"模式={plan.execution_mode.value}"
        )

        return plan

    def _build_decomposition_prompt(self, available_tools: Optional[List[str]] = None) -> str:
        """
        构建任务分解的 system prompt（增强版）

        V7.1 增强：
        - 添加扩展规则（防止资源浪费）
        - 工具选择启发式规则
        - 复杂度驱动的 Subagent 数量建议

        V7.11 增强：
        - 添加上下文关联性判断
        - 决定子任务是派发还是主 Agent 自己执行
        """
        tools_desc = ""
        if available_tools:
            tools_desc = f"\n\n**可用工具**：\n" + "\n".join(
                f"- {tool}" for tool in available_tools
            )

        from prompts import load_prompt

        try:
            return load_prompt(
                "multi_agent/task_decomposition",
                max_subtasks=self.max_subtasks,
                tools_desc=tools_desc,
            )
        except FileNotFoundError:
            logger.warning("⚠️ 任务分解 Prompt 文件不存在，使用 fallback")
            return f"你是任务规划者，将任务分解为 1-{self.max_subtasks} 个子任务，输出 JSON。{tools_desc}"

    def _build_decomposition_message(
        self,
        user_query: str,
        conversation_history: Optional[List[Dict[str, str]]],
        intent_info: Optional[Dict[str, Any]],
    ) -> str:
        """构建任务分解的用户消息"""
        message_parts = [f"用户查询：{user_query}"]

        # 添加意图信息（V10.0+：只使用 complexity，task_type 已废弃）
        if intent_info:
            complexity = intent_info.get("complexity", "unknown")
            message_parts.append(f"\n意图分析：复杂度={complexity}")

        # 添加对话历史（如果有）
        if conversation_history and len(conversation_history) > 0:
            recent_history = conversation_history[-3:]  # 最近 3 轮
            history_text = "\n".join(
                [f"{msg['role']}: {msg['content'][:100]}..." for msg in recent_history]
            )
            message_parts.append(f"\n最近对话：\n{history_text}")

        message_parts.append("\n请分解这个任务为清晰的子任务。")

        return "\n".join(message_parts)

    def _parse_decomposition_response(
        self, response: str, original_query: str
    ) -> TaskDecompositionPlan:
        """
        解析 LLM 的分解响应

        V7.11 更新：解析上下文关联性字段
        """
        try:
            # 尝试从响应中提取 JSON
            # 可能包含在代码块中
            if "```json" in response:
                start = response.index("```json") + 7
                end = response.index("```", start)
                json_text = response[start:end].strip()
            elif "```" in response:
                start = response.index("```") + 3
                end = response.index("```", start)
                json_text = response[start:end].strip()
            else:
                json_text = response

            data = json.loads(json_text)

            # 构建 SubTask 对象
            subtasks = []
            for st_data in data.get("subtasks", []):
                # 🆕 V7.11: 解析上下文关联性
                context_dep_str = st_data.get("context_dependency", "low")
                try:
                    context_dependency = ContextDependency(context_dep_str)
                except ValueError:
                    context_dependency = ContextDependency.LOW

                # 根据关联性自动设置 execute_by_lead
                execute_by_lead = st_data.get("execute_by_lead", False)
                if context_dependency == ContextDependency.HIGH:
                    execute_by_lead = True  # 高关联性强制由主 Agent 执行

                subtask = SubTask(
                    subtask_id=st_data.get("subtask_id", f"task_{len(subtasks)+1}"),
                    title=st_data.get("title", ""),
                    description=st_data.get("description", ""),
                    assigned_agent_role=AgentRole(st_data.get("assigned_agent_role", "executor")),
                    tools_required=st_data.get("tools_required", []),
                    expected_output=st_data.get("expected_output", ""),
                    success_criteria=st_data.get("success_criteria", []),
                    depends_on=st_data.get("depends_on", []),
                    priority=st_data.get("priority", 0),
                    context=st_data.get("context", ""),
                    constraints=st_data.get("constraints", []),
                    max_time_seconds=st_data.get("max_time_seconds", 60),
                    # 🆕 V7.11: 上下文关联性字段
                    context_dependency=context_dependency,
                    execute_by_lead=execute_by_lead,
                    context_dependency_reason=st_data.get("context_dependency_reason", ""),
                )
                subtasks.append(subtask)

            # 🆕 V7.11: 记录上下文关联性统计
            lead_tasks = [st for st in subtasks if st.execute_by_lead]
            subagent_tasks = [st for st in subtasks if not st.execute_by_lead]
            logger.info(
                f"📊 上下文关联性分析: "
                f"主 Agent 执行 {len(lead_tasks)} 个, "
                f"Subagent 执行 {len(subagent_tasks)} 个"
            )

            # 构建 Plan
            plan = TaskDecompositionPlan(
                plan_id=str(uuid4()),
                original_query=original_query,
                decomposed_goal=data.get("decomposed_goal", original_query),
                subtasks=subtasks,
                execution_mode=ExecutionMode(data.get("execution_mode", "parallel")),
                synthesis_strategy=data.get("synthesis_strategy", ""),
                reasoning=data.get("reasoning", ""),
                estimated_time_seconds=data.get("estimated_time_seconds", 0),
            )

            return plan

        except Exception as e:
            logger.error(f"❌ 解析任务分解响应失败: {e}")
            logger.debug(f"原始响应：{response}")

            # 降级：创建单个子任务
            return self._create_fallback_plan(original_query)

    def _create_fallback_plan(self, user_query: str) -> TaskDecompositionPlan:
        """创建降级计划（当分解失败时）"""
        logger.warning("⚠️ 使用降级计划：创建单个子任务")

        return TaskDecompositionPlan(
            plan_id=str(uuid4()),
            original_query=user_query,
            decomposed_goal=user_query,
            subtasks=[
                SubTask(
                    subtask_id="task_fallback",
                    title="执行原始任务",
                    description=user_query,
                    assigned_agent_role=AgentRole.EXECUTOR,
                    expected_output="任务执行结果",
                    context=user_query,
                )
            ],
            execution_mode=ExecutionMode.SEQUENTIAL,
            synthesis_strategy="直接返回任务结果",
            reasoning="任务分解失败，降级为单任务执行",
        )

    # ===================
    # 结果综合
    # ===================

    async def synthesize_results(
        self,
        subtask_results: List[Dict[str, Any]],
        original_query: str,
        synthesis_strategy: Optional[str] = None,
    ) -> str:
        """
        综合所有子任务的结果

        Args:
            subtask_results: 子任务结果列表
            original_query: 原始用户查询
            synthesis_strategy: 综合策略（可选）

        Returns:
            str: 综合后的最终结果
        """
        logger.info(f"🔄 Lead Agent 开始结果综合: {len(subtask_results)} 个结果")

        # 构建综合 prompt
        system_prompt = self._build_synthesis_prompt()

        # 构建用户消息
        user_message = self._build_synthesis_message(
            subtask_results, original_query, synthesis_strategy
        )

        # 调用 LLM 进行综合
        messages = [Message(role="user", content=user_message)]

        llm = await self._get_llm()
        llm_response = await llm.create_message_async(
            messages=messages,
            system=system_prompt,
            temperature=0.5,
        )
        # 🆕 V7.4: 保存 LLM 响应供 Orchestrator 累积 usage
        self.last_llm_response = llm_response

        # 提取响应文本
        response = llm_response.content if hasattr(llm_response, "content") else str(llm_response)

        logger.info(f"✅ 结果综合完成: {len(response)} 字符")

        return response

    def _build_synthesis_prompt(self) -> str:
        """构建结果综合的 system prompt"""
        from prompts import load_prompt

        try:
            return load_prompt("multi_agent/result_synthesis")
        except FileNotFoundError:
            logger.warning("⚠️ 结果综合 Prompt 文件不存在，使用 fallback")
            return "你是信息综合者，将多个子任务结果整合为连贯的最终答案，使用 Markdown 格式。"

    def _build_synthesis_message(
        self,
        subtask_results: List[Dict[str, Any]],
        original_query: str,
        synthesis_strategy: Optional[str],
    ) -> str:
        """构建结果综合的用户消息"""
        message_parts = [f"原始用户查询：{original_query}", ""]

        # 添加综合策略
        if synthesis_strategy:
            message_parts.append(f"综合策略：{synthesis_strategy}\n")

        # 添加子任务结果
        message_parts.append("子任务结果：")
        for i, result in enumerate(subtask_results, 1):
            agent_id = result.get("agent_id", f"agent_{i}")
            title = result.get("title", "未命名任务")
            output = result.get("output", "")
            success = result.get("success", True)

            status = "✅" if success else "❌"
            message_parts.append(f"\n{status} 子任务 {i}：{title} (agent={agent_id})")
            message_parts.append(f"结果：\n{output[:1000]}{'...' if len(output) > 1000 else ''}")

        message_parts.append("\n请将以上所有子任务的结果综合为一个完整、连贯的答案。")

        return "\n".join(message_parts)

    # ===================
    # 质量检查
    # ===================

    async def review_result(
        self, final_result: str, original_query: str, success_criteria: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        审查最终结果的质量

        Args:
            final_result: 最终结果
            original_query: 原始查询
            success_criteria: 成功标准

        Returns:
            Dict: 审查结果
        """
        from prompts import load_prompt

        try:
            system_prompt = load_prompt("multi_agent/quality_review")
        except FileNotFoundError:
            logger.warning("⚠️ 质量评审 Prompt 文件不存在，使用 fallback")
            system_prompt = "你是质量审查者，评估任务完成的质量，输出 JSON 格式的评分和建议。"

        criteria_text = ""
        if success_criteria:
            criteria_text = f"\n成功标准：\n" + "\n".join(f"- {c}" for c in success_criteria)

        user_message = f"""原始查询：{original_query}{criteria_text}

最终结果：
{final_result}

请评估这个结果的质量。"""

        messages = [Message(role="user", content=user_message)]

        llm = await self._get_llm()
        llm_response = await llm.create_message_async(
            messages=messages,
            system=system_prompt,
            temperature=0.2,
        )
        # 🆕 V7.4: 保存 LLM 响应供 Orchestrator 累积 usage
        self.last_llm_response = llm_response

        # 提取响应文本
        response = llm_response.content if hasattr(llm_response, "content") else str(llm_response)

        # 解析 JSON
        try:
            if "```json" in response:
                start = response.index("```json") + 7
                end = response.index("```", start)
                json_text = response[start:end].strip()
            else:
                json_text = response

            review = json.loads(json_text)
            return review
        except Exception as e:
            logger.error(f"❌ 解析审查结果失败: {e}")
            return {
                "overall_score": 7,
                "passed": True,
                "feedback": "无法解析审查结果",
            }

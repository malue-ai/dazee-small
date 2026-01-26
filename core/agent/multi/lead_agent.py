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
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

# 2. 第三方库
from pydantic import BaseModel, Field

# 3. 本地模块
from core.agent.multi.models import (
    AgentConfig,
    AgentRole,
    ExecutionMode,
    TaskAssignment,
)
from core.llm import create_claude_service
from core.llm.base import Message
from logger import get_logger

logger = get_logger(__name__)


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
        
        # 确保 max_tokens > thinking_budget
        if max_tokens <= thinking_budget:
            max_tokens = thinking_budget + 1000
            logger.warning(f"⚠️ max_tokens ({max_tokens}) 必须大于 thinking_budget ({thinking_budget})，已自动调整")
        
        # 创建 LLM 服务
        self.llm = create_claude_service(
            model=model,
            enable_thinking=enable_thinking,
            max_tokens=max_tokens,
            thinking_budget=thinking_budget,
        )
        
        logger.info(f"✅ LeadAgent 初始化: model={model}, max_tokens={max_tokens}, thinking_budget={thinking_budget}")
        
        # 🆕 V7.4: 保存最后一次 LLM 响应供 Orchestrator 累积 usage
        self.last_llm_response = None
    
    # ===================
    # 任务分解
    # ===================
    
    async def decompose_task(
        self,
        user_query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        available_tools: Optional[List[str]] = None,
        intent_info: Optional[Dict[str, Any]] = None
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
            user_query,
            conversation_history,
            intent_info
        )
        
        # 调用 LLM 进行分解
        messages = [Message(role="user", content=user_message)]
        
        llm_response = await self.llm.create_message_async(
            messages=messages,
            system=system_prompt,
            temperature=0.3,  # 降低随机性，保持一致性
        )
        # 🆕 V7.4: 保存 LLM 响应供 Orchestrator 累积 usage
        self.last_llm_response = llm_response
        
        # 提取响应文本
        response = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
        
        # 解析 LLM 输出为 TaskDecompositionPlan
        plan = self._parse_decomposition_response(response, user_query)
        
        logger.info(
            f"✅ 任务分解完成: {len(plan.subtasks)} 个子任务, "
            f"模式={plan.execution_mode.value}"
        )
        
        return plan
    
    def _build_decomposition_prompt(
        self,
        available_tools: Optional[List[str]] = None
    ) -> str:
        """
        构建任务分解的 system prompt（增强版）
        
        V7.1 增强：
        - 添加扩展规则（防止资源浪费）
        - 工具选择启发式规则
        - 复杂度驱动的 Subagent 数量建议
        """
        tools_desc = ""
        if available_tools:
            tools_desc = f"\n\n**可用工具**：\n" + "\n".join(f"- {tool}" for tool in available_tools)
        
        return f"""你是一个专业的任务规划者（Lead Agent），负责将复杂任务分解为清晰的子任务。

你的职责：
1. **理解任务目标**：分析用户的真实需求和期望
2. **评估复杂度**：判断任务是否需要多智能体协作
3. **任务分解**：将任务拆分为 1-{self.max_subtasks} 个独立的子任务
4. **明确定义**：为每个子任务提供清晰的目标、输出格式、工具需求、边界
5. **执行模式**：选择合适的执行模式（parallel/sequential/hierarchical）

---

## 分解原则（参考 Anthropic Multi-Agent System）

### 1. 明确边界（Clear Boundaries）
- 每个子任务有清晰的范围，避免重叠
- 明确什么应该做，什么不应该做
- 防止 Subagent 之间重复工作

### 2. 独立性（Independence）
- 子任务应该能够独立执行（parallel）或有明确的依赖关系（sequential）
- 减少 Subagent 之间的协调成本

### 3. 可验证（Verifiable）
- 定义成功标准，便于验证完成质量
- 提供具体的、可检查的输出要求

### 4. 上下文充足（Sufficient Context）
- 为每个子任务提供必要的执行上下文
- 确保 Subagent 能够理解任务背景

---

## 扩展规则（防止资源浪费）

**重要**：遵循以下规则，避免过度分解和资源浪费：

### Rule 1: 简单任务不分解
- 如果任务可以在 **1 个 Agent + 1-2 轮对话** 中完成，**不要分解**
- 例如："什么是法国的首都？" → 直接返回 1 个子任务

### Rule 2: 复杂度驱动资源分配
- **低复杂度**（1-2 步骤）：1 个 Subagent
- **中等复杂度**（3-5 步骤，需要多个独立信息源）：2-4 个 Subagents
- **高复杂度**（5+ 步骤，需要深度研究和综合）：5-{self.max_subtasks} 个 Subagents

### Rule 3: 避免无意义的并行化
- 不要为了"看起来复杂"而分解任务
- 只有在子任务真正独立且能并行执行时，才使用 PARALLEL 模式

### Rule 4: 工具选择启发式
- 每个子任务只分配**真正需要的工具**
- 不要为所有子任务分配所有工具
- 根据子任务类型选择工具：
  - 信息收集 → 搜索工具
  - 代码执行 → 代码工具
  - 文档生成 → 不需要特殊工具

---

## 执行模式选择

- **PARALLEL**：子任务彼此独立，可以同时执行
  - 例如：收集多个独立主题的信息
  - 优点：快速
  - 缺点：成本高（多个 LLM 同时调用）

- **SEQUENTIAL**：子任务有依赖关系，需要顺序执行
  - 例如：先分析数据，再生成报告
  - 优点：逻辑清晰
  - 缺点：串行，耗时长

- **HIERARCHICAL**：有主子关系，适合有监督的执行
  - 例如：主 Agent 审查多个子 Agent 的工作
  - 优点：质量高
  - 缺点：复杂度高{tools_desc}

---

## 输出格式（JSON）

```json
{{
  "decomposed_goal": "分解后的目标描述",
  "execution_mode": "parallel/sequential/hierarchical",
  "subtasks": [
    {{
      "subtask_id": "task_1",
      "title": "子任务标题",
      "description": "详细描述任务内容（明确边界）",
      "assigned_agent_role": "researcher/executor/reviewer",
      "tools_required": ["tool1", "tool2"],
      "expected_output": "期望的输出格式（JSON/Markdown/纯文本）",
      "success_criteria": ["标准1", "标准2"],
      "depends_on": [],
      "priority": 1,
      "context": "执行所需的上下文信息",
      "constraints": ["不要做 X", "只关注 Y"],
      "max_time_seconds": 60
    }}
  ],
  "synthesis_strategy": "如何综合所有子任务的结果",
  "reasoning": "分解的推理过程（为什么这样分解？预期效果？）",
  "estimated_time_seconds": 180
}}
```

**记住**：少即是多。只有在真正需要时才分解任务。"""
    
    def _build_decomposition_message(
        self,
        user_query: str,
        conversation_history: Optional[List[Dict[str, str]]],
        intent_info: Optional[Dict[str, Any]]
    ) -> str:
        """构建任务分解的用户消息"""
        message_parts = [f"用户查询：{user_query}"]
        
        # 添加意图信息
        if intent_info:
            task_type = intent_info.get("task_type", "unknown")
            complexity = intent_info.get("complexity", "unknown")
            message_parts.append(f"\n意图分析：任务类型={task_type}, 复杂度={complexity}")
        
        # 添加对话历史（如果有）
        if conversation_history and len(conversation_history) > 0:
            recent_history = conversation_history[-3:]  # 最近 3 轮
            history_text = "\n".join([
                f"{msg['role']}: {msg['content'][:100]}..."
                for msg in recent_history
            ])
            message_parts.append(f"\n最近对话：\n{history_text}")
        
        message_parts.append("\n请分解这个任务为清晰的子任务。")
        
        return "\n".join(message_parts)
    
    def _parse_decomposition_response(
        self,
        response: str,
        original_query: str
    ) -> TaskDecompositionPlan:
        """解析 LLM 的分解响应"""
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
                )
                subtasks.append(subtask)
            
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
    
    def _suggest_subagent_count(
        self,
        user_query: str,
        intent_info: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        根据任务复杂度建议 Subagent 数量（启发式算法）
        
        参考 Anthropic 经验：
        - 简单查询：1 个 Subagent
        - 中等复杂度：2-4 个 Subagents
        - 复杂研究：5+ 个 Subagents
        
        Args:
            user_query: 用户查询
            intent_info: 意图分析结果
            
        Returns:
            int: 建议的 Subagent 数量
        """
        # 基础评分
        score = 0
        
        # 1. 查询长度（长度越长，越复杂）
        query_length = len(user_query)
        if query_length < 50:
            score += 1
        elif query_length < 200:
            score += 2
        else:
            score += 3
        
        # 2. 关键词检测（复杂任务的标志）
        complexity_keywords = [
            "比较", "对比", "分析", "研究", "调查",
            "compare", "analyze", "research", "investigate",
            "详细", "全面", "深入", "系统",
            "多个", "所有", "各种",
        ]
        
        keyword_count = sum(1 for kw in complexity_keywords if kw in user_query.lower())
        score += min(keyword_count, 3)  # 最多加 3 分
        
        # 3. 意图信息
        if intent_info:
            complexity = intent_info.get("complexity", "unknown")
            if complexity == "high":
                score += 3
            elif complexity == "medium":
                score += 2
            else:
                score += 1
        
        # 4. 映射到 Subagent 数量
        if score <= 3:
            # 简单任务
            return 1
        elif score <= 6:
            # 中等复杂度
            return min(3, self.max_subtasks)
        else:
            # 高复杂度
            return min(5, self.max_subtasks)
    
    def _create_fallback_plan(
        self,
        user_query: str
    ) -> TaskDecompositionPlan:
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
        synthesis_strategy: Optional[str] = None
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
            subtask_results,
            original_query,
            synthesis_strategy
        )
        
        # 调用 LLM 进行综合
        messages = [Message(role="user", content=user_message)]
        
        llm_response = await self.llm.create_message_async(
            messages=messages,
            system=system_prompt,
            temperature=0.5,
        )
        # 🆕 V7.4: 保存 LLM 响应供 Orchestrator 累积 usage
        self.last_llm_response = llm_response
        
        # 提取响应文本
        response = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
        
        logger.info(f"✅ 结果综合完成: {len(response)} 字符")
        
        return response
    
    def _build_synthesis_prompt(self) -> str:
        """构建结果综合的 system prompt"""
        return """你是一个专业的信息综合者（Lead Agent），负责将多个子任务的结果整合为连贯的最终答案。

你的职责：
1. **理解用户需求**：回顾原始查询的真实意图
2. **整合信息**：将所有子任务结果有机地整合在一起
3. **消除冗余**：去除重复信息，保持简洁
4. **逻辑连贯**：确保最终答案结构清晰、逻辑流畅
5. **质量检查**：验证答案是否完整回答了用户的问题

综合原则（参考 Anthropic Multi-Agent System）：
- **用户视角**：从用户的角度组织信息，而非按子任务顺序堆砌
- **突出重点**：识别最重要的发现，优先展示
- **补充上下文**：在必要时添加背景信息，帮助理解
- **引用来源**：明确标注信息来源（如果有）

输出要求：
- 使用 Markdown 格式
- 结构清晰（标题、列表、段落）
- 语言自然流畅
- 完整回答用户问题"""
    
    def _build_synthesis_message(
        self,
        subtask_results: List[Dict[str, Any]],
        original_query: str,
        synthesis_strategy: Optional[str]
    ) -> str:
        """构建结果综合的用户消息"""
        message_parts = [
            f"原始用户查询：{original_query}",
            ""
        ]
        
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
        self,
        final_result: str,
        original_query: str,
        success_criteria: Optional[List[str]] = None
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
        system_prompt = """你是一个质量审查者，负责评估任务完成的质量。

评估维度：
1. **完整性**：是否完整回答了用户的问题？
2. **准确性**：信息是否准确可信？
3. **相关性**：内容是否与用户需求相关？
4. **清晰性**：表达是否清晰易懂？
5. **实用性**：是否提供了可操作的信息？

输出格式（JSON）：
{
  "overall_score": 0-10,
  "passed": true/false,
  "dimensions": {
    "completeness": 0-10,
    "accuracy": 0-10,
    "relevance": 0-10,
    "clarity": 0-10,
    "usefulness": 0-10
  },
  "feedback": "详细反馈",
  "suggestions": ["改进建议1", "改进建议2"]
}"""
        
        criteria_text = ""
        if success_criteria:
            criteria_text = f"\n成功标准：\n" + "\n".join(f"- {c}" for c in success_criteria)
        
        user_message = f"""原始查询：{original_query}{criteria_text}

最终结果：
{final_result}

请评估这个结果的质量。"""
        
        messages = [Message(role="user", content=user_message)]
        
        llm_response = await self.llm.create_message_async(
            messages=messages,
            system=system_prompt,
            temperature=0.2,
        )
        # 🆕 V7.4: 保存 LLM 响应供 Orchestrator 累积 usage
        self.last_llm_response = llm_response
        
        # 提取响应文本
        response = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
        
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

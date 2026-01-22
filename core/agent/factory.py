"""
AgentFactory - Agent 创建工厂

V7.8 重构版本

设计原则：
1. **路由逻辑集中在 AgentRouter** - Factory 不做路由决策
2. **统一创建入口** - create_from_decision() 根据路由决策创建 Agent
3. **Schema 驱动** - 所有 Agent 都通过 Schema 配置初始化
4. **支持 Prompt 驱动** - from_prompt() 用于实例级 Agent 初始化

调用链：
    AgentRouter.route()
        ↓ RoutingDecision
    AgentFactory.create_from_decision()
        ↓
    SimpleAgent / MultiAgentOrchestrator

参考：
- docs/architecture/00-ARCHITECTURE-OVERVIEW.md
- core/agent/protocol.py
- core/agent/coordinator.py
"""

import json
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from enum import Enum

from logger import get_logger

# 导入强类型 Schema
from core.schemas import (
    AgentSchema,
    DEFAULT_AGENT_SCHEMA,
    IntentAnalyzerConfig,
    PlanManagerConfig,
    ToolSelectorConfig,
    MemoryManagerConfig,
    OutputFormatterConfig,
    SkillConfig,
)

if TYPE_CHECKING:
    from core.routing import RoutingDecision
    from core.agent.protocol import AgentProtocol

logger = get_logger(__name__)


# ============================================================
# 组件类型枚举
# ============================================================

class ComponentType(Enum):
    """组件类型"""
    INTENT_ANALYZER = "intent_analyzer"
    PLAN_MANAGER = "plan_manager"
    TOOL_SELECTOR = "tool_selector"
    MEMORY_MANAGER = "memory_manager"
    OUTPUT_FORMATTER = "output_formatter"


# ============================================================
# Schema 生成 Prompt（用于 from_prompt 方法）
# ============================================================

SCHEMA_GENERATOR_PROMPT = """
# Agent Schema 生成器

分析用户提供的 System Prompt，生成最合适的 Agent Schema 配置。

## 分析原则

通过语义理解推断配置，而非关键词匹配。

1. **任务复杂度**：分析 Prompt 描述的任务性质
2. **工具需求**：根据任务需求推断工具/技能
3. **组件配置**：根据场景启用/配置组件

## Few-shot 示例

<example>
<prompt>你是一个专业的数据分析师，帮助用户分析销售数据、生成报表。</prompt>
<schema>{"name": "DataAnalyst", "tools": ["e2b_sandbox"], "skills": [{"skill_id": "xlsx", "type": "custom"}], "max_turns": 15}</schema>
</example>

<example>
<prompt>你是一个简单的问答助手，回答用户的日常问题。</prompt>
<schema>{"name": "QAAssistant", "tools": [], "skills": [], "plan_manager": {"enabled": false}, "max_turns": 8}</schema>
</example>

<example>
<prompt>你是一个深度研究助手，帮助用户搜索信息、分析多个来源并生成研究报告。</prompt>
<schema>{"name": "ResearchAgent", "tools": ["web_search", "exa_search"], "plan_manager": {"enabled": true, "max_steps": 15}, "max_turns": 20}</schema>
</example>

## 输出格式

```json
{
  "name": "Agent 名称",
  "description": "Agent 描述",
  "tools": ["工具列表"],
  "skills": [{"skill_id": "技能ID", "type": "custom"}],
  "plan_manager": {"enabled": true/false, "max_steps": 10},
  "max_turns": 15,
  "reasoning": "配置理由"
}
```

现在，分析用户提供的 System Prompt 并生成 Agent Schema。
"""


# ============================================================
# AgentFactory - 主类
# ============================================================

class AgentFactory:
    """
    Agent 工厂 - 统一创建入口
    
    V7.8 设计：
    - 路由逻辑由 AgentRouter 完成（不在 Factory）
    - create_from_decision() 作为统一入口
    - from_schema() 是核心创建方法
    - from_prompt() 用于实例级初始化（LLM 生成 Schema）
    
    使用方式：
        # 推荐：通过 AgentCoordinator
        coordinator = AgentCoordinator(router=router)
        async for event in coordinator.route_and_execute(messages, ...):
            yield event
        
        # 直接使用：需要先路由
        decision = await router.route(query, history)
        agent = await AgentFactory.create_from_decision(decision, event_manager)
        
        # 实例级：从 System Prompt 创建
        agent = await AgentFactory.from_prompt(system_prompt, event_manager)
    """
    
    # ==================== 统一创建入口 ====================
    
    @classmethod
    async def create_from_decision(
        cls,
        decision: "RoutingDecision",
        event_manager,
        base_schema: AgentSchema = None,
        workspace_dir: str = None,
        conversation_service = None,
        system_prompt: str = "",
        prompt_cache = None,
        **kwargs
    ) -> "AgentProtocol":
        """
        从路由决策创建 Agent（V7.8 统一入口）
        
        核心设计：
        1. base_schema 来自实例配置（config.yaml + prompt.md）
        2. 根据 complexity_score 微调运行时参数
        3. 保留实例级配置（工具、技能、APIs、记忆等）
        
        Args:
            decision: 路由决策结果（由 AgentRouter.route() 返回）
            event_manager: 事件管理器
            base_schema: 实例级 Schema（来自 from_prompt 或 config）
            workspace_dir: 工作目录
            conversation_service: 会话服务
            system_prompt: 系统提示词
            prompt_cache: InstancePromptCache（包含分层提示词）
            **kwargs: 其他参数
            
        Returns:
            AgentProtocol 实例
        """
        if decision.agent_type == "multi":
            return await cls._create_multi_agent(
                decision=decision,
                event_manager=event_manager,
                base_schema=base_schema,
                workspace_dir=workspace_dir,
                conversation_service=conversation_service,
                system_prompt=system_prompt,
                prompt_cache=prompt_cache,
                **kwargs
            )
        else:
            return cls._create_simple_agent(
                decision=decision,
                event_manager=event_manager,
                base_schema=base_schema,
                workspace_dir=workspace_dir,
                conversation_service=conversation_service,
                system_prompt=system_prompt,
                prompt_cache=prompt_cache,
                **kwargs
            )
    
    @classmethod
    def _create_simple_agent(
        cls,
        decision: "RoutingDecision",
        event_manager,
        base_schema: AgentSchema = None,
        workspace_dir: str = None,
        conversation_service = None,
        system_prompt: str = "",
        prompt_cache = None,
        **kwargs
    ):
        """
        从路由决策创建 SimpleAgent
        
        核心逻辑：
        1. 使用 base_schema 作为基础（保留实例级配置）
        2. 根据 complexity_score 微调运行时参数
        3. 选择对应复杂度的提示词（从 prompt_cache）
        """
        from core.agent.simple import SimpleAgent
        
        # 获取复杂度评分
        intent = decision.intent
        complexity_score = None
        if hasattr(decision, 'complexity') and decision.complexity:
            complexity_score = decision.complexity.score
        if complexity_score is None and intent:
            complexity_score = getattr(intent, 'complexity_score', None)
        if complexity_score is None:
            complexity_score = 5.0
        
        # 确定复杂度层级
        complexity_level = cls._score_to_level(complexity_score)
        
        logger.info(
            f"🏭 创建 SimpleAgent: complexity_score={complexity_score:.2f}, "
            f"level={complexity_level}"
        )
        
        # 获取 intent
        intent = decision.intent
        
        # 使用 base_schema 或创建默认 Schema
        if base_schema is not None:
            # 在实例 Schema 基础上微调运行时参数（优先使用 LLM 语义建议）
            schema = cls._adjust_schema_for_complexity(
                base_schema, 
                complexity_score, 
                complexity_level,
                intent=intent  # 传递 LLM 语义建议
            )
            logger.info(f"   基于实例 Schema 微调: {base_schema.name}")
        else:
            # 无实例 Schema，使用复杂度驱动的默认 Schema
            schema = cls._complexity_to_schema(complexity_score)
            logger.info(f"   使用默认 Schema: {schema.name}")
        
        # 选择对应复杂度的提示词
        effective_system_prompt = system_prompt
        if prompt_cache and hasattr(prompt_cache, 'get_prompt_by_complexity'):
            cached_prompt = prompt_cache.get_prompt_by_complexity(complexity_level)
            if cached_prompt:
                effective_system_prompt = cached_prompt
                logger.info(f"   使用 {complexity_level} 层提示词")
        
        # 创建 Agent
        agent = SimpleAgent(
            model=schema.model,
            max_turns=schema.max_turns,
            event_manager=event_manager,
            workspace_dir=workspace_dir,
            conversation_service=conversation_service,
            schema=schema,
            system_prompt=effective_system_prompt or "你是一个智能助手，帮助用户完成任务。",
            prompt_cache=prompt_cache,
            **kwargs
        )
        
        logger.info(f"✅ SimpleAgent 创建完成: max_turns={schema.max_turns}")
        return agent
    
    @classmethod
    def _score_to_level(cls, complexity_score: float) -> str:
        """
        将复杂度评分转换为层级
        
        对应 prompt.md 中的分层建议：
        - simple: 直接回答，不强制计划
        - medium: 保留最小计划（3-5步）
        - complex: 完整计划与质量验证
        """
        if complexity_score <= 3.0:
            return "simple"
        elif complexity_score <= 6.0:
            return "medium"
        else:
            return "complex"
    
    @classmethod
    def _adjust_schema_for_complexity(
        cls,
        base_schema: AgentSchema,
        complexity_score: float,
        complexity_level: str,
        intent: "IntentResult" = None
    ) -> AgentSchema:
        """
        在实例 Schema 基础上根据复杂度微调运行时参数
        
        V7.8 核心设计：
        1. 优先使用 LLM 语义建议（intent.suggested_*）
        2. 回退到硬规则映射
        3. 保留实例级配置（工具、技能、APIs、记忆等）
        
        Args:
            base_schema: 实例级 Schema
            complexity_score: 复杂度评分
            complexity_level: 复杂度层级 (simple/medium/complex)
            intent: IntentResult（包含 LLM 语义建议）
            
        Returns:
            微调后的 Schema
        """
        from core.agent.types import IntentResult
        import copy
        
        adjusted = copy.deepcopy(base_schema)
        
        # ==================== max_turns ====================
        # 使用硬规则设置安全阀（智能体自主决定何时退出，max_turns 只是防止死循环）
        if complexity_level == "simple":
            adjusted.max_turns = min(base_schema.max_turns, 8)
        elif complexity_level == "medium":
            adjusted.max_turns = min(base_schema.max_turns, 15)
        else:  # complex
            adjusted.max_turns = base_schema.max_turns  # 使用实例默认值
        
        # ==================== plan_manager ====================
        if adjusted.plan_manager:
            # 优先使用 LLM 建议的规划深度
            if intent and intent.suggested_planning_depth:
                depth = intent.suggested_planning_depth
                if depth == "none":
                    adjusted.plan_manager.enabled = False
                elif depth == "minimal":
                    adjusted.plan_manager.enabled = True
                    adjusted.plan_manager.max_steps = 5
                    adjusted.plan_manager.granularity = "coarse"
                elif depth == "full":
                    adjusted.plan_manager.enabled = True
                    adjusted.plan_manager.granularity = "fine"
                    adjusted.plan_manager.replan_enabled = True
                logger.debug(f"   plan_manager: 使用 LLM 建议 → {depth}")
            else:
                # 回退到硬规则
                if complexity_level == "simple":
                    adjusted.plan_manager.enabled = False
                elif complexity_level == "medium":
                    adjusted.plan_manager.enabled = True
                    adjusted.plan_manager.max_steps = min(
                        adjusted.plan_manager.max_steps or 10, 5
                    )
                    adjusted.plan_manager.granularity = "coarse"
                else:  # complex
                    adjusted.plan_manager.enabled = True
                    adjusted.plan_manager.granularity = "fine"
                    adjusted.plan_manager.replan_enabled = True
        
        # ==================== tool_selector ====================
        if adjusted.tool_selector:
            # 优先使用 LLM 建议的工具使用模式
            if intent and intent.tool_usage_hint:
                hint = intent.tool_usage_hint
                if hint == "single":
                    adjusted.tool_selector.allow_parallel = False
                    adjusted.tool_selector.max_parallel_tools = 1
                elif hint == "sequential":
                    adjusted.tool_selector.allow_parallel = False
                    adjusted.tool_selector.max_parallel_tools = 1
                elif hint == "parallel":
                    adjusted.tool_selector.allow_parallel = True
                    adjusted.tool_selector.max_parallel_tools = 5
                logger.debug(f"   tool_selector: 使用 LLM 建议 → {hint}")
            else:
                # 回退到硬规则
                if complexity_level == "simple":
                    adjusted.tool_selector.allow_parallel = False
                    adjusted.tool_selector.max_parallel_tools = 1
                elif complexity_level == "medium":
                    adjusted.tool_selector.allow_parallel = True
                    adjusted.tool_selector.max_parallel_tools = 3
                else:  # complex
                    adjusted.tool_selector.allow_parallel = True
                    adjusted.tool_selector.max_parallel_tools = 5
        
        # ==================== requires_deep_reasoning ====================
        # 特殊处理：即使是简单问题，如果 LLM 认为需要深度推理，提升配置
        if intent and intent.requires_deep_reasoning and complexity_level == "simple":
            adjusted.max_turns = max(adjusted.max_turns, 12)
            if adjusted.plan_manager:
                adjusted.plan_manager.enabled = True
                adjusted.plan_manager.max_steps = 5
            logger.debug(f"   requires_deep_reasoning: 提升简单任务配置")
        
        # 更新 reasoning
        llm_hint = ""
        if intent:
            hints = []
            if intent.suggested_planning_depth:
                hints.append(f"planning={intent.suggested_planning_depth}")
            if intent.tool_usage_hint:
                hints.append(f"tools={intent.tool_usage_hint}")
            if intent.requires_deep_reasoning:
                hints.append("deep_reasoning")
            if hints:
                llm_hint = f" [LLM建议: {', '.join(hints)}]"
        
        adjusted.reasoning = (
            f"{base_schema.reasoning or ''} | "
            f"运行时调整: {complexity_level} (score={complexity_score:.2f}){llm_hint}"
        )
        
        logger.debug(
            f"   Schema 微调完成: max_turns {base_schema.max_turns} → {adjusted.max_turns}, "
            f"plan_enabled={adjusted.plan_manager.enabled if adjusted.plan_manager else 'N/A'}"
        )
        
        return adjusted
    
    @classmethod
    async def _create_multi_agent(
        cls,
        decision: "RoutingDecision",
        event_manager,
        workspace_dir: str = None,
        conversation_service = None,
        system_prompt: str = "",
        **kwargs
    ):
        """从路由决策创建 MultiAgentOrchestrator"""
        from core.agent.multi import MultiAgentOrchestrator, ExecutionMode
        from core.agent.multi.models import load_multi_agent_config
        
        intent = decision.intent
        
        logger.info(
            f"🏭 创建 MultiAgentOrchestrator: "
            f"task_type={intent.task_type.value if intent else 'unknown'}"
        )
        
        # 加载多智能体配置
        try:
            config = load_multi_agent_config()
        except Exception as e:
            logger.warning(f"⚠️ 加载多智能体配置失败，使用默认: {e}")
            config = None
        
        # 根据任务类型选择执行模式（V7.7 DAGScheduler）
        if intent and intent.task_type.value in ["code_development", "data_analysis"]:
            mode = ExecutionMode.SEQUENTIAL
        else:
            mode = ExecutionMode.PARALLEL  # 默认使用 DAGScheduler
        
        # 创建编排器
        orchestrator = MultiAgentOrchestrator(
            config=config,
            mode=mode,
            enable_checkpoints=True,
            enable_lead_agent=True,
        )
        
        # 附加元数据
        orchestrator.workspace_dir = workspace_dir
        orchestrator.system_prompt = system_prompt
        
        logger.info(f"✅ MultiAgentOrchestrator 创建完成: mode={mode.value}")
        return orchestrator
    
    @classmethod
    def _complexity_to_schema(cls, complexity_score: float) -> AgentSchema:
        """
        根据复杂度评分生成差异化 Schema
        
        核心差异化配置：
        1. max_turns: 控制最大轮数
        2. memory_manager: 控制记忆策略
        3. plan_manager: 控制规划粒度
        4. tool_selector: 控制工具选择策略
        5. output_formatter: 控制输出格式
        
        注：Plan 是否启用由 Claude 自主决定（通过 plan_todo 工具）
        """
        if complexity_score <= 3.0:
            # ===== 简单任务：快速响应 =====
            # 特点：无需规划，快速直达，限制轮数
            return AgentSchema(
                name="SimpleAgent",
                description="简单任务快速响应",
                intent_analyzer=IntentAnalyzerConfig(enabled=False),
                tool_selector=ToolSelectorConfig(
                    enabled=True,
                    selection_strategy="priority_based",  # 优先级选择，快速
                    allow_parallel=False,  # 禁止并行，简化执行
                    max_parallel_tools=1,
                ),
                plan_manager=PlanManagerConfig(
                    enabled=False,  # 简单任务不需要规划
                ),
                memory_manager=MemoryManagerConfig(
                    working_memory_limit=10,  # 较小记忆窗口
                    auto_compress=False,  # 无需压缩
                ),
                output_formatter=OutputFormatterConfig(
                    default_format="text",  # 简洁文本输出
                ),
                max_turns=8,
                reasoning=f"简单任务（score={complexity_score:.2f}）：快速响应，限制轮数"
            )
        
        elif complexity_score <= 6.0:
            # ===== 中等任务：平衡配置 =====
            # 特点：适度规划，适中轮数，标准记忆
            return AgentSchema(
                name="MediumAgent",
                description="中等复杂度任务",
                intent_analyzer=IntentAnalyzerConfig(enabled=False),
                tool_selector=ToolSelectorConfig(
                    enabled=True,
                    selection_strategy="capability_based",  # 能力匹配
                    allow_parallel=True,  # 允许并行
                    max_parallel_tools=3,
                ),
                plan_manager=PlanManagerConfig(
                    enabled=True,
                    max_steps=10,
                    granularity="medium",  # 中等粒度
                ),
                memory_manager=MemoryManagerConfig(
                    working_memory_limit=20,
                    auto_compress=True,  # 自动压缩
                ),
                output_formatter=OutputFormatterConfig(
                    default_format="markdown",
                    code_highlighting=True,
                ),
                max_turns=15,
                reasoning=f"中等任务（score={complexity_score:.2f}）：平衡配置"
            )
        
        else:
            # ===== 复杂任务：完整配置 =====
            # 特点：精细规划，充足轮数，持久记忆，允许重规划
            return AgentSchema(
                name="ComplexAgent",
                description="复杂任务完整配置",
                intent_analyzer=IntentAnalyzerConfig(enabled=False),
                tool_selector=ToolSelectorConfig(
                    enabled=True,
                    selection_strategy="capability_based",
                    allow_parallel=True,
                    max_parallel_tools=5,  # 更多并行
                ),
                plan_manager=PlanManagerConfig(
                    enabled=True,
                    max_steps=20,
                    granularity="fine",  # 精细规划
                    replan_enabled=True,  # 允许重规划
                    max_replan_attempts=3,
                    failure_threshold=0.2,  # 更低的失败阈值
                ),
                memory_manager=MemoryManagerConfig(
                    retention_policy="session",
                    working_memory_limit=30,
                    episodic_memory=True,  # 启用情景记忆
                    auto_compress=True,
                ),
                output_formatter=OutputFormatterConfig(
                    default_format="markdown",
                    code_highlighting=True,
                    include_metadata=True,  # 包含元数据
                ),
                max_turns=25,
                reasoning=f"复杂任务（score={complexity_score:.2f}）：精细规划，完整配置"
            )
    
    # ==================== Schema 驱动创建 ====================
    
    @classmethod
    def from_schema(
        cls,
        schema: AgentSchema,
        system_prompt: str,
        event_manager,
        workspace_dir: str = None,
        conversation_service = None,
        prompt_schema = None,
        prompt_cache = None,
        apis_config = None,
    ):
        """
        根据 Schema 创建 Agent
        
        这是核心创建方法，所有创建最终都调用此方法。
        
        Args:
            schema: AgentSchema 配置
            system_prompt: 系统提示词
            event_manager: 事件管理器
            其他参数...
            
        Returns:
            Agent 实例
        """
        logger.info(f"🏗️ 根据 Schema 创建 Agent: {schema.name}")
        
        # 优先使用 prompt_cache 中的 prompt_schema
        effective_prompt_schema = prompt_schema or (
            prompt_cache.prompt_schema if prompt_cache else None
        )
        
        # 根据 schema.multi_agent 决定类型
        if schema.multi_agent is not None:
            return cls._create_multi_agent_from_schema(
                schema=schema,
                system_prompt=system_prompt,
                event_manager=event_manager,
                workspace_dir=workspace_dir,
                conversation_service=conversation_service,
                prompt_schema=effective_prompt_schema,
                prompt_cache=prompt_cache,
                apis_config=apis_config,
            )
        else:
            from core.agent.simple import SimpleAgent
            
            agent = SimpleAgent(
                model=schema.model,
                max_turns=schema.max_turns,
                event_manager=event_manager,
                workspace_dir=workspace_dir,
                conversation_service=conversation_service,
                schema=schema,
                system_prompt=system_prompt,
                prompt_schema=effective_prompt_schema,
                prompt_cache=prompt_cache,
                apis_config=apis_config,
            )
            
            logger.info(f"✅ SimpleAgent 创建完成: {schema.name}")
            return agent
    
    @classmethod
    def _create_multi_agent_from_schema(
        cls,
        schema,
        system_prompt: str,
        event_manager,
        workspace_dir: str,
        conversation_service,
        prompt_schema,
        prompt_cache,
        apis_config
    ):
        """根据 Schema 创建 MultiAgentOrchestrator"""
        from core.agent.multi import MultiAgentOrchestrator
        from core.agent.multi.models import OrchestratorConfig
        from core.llm import create_llm_service
        from config.llm_config import get_llm_profile
        from core.memory.working import WorkingMemory
        
        # 创建 LLM Service
        profile = get_llm_profile("lead_agent")
        profile.update({
            "model": schema.model,
            "enable_thinking": True,
            "enable_caching": True,
        })
        llm_service = create_llm_service(**profile)
        
        # 创建 Memory Manager
        memory_manager = WorkingMemory(event_manager=event_manager)
        
        # 解析 multi_agent 配置
        multi_agent_config = schema.multi_agent
        orchestrator_config = OrchestratorConfig(
            max_parallel_workers=getattr(multi_agent_config, 'max_parallel_workers', 3),
            enable_checkpointing=getattr(multi_agent_config, 'enable_checkpointing', True),
            checkpoint_interval=getattr(multi_agent_config, 'checkpoint_interval', 60),
        )
        
        workers_config = getattr(multi_agent_config, 'workers', [])
        
        orchestrator = MultiAgentOrchestrator(
            event_manager=event_manager,
            memory_manager=memory_manager,
            llm_service=llm_service,
            config=orchestrator_config,
            prompt_cache=prompt_cache,
            workers_config=workers_config,
        )
        
        # 附加元数据
        orchestrator.schema = schema
        orchestrator.system_prompt = system_prompt
        orchestrator.workspace_dir = workspace_dir
        orchestrator.conversation_service = conversation_service
        orchestrator.model = schema.model
        orchestrator.max_turns = schema.max_turns
        
        logger.info(f"✅ MultiAgentOrchestrator 创建完成: {schema.name}")
        return orchestrator
    
    # ==================== Prompt 驱动创建 ====================
    
    @classmethod
    async def from_prompt(
        cls,
        system_prompt: str,
        event_manager,
        workspace_dir: str = None,
        conversation_service = None,
        llm_service = None,
        use_default_if_failed: bool = True,
        cache_dir: str = None,
        instance_path: str = None,
        force_refresh: bool = False,
        prompt_schema = None,
    ):
        """
        从 System Prompt 创建 Agent
        
        流程：
        1. 检查缓存
        2. 调用 LLM 生成 Schema
        3. 根据 Schema 创建 Agent
        
        主要用于实例级 Agent 初始化。
        """
        from pathlib import Path
        
        schema = None
        
        # 1. 尝试从缓存加载
        if cache_dir and instance_path and not force_refresh:
            cache_path = Path(cache_dir)
            instance_dir = Path(instance_path)
            
            if cls._should_use_cache(cache_path, instance_dir):
                schema_data = cls._load_schema_from_cache(cache_path)
                if schema_data:
                    try:
                        schema = AgentSchema.from_dict(schema_data)
                        logger.info(f"✅ 从缓存加载 Schema: {schema.name}")
                    except Exception as e:
                        logger.warning(f"⚠️ 缓存解析失败: {e}")
                        schema = None
        
        # 2. 生成新 Schema
        if schema is None:
            try:
                schema = await cls._generate_schema(system_prompt, llm_service)
                logger.info(f"✅ Schema 生成成功: {schema.name}")
            except Exception as e:
                logger.warning(f"⚠️ Schema 生成失败: {e}")
                if use_default_if_failed:
                    schema = cls._get_default_schema()
                else:
                    raise
            
            # 保存到缓存
            if cache_dir and instance_path and schema:
                cls._save_schema_to_cache(
                    Path(cache_dir), Path(instance_path), schema
                )
        
        # 3. 创建 Agent
        return cls.from_schema(
            schema=schema,
            system_prompt=system_prompt,
            event_manager=event_manager,
            workspace_dir=workspace_dir,
            conversation_service=conversation_service,
            prompt_schema=prompt_schema,
        )
    
    @classmethod
    async def _generate_schema(
        cls,
        system_prompt: str,
        llm_service = None
    ) -> AgentSchema:
        """调用 LLM 生成 Schema"""
        from core.llm import Message
        
        if llm_service is None:
            from core.llm import create_llm_service
            from config.llm_config import get_llm_profile
            profile = get_llm_profile("schema_generator")
            llm_service = create_llm_service(**profile)
        
        response = await llm_service.create_message_async(
            messages=[Message(
                role="user",
                content=f"分析以下 System Prompt 并生成 Agent Schema:\n\n{system_prompt}"
            )],
            system=SCHEMA_GENERATOR_PROMPT
        )
        
        content = response.content if response.content else ""
        schema_json = cls._extract_json(content)
        
        return AgentSchema.from_llm_output(schema_json)
    
    @classmethod
    def _get_default_schema(cls) -> AgentSchema:
        """获取默认 Schema"""
        return AgentSchema(
            name="GeneralAgent",
            description="通用智能体",
            plan_manager=PlanManagerConfig(enabled=True),
            max_turns=15,
            reasoning="默认配置"
        )
    
    # ==================== 路由器创建 ====================
    
    @classmethod
    def create_router(cls, prompt_cache=None):
        """
        创建 AgentRouter
        
        Args:
            prompt_cache: InstancePromptCache（可选）
            
        Returns:
            AgentRouter 实例
        """
        from core.routing import AgentRouter
        from core.llm import create_llm_service
        from config.llm_config import get_llm_profile
        
        profile = get_llm_profile("intent_analyzer")
        profile.setdefault("tools", [])
        llm_service = create_llm_service(**profile)
        
        return AgentRouter(llm_service=llm_service, prompt_cache=prompt_cache)
    
    # ==================== 辅助方法 ====================
    
    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """从文本中提取 JSON"""
        import re
        
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', text)
        if json_match:
            return json.loads(json_match.group(1))
        
        brace_match = re.search(r'\{[\s\S]*\}', text)
        if brace_match:
            return json.loads(brace_match.group(0))
        
        raise ValueError("无法从响应中提取 JSON")
    
    @classmethod
    def _should_use_cache(cls, cache_dir, instance_dir) -> bool:
        """检查是否应该使用缓存"""
        try:
            from utils.cache_utils import is_cache_valid
            return is_cache_valid(cache_dir, instance_dir)
        except Exception as e:
            logger.warning(f"缓存检查失败: {e}")
            return False
    
    @classmethod
    def _load_schema_from_cache(cls, cache_dir) -> Optional[Dict[str, Any]]:
        """从缓存加载 Schema"""
        try:
            from utils.cache_utils import load_schema_cache
            return load_schema_cache(cache_dir)
        except Exception as e:
            logger.error(f"加载缓存失败: {e}")
            return None
    
    @classmethod
    def _save_schema_to_cache(cls, cache_dir, instance_dir, schema: AgentSchema) -> bool:
        """保存 Schema 到缓存"""
        try:
            from utils.cache_utils import save_schema_cache, save_cache_metadata
            
            schema_data = schema.to_dict() if hasattr(schema, 'to_dict') else schema.dict()
            save_schema_cache(cache_dir, schema_data)
            save_cache_metadata(cache_dir, instance_dir)
            
            logger.info(f"✅ Schema 已缓存: {cache_dir}")
            return True
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")
            return False


# ============================================================
# 预设 Agent 配置
# ============================================================

class AgentPresets:
    """预设 Agent 配置"""
    
    @staticmethod
    def data_analyst() -> AgentSchema:
        return AgentSchema(
            name="DataAnalysisAgent",
            description="数据分析助手",
            skills=[SkillConfig(skill_id="xlsx", type="custom")],
            tools=["e2b_sandbox"],
            max_turns=15,
            plan_manager=PlanManagerConfig(enabled=True, max_steps=10),
            reasoning="数据分析任务"
        )
    
    @staticmethod
    def researcher() -> AgentSchema:
        return AgentSchema(
            name="ResearchAgent",
            description="研究助手",
            tools=["web_search", "exa_search"],
            max_turns=20,
            plan_manager=PlanManagerConfig(enabled=True, max_steps=15),
            reasoning="研究任务"
        )
    
    @staticmethod
    def simple_qa() -> AgentSchema:
        return AgentSchema(
            name="SimpleQAAgent",
            description="问答助手",
            max_turns=5,
            plan_manager=PlanManagerConfig(enabled=False),
            reasoning="简单问答"
        )


# ============================================================
# 便捷函数
# ============================================================

async def create_agent_from_prompt(
    system_prompt: str,
    event_manager,
    **kwargs
):
    """从 Prompt 创建 Agent"""
    return await AgentFactory.from_prompt(system_prompt, event_manager, **kwargs)


def create_agent_from_preset(
    preset_name: str,
    event_manager,
    system_prompt: str = "",
    **kwargs
):
    """从预设创建 Agent"""
    presets = {
        "data_analyst": AgentPresets.data_analyst,
        "researcher": AgentPresets.researcher,
        "simple_qa": AgentPresets.simple_qa,
    }
    
    if preset_name not in presets:
        raise ValueError(f"未知预设: {preset_name}，可用: {list(presets.keys())}")
    
    schema = presets[preset_name]()
    return AgentFactory.from_schema(
        schema=schema,
        system_prompt=system_prompt,
        event_manager=event_manager,
        **kwargs
    )


def create_schema_from_dict(data: Dict[str, Any]) -> AgentSchema:
    """从字典创建 Schema"""
    return AgentSchema.from_dict(data)

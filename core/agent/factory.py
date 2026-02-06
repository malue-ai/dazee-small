"""
AgentFactory - Prompt 驱动的 Agent 动态初始化

🆕 V6.1: Schema 生成 Few-shot 化（替代硬编码映射）

核心理念：
- Prompt → LLM 生成 Schema → 动态初始化 Agent
- 修改 Prompt 即可改变 Agent 行为
- Prompt 是唯一的真相来源
- 🆕 通过 Few-shot 示例引导 LLM 推断，而非关键词匹配

参考：docs/15-FRAMEWORK_PROMPT_CONTRACT.md
"""

# 1. 标准库
import json
import re
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.llm import Message, create_llm_service

# 导入强类型 Schema
from core.schemas import (
    DEFAULT_AGENT_SCHEMA,
    AgentSchema,
    IntentAnalyzerConfig,
    MemoryManagerConfig,
    OutputFormatterConfig,
    PlanManagerConfig,
    SkillConfig,
    ToolSelectorConfig,
)

# 3. 本地模块
from logger import get_logger

# 2. 第三方库（无）

# 注意：multi 模块延迟导入（避免循环依赖/降低启动成本）
# from core.agent.orchestrator import MultiAgentOrchestrator
# from core.agent.models import OrchestratorConfig


# 🆕 V7: 类型检查导入（避免循环依赖）
if TYPE_CHECKING:
    from core.agent.base import Agent
    from core.agent.execution._multi import MultiAgentOrchestrator
    from core.agent.execution.protocol import ExecutorProtocol
    from core.routing import RoutingDecision


# ============================================================
# 🆕 V10.0: Executor 注册表
# ============================================================


def _get_executor_registry() -> Dict[str, type]:
    """
    获取 Executor 注册表（延迟加载）

    扩展点：新增策略只需在这里注册

    单智能体：
    - rvr: 标准 RVR 循环
    - rvr-b: 带回溯的 RVR-B

    多智能体：
    - sequential: 串行执行
    - parallel: 并行执行
    - hierarchical: 层级执行
    - multi: 通用多智能体（默认串行）
    """
    from core.agent.execution import (
        HierarchicalMultiExecutor,
        MultiAgentExecutor,
        ParallelMultiExecutor,
        RVRBExecutor,
        RVRExecutor,
        SequentialMultiExecutor,
    )

    return {
        # 单智能体
        "rvr": RVRExecutor,
        "rvr-b": RVRBExecutor,
        "rvrb": RVRBExecutor,
        "simple": RVRExecutor,
        # 多智能体
        "sequential": SequentialMultiExecutor,
        "parallel": ParallelMultiExecutor,
        "hierarchical": HierarchicalMultiExecutor,
        "multi": SequentialMultiExecutor,  # 默认串行
    }


def get_available_strategies() -> List[str]:
    """获取所有可用的执行策略"""
    return list(_get_executor_registry().keys())


logger = get_logger(__name__)


# ============================================================
# 组件类型枚举（用于类型安全）
# ============================================================


class ComponentType(Enum):
    """组件类型"""

    INTENT_ANALYZER = "intent_analyzer"
    PLAN_MANAGER = "plan_manager"
    TOOL_SELECTOR = "tool_selector"
    MEMORY_MANAGER = "memory_manager"
    OUTPUT_FORMATTER = "output_formatter"


# ============================================================
# Schema 生成 Prompt
# ============================================================

def _load_schema_generator_prompt() -> str:
    """加载 Schema 生成器 Prompt"""
    from prompts import load_prompt

    try:
        return load_prompt("factory/schema_generator")
    except FileNotFoundError:
        logger.warning("⚠️ Schema 生成器 Prompt 文件不存在，使用内联 fallback")
        return "分析以下 System Prompt 并生成 Agent Schema 配置（JSON 格式）。"


# ============================================================
# AgentFactory
# ============================================================


class AgentFactory:
    """
    Agent 工厂 - Prompt 驱动的动态初始化

    🆕 V7: 支持路由层集成

    用法：
        # 方式 1: 从 Prompt 创建（推荐）
        agent = await AgentFactory.from_prompt(system_prompt, event_manager)

        # 方式 2: 从 Schema 创建（精确控制）
        schema = AgentSchema(name="DataAgent", tools=["e2b_sandbox"], ...)
        agent = AgentFactory.from_schema(schema, system_prompt, event_manager)

        # 方式 3: 使用默认配置
        agent = AgentFactory.create_default(event_manager)

        # 🆕 方式 4: 从路由决策创建（V7 路由集成）
        routing_decision = await router.route(message, history)
        agent = await AgentFactory.from_routing_decision(
            decision=routing_decision,
            event_manager=event_manager
        )
    """

    @classmethod
    async def from_prompt(
        cls,
        system_prompt: str,
        event_manager,
        conversation_service=None,
        llm_service=None,
        use_default_if_failed: bool = True,
        cache_dir: str = None,
        instance_path: str = None,
        force_refresh: bool = False,
        prompt_schema=None,  # 🆕 V4.6: PromptSchema（提示词分层）
    ):
        """
        从 System Prompt 创建 Agent（核心方法）

        流程：
        1. 检查缓存（如果提供 cache_dir）
        2. 调用 LLM 根据 Prompt 生成 Schema（缓存未命中或 force_refresh）
        3. 验证 Schema（使用强类型 Pydantic 模型）
        4. 保存缓存（如果提供 cache_dir）
        5. 根据 Schema 初始化 Agent

        Args:
            system_prompt: 系统提示词
            event_manager: 事件管理器
            conversation_service: 会话服务
            llm_service: LLM 服务（用于生成 Schema，默认用 Haiku）
            use_default_if_failed: 生成失败时使用默认 Schema
            cache_dir: 缓存目录（如 instances/test_agent/.cache）
            instance_path: 实例目录（用于缓存失效检测）
            force_refresh: 强制刷新缓存，重新生成 Schema
            prompt_schema: 🆕 V4.6 PromptSchema（用于根据复杂度动态生成提示词）

        Returns:
            配置好的 Agent 实例
        """
        schema = None
        schema_data = None

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
                        logger.warning(f"⚠️ 缓存 Schema 解析失败: {e}，将重新生成")
                        schema = None

        # 2. 生成新 Schema（缓存未命中或失效）
        if schema is None:
            try:
                schema = await cls._generate_schema(system_prompt, llm_service)
                logger.info(f"✅ Schema 生成成功: {schema.name}")
                logger.debug(f"   Reasoning: {schema.reasoning}")

            except Exception as e:
                logger.warning(f"⚠️ Schema 生成失败: {e}")
                if use_default_if_failed:
                    logger.info("使用默认 Schema（基于关键词推断）")
                    schema = cls._infer_schema_from_prompt(system_prompt)
                else:
                    raise

            # 保存到缓存（无论是 LLM 生成还是关键词推断）
            if cache_dir and instance_path and schema:
                cls._save_schema_to_cache(Path(cache_dir), Path(instance_path), schema)

        # 3. 根据 Schema 创建 Agent
        return await cls.from_schema(
            schema=schema,
            system_prompt=system_prompt,
            event_manager=event_manager,
            conversation_service=conversation_service,
            prompt_schema=prompt_schema,  # 🆕 V4.6: 传递 PromptSchema
        )

    @classmethod
    async def _generate_schema(cls, system_prompt: str, llm_service=None) -> AgentSchema:
        """调用 LLM 生成 Schema"""
        if llm_service is None:
            # 🆕 使用配置化的 LLM Profile
            from config.llm_config import get_llm_profile

            profile = await get_llm_profile("schema_generator")
            llm_service = create_llm_service(**profile)

        response = await llm_service.create_message_async(
            messages=[
                Message(
                    role="user",
                    content=f"分析以下 System Prompt 并生成 Agent Schema:\n\n{system_prompt}",
                )
            ],
            system=_load_schema_generator_prompt(),
        )

        # 提取 JSON（LLMResponse.content 是 str 类型）
        content = response.content if response.content else ""
        schema_json = cls._extract_json(content)

        # 使用强类型 Schema 验证和解析
        return AgentSchema.from_llm_output(schema_json)

    @classmethod
    def _infer_schema_from_prompt(cls, system_prompt: str) -> AgentSchema:
        """
        V5.0: 获取保守默认 Schema（不做关键词猜测）

        用于：
        - LLM 调用失败时的 fallback
        - 快速启动场景

        V5.0 策略：
        - 不使用关键词匹配
        - 返回通用配置，让 Agent 自适应
        - 工具/Skills 由 instance 的 config.yaml 配置
        """
        logger.info("⚠️ 使用保守默认 Schema（LLM 推断失败）")

        # V5.0: 保守默认值，不做关键词猜测
        # 工具/Skills 应由 instance 的 config.yaml 配置
        return AgentSchema(
            name="GeneralAgent",
            description="通用智能体（保守默认配置）",
            plan_manager=PlanManagerConfig(enabled=True),  # 启用规划，适应复杂任务
            skills=[],  # 由 instance 配置
            tools=[],  # 由 instance 配置
            max_turns=15,  # 默认中等复杂度
            reasoning="V5.0 保守默认配置：LLM 推断失败，使用通用配置",
        )

    @classmethod
    async def from_schema(
        cls,
        schema: AgentSchema,
        system_prompt: str,
        event_manager,
        conversation_service=None,
        prompt_schema=None,  # 🆕 V4.6: PromptSchema（提示词分层）
        prompt_cache=None,  # 🆕 V4.6.2: InstancePromptCache（提示词缓存）
        apis_config=None,  # 🆕 预配置的 APIs（用于 api_calling 自动注入）
    ):
        """
        根据 Schema 创建 Agent（设计哲学：Schema 驱动）

        这是核心方法：根据强类型 Schema 动态初始化所有组件

        设计哲学：
        1. Schema 定义组件启用状态和配置参数
        2. System Prompt 作为运行时指令传递给 Agent
        3. Agent 根据 Schema 动态初始化组件
        4. 🆕 V4.6: PromptSchema 支持根据复杂度动态裁剪提示词
        5. 🆕 V4.6.2: InstancePromptCache 提供预生成的提示词版本
        6. 🆕 apis_config: 预配置的 APIs，用于 api_calling 工具自动注入认证
        7. 🆕 V7.1: 支持多智能体（根据 schema.multi_agent 自动选择）
        """
        logger.info(f"🏗️ 根据 Schema 初始化 Agent: {schema.name}")
        logger.debug(f"   Model: {schema.model}")
        logger.debug(
            f"   Skills: {[s.name if isinstance(s, SkillConfig) else s for s in schema.skills]}"
        )
        logger.debug(f"   Tools: {schema.tools}")
        logger.debug(f"   Max Turns: {schema.max_turns}")
        logger.debug(f"   Intent Analyzer: {'启用' if schema.intent_analyzer.enabled else '禁用'}")
        logger.debug(f"   Plan Manager: {'启用' if schema.plan_manager.enabled else '禁用'}")
        logger.debug(f"   Tool Selector: {'启用' if schema.tool_selector.enabled else '禁用'}")
        # 注意：output_formatter 配置保留在 Schema 中，但 Agent 不使用（由 API 层处理）
        if prompt_schema:
            logger.debug(
                f"   PromptSchema: {prompt_schema.agent_name} ({len(prompt_schema.modules)} 模块)"
            )
        if prompt_cache:
            logger.debug(
                f"   PromptCache: {prompt_cache.instance_name} (loaded={prompt_cache.is_loaded})"
            )
        if apis_config:
            logger.debug(f"   APIs: {len(apis_config)} 个预配置")

        # 🆕 V4.6.2: 优先使用 prompt_cache 中的 prompt_schema
        effective_prompt_schema = prompt_schema or (
            prompt_cache.prompt_schema if prompt_cache else None
        )

        # 🆕 V10.0: 统一使用 Agent + Executor 模式
        # 多智能体暂时保留旧实现（后续迁移）
        if schema.multi_agent is not None:
            # 多智能体模式（保留旧实现）
            logger.info(
                f"   🤝 多智能体模式: {schema.multi_agent.mode if hasattr(schema.multi_agent, 'mode') else 'default'}"
            )
            return await cls._create_multi_agent(
                schema=schema,
                system_prompt=system_prompt,
                event_manager=event_manager,
                conversation_service=conversation_service,
                prompt_schema=effective_prompt_schema,
                prompt_cache=prompt_cache,
                apis_config=apis_config,
            )
        else:
            # 🆕 V10.0: 单智能体使用统一 Agent + Executor
            return await cls._create_single_agent(
                schema=schema,
                system_prompt=system_prompt,
                event_manager=event_manager,
                conversation_service=conversation_service,
                prompt_schema=effective_prompt_schema,
                prompt_cache=prompt_cache,
                apis_config=apis_config,
                strategy=(
                    schema.execution_strategy if hasattr(schema, "execution_strategy") else "rvr"
                ),
            )

    @classmethod
    async def _create_single_agent(
        cls,
        schema: AgentSchema,
        system_prompt: str,
        event_manager,
        conversation_service,
        prompt_schema,
        prompt_cache,
        apis_config,
        strategy: str = "rvr",
    ) -> "Agent":
        """
        🆕 V10.0: 创建单智能体（统一 Agent + Executor）

        Args:
            schema: AgentSchema
            system_prompt: 系统提示词
            event_manager: 事件管理器
            conversation_service: 会话服务
            prompt_schema: 提示词模式
            prompt_cache: 提示词缓存
            apis_config: API 配置
            strategy: 执行策略 (rvr, rvr-b, ...)

        Returns:
            Agent 实例
        """
        import os

        from core.agent.base import Agent
        from core.context.compaction import QoSLevel, get_context_strategy
        from core.events.broadcaster import EventBroadcaster
        from core.tool import create_tool_context, create_tool_executor, create_tool_selector
        from core.tool.registry import create_capability_registry

        # 1. 获取 Executor
        registry = _get_executor_registry()
        strategy_key = strategy.lower().replace("-", "").replace("_", "")

        if strategy_key not in registry and strategy not in registry:
            logger.warning(f"未知策略 '{strategy}'，使用默认 'rvr'")
            strategy_key = "rvr"

        executor_cls = registry.get(strategy_key) or registry.get(strategy) or registry["rvr"]
        executor = executor_cls()

        # 2. 创建 LLM
        from config.llm_config import get_llm_profile
        from core.llm import ToolType

        # 🆕 V10.3: thinking_mode 决定是否启用原生 thinking
        # - native: 使用 LLM 原生 Extended Thinking
        # - simulated: 禁用原生 thinking，由 Agent 生成模拟思考
        # - none: 不展示思考
        llm_enable_thinking = False  # 默认关闭
        if schema.thinking_mode == "native":
            llm_enable_thinking = (
                schema.enable_thinking if schema.enable_thinking is not None else True
            )
        elif schema.thinking_mode == "simulated":
            llm_enable_thinking = False  # 模拟思考模式下禁用原生 thinking
        elif schema.thinking_mode == "none":
            llm_enable_thinking = False
        else:
            # 向后兼容：未配置时使用 enable_thinking
            llm_enable_thinking = (
                schema.enable_thinking if schema.enable_thinking is not None else True
            )

        llm_enable_caching = schema.enable_caching if schema.enable_caching is not None else True

        llm_kwargs = {
            "enable_thinking": llm_enable_thinking,
            "enable_caching": llm_enable_caching,
            "tools": [ToolType.BASH, ToolType.TEXT_EDITOR],
        }

        logger.info(
            f"🧠 Thinking 模式: {schema.thinking_mode}, 原生 thinking: {llm_enable_thinking}"
        )

        if schema.temperature is not None:
            llm_kwargs["temperature"] = schema.temperature
        if schema.max_tokens is not None:
            llm_kwargs["max_tokens"] = schema.max_tokens

        main_profile = await get_llm_profile("main_agent")
        profile_provider = str(main_profile.get("provider", "claude")).lower()
        if profile_provider == "claude":
            main_profile["model"] = schema.model
        main_profile.update(llm_kwargs)
        llm = create_llm_service(**main_profile)

        # 3. 创建 Broadcaster
        broadcaster = EventBroadcaster(event_manager, conversation_service=conversation_service)

        # 4. 创建 ToolExecutor
        capability_registry = create_capability_registry()
        tool_context = create_tool_context(
            event_manager=event_manager,
            workspace_dir=None,
            apis_config=apis_config or [],
        )
        tool_executor = create_tool_executor(
            registry=capability_registry,
            tool_context=tool_context,
        )

        # 5. Context Strategy
        qos_level_str = os.getenv("QOS_LEVEL", "pro")
        try:
            qos_level = QoSLevel(qos_level_str)
        except ValueError:
            qos_level = QoSLevel.PRO
        context_strategy = get_context_strategy(qos_level=qos_level)

        # 6. 创建 Agent
        agent = Agent(
            executor=executor,
            llm=llm,
            tool_executor=tool_executor,
            broadcaster=broadcaster,
            schema=schema,
            prompt_cache=prompt_cache,
            context_strategy=context_strategy,
            max_steps=schema.max_turns,
        )

        # 保存额外属性（用于克隆）
        agent.capability_registry = capability_registry
        agent.tool_selector = (
            create_tool_selector(registry=capability_registry)
            if schema.tool_selector.enabled
            else None
        )
        agent.apis_config = apis_config or []
        agent.workspace_dir = None
        agent.event_manager = event_manager
        agent.conversation_service = conversation_service

        logger.info(f"✅ Agent 初始化完成: {schema.name}, executor={executor.name}")
        if schema.reasoning:
            logger.info(f"   Reasoning: {schema.reasoning}")

        return agent

    @classmethod
    async def _create_multi_agent(
        cls,
        schema,
        system_prompt: str,
        event_manager,
        conversation_service,
        prompt_schema=None,
        prompt_cache=None,
        apis_config=None,
    ):
        """V7.1 遗留入口 — 委托给 create_multi_agent()"""
        return cls.create_multi_agent(
            schema=schema,
            event_manager=event_manager,
            conversation_service=conversation_service,
            prompt_cache=prompt_cache,
            system_prompt=system_prompt,
        )

    @classmethod
    async def create_default(cls, event_manager, conversation_service=None):
        """创建默认配置的 Agent"""
        return await cls.from_schema(
            schema=DEFAULT_AGENT_SCHEMA,
            system_prompt="",
            event_manager=event_manager,
            conversation_service=conversation_service,
        )

    @classmethod
    def create_router(cls, llm_service=None, prompt_cache=None, enable_llm: bool = True):
        """
        创建 AgentRouter 实例

        用于延迟初始化路由器。

        Args:
            llm_service: LLM 服务（用于意图分析）
            prompt_cache: InstancePromptCache
            enable_llm: 是否启用 LLM 分析

        Returns:
            AgentRouter 实例
        """
        from core.routing import AgentRouter

        return AgentRouter(
            llm_service=llm_service, prompt_cache=prompt_cache, enable_llm=enable_llm
        )

    @classmethod
    async def create_from_decision(
        cls,
        decision: "RoutingDecision",
        event_manager,
        conversation_service=None,
        workspace_dir: str = None,
        base_schema: "AgentSchema" = None,
        prompt_cache=None,
        system_prompt: str = None,
        apis_config=None,
        **kwargs,
    ):
        """
        根据路由决策创建 Agent（V7.8 新增）

        流程：
        1. 从 decision 获取 intent 和 agent_type
        2. 在 base_schema 基础上微调运行时参数
        3. 创建对应类型的 Agent（single/multi）

        Args:
            decision: RoutingDecision 路由决策
            event_manager: 事件管理器
            conversation_service: 会话服务
            workspace_dir: 工作目录
            base_schema: 实例级 Schema（来自 config.yaml）
            prompt_cache: InstancePromptCache
            system_prompt: 系统提示词
            apis_config: 预配置的 APIs
            **kwargs: 其他参数

        Returns:
            Agent 或 MultiAgentOrchestrator 实例
        """
        intent = decision.intent
        agent_type = decision.agent_type

        logger.info(
            f"🏗️ AgentFactory.create_from_decision: "
            f"agent_type={agent_type}, "
            f"complexity={intent.complexity.value if intent else 'N/A'}"
        )

        # 确定基础 Schema
        schema = base_schema or DEFAULT_AGENT_SCHEMA

        # 根据 intent 微调运行时参数
        if intent:
            # 根据复杂度调整 max_turns
            from core.routing.types import Complexity

            if intent.complexity == Complexity.SIMPLE:
                schema = schema.model_copy(update={"max_turns": min(schema.max_turns, 8)})
            elif intent.complexity == Complexity.COMPLEX:
                schema = schema.model_copy(update={"max_turns": max(schema.max_turns, 20)})

        # 根据 agent_type 创建对应的 Agent
        if agent_type == "multi":
            # 多智能体：统一创建入口
            return cls.create_multi_agent(
                schema=schema,
                event_manager=event_manager,
                conversation_service=conversation_service,
                prompt_cache=prompt_cache,
                system_prompt=system_prompt,
                multi_agent_config=kwargs.get("multi_agent_config"),
                broadcaster=kwargs.get("broadcaster"),
            )
        else:
            # 🆕 V10.0: 单智能体使用统一 Agent + Executor
            strategy = "rvr-b" if agent_type == "rvr-b" else "rvr"
            return await cls._create_single_agent(
                schema=schema,
                system_prompt=system_prompt or "",
                event_manager=event_manager,
                conversation_service=conversation_service,
                prompt_schema=None,
                prompt_cache=prompt_cache,
                apis_config=apis_config,
                strategy=strategy,
            )

    @classmethod
    def create_multi_agent(
        cls,
        schema=None,
        event_manager=None,
        conversation_service=None,
        prompt_cache=None,
        system_prompt: str = None,
        multi_agent_config=None,
        broadcaster=None,
    ) -> "MultiAgentOrchestrator":
        """
        统一的多智能体创建入口

        V10.3: 合并原有的 3 条创建路径为 1 条公共方法。

        Args:
            schema: AgentSchema（可选）
            event_manager: 事件管理器（可选）
            conversation_service: 会话服务（可选）
            prompt_cache: 提示词缓存（可选）
            system_prompt: 系统提示词（可选）
            multi_agent_config: MultiAgentConfig（可选，默认使用默认配置）
            broadcaster: EventBroadcaster（可选，用于事件发送）

        Returns:
            MultiAgentOrchestrator 实例
        """
        from core.agent.execution._multi import MultiAgentOrchestrator
        from core.agent.models import MultiAgentConfig

        config = multi_agent_config or MultiAgentConfig()

        orchestrator = MultiAgentOrchestrator(
            config=config,
            enable_checkpoints=True,
            enable_lead_agent=True,
        )

        # V10.4: 正规依赖注入
        if broadcaster:
            orchestrator.inject_dependencies(broadcaster=broadcaster)

        # 附加元数据
        orchestrator.schema = schema
        orchestrator.system_prompt = system_prompt
        orchestrator.conversation_service = conversation_service
        if schema:
            orchestrator.model = schema.model
            orchestrator.max_turns = schema.max_turns

        logger.info("✅ MultiAgentOrchestrator 创建完成 (via Factory)")
        return orchestrator

    @classmethod
    def _create_multi_agent_from_decision(
        cls,
        decision: "RoutingDecision" = None,
        schema=None,
        event_manager=None,
        conversation_service=None,
        prompt_cache=None,
        system_prompt=None,
        apis_config=None,
        broadcaster=None,
        multi_agent_config=None,
        **kwargs,
    ):
        """从路由决策创建多智能体 — 委托给 create_multi_agent()"""
        return cls.create_multi_agent(
            schema=schema,
            event_manager=event_manager,
            conversation_service=conversation_service,
            prompt_cache=prompt_cache,
            system_prompt=system_prompt,
            multi_agent_config=multi_agent_config,
            broadcaster=broadcaster,
        )

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """从文本中提取 JSON"""
        # 尝试找 ```json ... ``` 块
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if json_match:
            return json.loads(json_match.group(1))

        # 尝试找 { ... } 块
        brace_match = re.search(r"\{[\s\S]*\}", text)
        if brace_match:
            return json.loads(brace_match.group(0))

        raise ValueError("无法从响应中提取 JSON")

    @classmethod
    def _should_use_cache(cls, cache_dir, instance_dir) -> bool:
        """
        检查是否应该使用缓存

        Args:
            cache_dir: 缓存目录 Path 对象
            instance_dir: 实例目录 Path 对象

        Returns:
            True 表示可以使用缓存
        """
        try:
            from utils.cache_utils import is_cache_valid

            return is_cache_valid(cache_dir, instance_dir)
        except Exception as e:
            logger.warning(f"缓存有效性检查失败: {e}")
            return False

    @classmethod
    def _load_schema_from_cache(cls, cache_dir) -> Optional[Dict[str, Any]]:
        """
        从缓存加载 Schema

        Args:
            cache_dir: 缓存目录 Path 对象

        Returns:
            Schema 字典，失败返回 None
        """
        try:
            from utils.cache_utils import load_schema_cache

            return load_schema_cache(cache_dir)
        except Exception as e:
            logger.error(f"加载 Schema 缓存失败: {e}")
            return None

    @classmethod
    def _save_schema_to_cache(cls, cache_dir, instance_dir, schema: AgentSchema) -> bool:
        """
        保存 Schema 到缓存

        Args:
            cache_dir: 缓存目录 Path 对象
            instance_dir: 实例目录 Path 对象
            schema: AgentSchema 对象

        Returns:
            成功返回 True
        """
        try:
            from utils.cache_utils import save_cache_metadata, save_schema_cache

            # 转换为字典
            schema_data = schema.to_dict() if hasattr(schema, "to_dict") else schema.dict()

            # 保存 Schema
            save_schema_cache(cache_dir, schema_data)

            # 保存元数据
            save_cache_metadata(cache_dir, instance_dir)

            logger.info(f"✅ Schema 已保存到缓存: {cache_dir}")
            return True
        except Exception as e:
            logger.error(f"保存 Schema 缓存失败: {e}")
            return False


# ============================================================
# 预设 Agent 配置
# ============================================================


class AgentPresets:
    """预设 Agent 配置，快速创建常用 Agent"""

    @staticmethod
    def data_analyst() -> AgentSchema:
        """数据分析 Agent"""
        return AgentSchema(
            name="DataAnalysisAgent",
            description="专业数据分析助手，擅长处理 CSV/Excel 数据并生成报表",
            skills=[SkillConfig(name="excel-generator")],
            tools=["e2b_sandbox"],
            max_turns=15,
            plan_manager=PlanManagerConfig(enabled=True, max_steps=10, granularity="medium"),
            output_formatter=OutputFormatterConfig(
                default_format="markdown", code_highlighting=True
            ),
            reasoning="数据分析任务需要 E2B 沙箱执行 pandas 代码，xlsx 生成报表",
        )

    @staticmethod
    def researcher() -> AgentSchema:
        """研究助手 Agent"""
        return AgentSchema(
            name="ResearchAgent",
            description="深度研究助手，擅长搜索、分析和总结信息",
            skills=[],
            tools=["tavily_search", "exa_search"],
            max_turns=20,
            plan_manager=PlanManagerConfig(enabled=True, max_steps=15, granularity="fine"),
            memory_manager=MemoryManagerConfig(retention_policy="session", working_memory_limit=30),
            reasoning="研究任务需要多轮搜索和信息整合，启用计划管理",
        )

    @staticmethod
    def report_generator() -> AgentSchema:
        """报告生成 Agent"""
        return AgentSchema(
            name="ReportAgent",
            description="专业报告生成助手，支持 Excel/PPT/PDF 多种格式",
            skills=[
                SkillConfig(name="excel-generator"),
                SkillConfig(name="ppt-generator"),
                SkillConfig(name="pdf-generator"),
            ],
            tools=["e2b_sandbox", "tavily_search"],
            max_turns=15,
            plan_manager=PlanManagerConfig(enabled=True, max_steps=12),
            output_formatter=OutputFormatterConfig(
                default_format="markdown", include_metadata=True
            ),
            reasoning="报告生成需要多种 Skills 和数据处理能力",
        )

    @staticmethod
    def simple_qa() -> AgentSchema:
        """简单问答 Agent"""
        return AgentSchema(
            name="SimpleQAAgent",
            description="简单问答助手，快速响应",
            skills=[],
            tools=[],
            max_turns=5,
            plan_manager=PlanManagerConfig(enabled=False),
            memory_manager=MemoryManagerConfig(working_memory_limit=10, auto_compress=False),
            reasoning="简单问答不需要工具和计划，快速响应",
        )


# ============================================================
# 便捷函数
# ============================================================


async def create_agent_from_prompt(system_prompt: str, event_manager, **kwargs):
    """便捷函数：从 Prompt 创建 Agent"""
    return await AgentFactory.from_prompt(system_prompt, event_manager, **kwargs)


async def create_agent_from_preset(
    preset_name: str, event_manager, system_prompt: str = "", **kwargs
):
    """
    便捷函数：从预设创建 Agent

    Args:
        preset_name: 预设名称 (data_analyst, researcher, report_generator, simple_qa)
        event_manager: 事件管理器
        system_prompt: 自定义系统提示词
    """
    presets = {
        "data_analyst": AgentPresets.data_analyst,
        "researcher": AgentPresets.researcher,
        "report_generator": AgentPresets.report_generator,
        "simple_qa": AgentPresets.simple_qa,
    }

    if preset_name not in presets:
        raise ValueError(f"未知预设: {preset_name}，可用: {list(presets.keys())}")

    schema = presets[preset_name]()

    return await AgentFactory.from_schema(
        schema=schema, system_prompt=system_prompt, event_manager=event_manager, **kwargs
    )


def create_schema_from_dict(data: Dict[str, Any]) -> AgentSchema:
    """从字典创建强类型 Schema（供外部使用）"""
    return AgentSchema.from_dict(data)

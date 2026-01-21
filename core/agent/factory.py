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

# 🆕 V7: 类型检查导入（避免循环依赖）
if TYPE_CHECKING:
    from core.routing import RoutingDecision
    from core.agent import SimpleAgent
    from core.agent.multi import MultiAgentOrchestrator

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

SCHEMA_GENERATOR_PROMPT = """
# Agent Schema 生成器

分析用户提供的 System Prompt，生成最合适的 Agent Schema 配置。

## 分析原则

通过语义理解推断配置，而非关键词匹配。

1. **任务复杂度**：分析 Prompt 描述的任务性质
2. **工具需求**：根据任务需求推断工具/技能
3. **组件配置**：根据场景启用/配置组件

## Few-shot 示例（学习推断模式）

<example>
<prompt>
你是一个专业的数据分析师，帮助用户分析销售数据、生成报表、可视化趋势。你擅长使用 pandas 处理数据，能够生成专业的 Excel 报告。
</prompt>
<schema>
{
  "name": "DataAnalyst",
  "description": "专业数据分析助手",
  "tools": ["e2b_sandbox"],
  "skills": [{"skill_id": "xlsx", "type": "custom"}],
  "plan_manager": {"enabled": true, "max_steps": 15},
  "max_turns": 15,
  "reasoning": "涉及数据处理、代码执行和报表生成，需要沙箱环境和 Excel 能力"
}
</schema>
</example>

<example>
<prompt>
你是一个简单的问答助手，回答用户的日常问题，如天气、时间、基础知识等。保持回复简洁明了。
</prompt>
<schema>
{
  "name": "QAAssistant",
  "description": "简单问答助手",
  "tools": [],
  "skills": [],
  "plan_manager": {"enabled": false},
  "max_turns": 8,
  "reasoning": "简单问答场景，无需工具和规划，快速响应"
}
</schema>
</example>

<example>
<prompt>
你是一个深度研究助手，帮助用户搜索信息、分析多个来源、整合观点并生成研究报告。需要从网络获取最新信息。
</prompt>
<schema>
{
  "name": "ResearchAgent",
  "description": "深度研究助手",
  "tools": ["web_search", "exa_search"],
  "skills": [],
  "plan_manager": {"enabled": true, "max_steps": 15, "granularity": "fine"},
  "memory_manager": {"retention_policy": "session", "working_memory_limit": 30},
  "max_turns": 20,
  "reasoning": "研究任务需要多轮搜索和信息整合，启用细粒度规划"
}
</schema>
</example>

<example>
<prompt>
你是一个报告生成专家，能够根据用户需求生成 PPT 演示文稿、Excel 数据报表和 PDF 文档。支持多种输出格式。
</prompt>
<schema>
{
  "name": "ReportGenerator",
  "description": "多格式报告生成专家",
  "tools": ["e2b_sandbox"],
  "skills": [
    {"skill_id": "xlsx", "type": "custom"},
    {"skill_id": "pptx", "type": "custom"},
    {"skill_id": "pdf", "type": "custom"}
  ],
  "plan_manager": {"enabled": true, "max_steps": 12},
  "output_formatter": {"default_format": "markdown", "include_metadata": true},
  "max_turns": 15,
  "reasoning": "报告生成需要多种文档技能和代码执行能力"
}
</schema>
</example>

<example>
<prompt>
你是一个编程助手，帮助用户编写代码、调试问题、解释代码逻辑。支持多种编程语言。
</prompt>
<schema>
{
  "name": "CodeAssistant",
  "description": "编程助手",
  "tools": ["e2b_sandbox"],
  "skills": [],
  "plan_manager": {"enabled": true, "max_steps": 10},
  "output_formatter": {"default_format": "markdown", "code_highlighting": true},
  "max_turns": 15,
  "reasoning": "编程任务需要代码执行环境验证代码正确性"
}
</schema>
</example>

## 组件配置字段说明

## 组件配置字段说明

### intent_analyzer
- enabled: bool (是否启用)
- complexity_levels: List[str] (支持的复杂度级别)
- task_types: List[str] (支持的任务类型)
- output_formats: List[str] (支持的输出格式)
- use_llm: bool (是否使用 LLM 分析)

### plan_manager
- enabled: bool
- trigger_condition: str (触发条件表达式)
- max_steps: int (1-50)
- granularity: str (fine/medium/coarse)
- allow_dynamic_adjustment: bool
- replan_enabled: bool (是否允许重新规划，默认 true)
- max_replan_attempts: int (最大重规划次数，0-5，默认 2)
- replan_strategy: str (full: 全量重规划 / incremental: 保留已完成步骤)
- failure_threshold: float (失败率阈值，超过时建议重规划，0-1，默认 0.3)

### tool_selector
- enabled: bool
- available_tools: List[str] (可用工具，空为全部)
- selection_strategy: str (capability_based/priority_based/all)
- allow_parallel: bool
- max_parallel_tools: int (1-10)
- base_tools: List[str] (始终包含的工具)

### memory_manager
- enabled: bool
- retention_policy: str (session/user/persistent)
- episodic_memory: bool
- working_memory_limit: int (5-100)
- auto_compress: bool

### output_formatter
**说明**：此配置供 Service 层使用，Agent 本身不做格式化。
**用途**：Service 层通过 agent.schema.output_formatter 读取配置，按需创建 OutputFormatter。
- enabled: bool
- default_format: str (text/markdown/json/html)
- code_highlighting: bool
- max_output_length: int

## 输出格式

```json
{
  "name": "Agent 名称",
  "description": "Agent 描述",
  "intent_analyzer": {"enabled": true, "task_types": [...], ...},
  "plan_manager": {"enabled": true/false, "max_steps": 10, ...},
  "tool_selector": {"enabled": true, "selection_strategy": "capability_based", ...},
  "memory_manager": {"enabled": true, "retention_policy": "session", ...},
  "output_formatter": {"enabled": true, "default_format": "markdown", ...},
  "skills": [{"skill_id": "xlsx", "type": "custom"}],
  "tools": ["e2b_sandbox", "web_search"],
  "model": "claude-sonnet-4-5-20250929",
  "max_turns": 15,
  "allow_parallel_tools": false,
  "reasoning": "配置理由"
}
```

## 默认策略

- Prompt 未明确 → 使用保守默认值
- 优先用户安全和体验
- Skills 列表尽量精简（利于 Prompt Cache）

现在，分析用户提供的 System Prompt 并生成 Agent Schema。
"""


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
            event_manager=event_manager,
            workspace_dir=workspace_dir
        )
    """
    
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
        prompt_schema = None,  # 🆕 V4.6: PromptSchema（提示词分层）
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
            workspace_dir: 工作目录
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
        from pathlib import Path
        
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
        return cls.from_schema(
            schema=schema,
            system_prompt=system_prompt,
            event_manager=event_manager,
            workspace_dir=workspace_dir,
            conversation_service=conversation_service,
            prompt_schema=prompt_schema,  # 🆕 V4.6: 传递 PromptSchema
        )

    @classmethod
    def create_router(
        cls,
        prompt_cache=None
    ):
        """
        创建路由器（注入 InstancePromptCache）
        """
        from core.routing import AgentRouter
        from core.llm import create_llm_service
        from config.llm_config import get_llm_profile
        
        profile = get_llm_profile("intent_analyzer")
        profile.setdefault("tools", [])
        llm_service = create_llm_service(**profile)
        
        return AgentRouter(llm_service=llm_service, prompt_cache=prompt_cache)

    @classmethod
    def create_route(
        cls,
        prompt_cache=None
    ):
        """
        兼容入口：create_route → create_router
        """
        return cls.create_router(prompt_cache=prompt_cache)
    
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
            # 🆕 使用配置化的 LLM Profile
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
            tools=[],   # 由 instance 配置
            max_turns=15,  # 默认中等复杂度
            reasoning="V5.0 保守默认配置：LLM 推断失败，使用通用配置"
        )
    
    @classmethod
    def from_schema(
        cls,
        schema: AgentSchema,
        system_prompt: str,
        event_manager,
        workspace_dir: str = None,
        conversation_service = None,
        prompt_schema = None,  # 🆕 V4.6: PromptSchema（提示词分层）
        prompt_cache = None,   # 🆕 V4.6.2: InstancePromptCache（提示词缓存）
        apis_config = None,    # 🆕 预配置的 APIs（用于 api_calling 自动注入）
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
        logger.debug(f"   Skills: {[s.skill_id if isinstance(s, SkillConfig) else s for s in schema.skills]}")
        logger.debug(f"   Tools: {schema.tools}")
        logger.debug(f"   Max Turns: {schema.max_turns}")
        logger.debug(f"   Intent Analyzer: {'启用' if schema.intent_analyzer.enabled else '禁用'}")
        logger.debug(f"   Plan Manager: {'启用' if schema.plan_manager.enabled else '禁用'}")
        logger.debug(f"   Tool Selector: {'启用' if schema.tool_selector.enabled else '禁用'}")
        # 注意：output_formatter 配置保留在 Schema 中，但 Agent 不使用（由 API 层处理）
        if prompt_schema:
            logger.debug(f"   PromptSchema: {prompt_schema.agent_name} ({len(prompt_schema.modules)} 模块)")
        if prompt_cache:
            logger.debug(f"   PromptCache: {prompt_cache.instance_name} (loaded={prompt_cache.is_loaded})")
        if apis_config:
            logger.debug(f"   APIs: {len(apis_config)} 个预配置")
        
        # 🆕 V4.6.2: 优先使用 prompt_cache 中的 prompt_schema
        effective_prompt_schema = prompt_schema or (prompt_cache.prompt_schema if prompt_cache else None)
        
        # 🆕 V7.1: 根据 schema.multi_agent 决定创建单智能体或多智能体
        if schema.multi_agent is not None:
            # 多智能体模式
            logger.info(f"   🤝 多智能体模式: {schema.multi_agent.mode if hasattr(schema.multi_agent, 'mode') else 'default'}")
            return cls._create_multi_agent(
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
            # 单智能体模式
            from core.agent.simple import SimpleAgent
            
            agent = SimpleAgent(
                model=schema.model,
                max_turns=schema.max_turns,
                event_manager=event_manager,
                workspace_dir=workspace_dir,
                conversation_service=conversation_service,
                schema=schema,  # 🆕 传递 Schema（驱动组件初始化）
                system_prompt=system_prompt,  # 🆕 传递 System Prompt（运行时指令）
                prompt_schema=effective_prompt_schema,  # 🆕 V4.6: 传递 PromptSchema（提示词分层）
                prompt_cache=prompt_cache,  # 🆕 V4.6.2: 传递 InstancePromptCache
                apis_config=apis_config,  # 🆕 传递预配置的 APIs
            )
            
            logger.info(f"✅ SimpleAgent 初始化完成: {schema.name}")
            if schema.reasoning:
                logger.info(f"   Reasoning: {schema.reasoning}")
            
            return agent
    
    @classmethod
    def _create_multi_agent(
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
        """
        🆕 V7.1: 创建多智能体编排器
        
        Args:
            schema: AgentSchema（包含 multi_agent 配置）
            其他参数同 from_schema()
            
        Returns:
            MultiAgentOrchestrator 实例
        """
        from core.agent.multi import MultiAgentOrchestrator
        from core.agent.multi.models import OrchestratorConfig
        from core.llm import create_llm_service
        from config.llm_config import get_llm_profile
        from core.memory.working import WorkingMemory
        
        # 创建 LLM Service（用于任务分解和结果聚合）
        profile = get_llm_profile("lead_agent")
        profile.update({
            "model": schema.model,
            "enable_thinking": True,
            "enable_caching": True,
        })
        llm_service = create_llm_service(**profile)
        
        # 创建 Memory Manager（TODO: 从 schema 配置）
        memory_manager = WorkingMemory(event_manager=event_manager)
        
        # 解析 multi_agent 配置
        multi_agent_config = schema.multi_agent
        orchestrator_config = OrchestratorConfig(
            max_parallel_workers=getattr(multi_agent_config, 'max_parallel_workers', 3),
            enable_checkpointing=getattr(multi_agent_config, 'enable_checkpointing', True),
            checkpoint_interval=getattr(multi_agent_config, 'checkpoint_interval', 60),
        )
        
        # 提取 workers 配置
        workers_config = getattr(multi_agent_config, 'workers', [])
        
        # 创建编排器
        orchestrator = MultiAgentOrchestrator(
            event_manager=event_manager,
            memory_manager=memory_manager,
            llm_service=llm_service,
            config=orchestrator_config,
            prompt_cache=prompt_cache,
            workers_config=workers_config,
        )
        
        # 附加元数据（用于统一接口）
        orchestrator.schema = schema
        orchestrator.system_prompt = system_prompt
        orchestrator.workspace_dir = workspace_dir
        orchestrator.conversation_service = conversation_service
        orchestrator.model = schema.model
        orchestrator.max_turns = schema.max_turns
        
        logger.info(f"✅ MultiAgentOrchestrator 初始化完成: {schema.name} ({len(workers_config)} workers)")
        return orchestrator
    
    @classmethod
    def create_default(
        cls,
        event_manager,
        workspace_dir: str = None,
        conversation_service = None
    ):
        """创建默认配置的 Agent"""
        return cls.from_schema(
            schema=DEFAULT_AGENT_SCHEMA,
            system_prompt="",
            event_manager=event_manager,
            workspace_dir=workspace_dir,
            conversation_service=conversation_service
        )
    
    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """从文本中提取 JSON"""
        import re
        
        # 尝试找 ```json ... ``` 块
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', text)
        if json_match:
            return json.loads(json_match.group(1))
        
        # 尝试找 { ... } 块
        brace_match = re.search(r'\{[\s\S]*\}', text)
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
            from utils.cache_utils import save_schema_cache, save_cache_metadata
            
            # 转换为字典
            schema_data = schema.to_dict() if hasattr(schema, 'to_dict') else schema.dict()
            
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
            skills=[SkillConfig(skill_id="xlsx", type="custom")],
            tools=["e2b_sandbox"],
            max_turns=15,
            plan_manager=PlanManagerConfig(
                enabled=True, 
                max_steps=10,
                granularity="medium"
            ),
            output_formatter=OutputFormatterConfig(
                default_format="markdown",
                code_highlighting=True
            ),
            reasoning="数据分析任务需要 E2B 沙箱执行 pandas 代码，xlsx 生成报表"
        )
    
    @staticmethod
    def researcher() -> AgentSchema:
        """研究助手 Agent"""
        return AgentSchema(
            name="ResearchAgent",
            description="深度研究助手，擅长搜索、分析和总结信息",
            skills=[],
            tools=["web_search", "exa_search"],
            max_turns=20,
            plan_manager=PlanManagerConfig(
                enabled=True,
                max_steps=15,
                granularity="fine"
            ),
            memory_manager=MemoryManagerConfig(
                retention_policy="session",
                working_memory_limit=30
            ),
            reasoning="研究任务需要多轮搜索和信息整合，启用计划管理"
        )
    
    @staticmethod
    def report_generator() -> AgentSchema:
        """报告生成 Agent"""
        return AgentSchema(
            name="ReportAgent",
            description="专业报告生成助手，支持 Excel/PPT/PDF 多种格式",
            skills=[
                SkillConfig(skill_id="xlsx", type="custom"),
                SkillConfig(skill_id="pptx", type="custom"),
                SkillConfig(skill_id="pdf", type="custom"),
            ],
            tools=["e2b_sandbox", "web_search"],
            max_turns=15,
            plan_manager=PlanManagerConfig(
                enabled=True,
                max_steps=12
            ),
            output_formatter=OutputFormatterConfig(
                default_format="markdown",
                include_metadata=True
            ),
            reasoning="报告生成需要多种 Skills 和数据处理能力"
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
            memory_manager=MemoryManagerConfig(
                working_memory_limit=10,
                auto_compress=False
            ),
            reasoning="简单问答不需要工具和计划，快速响应"
        )


# ============================================================
# 便捷函数
# ============================================================

async def create_agent_from_prompt(
    system_prompt: str,
    event_manager,
    **kwargs
):
    """便捷函数：从 Prompt 创建 Agent"""
    return await AgentFactory.from_prompt(system_prompt, event_manager, **kwargs)


def create_agent_from_preset(
    preset_name: str,
    event_manager,
    system_prompt: str = "",
    **kwargs
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
    
    return AgentFactory.from_schema(
        schema=schema,
        system_prompt=system_prompt,
        event_manager=event_manager,
        **kwargs
    )


# ============================================================
# 🆕 V7: 路由层集成
# ============================================================

async def create_agent_from_routing_decision(
    routing_decision: "RoutingDecision",
    event_manager,
    workspace_dir: str = None,
    conversation_service = None,
    system_prompt: str = "",
    **kwargs
) -> "SimpleAgent":
    """
    🆕 V7: 从路由决策创建 Agent（支持意图注入）
    
    流程：
    1. 从 routing_decision 提取 intent 和 complexity
    2. 根据 complexity 选择 Schema 配置（简单/中等/复杂）
    3. 创建 Agent，并将 intent 传递给 Agent.chat()
    
    Args:
        routing_decision: 路由决策结果
        event_manager: 事件管理器
        workspace_dir: 工作目录
        conversation_service: 会话服务
        system_prompt: 系统提示词（可选）
        **kwargs: 其他参数
        
    Returns:
        配置好的 SimpleAgent 实例（intent 已注入）
        
    使用示例：
        decision = await router.route(message, history)
        agent = await create_agent_from_routing_decision(
            decision, event_manager, workspace_dir
        )
        
        # Agent 内部会使用 routing_decision.intent，跳过内部意图分析
        async for event in agent.chat(messages, intent=decision.intent):
            yield event
    """
    from core.routing import RoutingDecision
    
    intent = routing_decision.intent
    complexity_score = routing_decision.complexity_score
    
    logger.info(
        f"🏭 从路由决策创建 Agent: task_type={intent.task_type.value}, "
        f"complexity={complexity_score:.2f}"
    )
    
    # 根据复杂度选择 Schema 配置
    # 🔑 关键原则：Plan 是否启用由 Claude 自主决定（通过 plan_todo 工具），
    #              我们只设置结构性配置（max_turns）
    if complexity_score <= 3.0:
        # 简单任务：快速响应，限制轮数
        schema = AgentSchema(
            name="SimpleAgent",
            description="简单任务快速响应",
            intent_analyzer=IntentAnalyzerConfig(enabled=False),  # 跳过内部分析（路由层已完成）
            tool_selector=ToolSelectorConfig(enabled=True),
            max_turns=8,
            reasoning=f"简单任务（score={complexity_score:.2f}），限制 8 轮"
        )
    elif complexity_score <= 6.0:
        # 中等任务：适中轮数
        schema = AgentSchema(
            name="MediumAgent",
            description="中等复杂度任务",
            intent_analyzer=IntentAnalyzerConfig(enabled=False),  # 跳过内部分析（路由层已完成）
            tool_selector=ToolSelectorConfig(enabled=True),
            max_turns=15,
            reasoning=f"中等任务（score={complexity_score:.2f}），限制 15 轮"
        )
    else:
        # 复杂任务：完整轮数配置
        schema = AgentSchema(
            name="ComplexAgent",
            description="复杂任务完整配置",
            intent_analyzer=IntentAnalyzerConfig(enabled=False),  # 跳过内部分析（路由层已完成）
            tool_selector=ToolSelectorConfig(enabled=True),
            memory_manager=MemoryManagerConfig(
                retention_policy="session",
                working_memory_limit=30
            ),
            max_turns=25,
            reasoning=f"复杂任务（score={complexity_score:.2f}），完整配置"
        )
    
    # 创建 Agent（intent 由路由层提供，不再内部分析）
    agent = AgentFactory.from_schema(
        schema=schema,
        system_prompt=system_prompt or "你是一个智能助手，帮助用户完成任务。",
        event_manager=event_manager,
        workspace_dir=workspace_dir,
        conversation_service=conversation_service,
        **kwargs
    )
    
    logger.info(f"✅ Agent 创建完成: schema={schema.name}, max_turns={schema.max_turns}")
    
    return agent


async def create_multi_agent_from_routing_decision(
    routing_decision: "RoutingDecision",
    **kwargs
) -> "MultiAgentOrchestrator":
    """
    🆕 V7: 从路由决策创建多智能体编排器
    
    Args:
        routing_decision: 路由决策结果
        **kwargs: 其他参数
        
    Returns:
        MultiAgentOrchestrator 实例
        
    注意：P1 待完善多智能体执行逻辑
    """
    from core.agent.multi import MultiAgentOrchestrator, ExecutionMode
    from core.routing import RoutingDecision
    
    intent = routing_decision.intent
    
    logger.info(
        f"🏭 从路由决策创建多智能体: task_type={intent.task_type.value}, "
        f"complexity={routing_decision.complexity_score:.2f}"
    )
    
    # 根据任务类型选择执行模式
    if intent.task_type.value in ["coding", "research"]:
        mode = ExecutionMode.SEQUENTIAL
    elif intent.task_type.value in ["document", "analysis"]:
        mode = ExecutionMode.PARALLEL
    else:
        mode = ExecutionMode.HIERARCHICAL
    
    # 创建编排器配置（占位实现，P1 完善）
    orchestrator = MultiAgentOrchestrator(
        mode=mode,
        agents=[
            {"agent_id": "planner", "role": "planner"},
            {"agent_id": "executor", "role": "executor"},
            {"agent_id": "reviewer", "role": "reviewer"},
        ]
    )
    
    logger.info(f"✅ 多智能体编排器创建完成: mode={mode.value}")
    
    return orchestrator
    return AgentFactory.from_schema(schema, system_prompt, event_manager, **kwargs)


def create_schema_from_dict(data: Dict[str, Any]) -> AgentSchema:
    """从字典创建强类型 Schema（供外部使用）"""
    return AgentSchema.from_dict(data)

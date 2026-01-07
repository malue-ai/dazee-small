"""
AgentFactory - Prompt 驱动的 Agent 动态初始化

核心理念：
- Prompt → LLM 生成 Schema → 动态初始化 Agent
- 修改 Prompt 即可改变 Agent 行为
- Prompt 是唯一的真相来源

参考：docs/15-FRAMEWORK_PROMPT_CONTRACT.md
"""

import json
from typing import Optional, List, Dict, Any
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

## 分析维度

1. **任务复杂度**：
   - 简单问答 → max_turns=8, plan_manager.enabled=false
   - 复杂任务 → max_turns=15, plan_manager.enabled=true

2. **工具需求**：
   - 提到"数据分析"、"pandas" → tools=["e2b_sandbox"]
   - 提到"搜索"、"查找" → tools=["web_search", "exa_search"]
   - 提到"Excel"、"表格" → skills=[{"skill_id": "xlsx", "type": "custom"}]
   - 提到"PPT"、"演示" → skills=[{"skill_id": "pptx", "type": "custom"}]

3. **组件配置**：
   - intent_analyzer: 默认启用，可配置 task_types, output_formats
   - plan_manager: 复杂任务启用，配置 max_steps, granularity
   - tool_selector: 默认启用，配置 selection_strategy, allow_parallel
   - memory_manager: 默认启用，配置 retention_policy, working_memory_limit
   - output_formatter: 默认启用，配置 default_format

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
    
    用法：
        # 方式 1: 从 Prompt 创建（推荐）
        agent = await AgentFactory.from_prompt(system_prompt, event_manager)
        
        # 方式 2: 从 Schema 创建（精确控制）
        schema = AgentSchema(name="DataAgent", tools=["e2b_sandbox"], ...)
        agent = AgentFactory.from_schema(schema, system_prompt, event_manager)
        
        # 方式 3: 使用默认配置
        agent = AgentFactory.create_default(event_manager)
    """
    
    @classmethod
    async def from_prompt(
        cls,
        system_prompt: str,
        event_manager,
        workspace_dir: str = None,
        conversation_service = None,
        llm_service = None,
        use_default_if_failed: bool = True
    ):
        """
        从 System Prompt 创建 Agent（核心方法）
        
        流程：
        1. 调用 LLM 根据 Prompt 生成 Schema
        2. 验证 Schema（使用强类型 Pydantic 模型）
        3. 根据 Schema 初始化 Agent
        
        Args:
            system_prompt: 系统提示词
            event_manager: 事件管理器
            workspace_dir: 工作目录
            conversation_service: 会话服务
            llm_service: LLM 服务（用于生成 Schema，默认用 Haiku）
            use_default_if_failed: 生成失败时使用默认 Schema
        
        Returns:
            配置好的 Agent 实例
        """
        # 1. 生成 Schema
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
        
        # 2. 根据 Schema 创建 Agent
        return cls.from_schema(
            schema=schema,
            system_prompt=system_prompt,
            event_manager=event_manager,
            workspace_dir=workspace_dir,
            conversation_service=conversation_service
        )
    
    @classmethod
    async def _generate_schema(
        cls,
        system_prompt: str,
        llm_service = None
    ) -> AgentSchema:
        """调用 LLM 生成 Schema"""
        if llm_service is None:
            from core.llm import create_claude_service
            # 使用 Haiku 4.5（快速且便宜，支持 64K output tokens）
            llm_service = create_claude_service(model="claude-haiku-4-5-20251001")
        
        response = await llm_service.create_message(
            system=SCHEMA_GENERATOR_PROMPT,
            messages=[{
                "role": "user",
                "content": f"分析以下 System Prompt 并生成 Agent Schema:\n\n{system_prompt}"
            }],
            max_tokens=2048
        )
        
        # 提取 JSON
        content = response.content[0].text if response.content else ""
        schema_json = cls._extract_json(content)
        
        # 使用强类型 Schema 验证和解析
        return AgentSchema.from_llm_output(schema_json)
    
    @classmethod
    def _infer_schema_from_prompt(cls, system_prompt: str) -> AgentSchema:
        """
        从 Prompt 推断 Schema（不调用 LLM，快速启动）
        
        用于：
        - LLM 调用失败时的 fallback
        - 快速启动场景
        """
        prompt_lower = system_prompt.lower()
        
        # 推断 Skills
        skills = []
        if any(kw in prompt_lower for kw in ["excel", "表格", "xlsx", "报表"]):
            skills.append(SkillConfig(skill_id="xlsx", type="custom"))
        if any(kw in prompt_lower for kw in ["ppt", "演示", "幻灯片", "pptx"]):
            skills.append(SkillConfig(skill_id="pptx", type="custom"))
        if any(kw in prompt_lower for kw in ["pdf", "文档"]):
            skills.append(SkillConfig(skill_id="pdf", type="custom"))
        
        # 推断 Tools
        tools = []
        if any(kw in prompt_lower for kw in ["数据分析", "pandas", "numpy", "分析数据"]):
            tools.append("e2b_sandbox")
        if any(kw in prompt_lower for kw in ["搜索", "查找", "检索", "search"]):
            tools.extend(["web_search", "exa_search"])
        
        # 推断复杂度
        is_complex = any(kw in prompt_lower for kw in [
            "计划", "规划", "多步骤", "分析", "报告", "报表"
        ])
        
        # 推断名称
        name = "GeneralAgent"
        if "数据分析" in prompt_lower:
            name = "DataAnalysisAgent"
        elif "搜索" in prompt_lower or "研究" in prompt_lower:
            name = "ResearchAgent"
        elif "报告" in prompt_lower or "报表" in prompt_lower:
            name = "ReportAgent"
        
        return AgentSchema(
            name=name,
            description=f"根据 Prompt 推断的 {name}",
            plan_manager=PlanManagerConfig(enabled=is_complex),
            skills=skills,
            tools=tools,
            max_turns=15 if is_complex else 8,
            reasoning=f"从 Prompt 关键词推断: skills={[s.skill_id for s in skills]}, tools={tools}, complex={is_complex}"
        )
    
    @classmethod
    def from_schema(
        cls,
        schema: AgentSchema,
        system_prompt: str,
        event_manager,
        workspace_dir: str = None,
        conversation_service = None
    ):
        """
        根据 Schema 创建 Agent（设计哲学：Schema 驱动）
        
        这是核心方法：根据强类型 Schema 动态初始化所有组件
        
        设计哲学：
        1. Schema 定义组件启用状态和配置参数
        2. System Prompt 作为运行时指令传递给 Agent
        3. Agent 根据 Schema 动态初始化组件
        """
        from core.agent.simple_agent import SimpleAgent
        
        logger.info(f"🏗️ 根据 Schema 初始化 Agent: {schema.name}")
        logger.debug(f"   Model: {schema.model}")
        logger.debug(f"   Skills: {[s.skill_id if isinstance(s, SkillConfig) else s for s in schema.skills]}")
        logger.debug(f"   Tools: {schema.tools}")
        logger.debug(f"   Max Turns: {schema.max_turns}")
        logger.debug(f"   Intent Analyzer: {'启用' if schema.intent_analyzer.enabled else '禁用'}")
        logger.debug(f"   Plan Manager: {'启用' if schema.plan_manager.enabled else '禁用'}")
        logger.debug(f"   Tool Selector: {'启用' if schema.tool_selector.enabled else '禁用'}")
        logger.debug(f"   Output Formatter: {schema.output_formatter.default_format}")
        
        # 🆕 核心改动：直接传递 schema 和 system_prompt 给 SimpleAgent
        # SimpleAgent 会根据 Schema 动态初始化组件
        agent = SimpleAgent(
            model=schema.model,
            max_turns=schema.max_turns,
            event_manager=event_manager,
            workspace_dir=workspace_dir,
            conversation_service=conversation_service,
            schema=schema,  # 🆕 传递 Schema（驱动组件初始化）
            system_prompt=system_prompt  # 🆕 传递 System Prompt（运行时指令）
        )
        
        logger.info(f"✅ Agent 初始化完成: {schema.name}")
        if schema.reasoning:
            logger.info(f"   Reasoning: {schema.reasoning}")
        
        return agent
    
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
    return AgentFactory.from_schema(schema, system_prompt, event_manager, **kwargs)


def create_schema_from_dict(data: Dict[str, Any]) -> AgentSchema:
    """从字典创建强类型 Schema（供外部使用）"""
    return AgentSchema.from_dict(data)

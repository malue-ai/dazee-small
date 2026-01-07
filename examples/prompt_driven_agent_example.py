"""
Prompt 驱动 Agent 完整示例

演示设计哲学：System Prompt → LLM 生成 Schema → 动态初始化 Agent

核心理念：
- System Prompt 是场景实例化的输入，定义 Agent 的行为规范
- LLM 分析 System Prompt，推断出需要的组件配置（Schema）
- AgentFactory 根据 Schema 动态初始化 Agent
- Agent 运行时使用 System Prompt 作为行为指令

使用方法：
    python examples/prompt_driven_agent_example.py
"""

import asyncio
from core.agent import AgentFactory, AgentSchema
from core.events import create_event_manager, get_memory_storage
from core.schemas import (
    IntentAnalyzerConfig,
    PlanManagerConfig,
    ToolSelectorConfig,
    MemoryManagerConfig,
    OutputFormatterConfig,
    SkillConfig,
)


# ============================================================
# 示例 1: 自定义 System Prompt → LLM 生成 Schema
# ============================================================

async def example_1_from_custom_prompt():
    """
    示例 1：从自定义 System Prompt 创建 Agent
    
    设计哲学：
    - 开发者编写 System Prompt 描述 Agent 应该如何工作
    - LLM 分析 Prompt，推断出需要的工具、能力、配置
    - AgentFactory 根据推断的 Schema 初始化 Agent
    """
    print("=" * 80)
    print("示例 1: 从自定义 System Prompt 创建 Agent")
    print("=" * 80)
    
    # 开发者自定义 System Prompt（描述 Agent 的角色和规则）
    DATA_ANALYST_PROMPT = """
你是一个专业的数据分析助手，专为业务分析师设计。

## 核心能力
- 使用 pandas 和 numpy 分析数据
- 生成带图表的 Excel 报表
- 提供数据驱动的业务洞察

## 工作流程
1. 接收数据文件（CSV/Excel）
2. 使用 E2B Sandbox 进行数据清洗和分析
3. 计算关键指标（KPI）
4. 生成可视化图表
5. 使用 xlsx Skill 生成专业报表
6. 提供分析结论和建议

## 决策规则
- 任务涉及多步骤时，先用 plan_todo 制定详细计划
- 缺少数据时，先用 web_search 补充背景信息
- 分析结果必须包含推理过程
- Excel 报表必须包含数据透视表和图表

## 质量标准
- 数据准确性：所有计算必须验证
- 专业性：使用业务术语和行业标准
- 可操作性：提供具体的业务建议
"""
    
    # 创建 EventManager（必需）
    storage = get_memory_storage()
    event_manager = create_event_manager(storage)
    
    # 🆕 从 System Prompt 创建 Agent（LLM 会分析 Prompt 生成 Schema）
    agent = await AgentFactory.from_prompt(
        system_prompt=DATA_ANALYST_PROMPT,
        event_manager=event_manager
    )
    
    print(f"\n✅ Agent 创建成功!")
    print(f"   名称: {agent.schema.name}")
    print(f"   模型: {agent.schema.model}")
    print(f"   Skills: {[s.skill_id if isinstance(s, SkillConfig) else s for s in agent.schema.skills]}")
    print(f"   Tools: {agent.schema.tools}")
    print(f"   Intent Analyzer: {'启用' if agent.schema.intent_analyzer.enabled else '禁用'}")
    print(f"   Plan Manager: {'启用' if agent.schema.plan_manager.enabled else '禁用'}")
    print(f"   Reasoning: {agent.schema.reasoning}")
    
    # 用户发送请求（User Query，不是 System Prompt）
    user_query = "分析这份销售数据，找出增长趋势，生成 Excel 报表"
    
    print(f"\n📝 用户请求: {user_query}")
    print("\n💬 Agent 响应:")
    
    # Agent 根据 System Prompt 中的规则处理 User Query
    async for event in agent.chat([{"role": "user", "content": user_query}], session_id="demo_session"):
        if event.get("type") == "content_delta":
            delta = event.get("data", {}).get("delta", {})
            if delta.get("type") == "text_delta":
                print(delta.get("text", ""), end="", flush=True)


# ============================================================
# 示例 2: 精确控制 - 直接提供 Schema
# ============================================================

async def example_2_from_explicit_schema():
    """
    示例 2：精确控制配置
    
    当开发者需要精确控制组件配置时，可以直接提供 Schema
    """
    print("\n\n" + "=" * 80)
    print("示例 2: 直接提供 Schema（精确控制）")
    print("=" * 80)
    
    # 精确定义 Schema
    custom_schema = AgentSchema(
        name="CustomDataAgent",
        description="自定义数据分析 Agent",
        
        # 启用意图分析器
        intent_analyzer=IntentAnalyzerConfig(
            enabled=True,
            use_llm=True,
            llm_model="claude-haiku-4-5-20251001"
        ),
        
        # 启用 Plan Manager（复杂任务需要）
        plan_manager=PlanManagerConfig(
            enabled=True,
            max_steps=10,
            granularity="medium",
            allow_dynamic_adjustment=True
        ),
        
        # 配置工具选择器
        tool_selector=ToolSelectorConfig(
            enabled=True,
            selection_strategy="capability_based",
            allow_parallel=False,
            base_tools=["plan_todo"]
        ),
        
        # 配置记忆管理器
        memory_manager=MemoryManagerConfig(
            enabled=True,
            retention_policy="session",
            working_memory_limit=20
        ),
        
        # 配置输出格式化器
        output_formatter=OutputFormatterConfig(
            enabled=True,
            default_format="markdown",
            code_highlighting=True
        ),
        
        # 指定 Skills
        skills=[
            SkillConfig(skill_id="xlsx", type="custom"),
        ],
        
        # 指定 Tools
        tools=["e2b_sandbox"],
        
        # 运行时参数
        model="claude-sonnet-4-5-20250929",
        max_turns=15,
        allow_parallel_tools=False,
        
        reasoning="数据分析任务需要 E2B Sandbox + xlsx Skill，启用计划管理"
    )
    
    # 自定义 System Prompt
    system_prompt = """
你是数据分析专家。使用 pandas 分析数据，用 xlsx 生成报表。
复杂任务时先制定计划。保持专业和精确。
"""
    
    storage = get_memory_storage()
    event_manager = create_event_manager(storage)
    
    # 从 Schema 创建 Agent
    agent = AgentFactory.from_schema(
        schema=custom_schema,
        system_prompt=system_prompt,
        event_manager=event_manager
    )
    
    print(f"\n✅ Agent 创建成功!")
    print(f"   名称: {agent.schema.name}")
    print(f"   Intent Analyzer 启用: {agent.intent_analyzer is not None}")
    print(f"   Plan Manager 启用: {agent.plan_todo_tool is not None}")
    print(f"   Tool Selector 启用: {agent.tool_selector is not None}")


# ============================================================
# 示例 3: 不同场景使用不同 Schema
# ============================================================

async def example_3_different_scenarios():
    """
    示例 3：不同场景使用不同配置
    
    通过修改 System Prompt，为不同用户/场景创建定制的 Agent
    """
    print("\n\n" + "=" * 80)
    print("示例 3: 不同场景的 Agent")
    print("=" * 80)
    
    storage = get_memory_storage()
    event_manager = create_event_manager(storage)
    
    # 场景 1: 简单问答助手（不需要工具和计划）
    simple_qa_prompt = """
你是一个简单问答助手。快速准确地回答用户问题。
不需要使用工具或制定计划，直接基于知识回答。
"""
    
    qa_agent = await AgentFactory.from_prompt(
        system_prompt=simple_qa_prompt,
        event_manager=event_manager,
        use_default_if_failed=True  # LLM 生成失败时使用默认配置
    )
    
    print(f"\n场景 1: 简单问答助手")
    print(f"   Plan Manager: {'启用' if qa_agent.schema.plan_manager.enabled else '禁用'}")
    print(f"   Tools: {qa_agent.schema.tools}")
    print(f"   Max Turns: {qa_agent.schema.max_turns}")
    
    # 场景 2: 研究助手（需要搜索和计划）
    research_prompt = """
你是一个深度研究助手。
你擅长搜索信息、分析资料、总结观点。
复杂研究任务时，你会制定详细的调研计划。
"""
    
    research_agent = await AgentFactory.from_prompt(
        system_prompt=research_prompt,
        event_manager=event_manager
    )
    
    print(f"\n场景 2: 研究助手")
    print(f"   Plan Manager: {'启用' if research_agent.schema.plan_manager.enabled else '禁用'}")
    print(f"   Tools: {research_agent.schema.tools}")
    print(f"   Max Turns: {research_agent.schema.max_turns}")


# ============================================================
# 示例 4: 向后兼容 - 不使用 Schema
# ============================================================

async def example_4_backward_compatibility():
    """
    示例 4：向后兼容
    
    不提供 Schema 时，使用默认配置
    """
    print("\n\n" + "=" * 80)
    print("示例 4: 向后兼容（不使用 Schema）")
    print("=" * 80)
    
    from core.agent import SimpleAgent
    
    storage = get_memory_storage()
    event_manager = create_event_manager(storage)
    
    # 直接创建 SimpleAgent（不提供 Schema）
    # 将使用 DEFAULT_AGENT_SCHEMA
    agent = SimpleAgent(
        event_manager=event_manager
    )
    
    print(f"\n✅ Agent 创建成功（使用默认配置）")
    print(f"   Schema 名称: {agent.schema.name}")
    print(f"   Intent Analyzer: {agent.intent_analyzer is not None}")
    print(f"   Plan Manager: {agent.plan_todo_tool is not None}")
    print(f"   使用的 System Prompt: {'自定义' if agent.system_prompt else '运行时动态选择'}")


# ============================================================
# 主函数
# ============================================================

async def main():
    """运行所有示例"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "Prompt 驱动 Agent 完整示例" + " " * 30 + "║")
    print("║" + " " * 15 + "System Prompt → Schema → Agent" + " " * 32 + "║")
    print("╚" + "=" * 78 + "╝")
    
    # 示例 1: 从自定义 Prompt 创建
    # await example_1_from_custom_prompt()
    
    # 示例 2: 精确控制 Schema
    await example_2_from_explicit_schema()
    
    # 示例 3: 不同场景
    await example_3_different_scenarios()
    
    # 示例 4: 向后兼容
    await example_4_backward_compatibility()
    
    print("\n\n✅ 所有示例执行完成！")
    print("\n📚 设计哲学总结:")
    print("   1. System Prompt 定义 Agent 的行为规范（角色、能力、规则）")
    print("   2. LLM 分析 Prompt 生成 Schema（组件配置）")
    print("   3. AgentFactory 根据 Schema 动态初始化 Agent")
    print("   4. Agent 运行时使用 System Prompt 作为指令")
    print("   5. User Query 是用户的具体请求，不是配置")


if __name__ == "__main__":
    asyncio.run(main())


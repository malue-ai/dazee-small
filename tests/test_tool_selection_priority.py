"""
测试工具选择的三级优先级策略

V7.6 改进验证：
1. Schema > Plan > Intent 优先级逻辑
2. Schema 工具有效性验证
3. 覆盖透明化日志
4. Tracer 追踪完整性
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from core.agent.simple.simple_agent import SimpleAgent
from core.agent.types import IntentResult, TaskType, Complexity
from core.schemas.validator import AgentSchema, ToolSelectorConfig


@pytest.fixture
def mock_schema():
    """创建测试用的 AgentSchema"""
    schema = AgentSchema(
        name="TestAgent",
        description="测试 Agent",
        tool_selector=ToolSelectorConfig(
            enabled=True,
            selection_strategy="capability_based"
        )
    )
    return schema


@pytest.fixture
def mock_capability_registry():
    """Mock CapabilityRegistry"""
    registry = Mock()
    
    # 模拟有效工具
    def mock_get(tool_name):
        valid_tools = {
            "web_search": Mock(name="web_search"),
            "e2b_sandbox": Mock(name="e2b_sandbox"),
            "plan_todo": Mock(name="plan_todo"),
        }
        return valid_tools.get(tool_name)
    
    registry.get = mock_get
    registry.get_capabilities_for_task_type = Mock(
        return_value=["web_search", "plan_todo"]
    )
    registry.get_all_capabilities = Mock(return_value=[])
    
    return registry


@pytest.fixture
def mock_tool_selector():
    """Mock ToolSelector"""
    selector = Mock()
    selector.NATIVE_TOOLS = ["bash", "text_editor", "web_search"]
    selector.get_available_apis = Mock(return_value=[])
    
    from core.tool.selector import ToolSelectionResult
    selector.select = Mock(return_value=ToolSelectionResult(
        tools=[],
        tool_names=["plan_todo", "web_search"],
        base_tools=["plan_todo"],
        dynamic_tools=["web_search"],
        reason="测试选择"
    ))
    selector.get_tools_for_llm = Mock(return_value=[
        {"name": "plan_todo", "description": "Plan tool"},
        {"name": "web_search", "description": "Search tool"}
    ])
    
    return selector


@pytest.fixture
async def simple_agent(mock_schema, mock_capability_registry, mock_tool_selector):
    """创建测试用的 SimpleAgent"""
    with patch('core.agent.simple.simple_agent.create_llm_service'):
        with patch('core.agent.simple.simple_agent.create_tool_executor'):
            with patch('core.agent.simple.simple_agent.create_invocation_selector'):
                with patch('core.agent.simple.simple_agent.create_unified_tool_caller'):
                    agent = SimpleAgent(
                        model="claude-sonnet-4-5",
                        schema=mock_schema
                    )
                    
                    # 注入 mock 对象
                    agent.capability_registry = mock_capability_registry
                    agent.tool_selector = mock_tool_selector
                    agent._plan_cache = {"plan": None, "todo": None, "tool_calls": []}
                    agent.invocation_selector = Mock()
                    agent.invocation_selector.select_strategy = Mock(return_value=None)
                    agent.llm = Mock()
                    agent.llm.supports_skills = Mock(return_value=False)
                    
                    return agent


@pytest.mark.asyncio
async def test_schema_tools_priority(simple_agent, caplog):
    """测试 Schema 工具配置的最高优先级"""
    import logging
    caplog.set_level(logging.INFO)
    
    # 配置 Schema 工具
    simple_agent.schema.tools = ["web_search", "e2b_sandbox"]
    
    # 配置 Plan 推荐
    simple_agent._plan_cache["plan"] = {
        "required_capabilities": ["plan_todo", "bash"]
    }
    
    # 创建 Intent
    intent = IntentResult(
        task_type=TaskType.QUESTION_ANSWERING,
        complexity=Complexity.SIMPLE,
        needs_plan=False,
        needs_multi_agent=False
    )
    
    # 执行工具选择
    tools_for_llm, selection = await simple_agent._select_tools(intent, {})
    
    # 验证：应该使用 Schema 配置
    call_args = simple_agent.tool_selector.select.call_args
    required_capabilities = call_args[1]["required_capabilities"]
    
    assert "web_search" in required_capabilities
    assert "e2b_sandbox" in required_capabilities
    
    # 验证日志：应该记录覆盖了 Plan
    assert "Schema 工具优先" in caplog.text or "schema" in caplog.text.lower()


@pytest.mark.asyncio
async def test_invalid_schema_tools_filtered(simple_agent, caplog):
    """测试 Schema 配置无效工具时的过滤逻辑"""
    import logging
    caplog.set_level(logging.WARNING)
    
    # 配置包含无效工具的 Schema
    simple_agent.schema.tools = [
        "web_search",       # 有效
        "invalid_tool_123",  # 无效
        "e2b_sandbox"       # 有效
    ]
    
    intent = IntentResult(
        task_type=TaskType.QUESTION_ANSWERING,
        complexity=Complexity.SIMPLE,
        needs_plan=False,
        needs_multi_agent=False
    )
    
    # 执行工具选择
    tools_for_llm, selection = await simple_agent._select_tools(intent, {})
    
    # 验证：无效工具应该被过滤
    call_args = simple_agent.tool_selector.select.call_args
    required_capabilities = call_args[1]["required_capabilities"]
    
    assert "web_search" in required_capabilities
    assert "e2b_sandbox" in required_capabilities
    assert "invalid_tool_123" not in required_capabilities
    
    # 验证日志：应该警告无效工具
    assert "无效工具" in caplog.text or "invalid_tool_123" in caplog.text


@pytest.mark.asyncio
async def test_plan_priority_when_no_schema(simple_agent, caplog):
    """测试没有 Schema 配置时，Plan 优先级高于 Intent"""
    import logging
    caplog.set_level(logging.DEBUG)
    
    # 不配置 Schema 工具
    simple_agent.schema.tools = []
    
    # 配置 Plan 推荐
    simple_agent._plan_cache["plan"] = {
        "required_capabilities": ["e2b_sandbox", "bash"]
    }
    
    intent = IntentResult(
        task_type=TaskType.CODE_EXECUTION,
        complexity=Complexity.MEDIUM,
        needs_plan=False,
        needs_multi_agent=False
    )
    
    # 执行工具选择
    tools_for_llm, selection = await simple_agent._select_tools(intent, {})
    
    # 验证：应该使用 Plan 能力
    call_args = simple_agent.tool_selector.select.call_args
    required_capabilities = call_args[1]["required_capabilities"]
    
    assert "e2b_sandbox" in required_capabilities
    assert "bash" in required_capabilities


@pytest.mark.asyncio
async def test_intent_fallback_when_no_schema_and_plan(simple_agent, caplog):
    """测试没有 Schema 和 Plan 时，使用 Intent 推断"""
    import logging
    caplog.set_level(logging.DEBUG)
    
    # 不配置 Schema 和 Plan
    simple_agent.schema.tools = []
    simple_agent._plan_cache["plan"] = None
    
    intent = IntentResult(
        task_type=TaskType.WEB_SEARCH,
        complexity=Complexity.SIMPLE,
        needs_plan=False,
        needs_multi_agent=False
    )
    
    # 执行工具选择
    tools_for_llm, selection = await simple_agent._select_tools(intent, {})
    
    # 验证：应该调用 Intent 推断
    simple_agent.capability_registry.get_capabilities_for_task_type.assert_called_with(
        TaskType.WEB_SEARCH.value
    )
    
    # 验证日志
    assert "Intent" in caplog.text or "intent" in caplog.text.lower()


@pytest.mark.asyncio
async def test_tracer_records_all_sources(simple_agent):
    """测试 Tracer 记录完整的选择决策链路"""
    # 启用 Tracer
    mock_tracer = Mock()
    mock_stage = Mock()
    mock_tracer.create_stage = Mock(return_value=mock_stage)
    simple_agent._tracer = mock_tracer
    
    # 配置三层建议
    simple_agent.schema.tools = ["web_search"]
    simple_agent._plan_cache["plan"] = {
        "required_capabilities": ["e2b_sandbox"]
    }
    
    intent = IntentResult(
        task_type=TaskType.DATA_ANALYSIS,
        complexity=Complexity.MEDIUM,
        needs_plan=False,
        needs_multi_agent=False
    )
    
    # 执行工具选择
    await simple_agent._select_tools(intent, {})
    
    # 验证：Tracer 应该记录所有三层的建议
    mock_stage.set_input.assert_called_once()
    input_data = mock_stage.set_input.call_args[0][0]
    
    assert "schema_tools" in input_data
    assert "plan_capabilities" in input_data
    assert "intent_capabilities" in input_data
    assert input_data["schema_tools"] == ["web_search"]
    
    # 验证：complete 应该记录覆盖信息
    mock_stage.complete.assert_called_once()
    output_data = mock_stage.complete.call_args[0][0]
    assert "overridden_sources" in output_data
    assert "final_source" in output_data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

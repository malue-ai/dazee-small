"""
V7.6 优化验证脚本
验证：Schema > Plan > Intent 优先级逻辑
"""
import asyncio
from unittest.mock import Mock, patch
from core.agent.simple.simple_agent import SimpleAgent
from core.schemas.validator import AgentSchema
from core.agent.types import IntentResult, TaskType, Complexity


async def test_schema_invalid_tools():
    """测试1: Schema 配置无效工具时的过滤逻辑"""
    print("\n=== 测试 1: Schema 无效工具过滤 ===")
    
    # 创建 Agent，Schema 包含无效工具
    schema = AgentSchema(
        name="TestAgent",
        description="测试",
        tools=["web_search", "invalid_tool_123", "another_invalid"]
    )
    
    # Mock event_manager
    event_manager = Mock()
    
    agent = SimpleAgent(
        model="claude-sonnet-4-5-20250929",
        schema=schema,
        max_turns=5,
        event_manager=event_manager
    )
    
    # Mock 必要组件
    registry = Mock()
    valid_tools = {"web_search", "e2b_sandbox", "plan_todo", "bash"}
    registry.get = lambda name: Mock(name=name) if name in valid_tools else None
    registry.get_capabilities_for_task_type = lambda t: ["web_search"]
    registry.get_all_capabilities = lambda: {n: Mock() for n in valid_tools}
    
    agent.capability_registry = registry
    # Mock tool selector with proper list attributes
    mock_selection = Mock()
    mock_selection.tool_names = ["web_search", "plan_todo"]
    mock_selection.base_tools = ["plan_todo"]
    mock_selection.dynamic_tools = ["web_search"]
    
    agent.tool_selector = Mock()
    agent.tool_selector.NATIVE_TOOLS = ["bash"]
    agent.tool_selector.select = Mock(return_value=mock_selection)
    agent.tool_selector.get_tools_for_llm = Mock(return_value=[])
    agent.tool_selector.get_available_apis = Mock(return_value=[])
    agent.llm = Mock()
    agent.llm.supports_skills = Mock(return_value=False)
    agent.invocation_selector = Mock()
    agent.unified_tool_caller = Mock()
    agent.unified_tool_caller.ensure_skill_fallback = Mock(
        side_effect=lambda **k: k['required_capabilities']
    )
    agent._tracer = None
    
    intent = IntentResult(
        task_type=TaskType.INFORMATION_QUERY,
        complexity=Complexity.SIMPLE,
        needs_plan=False,
        needs_multi_agent=False
    )
    
    # 执行测试
    with patch('core.agent.simple.simple_agent.logger') as mock_logger:
        await agent._select_tools(intent, {})
        
        warnings = [str(call[0][0]) for call in mock_logger.warning.call_args_list]
        print(f"  ✓ 捕获到警告日志: {len(warnings)} 条")
        for w in warnings:
            if "无效工具" in w:
                print(f"  ✓ 警告内容: {w[:100]}...")
                return True
    
    print("  ✗ 未检测到无效工具警告")
    return False


async def test_override_transparency():
    """测试2: Schema 覆盖 Plan/Intent 时的透明化日志"""
    print("\n=== 测试 2: 覆盖透明化日志 ===")
    
    schema = AgentSchema(
        name="TestAgent",
        description="测试",
        tools=["web_search"]  # Schema 只配置 web_search
    )
    
    # Mock event_manager
    event_manager = Mock()
    
    agent = SimpleAgent(
        model="claude-sonnet-4-5-20250929",
        schema=schema,
        max_turns=5,
        event_manager=event_manager
    )
    
    # Mock 组件
    registry = Mock()
    valid_tools = {"web_search", "e2b_sandbox", "ppt_generator", "plan_todo"}
    registry.get = lambda name: Mock(name=name) if name in valid_tools else None
    registry.get_capabilities_for_task_type = lambda t: ["e2b_sandbox", "ppt_generator"]
    registry.get_all_capabilities = lambda: {n: Mock() for n in valid_tools}
    
    agent.capability_registry = registry
    agent.tool_selector = Mock()
    agent.tool_selector.NATIVE_TOOLS = ["bash"]
    agent.tool_selector.select = Mock(return_value=Mock(
        tool_names=["web_search"],
        base_tools=[],
        dynamic_tools=["web_search"]
    ))
    agent.tool_selector.get_tools_for_llm = Mock(return_value=[])
    agent.tool_selector.get_available_apis = Mock(return_value=[])
    agent.llm = Mock()
    agent.llm.supports_skills = Mock(return_value=False)
    agent.invocation_selector = Mock()
    agent.unified_tool_caller = Mock()
    agent.unified_tool_caller.ensure_skill_fallback = Mock(
        side_effect=lambda **k: k['required_capabilities']
    )
    agent._tracer = None
    
    # 设置 Plan 缓存（会被 Schema 覆盖）
    agent._plan_cache = {
        "plan": {
            "required_capabilities": ["e2b_sandbox", "ppt_generator"]
        }
    }
    
    intent = IntentResult(
        task_type=TaskType.DATA_ANALYSIS,
        complexity=Complexity.COMPLEX,
        needs_plan=True,
        needs_multi_agent=False
    )
    
    # 执行测试
    with patch('core.agent.simple.simple_agent.logger') as mock_logger:
        await agent._select_tools(intent, {})
        
        info_logs = [str(call[0][0]) for call in mock_logger.info.call_args_list]
        print(f"  ✓ 捕获到信息日志: {len(info_logs)} 条")
        
        for log in info_logs:
            if "覆盖" in log and ("plan:" in log or "Plan" in log):
                print(f"  ✓ 覆盖日志: {log[:120]}...")
                return True
    
    print("  ✗ 未检测到覆盖透明化日志")
    return False


async def test_tracer_enhancement():
    """测试3: Tracer 增强追踪记录"""
    print("\n=== 测试 3: Tracer 增强追踪 ===")
    
    schema = AgentSchema(
        name="TestAgent",
        description="测试",
        tools=["web_search"]
    )
    
    # Mock event_manager
    event_manager = Mock()
    
    agent = SimpleAgent(
        model="claude-sonnet-4-5-20250929",
        schema=schema,
        max_turns=5,
        event_manager=event_manager
    )
    
    # Mock 组件
    registry = Mock()
    valid_tools = {"web_search", "e2b_sandbox", "plan_todo"}
    registry.get = lambda name: Mock(name=name) if name in valid_tools else None
    registry.get_capabilities_for_task_type = lambda t: ["e2b_sandbox"]
    registry.get_all_capabilities = lambda: {name: Mock() for name in valid_tools}  # Return real dict
    
    agent.capability_registry = registry
    agent.tool_selector = Mock()
    agent.tool_selector.NATIVE_TOOLS = ["bash"]
    
    # Mock selection result with proper list attributes
    mock_selection = Mock()
    mock_selection.tool_names = ["web_search"]
    mock_selection.base_tools = []
    mock_selection.dynamic_tools = ["web_search"]
    
    agent.tool_selector.select = Mock(return_value=mock_selection)
    agent.tool_selector.get_tools_for_llm = Mock(return_value=[])
    agent.tool_selector.get_available_apis = Mock(return_value=[])
    agent.llm = Mock()
    agent.llm.supports_skills = Mock(return_value=False)
    agent.invocation_selector = Mock()
    agent.unified_tool_caller = Mock()
    agent.unified_tool_caller.ensure_skill_fallback = Mock(
        side_effect=lambda **k: k['required_capabilities']
    )
    
    # 启用 Tracer
    mock_tracer = Mock()
    mock_stage = Mock()
    mock_tracer.create_stage = Mock(return_value=mock_stage)
    agent._tracer = mock_tracer
    
    # 设置 Plan
    agent._plan_cache = {"plan": {"required_capabilities": ["e2b_sandbox"]}}
    
    intent = IntentResult(
        task_type=TaskType.INFORMATION_QUERY,
        complexity=Complexity.SIMPLE,
        needs_plan=False,
        needs_multi_agent=False
    )
    
    # 执行测试
    await agent._select_tools(intent, {})
    
    # 验证 Tracer 调用
    if mock_stage.set_input.called and mock_stage.complete.called:
        input_data = mock_stage.set_input.call_args[0][0]
        complete_data = mock_stage.complete.call_args[0][0]
        
        print(f"  ✓ Tracer.set_input 被调用")
        print(f"  ✓ Tracer.complete 被调用")
        
        # 验证增强字段
        enhanced_fields = ["schema_tools", "plan_capabilities", "intent_capabilities", "overridden_sources"]
        for field in enhanced_fields:
            if field in input_data:
                print(f"  ✓ set_input 包含字段: {field}")
        
        if "final_source" in complete_data:
            print(f"  ✓ complete 包含字段: final_source")
        
        return True
    
    print("  ✗ Tracer 未被正确调用")
    return False


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("V7.6 优化验证")
    print("Schema > Plan > Intent 优先级 + 有效性验证 + 透明化日志")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(("Schema 无效工具过滤", await test_schema_invalid_tools()))
    except Exception as e:
        print(f"  ✗ 测试异常: {e}")
        results.append(("Schema 无效工具过滤", False))
    
    try:
        results.append(("覆盖透明化日志", await test_override_transparency()))
    except Exception as e:
        print(f"  ✗ 测试异常: {e}")
        results.append(("覆盖透明化日志", False))
    
    try:
        results.append(("Tracer 增强追踪", await test_tracer_enhancement()))
    except Exception as e:
        import traceback
        print(f"  ✗ 测试异常: {e}")
        print(f"  详细堆栈:")
        traceback.print_exc()
        results.append(("Tracer 增强追踪", False))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
    
    passed = sum(1 for _, p in results if p)
    total = len(results)
    print(f"\n通过率: {passed}/{total} ({passed/total*100:.0f}%)")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)

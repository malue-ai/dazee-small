"""
上下文工程集成测试 - 验证与 SimpleAgent 的集成

运行方式:
    cd CoT_agent/mvp/zenflux_agent
    source /Users/liuyi/Documents/langchain/liuy/bin/activate
    pytest tests/test_integration_context_engineering.py -v
"""

import pytest
from unittest.mock import Mock, AsyncMock
from core.agent.simple import SimpleAgent
from core.context.context_engineering import (
    ContextEngineeringManager,
    AgentState,
)


class TestSimpleAgentIntegration:
    """验证 SimpleAgent 与 ContextEngineeringManager 的集成"""
    
    def test_simple_agent_has_context_engineering(self):
        """测试 SimpleAgent 包含 context_engineering 属性"""
        # 创建 mock 依赖
        mock_event_manager = Mock()
        mock_conversation_service = Mock()
        mock_schema = Mock()
        mock_schema.intent_analyzer = Mock(enabled=False)
        mock_schema.plan_manager = Mock(enabled=False)
        mock_schema.tools = []
        mock_schema.skills = []
        
        agent = SimpleAgent(
            model="claude-sonnet-4-5-20250929",
            max_turns=10,
            event_manager=mock_event_manager,
            workspace_dir="/tmp",
            conversation_service=mock_conversation_service,
            schema=mock_schema,
            system_prompt="test"
        )
        
        # 验证属性存在
        assert hasattr(agent, "context_engineering")
        assert isinstance(agent.context_engineering, ContextEngineeringManager)
        print("✅ SimpleAgent.context_engineering 属性验证通过")
    
    def test_context_engineering_components(self):
        """测试上下文工程管理器的所有组件"""
        mock_event_manager = Mock()
        mock_conversation_service = Mock()
        mock_schema = Mock()
        mock_schema.intent_analyzer = Mock(enabled=False)
        mock_schema.plan_manager = Mock(enabled=False)
        mock_schema.tools = []
        mock_schema.skills = []
        
        agent = SimpleAgent(
            model="claude-sonnet-4-5-20250929",
            max_turns=10,
            event_manager=mock_event_manager,
            workspace_dir="/tmp",
            conversation_service=mock_conversation_service,
            schema=mock_schema,
            system_prompt="test"
        )
        
        manager = agent.context_engineering
        
        # 验证所有组件
        assert hasattr(manager, "cache_optimizer")
        assert hasattr(manager, "todo_rewriter")
        assert hasattr(manager, "tool_masker")
        assert hasattr(manager, "compressor")
        assert hasattr(manager, "variation")
        assert hasattr(manager, "error_retention")
        print("✅ 所有上下文工程组件验证通过")
    
    def test_plan_injection_integration(self):
        """测试 Plan 状态注入功能"""
        from core.context.context_engineering import create_context_engineering_manager
        
        manager = create_context_engineering_manager()
        
        # 准备测试数据
        messages = [
            {"role": "user", "content": "帮我生成 PPT"}
        ]
        
        plan = {
            "goal": "生成产品PPT",
            "total_steps": 3,
            "current_step": 1,
            "completed_steps": 0,
            "status": "executing",
            "steps": [
                {"action": "搜索资料", "status": "pending"},
                {"action": "生成内容", "status": "pending"},
                {"action": "渲染PPT", "status": "pending"}
            ]
        }
        
        # 注入 Plan 状态
        result = manager.prepare_messages_for_llm(
            messages=messages,
            plan=plan,
            inject_plan=True
        )
        
        # 验证注入成功
        assert len(result) == 1
        assert "📋" in result[0]["content"]
        assert "生成产品PPT" in result[0]["content"]
        print("✅ Plan 状态注入功能验证通过")
    
    def test_error_retention_integration(self):
        """测试错误保留功能"""
        from core.context.context_engineering import create_context_engineering_manager
        
        manager = create_context_engineering_manager()
        
        # 记录错误
        manager.record_error(
            tool_name="exa_search",
            error=ValueError("搜索失败"),
            input_params={"query": "test"}
        )
        
        # 验证错误已记录
        stats = manager.get_stats()
        assert stats["errors_recorded"] == 1
        
        # 验证错误上下文
        messages = [
            {"role": "user", "content": "继续搜索"}
        ]
        
        result = manager.prepare_messages_for_llm(
            messages=messages,
            inject_errors=True
        )
        
        # 验证错误已注入
        assert "最近的错误记录" in result[0]["content"]
        assert "exa_search" in result[0]["content"]
        print("✅ 错误保留功能验证通过")
    
    def test_tool_masking_state_transitions(self):
        """测试工具遮蔽状态转换"""
        from core.context.context_engineering import create_context_engineering_manager
        
        manager = create_context_engineering_manager()
        
        all_tools = [
            "plan_todo",
            "web_search",
            "exa_search",
            "bash",
            "e2b_python_sandbox",
            "ppt_generator"
        ]
        
        # 初始状态：IDLE
        allowed = manager.get_allowed_tools(all_tools)
        assert "plan_todo" in allowed
        assert "web_search" in allowed
        
        # 转换到 BROWSING 状态
        manager.transition_state(AgentState.BROWSING)
        allowed = manager.get_allowed_tools(all_tools)
        assert "web_search" in allowed
        assert "exa_search" in allowed
        assert "bash" not in allowed
        
        # 转换到 CODING 状态
        manager.transition_state(AgentState.CODING)
        allowed = manager.get_allowed_tools(all_tools)
        assert "bash" in allowed
        assert "e2b_python_sandbox" in allowed
        assert "web_search" not in allowed
        
        print("✅ 工具遮蔽状态转换验证通过")


class TestCacheOptimizationIntegration:
    """测试 KV-Cache 优化集成"""
    
    def test_prefix_stability(self):
        """测试前缀稳定性（确保缓存命中）"""
        from core.context.context_engineering import CacheOptimizer
        
        # 模拟多轮对话，只追加消息
        messages_round1 = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮助你的？"}
        ]
        
        messages_round2 = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮助你的？"},
            {"role": "user", "content": "帮我搜索资料"}
        ]
        
        # 计算前缀哈希（round1 的所有消息 vs round2 的前 2 条消息）
        hash1 = CacheOptimizer.calculate_prefix_hash(messages_round1 + [{"role": "user", "content": "dummy"}], prefix_length=2)
        hash2 = CacheOptimizer.calculate_prefix_hash(messages_round2, prefix_length=2)
        
        # 前缀应该相同（表示可以缓存命中）
        assert hash1 == hash2
        print("✅ 前缀稳定性验证通过（KV-Cache 可命中）")
    
    def test_json_serialization_determinism(self):
        """测试 JSON 序列化确定性"""
        from core.context.context_engineering import CacheOptimizer
        
        # 同样的数据，不同顺序
        data1 = {"z": 1, "a": 2, "m": 3}
        data2 = {"m": 3, "z": 1, "a": 2}
        
        json1 = CacheOptimizer.stable_json_dumps(data1)
        json2 = CacheOptimizer.stable_json_dumps(data2)
        
        # 序列化结果应该相同
        assert json1 == json2
        print("✅ JSON 序列化确定性验证通过")


class TestCompressionIntegration:
    """测试压缩功能集成"""
    
    def test_large_content_compression(self):
        """测试大内容压缩"""
        from core.context.context_engineering import RecoverableCompressor
        
        compressor = RecoverableCompressor(max_summary_chars=200)
        
        # 模拟大型搜索结果
        large_result = {
            "results": [{"title": f"Result {i}", "content": "x" * 1000} for i in range(20)]
        }
        
        compressed, ref = compressor.compress_tool_result(
            tool_name="exa_search",
            result=large_result,
            tool_id="tool_123"
        )
        
        # 验证压缩效果
        original_size = len(str(large_result))
        compressed_size = len(compressed)
        compression_ratio = 1 - (compressed_size / original_size)
        
        assert compression_ratio > 0.5  # 至少压缩 50%
        assert ref.ref_id is not None
        assert ref.ref_type == "tool_result"
        
        print(f"✅ 压缩比: {compression_ratio:.1%} (原始: {original_size:,} → 压缩: {compressed_size:,})")


class TestVariationIntegration:
    """测试结构化变异集成"""
    
    def test_progress_display_variations(self):
        """测试进度显示变异"""
        from core.context.context_engineering import StructuralVariation
        
        variation = StructuralVariation(variation_level=0.8)
        
        # 生成 10 次，验证有变异
        displays = set()
        for _ in range(10):
            display = variation.vary_progress_display(completed=5, total=10)
            displays.add(display)
        
        # 应该有多种不同的格式
        assert len(displays) > 1
        print(f"✅ 进度显示变异：{len(displays)} 种不同格式")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


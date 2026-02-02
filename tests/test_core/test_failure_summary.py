"""
失败经验总结模块测试
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.context.failure_summary import (
    FailureSummary,
    format_failure_summary,
    serialize_messages_for_summary
)


def test_serialize_messages_for_summary_includes_tool_blocks():
    """序列化应包含工具调用与工具结果"""
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "你好"}]},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": "web_search", "input": {"query": "test"}}]
        },
        {
            "role": "assistant",
            "content": [{"type": "tool_result", "content": {"ok": True}}]
        },
    ]
    
    text = serialize_messages_for_summary(messages, max_chars=500, max_block_chars=200)
    
    assert "工具调用" in text
    assert "工具结果" in text


def test_format_failure_summary_renders_fields():
    """格式化应输出关键字段"""
    summary = FailureSummary(
        goal="完成总结",
        progress=["已完成 A"],
        failures=["超出最大轮次"],
        next_steps=["缩小范围再试"],
        final_status="max_turns_reached"
    )
    
    text = format_failure_summary(summary, max_chars=500)
    
    assert "目标: 完成总结" in text
    assert "已完成: 已完成 A" in text
    assert "失败原因: 超出最大轮次" in text
    assert "下一步: 缩小范围再试" in text
    assert "终止原因: max_turns_reached" in text


def test_generate_failure_summary_for_multiagent_checks_state():
    """MultiAgent 失败总结应检查 OrchestratorState"""
    from unittest.mock import Mock, AsyncMock
    from core.agent.multi.models import OrchestratorState, AgentResult, ExecutionMode
    from core.context.failure_summary import (
        generate_failure_summary_for_multiagent,
        get_failure_summary_config
    )
    
    # 创建模拟的 OrchestratorState（有失败 Agent）
    failed_result = AgentResult(
        result_id="result_1",
        agent_id="agent_1",
        success=False,
        error="执行超时",
        turns_used=5
    )
    
    state = OrchestratorState(
        state_id="test_state",
        session_id="test_session",
        config_id="test_config",
        mode=ExecutionMode.SEQUENTIAL,
        status="failed",
        agent_results=[failed_result],
        errors=[{"error": "Orchestrator 执行失败"}]
    )
    
    # 创建模拟的 LLM 服务
    mock_llm = Mock()
    mock_response = Mock()
    mock_response.content = [{"type": "text", "text": '{"goal": "测试", "failures": ["超时"]}'}]
    mock_llm.create_message_async = AsyncMock(return_value=mock_response)
    
    # 测试（需要异步）
    import asyncio
    
    async def run_test():
        config = get_failure_summary_config()
        result = await generate_failure_summary_for_multiagent(
            orchestrator_state=state,
            messages=[{"role": "user", "content": "测试"}],
            llm_service=mock_llm,
            config=config
        )
        
        assert result is not None
        assert result.summary_text
        assert "测试" in result.summary_text or "超时" in result.summary_text
    
    asyncio.run(run_test())


def test_generate_failure_summary_for_multiagent_no_failure_returns_none():
    """MultiAgent 无失败时应返回 None"""
    from unittest.mock import Mock
    from core.agent.multi.models import OrchestratorState, AgentResult, ExecutionMode
    from core.context.failure_summary import (
        generate_failure_summary_for_multiagent,
        get_failure_summary_config
    )
    
    # 创建模拟的 OrchestratorState（无失败）
    success_result = AgentResult(
        result_id="result_1",
        agent_id="agent_1",
        success=True,
        output="执行成功",
        turns_used=2
    )
    
    state = OrchestratorState(
        state_id="test_state",
        session_id="test_session",
        config_id="test_config",
        mode=ExecutionMode.SEQUENTIAL,
        status="completed",
        agent_results=[success_result]
    )
    
    # 创建模拟的 LLM 服务（不应被调用）
    mock_llm = Mock()
    
    # 测试（需要异步）
    import asyncio
    
    async def run_test():
        config = get_failure_summary_config()
        result = await generate_failure_summary_for_multiagent(
            orchestrator_state=state,
            messages=[{"role": "user", "content": "测试"}],
            llm_service=mock_llm,
            config=config
        )
        
        assert result is None
        mock_llm.create_message_async.assert_not_called()
    
    asyncio.run(run_test())

"""
多智能体 Mock 测试 - 验证完整逻辑流程

不依赖真实 API，使用 Mock 验证：
1. 系统提示词构建（8 个核心要素）
2. Lead Agent 任务分解
3. Subagents 并行执行
4. 结果综合
5. 完整流程验证
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from core.agent.multi import (
    MultiAgentOrchestrator,
    MultiAgentConfig,
    AgentConfig,
    AgentRole,
    ExecutionMode,
    OrchestratorConfig,
    WorkerConfig,
    SubTask,
)
from core.agent.types import IntentResult, TaskType, Complexity
from core.llm.base import LLMResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_full_flow_with_mock():
    """
    完整流程测试（使用 Mock）
    
    验证点：
    1. ✅ Orchestrator 初始化
    2. ✅ Lead Agent 任务分解（Mock LLM 返回任务分解结果）
    3. ✅ Subagents 并行执行（Mock LLM 返回研究结果）
    4. ✅ 结果综合（Mock LLM 返回最终报告）
    5. ✅ 完整流程完成
    """
    logger.info("\n" + "="*80)
    logger.info("🧪 完整流程测试（Mock）")
    logger.info("="*80)
    
    # ===== Mock LLM 响应 =====
    
    # Mock 1: Lead Agent 任务分解响应
    decomposition_response = LLMResponse(
        content="""```json
{
  "decomposed_goal": "分析 AI 对医疗行业的影响",
  "execution_mode": "parallel",
  "subtasks": [
    {
      "subtask_id": "task_tech",
      "title": "技术影响研究",
      "description": "研究 AI 技术对医疗诊断、治疗方案的影响",
      "assigned_agent_role": "researcher",
      "tools_required": ["web_search"],
      "expected_output": "技术影响分析报告（Markdown）",
      "success_criteria": ["覆盖诊断、治疗两个方面", "提供具体案例"],
      "depends_on": [],
      "priority": 1,
      "context": "聚焦 2025 年现状",
      "constraints": ["不讨论历史"],
      "max_time_seconds": 60
    },
    {
      "subtask_id": "task_econ",
      "title": "经济影响研究",
      "description": "研究 AI 对医疗成本、效率的经济影响",
      "assigned_agent_role": "researcher",
      "tools_required": ["web_search"],
      "expected_output": "经济影响分析报告（Markdown）",
      "success_criteria": ["覆盖成本、效率两个方面", "提供数据支撑"],
      "depends_on": [],
      "priority": 1,
      "context": "聚焦 2025 年现状",
      "constraints": ["不讨论历史"],
      "max_time_seconds": 60
    },
    {
      "subtask_id": "task_ethics",
      "title": "伦理影响研究",
      "description": "研究 AI 在医疗领域的伦理问题",
      "assigned_agent_role": "researcher",
      "tools_required": ["web_search"],
      "expected_output": "伦理影响分析报告（Markdown）",
      "success_criteria": ["覆盖隐私、公平性两个方面", "提供伦理框架"],
      "depends_on": [],
      "priority": 1,
      "context": "聚焦 2025 年现状",
      "constraints": ["不讨论历史"],
      "max_time_seconds": 60
    }
  ],
  "synthesis_strategy": "按技术、经济、伦理三个维度组织最终报告",
  "reasoning": "任务复杂，需要并行研究三个独立维度",
  "estimated_time_seconds": 180
}
```""",
        stop_reason="end_turn",
        usage={"input_tokens": 500, "output_tokens": 600},
    )
    
    # Mock 2: Subagent 执行响应（3 个）
    subagent_responses = [
        LLMResponse(
            content="# 技术影响分析\n\nAI 在医疗诊断中的应用：\n1. 影像识别准确率提升 30%\n2. 治疗方案个性化推荐\n3. 药物研发周期缩短",
            stop_reason="end_turn",
            usage={"input_tokens": 300, "output_tokens": 200},
        ),
        LLMResponse(
            content="# 经济影响分析\n\n成本优化：\n1. 诊断成本降低 25%\n2. 医疗效率提升 40%\n3. 资源配置优化",
            stop_reason="end_turn",
            usage={"input_tokens": 300, "output_tokens": 200},
        ),
        LLMResponse(
            content="# 伦理影响分析\n\n关键问题：\n1. 患者隐私保护\n2. 算法公平性\n3. 责任归属",
            stop_reason="end_turn",
            usage={"input_tokens": 300, "output_tokens": 200},
        ),
    ]
    
    # Mock 3: Lead Agent 结果综合响应
    synthesis_response = LLMResponse(
        content="""# AI 对医疗行业的影响综合分析

## 技术维度
AI 在医疗诊断中的应用显著提升了准确率和效率，影像识别准确率提升 30%，治疗方案个性化推荐成为可能。

## 经济维度
AI 带来显著的成本优化，诊断成本降低 25%，医疗效率提升 40%，资源配置得到优化。

## 伦理维度
AI 在医疗领域的应用面临患者隐私保护、算法公平性、责任归属等伦理挑战。

## 总结
AI 对医疗行业的影响是多维度的，既带来技术和经济的显著提升，也需要认真对待伦理问题。""",
        stop_reason="end_turn",
        usage={"input_tokens": 800, "output_tokens": 400},
    )
    
    # ===== 创建配置 =====
    agents = [
        AgentConfig(
            agent_id="researcher_tech",
            role=AgentRole.RESEARCHER,
            model="claude-sonnet-4-5-20250929",
            tools=["web_search"],
        ),
        AgentConfig(
            agent_id="researcher_econ",
            role=AgentRole.RESEARCHER,
            model="claude-sonnet-4-5-20250929",
            tools=["web_search"],
        ),
        AgentConfig(
            agent_id="researcher_ethics",
            role=AgentRole.RESEARCHER,
            model="claude-sonnet-4-5-20250929",
            tools=["web_search"],
        ),
    ]
    
    config = MultiAgentConfig(
        config_id="mock_test",
        mode=ExecutionMode.PARALLEL,
        agents=agents,
        orchestrator_config=OrchestratorConfig(
            model="claude-sonnet-4-5-20250929",
            thinking_budget=10000,
            max_tokens=16384,
        ),
        worker_config=WorkerConfig(
            model="claude-sonnet-4-5-20250929",
            thinking_budget=5000,
            max_tokens=8192,
        ),
        enable_final_summary=True,
    )
    
    logger.info("✅ 配置创建完成")
    
    # ===== Mock LLM 服务 =====
    # 关键：在创建 Orchestrator 之前就 patch
    with patch('core.llm.claude.ClaudeLLMService') as MockLLMService:
        # 创建 Mock LLM 实例
        mock_llm_instance = MagicMock()
        
        # 设置调用顺序：
        # 1. Lead Agent decompose (1 次)
        # 2. Subagent 1 execute (1 次)
        # 3. Subagent 2 execute (1 次)  
        # 4. Subagent 3 execute (1 次)
        # 5. Lead Agent synthesize (1 次)
        
        mock_llm_instance.create_message_async = AsyncMock(
            side_effect=[
                decomposition_response,  # Lead decompose
                subagent_responses[0],   # Subagent 1
                subagent_responses[1],   # Subagent 2
                subagent_responses[2],   # Subagent 3
                synthesis_response,      # Lead synthesize
            ]
        )
        
        # Mock 构造函数返回我们的 Mock 实例
        MockLLMService.return_value = mock_llm_instance
        
        # ===== 创建 Orchestrator（此时会使用 Mock LLM）=====
        orchestrator = MultiAgentOrchestrator(
            config=config,
            enable_checkpoints=False,  # 禁用检查点简化测试
            enable_lead_agent=True,
        )
        
        logger.info("✅ Orchestrator 已创建（使用 Mock LLM）")
        
        # ===== 执行 =====
        user_query = "分析 AI 对医疗行业的影响，包括技术、经济、伦理三个方面"
        
        intent = IntentResult(
            task_type=TaskType.DATA_ANALYSIS,
            complexity=Complexity.COMPLEX,
            complexity_score=8.5,
            needs_plan=True,
            needs_multi_agent=True,
        )
        
        messages = [{"role": "user", "content": user_query}]
        session_id = f"mock_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        logger.info(f"\n👤 用户查询: {user_query}")
        logger.info(f"📝 Session ID: {session_id}\n")
        
        # 收集事件
        events = []
        task_decomposition = None
        agent_executions = []
        final_output = None
        
        try:
            async for event in orchestrator.execute(
                intent=intent,
                messages=messages,
                session_id=session_id,
                resume_from_checkpoint=False,
            ):
                events.append(event)
                event_type = event.get("type")
                
                if event_type == "orchestrator_start":
                    logger.info(f"✅ [1] Orchestrator 启动: {event.get('agent_count')} Agents")
                
                elif event_type == "task_decomposition":
                    task_decomposition = event
                    logger.info(f"✅ [2] 任务分解完成:")
                    logger.info(f"     • 子任务数量: {event.get('subtasks_count')}")
                    logger.info(f"     • 执行模式: {event.get('execution_mode')}")
                
                elif event_type == "agent_start":
                    logger.info(f"✅ [3] Agent 启动: {event.get('agent_id')}")
                    if event.get('subtask_title'):
                        logger.info(f"     • 子任务: {event.get('subtask_title')}")
                
                elif event_type == "agent_end":
                    agent_executions.append(event)
                    logger.info(f"✅ [4] Agent 完成: {event.get('agent_id')}")
                    logger.info(f"     • 成功: {event.get('success')}")
                    output_preview = event.get('output_preview', '')
                    if output_preview:
                        logger.info(f"     • 输出预览: {output_preview[:80]}...")
                
                elif event_type == "orchestrator_summary":
                    final_output = event.get("content")
                    logger.info(f"✅ [5] 结果综合完成:")
                    logger.info(f"     • 由 Lead Agent 综合: {event.get('synthesized_by_lead_agent')}")
                    logger.info(f"     • 输出长度: {len(final_output)} 字符")
                
                elif event_type == "orchestrator_end":
                    logger.info(f"✅ [6] Orchestrator 完成:")
                    logger.info(f"     • 耗时: {event.get('duration_ms')}ms")
                    logger.info(f"     • Agent 结果: {event.get('agent_results')} 个")
        except Exception as e:
            logger.error(f"❌ Orchestrator 执行失败: {e}", exc_info=True)
            raise
    
    # ===== 验证结果 =====
    logger.info("\n" + "="*80)
    logger.info("📊 验证结果")
    logger.info("="*80)
    
    checks = {
        "Orchestrator 启动": any(e.get("type") == "orchestrator_start" for e in events),
        "任务分解完成": task_decomposition is not None,
        "子任务数量正确": task_decomposition and task_decomposition.get("subtasks_count") == 3,
        "3 个 Agents 执行": len(agent_executions) == 3,
        "所有 Agents 成功": all(e.get("success") for e in agent_executions),
        "最终汇总生成": final_output is not None and len(final_output) > 0,
        "由 Lead Agent 综合": any(e.get("type") == "orchestrator_summary" and e.get("synthesized_by_lead_agent") for e in events),
        "Orchestrator 完成": any(e.get("type") == "orchestrator_end" for e in events),
    }
    
    for check_name, result in checks.items():
        status = "✅" if result else "❌"
        logger.info(f"{status} {check_name}: {result}")
    
    # ===== 验证系统提示词 =====
    logger.info("\n" + "="*80)
    logger.info("🔍 验证系统提示词（8 个核心要素）")
    logger.info("="*80)
    
    # 获取第一个 Subagent 的调用参数
    first_subagent_call = mock_llm.create_message_async.call_args_list[1]  # 索引 1（0 是 decompose）
    
    # 提取 system prompt
    if first_subagent_call:
        kwargs = first_subagent_call.kwargs
        system_prompt = kwargs.get('system', '')
        
        logger.info(f"系统提示词长度: {len(system_prompt)} 字符")
        
        # 验证 8 个核心要素
        prompt_checks = {
            "1. 明确的目标": "**你的目标**" in system_prompt,
            "2. 输出格式": "**输出格式要求**" in system_prompt,
            "3. 工具指导": "**可用工具**" in system_prompt,
            "4. 任务边界": "**任务边界" in system_prompt,
            "5. 成功标准": "**成功标准**" in system_prompt,
            "6. 搜索策略": "**搜索策略指导**" in system_prompt,
            "7. Thinking 指导": "**Extended Thinking" in system_prompt,
            "8. 重要提醒": "**重要提醒**" in system_prompt,
        }
        
        for element, exists in prompt_checks.items():
            status = "✅" if exists else "❌"
            logger.info(f"{status} {element}: {exists}")
        
        all_elements_present = all(prompt_checks.values())
    else:
        all_elements_present = False
        logger.error("❌ 无法获取 Subagent 调用参数")
    
    # ===== 验证 LLM 调用次数 =====
    logger.info("\n" + "="*80)
    logger.info("📞 验证 LLM 调用次数")
    logger.info("="*80)
    
    call_count = mock_llm.create_message_async.call_count
    expected_calls = 5  # 1 decompose + 3 subagents + 1 synthesize
    
    logger.info(f"实际调用次数: {call_count}")
    logger.info(f"期望调用次数: {expected_calls}")
    logger.info(f"调用顺序:")
    for i, call in enumerate(mock_llm.create_message_async.call_args_list, 1):
        messages = call.kwargs.get('messages', [])
        system = call.kwargs.get('system', '')
        logger.info(f"  {i}. messages={len(messages)}, system_length={len(system)}")
    
    calls_correct = call_count == expected_calls
    status = "✅" if calls_correct else "❌"
    logger.info(f"\n{status} LLM 调用次数验证: {calls_correct}")
    
    # ===== 最终验证 =====
    logger.info("\n" + "="*80)
    logger.info("🎯 最终验证")
    logger.info("="*80)
    
    all_checks_passed = all(checks.values()) and all_elements_present and calls_correct
    
    if all_checks_passed:
        logger.info("🎉 所有验证通过！")
        logger.info("\n验证内容:")
        logger.info("  ✅ 完整流程执行")
        logger.info("  ✅ 任务分解逻辑")
        logger.info("  ✅ Subagents 并行执行")
        logger.info("  ✅ 系统提示词构建（8 个核心要素）")
        logger.info("  ✅ 结果综合")
        logger.info("  ✅ LLM 调用次数和顺序")
    else:
        logger.error("❌ 部分验证失败")
        logger.error("\n失败项:")
        for check_name, result in checks.items():
            if not result:
                logger.error(f"  ❌ {check_name}")
        if not all_elements_present:
            logger.error(f"  ❌ 系统提示词缺少核心要素")
        if not calls_correct:
            logger.error(f"  ❌ LLM 调用次数不正确")
    
    logger.info("="*80)
    
    return all_checks_passed


async def main():
    """运行测试"""
    result = await test_full_flow_with_mock()
    return result


if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)

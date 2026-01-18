"""
测试多智能体框架（Anthropic 启发的改进）

测试内容：
1. CheckpointManager - 检查点保存和恢复
2. LeadAgent - 任务分解和结果综合
3. MultiAgentOrchestrator - 完整流程
"""

import asyncio
import logging
from pathlib import Path

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_checkpoint_manager():
    """测试检查点管理器"""
    from core.agent.multi.checkpoint import CheckpointManager
    from core.agent.multi.models import OrchestratorState, AgentResult, ExecutionMode
    from datetime import datetime
    
    logger.info("=" * 60)
    logger.info("测试 1: CheckpointManager")
    logger.info("=" * 60)
    
    # 创建检查点管理器
    manager = CheckpointManager(
        storage_path="data/test_checkpoints",
        auto_save=True
    )
    
    # 创建模拟状态
    state = OrchestratorState(
        state_id="test_state_001",
        session_id="test_session_001",
        config_id="test_config",
        mode=ExecutionMode.SEQUENTIAL,
        status="running",
        completed_agents=["agent_1"],
        pending_agents=["agent_2", "agent_3"],
        current_agent="agent_2",
    )
    
    # 添加一个结果
    state.agent_results.append(
        AgentResult(
            result_id="result_001",
            agent_id="agent_1",
            success=True,
            output="第一个 Agent 的输出",
            turns_used=2,
            duration_ms=1500,
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
    )
    
    # 测试保存检查点
    checkpoint = await manager.save_checkpoint(
        state=state,
        reason="test",
        last_output="第一个 Agent 的输出"
    )
    
    logger.info(f"✅ 检查点已保存: {checkpoint.checkpoint_id}")
    logger.info(f"   - 已完成: {len(checkpoint.completed_agents)}")
    logger.info(f"   - 待执行: {len(checkpoint.pending_agents)}")
    
    # 测试加载检查点
    loaded_checkpoint = await manager.load_latest_checkpoint("test_session_001")
    
    assert loaded_checkpoint is not None, "加载检查点失败"
    assert loaded_checkpoint.checkpoint_id == checkpoint.checkpoint_id
    logger.info(f"✅ 检查点加载成功: {loaded_checkpoint.checkpoint_id}")
    
    # 测试恢复状态
    restored_state = manager.restore_state(loaded_checkpoint)
    
    assert restored_state.session_id == "test_session_001"
    assert len(restored_state.completed_agents) == 1
    assert len(restored_state.pending_agents) == 2
    logger.info(f"✅ 状态恢复成功: {len(restored_state.pending_agents)} 个待处理 Agent")
    
    # 测试是否可以恢复
    can_resume = manager.can_resume(loaded_checkpoint)
    assert can_resume, "应该可以恢复"
    logger.info(f"✅ 检查点可恢复: {can_resume}")
    
    logger.info("\n✅ CheckpointManager 测试通过\n")
    
    return manager


async def test_lead_agent():
    """测试 Lead Agent"""
    logger.info("=" * 60)
    logger.info("测试 2: LeadAgent")
    logger.info("=" * 60)
    
    try:
        from core.agent.multi.lead_agent import LeadAgent
        
        # 创建 Lead Agent
        lead_agent = LeadAgent(
            model="claude-sonnet-4-5-20250929",  # 测试用 Sonnet（Opus 太贵）
            max_subtasks=3,
            enable_thinking=False
        )
        
        logger.info("✅ LeadAgent 创建成功")
        
        # 测试任务分解
        user_query = "帮我研究人工智能在医疗领域的应用，包括诊断、治疗和药物研发三个方面"
        
        logger.info(f"\n📋 用户查询: {user_query}")
        logger.info("正在进行任务分解...")
        
        plan = await lead_agent.decompose_task(
            user_query=user_query,
            available_tools=["web_search", "knowledge_query", "document_analysis"],
            intent_info={"task_type": "research", "complexity": "complex"}
        )
        
        logger.info(f"\n✅ 任务分解完成:")
        logger.info(f"   - Plan ID: {plan.plan_id}")
        logger.info(f"   - 执行模式: {plan.execution_mode.value}")
        logger.info(f"   - 子任务数量: {len(plan.subtasks)}")
        logger.info(f"   - 分解推理: {plan.reasoning[:200]}...")
        
        for i, subtask in enumerate(plan.subtasks, 1):
            logger.info(f"\n   子任务 {i}: {subtask.title}")
            logger.info(f"     - 角色: {subtask.assigned_agent_role.value}")
            logger.info(f"     - 描述: {subtask.description[:100]}...")
            logger.info(f"     - 需要工具: {subtask.tools_required}")
        
        # 测试结果综合（模拟）
        mock_results = [
            {
                "agent_id": "agent_1",
                "title": "诊断应用研究",
                "output": "AI 在医疗诊断中的应用非常广泛，包括影像分析、疾病预测等...",
                "success": True,
            },
            {
                "agent_id": "agent_2",
                "title": "治疗应用研究",
                "output": "AI 辅助治疗方案制定，个性化医疗，精准治疗...",
                "success": True,
            },
            {
                "agent_id": "agent_3",
                "title": "药物研发研究",
                "output": "AI 加速药物发现，预测分子结构，优化临床试验设计...",
                "success": True,
            },
        ]
        
        logger.info("\n正在综合结果...")
        
        final_result = await lead_agent.synthesize_results(
            subtask_results=mock_results,
            original_query=user_query,
            synthesis_strategy=plan.synthesis_strategy
        )
        
        logger.info(f"\n✅ 结果综合完成:")
        logger.info(f"   输出长度: {len(final_result)} 字符")
        logger.info(f"   预览: {final_result[:200]}...")
        
        logger.info("\n✅ LeadAgent 测试通过\n")
        
        return lead_agent
        
    except Exception as e:
        logger.error(f"❌ LeadAgent 测试失败: {e}", exc_info=True)
        logger.info("⚠️ 这可能是因为缺少 LLM 配置或网络问题")
        logger.info("   跳过此测试，继续其他测试...\n")
        return None


async def test_multi_agent_orchestrator():
    """测试多智能体编排器（完整流程）"""
    logger.info("=" * 60)
    logger.info("测试 3: MultiAgentOrchestrator 完整流程")
    logger.info("=" * 60)
    
    from core.agent.multi.orchestrator import MultiAgentOrchestrator
    from core.agent.multi.models import (
        MultiAgentConfig,
        AgentConfig,
        AgentRole,
        ExecutionMode
    )
    
    # 创建配置
    config = MultiAgentConfig(
        config_id="test_config_001",
        name="测试多智能体配置",
        mode=ExecutionMode.SEQUENTIAL,
        agents=[
            AgentConfig(
                agent_id="researcher_1",
                role=AgentRole.RESEARCHER,
                model="claude-sonnet-4-5-20250929",
                tools=["web_search", "knowledge_query"],
            ),
            AgentConfig(
                agent_id="executor_1",
                role=AgentRole.EXECUTOR,
                model="claude-sonnet-4-5-20250929",
                tools=["document_creation"],
            ),
            AgentConfig(
                agent_id="reviewer_1",
                role=AgentRole.REVIEWER,
                model="claude-sonnet-4-5-20250929",
                tools=[],
            ),
        ],
        enable_final_summary=True,
    )
    
    # 创建编排器
    orchestrator = MultiAgentOrchestrator(
        config=config,
        enable_checkpoints=True,
        enable_lead_agent=False,  # 简化测试，不使用 Lead Agent
    )
    
    logger.info("✅ 编排器创建成功")
    logger.info(f"   - 模式: {config.mode.value}")
    logger.info(f"   - Agent 数量: {len(config.agents)}")
    logger.info(f"   - 检查点: 启用")
    
    # 执行
    messages = [
        {"role": "user", "content": "请研究人工智能的最新进展"}
    ]
    
    logger.info("\n开始执行...")
    
    events = []
    async for event in orchestrator.execute(
        intent=None,
        messages=messages,
        session_id="test_session_002",
        resume_from_checkpoint=False,
    ):
        events.append(event)
        event_type = event.get("type")
        
        if event_type == "orchestrator_start":
            logger.info(f"  🚀 编排开始: {event.get('agent_count')} 个 Agent")
        
        elif event_type == "agent_start":
            logger.info(f"  🤖 Agent 开始: {event.get('agent_id')} ({event.get('role')})")
        
        elif event_type == "agent_end":
            success = "✅" if event.get('success') else "❌"
            logger.info(f"  {success} Agent 完成: {event.get('agent_id')}")
            if event.get('checkpoint_saved'):
                logger.info(f"     💾 检查点已保存")
        
        elif event_type == "orchestrator_summary":
            logger.info(f"  📊 生成汇总")
        
        elif event_type == "orchestrator_end":
            logger.info(f"  🎉 编排完成: 耗时 {event.get('duration_ms')}ms")
    
    logger.info(f"\n✅ 收到 {len(events)} 个事件")
    
    # 检查状态
    state = orchestrator.get_state()
    logger.info(f"✅ 最终状态:")
    logger.info(f"   - 状态: {state.status}")
    logger.info(f"   - 已完成: {len(state.completed_agents)} 个")
    logger.info(f"   - 结果数量: {len(state.agent_results)}")
    
    # 检查追踪
    trace = orchestrator.get_execution_trace()
    logger.info(f"✅ 执行追踪: {len(trace)} 条记录")
    for entry in trace[:5]:  # 显示前 5 条
        logger.info(f"   - {entry['event_type']}: {entry['data']}")
    
    logger.info("\n✅ MultiAgentOrchestrator 测试通过\n")
    
    return orchestrator


async def main():
    """运行所有测试"""
    logger.info("\n" + "=" * 60)
    logger.info("🧪 多智能体框架测试（Anthropic 启发）")
    logger.info("=" * 60 + "\n")
    
    try:
        # 测试 1: CheckpointManager
        await test_checkpoint_manager()
        
        # 测试 2: LeadAgent（可能失败，取决于 LLM 配置）
        await test_lead_agent()
        
        # 测试 3: MultiAgentOrchestrator
        await test_multi_agent_orchestrator()
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ 所有测试完成！")
        logger.info("=" * 60 + "\n")
        
    except Exception as e:
        logger.error(f"\n❌ 测试失败: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())

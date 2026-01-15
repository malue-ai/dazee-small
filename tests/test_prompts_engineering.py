"""
测试 Prompts Engineering 实现

V7.1 验证内容：
1. _build_subagent_system_prompt() - 8 个核心要素
2. _execute_single_agent() - 真实执行
3. _build_decomposition_prompt() - 扩展规则
4. _suggest_subagent_count() - 复杂度驱动资源分配
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import logging
from core.agent.multi import (
    MultiAgentOrchestrator,
    MultiAgentConfig,
    AgentConfig,
    AgentRole,
    ExecutionMode,
    OrchestratorConfig,
    WorkerConfig,
    LeadAgent,
    SubTask,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_subagent_system_prompt():
    """测试 Subagent 系统提示词生成"""
    logger.info("=" * 60)
    logger.info("测试 1: Subagent 系统提示词生成")
    logger.info("=" * 60)
    
    # 创建测试配置
    config = MultiAgentConfig(
        config_id="test_config",
        mode=ExecutionMode.SEQUENTIAL,
        agents=[
            AgentConfig(
                agent_id="researcher_1",
                role=AgentRole.RESEARCHER,
                model="claude-sonnet-4-5-20250929",
                tools=["web_search", "wikipedia"],
            )
        ],
        orchestrator_config=OrchestratorConfig(),
        worker_config=WorkerConfig(),
    )
    
    orchestrator = MultiAgentOrchestrator(config=config)
    
    # 创建测试子任务
    subtask = SubTask(
        subtask_id="task_1",
        title="研究 Python vs JavaScript",
        description="比较 Python 和 JavaScript 的优缺点",
        assigned_agent_role=AgentRole.RESEARCHER,
        tools_required=["web_search"],
        expected_output="结构化的 Markdown 表格",
        success_criteria=["覆盖性能、语法、生态系统", "提供具体示例"],
        constraints=["不要讨论历史", "只关注 2025 年现状"],
        max_time_seconds=60,
    )
    
    # 生成系统提示词
    system_prompt = orchestrator._build_subagent_system_prompt(
        config=config.agents[0],
        subtask=subtask,
        orchestrator_context="这是第一个子任务"
    )
    
    logger.info(f"生成的系统提示词长度: {len(system_prompt)} 字符")
    logger.info(f"\n系统提示词预览（前 500 字符）:\n{system_prompt[:500]}...")
    
    # 验证包含 8 个核心要素
    checks = {
        "目标": "**你的目标**" in system_prompt,
        "输出格式": "**输出格式要求**" in system_prompt,
        "工具指导": "**可用工具**" in system_prompt,
        "任务边界": "**任务边界" in system_prompt,
        "成功标准": "**成功标准**" in system_prompt,
        "搜索策略": "**搜索策略指导**" in system_prompt,
        "Thinking 指导": "**Extended Thinking" in system_prompt,
        "重要提醒": "**重要提醒**" in system_prompt,
    }
    
    for check_name, check_result in checks.items():
        status = "✅" if check_result else "❌"
        logger.info(f"{status} {check_name}: {check_result}")
    
    all_passed = all(checks.values())
    logger.info(f"\n{'✅ 测试通过' if all_passed else '❌ 测试失败'}")
    
    return all_passed


async def test_suggest_subagent_count():
    """测试 Subagent 数量建议"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 2: Subagent 数量建议")
    logger.info("=" * 60)
    
    lead_agent = LeadAgent(max_subtasks=5)
    
    test_cases = [
        ("What is the capital of France?", 1, "简单查询"),
        ("Compare Python vs JavaScript", 3, "中等复杂度"),
        ("深入研究和分析 AI 对医疗行业的影响，包括多个方面的详细对比", 5, "高复杂度"),
    ]
    
    all_passed = True
    
    for query, expected_count, description in test_cases:
        suggested_count = lead_agent._suggest_subagent_count(query)
        passed = suggested_count == expected_count
        status = "✅" if passed else "❌"
        
        logger.info(
            f"{status} {description}: query='{query[:50]}...', "
            f"建议={suggested_count}, 期望={expected_count}"
        )
        
        if not passed:
            all_passed = False
    
    logger.info(f"\n{'✅ 测试通过' if all_passed else '❌ 测试失败'}")
    
    return all_passed


async def test_decomposition_prompt_rules():
    """测试分解 prompt 包含扩展规则"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 3: 分解 Prompt 扩展规则")
    logger.info("=" * 60)
    
    lead_agent = LeadAgent()
    
    prompt = lead_agent._build_decomposition_prompt(
        available_tools=["web_search", "code_executor"]
    )
    
    logger.info(f"分解 Prompt 长度: {len(prompt)} 字符")
    
    # 验证包含扩展规则
    checks = {
        "Rule 1 - 简单任务不分解": "简单任务不分解" in prompt,
        "Rule 2 - 复杂度驱动": "复杂度驱动资源分配" in prompt,
        "Rule 3 - 避免无意义并行化": "避免无意义的并行化" in prompt,
        "Rule 4 - 工具选择启发式": "工具选择启发式" in prompt,
        "明确边界": "明确边界" in prompt,
        "独立性": "独立性" in prompt,
        "可验证": "可验证" in prompt,
        "上下文充足": "上下文充足" in prompt,
    }
    
    for check_name, check_result in checks.items():
        status = "✅" if check_result else "❌"
        logger.info(f"{status} {check_name}: {check_result}")
    
    all_passed = all(checks.values())
    logger.info(f"\n{'✅ 测试通过' if all_passed else '❌ 测试失败'}")
    
    return all_passed


async def test_orchestrator_summary():
    """测试 Orchestrator 摘要生成"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 4: Orchestrator 摘要生成（上下文隔离）")
    logger.info("=" * 60)
    
    config = MultiAgentConfig(
        config_id="test_config",
        mode=ExecutionMode.SEQUENTIAL,
        agents=[],
    )
    
    orchestrator = MultiAgentOrchestrator(config=config)
    
    # 模拟初始状态
    from core.agent.multi.models import OrchestratorState, AgentResult
    from datetime import datetime
    
    orchestrator._state = OrchestratorState(
        state_id="test_state",
        session_id="test_session",
        config_id="test_config",
        mode=ExecutionMode.SEQUENTIAL,
        status="running",
        completed_agents=["agent_1", "agent_2"],
        pending_agents=["agent_3"],
        started_at=datetime.now(),
    )
    
    orchestrator._state.agent_results.append(
        AgentResult(
            result_id="result_1",
            agent_id="agent_1",
            success=True,
            output="这是一个很长的输出" * 100,  # 模拟长输出
            turns_used=1,
        )
    )
    
    # 生成摘要
    summary = orchestrator._build_orchestrator_summary()
    
    logger.info(f"摘要长度: {len(summary)} 字符")
    logger.info(f"摘要内容:\n{summary}")
    
    # 验证摘要不超过 2000 字符（约 500 tokens）
    passed = len(summary) <= 2000
    status = "✅" if passed else "❌"
    
    logger.info(f"\n{status} 摘要长度验证: {len(summary)} <= 2000")
    logger.info(f"\n{'✅ 测试通过' if passed else '❌ 测试失败'}")
    
    return passed


async def main():
    """运行所有测试"""
    logger.info("\n" + "🧪" * 30)
    logger.info("Prompts Engineering 测试套件")
    logger.info("🧪" * 30 + "\n")
    
    results = []
    
    # 运行测试
    results.append(("Subagent 系统提示词", await test_subagent_system_prompt()))
    results.append(("Subagent 数量建议", await test_suggest_subagent_count()))
    results.append(("分解 Prompt 扩展规则", await test_decomposition_prompt_rules()))
    results.append(("Orchestrator 摘要", await test_orchestrator_summary()))
    
    # 汇总结果
    logger.info("\n" + "=" * 60)
    logger.info("测试结果汇总")
    logger.info("=" * 60)
    
    for test_name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        logger.info(f"{status}: {test_name}")
    
    all_passed = all(result[1] for result in results)
    
    logger.info("\n" + "=" * 60)
    if all_passed:
        logger.info("🎉 所有测试通过！")
    else:
        logger.info("❌ 部分测试失败")
    logger.info("=" * 60)
    
    return all_passed


if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)

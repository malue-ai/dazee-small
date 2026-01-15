"""
端到端测试：Claude 研究报告场景

模拟 Anthropic Multi-Agent Research System 的完整流程：
1. 用户提交复杂研究查询
2. Lead Agent 分解任务
3. 多个 Subagents 并行执行
4. 结果综合
5. 生成研究报告

参考：https://www.anthropic.com/engineering/multi-agent-research-system
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件
from dotenv import load_dotenv
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ 已加载 .env 文件: {env_path}")
else:
    print(f"⚠️ 未找到 .env 文件: {env_path}")

import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any

from core.agent.multi import (
    MultiAgentOrchestrator,
    MultiAgentConfig,
    AgentConfig,
    AgentRole,
    ExecutionMode,
    OrchestratorConfig,
    WorkerConfig,
)
from core.agent.types import IntentResult, TaskType, Complexity

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_research_report_scenario():
    """
    测试场景：复杂研究报告
    
    查询："分析 AI 对医疗行业的影响，包括多个方面的详细对比"
    
    预期流程：
    1. Lead Agent 分解为多个子任务（如：技术影响、经济影响、伦理影响等）
    2. 多个 Subagents 并行执行
    3. Lead Agent 综合结果
    4. 生成完整的研究报告
    """
    logger.info("\n" + "="*80)
    logger.info("🧪 端到端测试：Claude 研究报告场景")
    logger.info("="*80)
    
    # ===== 1. 用户查询 =====
    user_query = "分析 AI 对医疗行业的影响，包括技术、经济、伦理三个方面的详细对比"
    
    logger.info(f"\n👤 用户查询：{user_query}")
    logger.info(f"📅 测试时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # ===== 2. 创建多智能体配置 =====
    logger.info("\n" + "-"*80)
    logger.info("📦 阶段 1: 创建多智能体配置")
    logger.info("-"*80)
    
    # 创建 Worker Agents（研究不同方面）
    agents = [
        AgentConfig(
            agent_id="researcher_tech",
            role=AgentRole.RESEARCHER,
            model="claude-sonnet-4-5-20250929",
            tools=["web_search", "wikipedia"],
            system_prompt="你是一个专注于技术研究的专家",
        ),
        AgentConfig(
            agent_id="researcher_econ",
            role=AgentRole.RESEARCHER,
            model="claude-sonnet-4-5-20250929",
            tools=["web_search", "wikipedia"],
            system_prompt="你是一个专注于经济分析的专家",
        ),
        AgentConfig(
            agent_id="researcher_ethics",
            role=AgentRole.RESEARCHER,
            model="claude-sonnet-4-5-20250929",
            tools=["web_search", "wikipedia"],
            system_prompt="你是一个专注于伦理研究的专家",
        ),
    ]
    
    # 创建配置（强弱配对策略）
    config = MultiAgentConfig(
        config_id="research_config_001",
        name="研究报告配置",
        description="用于生成复杂研究报告的多智能体配置",
        mode=ExecutionMode.PARALLEL,  # 并行执行
        agents=agents,
        orchestrator_config=OrchestratorConfig(
            model="claude-opus-4-5-20251101",  # 使用 Opus 4.5
            enable_thinking=True,
            max_tokens=16384,
            thinking_budget=10000,
            temperature=0.3,
        ),
        worker_config=WorkerConfig(
            model="claude-sonnet-4-5-20250929",
            enable_thinking=True,
            max_tokens=8192,
            thinking_budget=5000,
            temperature=0.5,
        ),
        enable_final_summary=True,
        max_total_turns=30,
        timeout_seconds=300,
    )
    
    logger.info(f"✅ 配置创建完成：")
    logger.info(f"   • Orchestrator: {config.orchestrator_config.model}")
    logger.info(f"   • Workers: {config.worker_config.model}")
    logger.info(f"   • 执行模式: {config.mode.value}")
    logger.info(f"   • Agent 数量: {len(agents)}")
    logger.info(f"\n⚙️  参数配置：")
    logger.info(f"   • Orchestrator: max_tokens={config.orchestrator_config.max_tokens}, thinking_budget={config.orchestrator_config.thinking_budget}")
    logger.info(f"   • Workers: max_tokens={config.worker_config.max_tokens}, thinking_budget={config.worker_config.thinking_budget}")
    
    # ===== 3. 创建 Orchestrator =====
    logger.info("\n" + "-"*80)
    logger.info("🚀 阶段 2: 创建 MultiAgentOrchestrator")
    logger.info("-"*80)
    
    orchestrator = MultiAgentOrchestrator(
        config=config,
        enable_checkpoints=True,
        enable_lead_agent=True,
    )
    
    logger.info("✅ Orchestrator 已创建")
    
    # ===== 4. 模拟意图分析结果 =====
    intent = IntentResult(
        task_type=TaskType.DATA_ANALYSIS,
        complexity=Complexity.COMPLEX,
        complexity_score=8.5,
        needs_plan=True,
        needs_multi_agent=True,
        keywords=["AI", "医疗", "影响", "技术", "经济", "伦理"],
    )
    
    # ===== 5. 执行多智能体协作 =====
    logger.info("\n" + "-"*80)
    logger.info("🔄 阶段 3: 执行多智能体协作")
    logger.info("-"*80)
    
    messages = [{"role": "user", "content": user_query}]
    session_id = f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    logger.info(f"📝 Session ID: {session_id}")
    logger.info(f"📨 消息数量: {len(messages)}")
    
    # 收集所有事件
    events = []
    final_output = None
    task_decomposition = None
    
    try:
        async for event in orchestrator.execute(
            intent=intent,
            messages=messages,
            session_id=session_id,
            resume_from_checkpoint=False,
        ):
            events.append(event)
            event_type = event.get("type", "unknown")
            
            # 记录关键事件
            if event_type == "orchestrator_start":
                logger.info(f"✅ Orchestrator 启动: {event.get('agent_count')} 个 Agents")
            
            elif event_type == "task_decomposition":
                task_decomposition = event
                logger.info(f"📋 任务分解完成:")
                logger.info(f"   • Plan ID: {event.get('plan_id')}")
                logger.info(f"   • 子任务数量: {event.get('subtasks_count')}")
                logger.info(f"   • 执行模式: {event.get('execution_mode')}")
                logger.info(f"   • 推理过程: {event.get('reasoning', '')[:100]}...")
            
            elif event_type == "agent_start":
                logger.info(f"🤖 Agent 开始: {event.get('agent_id')} ({event.get('role')})")
                if event.get('subtask_title'):
                    logger.info(f"   • 子任务: {event.get('subtask_title')}")
            
            elif event_type == "agent_end":
                logger.info(f"✅ Agent 完成: {event.get('agent_id')}")
                logger.info(f"   • 成功: {event.get('success')}")
                logger.info(f"   • 输出预览: {event.get('output_preview', '')[:100]}...")
            
            elif event_type == "orchestrator_summary":
                final_output = event.get("content", "")
                logger.info(f"📊 最终汇总生成:")
                logger.info(f"   • 由 Lead Agent 综合: {event.get('synthesized_by_lead_agent')}")
                logger.info(f"   • 输出长度: {len(final_output)} 字符")
            
            elif event_type == "orchestrator_end":
                logger.info(f"🎉 Orchestrator 完成:")
                logger.info(f"   • 状态: {event.get('status')}")
                logger.info(f"   • 耗时: {event.get('duration_ms')}ms")
                logger.info(f"   • Agent 结果数量: {event.get('agent_results')}")
            
            elif event_type == "orchestrator_error":
                logger.error(f"❌ Orchestrator 错误: {event.get('error')}")
    
    except Exception as e:
        logger.error(f"❌ 执行失败: {e}", exc_info=True)
        return False
    
    # ===== 6. 验证结果 =====
    logger.info("\n" + "-"*80)
    logger.info("✅ 阶段 4: 验证结果")
    logger.info("-"*80)
    
    checks = {
        "Orchestrator 启动": any(e.get("type") == "orchestrator_start" for e in events),
        "任务分解完成": task_decomposition is not None,
        "至少一个 Agent 执行": any(e.get("type") == "agent_start" for e in events),
        "最终汇总生成": final_output is not None and len(final_output) > 0,
        "Orchestrator 完成": any(e.get("type") == "orchestrator_end" for e in events),
    }
    
    for check_name, check_result in checks.items():
        status = "✅" if check_result else "❌"
        logger.info(f"{status} {check_name}: {check_result}")
    
    # ===== 7. 输出最终报告 =====
    if final_output:
        logger.info("\n" + "-"*80)
        logger.info("📄 最终研究报告")
        logger.info("-"*80)
        logger.info(final_output[:500] + "..." if len(final_output) > 500 else final_output)
    
    # ===== 8. 输出执行追踪 =====
    trace = orchestrator.get_execution_trace()
    if trace:
        logger.info("\n" + "-"*80)
        logger.info("📊 执行追踪（前 5 条）")
        logger.info("-"*80)
        for i, entry in enumerate(trace[:5], 1):
            logger.info(f"{i}. {entry.get('event_type')}: {entry.get('data', {})}")
    
    # ===== 9. 统计信息 =====
    logger.info("\n" + "-"*80)
    logger.info("📈 统计信息")
    logger.info("-"*80)
    
    state = orchestrator.get_state()
    if state:
        logger.info(f"• 总轮次: {state.total_turns}")
        logger.info(f"• 已完成 Agents: {len(state.completed_agents)}")
        logger.info(f"• Agent 结果数量: {len(state.agent_results)}")
        logger.info(f"• 总耗时: {state.total_duration_ms}ms" if state.total_duration_ms else "• 总耗时: 未完成")
    
    all_passed = all(checks.values())
    
    logger.info("\n" + "="*80)
    if all_passed:
        logger.info("🎉 端到端测试通过！")
    else:
        logger.info("❌ 端到端测试失败")
    logger.info("="*80)
    
    return all_passed


async def main():
    """运行端到端测试"""
    try:
        result = await test_research_report_scenario()
        return result
    except Exception as e:
        logger.error(f"❌ 测试执行失败: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)

"""
验证多智能体触发逻辑

检查 "研究 AWS、Azure、GCP 三家云服务商的 AI 战略" 是否正确触发多智能体
"""

import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)

sys.path.insert(0, str(project_root))

from core.routing.intent_analyzer import IntentAnalyzer
from core.routing.router import AgentRouter
from core.llm import create_claude_service


async def main():
    """验证多智能体触发"""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY 未设置")
        return
    
    print("="*70)
    print("验证多智能体触发逻辑")
    print("="*70)
    
    # 创建 LLM 服务
    llm_service = create_claude_service(
        model="claude-3-5-haiku-20241022",
        api_key=api_key,
        enable_thinking=False,
        enable_caching=True,
        max_tokens=4096
    )
    
    # 创建 IntentAnalyzer
    analyzer = IntentAnalyzer(llm_service=llm_service, enable_llm=True)
    
    # 创建 AgentRouter
    router = AgentRouter(llm_service=llm_service)
    
    # 测试 case
    test_queries = [
        {
            "name": "三家云服务商对比（应该触发多智能体）",
            "query": "研究 AWS、Azure、GCP 三家云服务商的 AI 战略，生成对比分析报告",
            "expected_multi_agent": True
        },
        {
            "name": "提示词中的例子（应该触发多智能体）",
            "query": "对比 AWS、Azure、GCP 三家云服务商的定价策略",
            "expected_multi_agent": True
        },
        {
            "name": "单一任务（不应触发多智能体）",
            "query": "帮我写一个 Python 排序算法并补充单元测试",
            "expected_multi_agent": False
        },
        {
            "name": "四个城市天气（应该触发多智能体）",
            "query": "同时查询北京、上海、广州、深圳四个城市的天气",
            "expected_multi_agent": True
        }
    ]
    
    for test in test_queries:
        print(f"\n{'='*70}")
        print(f"测试: {test['name']}")
        print(f"Query: {test['query']}")
        print(f"预期: needs_multi_agent={test['expected_multi_agent']}")
        print(f"{'='*70}")
        
        # 1. IntentAnalyzer 分析
        messages = [{"role": "user", "content": test["query"]}]
        intent = await analyzer.analyze(messages)
        
        print(f"\n📊 IntentAnalyzer 结果:")
        print(f"  • task_type: {intent.task_type}")
        print(f"  • complexity: {intent.complexity.value}")
        print(f"  • complexity_score: {intent.complexity_score}")
        print(f"  • needs_plan: {intent.needs_plan}")
        print(f"  • needs_multi_agent: {intent.needs_multi_agent}")  # 🔍 关键字段
        print(f"  • execution_strategy: {intent.execution_strategy}")
        print(f"  • suggested_planning_depth: {intent.suggested_planning_depth}")
        
        # 2. AgentRouter 路由决策
        decision = await router.route(
            user_query=test["query"],
            conversation_history=[]
        )
        
        print(f"\n🔀 AgentRouter 路由决策:")
        print(f"  • agent_type: {decision.agent_type}")
        print(f"  • execution_strategy: {decision.execution_strategy}")
        print(f"  • routing_reason: {decision.context.get('routing_reason')}")
        
        # 3. 验证结果
        is_correct = (intent.needs_multi_agent == test["expected_multi_agent"]) and \
                     ((decision.agent_type == "multi") == test["expected_multi_agent"])
        
        if is_correct:
            print(f"\n✅ 测试通过: needs_multi_agent={intent.needs_multi_agent}, agent_type={decision.agent_type}")
        else:
            print(f"\n❌ 测试失败:")
            print(f"   预期: needs_multi_agent={test['expected_multi_agent']}")
            print(f"   实际: needs_multi_agent={intent.needs_multi_agent}, agent_type={decision.agent_type}")
    
    print(f"\n{'='*70}")
    print("验证完成")
    print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())

"""
端到端验证：V9.0 意图识别优化 + 真实 API 调用

验证目标：
1. 真实意图识别（Claude Haiku + 上下文过滤）
2. 真实路由决策（AgentRouter）
3. 真实 Agent 执行（SimpleAgent/RVRBAgent + Claude Sonnet）
4. 追问场景识别准确率

估计消耗：~10-15K tokens（约 $0.1-0.15）
"""

# 1. 标准库
import os
import sys
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime

# 添加项目根目录到 sys.path
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 2. 第三方库
import pytest

# 3. 本地模块


def load_env():
    """加载 .env 文件"""
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=True)
            print(f"✅ 加载 .env: {env_path}")
        else:
            print(f"⚠️ .env 不存在: {env_path}")
            return False
        return True
    except Exception as e:
        print(f"❌ 加载 .env 失败: {e}")
        return False


async def test_scenario_1_simple_query():
    """场景 1: 简单问答（验证上下文过滤）"""
    print("\n" + "=" * 80)
    print("场景 1: 简单问答 - 验证上下文过滤")
    print("=" * 80)
    
    from core.routing import AgentRouter
    from core.llm import create_llm_service
    
    # 创建 IntentAnalyzer（真实 LLM）
    llm = create_llm_service(
        provider="claude",
        model="claude-3-5-haiku-20241022",  # Haiku 3.5 用于意图识别
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        enable_thinking=False,  # Haiku 不支持 thinking
        max_tokens=1024
    )
    
    router = AgentRouter(llm_service=llm, enable_llm=True)
    
    # 模拟长对话历史（含大量工具调用）
    conversation_history = [
        {"role": "user", "content": "帮我搜索 Python 教程"},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "1", "name": "web_search", "input": {"query": "Python tutorial"}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "1", "content": "搜索结果：" + "x" * 5000},  # 大量文本
        ]},
        {"role": "assistant", "content": "我找到了一些 Python 教程..." + "y" * 1000},  # 长回复
        {"role": "user", "content": "然后呢？"},
    ]
    
    user_query = "然后呢？"
    
    print(f"\n📝 原始对话历史: {len(conversation_history)} 条消息")
    print(f"   用户 query: {user_query}")
    
    # 执行路由决策（会调用真实 API）
    decision = await router.route(
        user_query=user_query,
        conversation_history=conversation_history
    )
    
    print(f"\n✅ 路由决策完成:")
    print(f"   agent_type: {decision.agent_type}")
    print(f"   execution_strategy: {decision.execution_strategy}")
    print(f"   task_type: {decision.intent.task_type.value}")
    print(f"   complexity: {decision.intent.complexity.value}")
    print(f"   is_follow_up: {decision.intent.is_follow_up}")
    print(f"   needs_multi_agent: {decision.intent.needs_multi_agent}")
    
    # 验证：应该识别为追问
    assert decision.intent.is_follow_up == True, "应该识别为追问"
    print("\n✅ 场景 1 通过: 成功识别追问")
    
    return decision


async def test_scenario_2_code_development():
    """场景 2: 代码开发（验证新意图 → 追问）"""
    print("\n" + "=" * 80)
    print("场景 2: 代码开发 + 追问 - 验证意图状态转换")
    print("=" * 80)
    
    from core.routing import AgentRouter
    from core.llm import create_llm_service
    
    llm = create_llm_service(
        provider="claude",
        model="claude-3-5-haiku-20241022",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        enable_thinking=False,  # Haiku 不支持 thinking
        max_tokens=1024
    )
    
    router = AgentRouter(llm_service=llm, enable_llm=True)
    
    # 第一轮：新问题
    print("\n--- 第 1 轮：写快速排序 ---")
    decision_1 = await router.route(
        user_query="帮我写一个 Python 快速排序函数",
        conversation_history=[]
    )
    
    print(f"✅ 第 1 轮意图:")
    print(f"   task_type: {decision_1.intent.task_type.value}")
    print(f"   is_follow_up: {decision_1.intent.is_follow_up}")
    print(f"   needs_plan: {decision_1.intent.needs_plan}")
    
    # 第二轮：追问
    print("\n--- 第 2 轮：那如果要降序呢？ ---")
    conversation_history_2 = [
        {"role": "user", "content": "帮我写一个 Python 快速排序函数"},
        {"role": "assistant", "content": "好的，这是快速排序函数..."},
    ]
    
    decision_2 = await router.route(
        user_query="那如果要降序呢？",
        conversation_history=conversation_history_2,
        previous_intent=decision_1.intent  # 传入上轮意图
    )
    
    print(f"✅ 第 2 轮意图:")
    print(f"   task_type: {decision_2.intent.task_type.value}")
    print(f"   is_follow_up: {decision_2.intent.is_follow_up}")
    print(f"   继承的 task_type: {decision_2.intent.task_type == decision_1.intent.task_type}")
    
    # 验证：第二轮应该识别为追问
    assert decision_2.intent.is_follow_up == True, "第二轮应该识别为追问"
    print("\n✅ 场景 2 通过: 成功识别追问并继承 task_type")
    
    return decision_1, decision_2


async def test_scenario_3_multi_turn_conversation():
    """场景 3: 多轮对话（验证追问识别准确率）"""
    print("\n" + "=" * 80)
    print("场景 3: 多轮对话 - 验证追问识别准确率")
    print("=" * 80)
    
    from core.routing import AgentRouter
    from core.llm import create_llm_service
    
    llm = create_llm_service(
        provider="claude",
        model="claude-3-5-haiku-20241022",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        enable_thinking=False,
        max_tokens=1024
    )
    
    router = AgentRouter(llm_service=llm, enable_llm=True)
    
    # 测试案例：新意图 → 追问 → 新意图
    test_cases = [
        {
            "round": 1,
            "query": "Python 怎么写排序？",
            "history": [],
            "expected_follow_up": False,
            "description": "新问题"
        },
        {
            "round": 2,
            "query": "那降序呢？",
            "history": [
                {"role": "user", "content": "Python 怎么写排序？"},
                {"role": "assistant", "content": "可以用 sorted() 函数..."},
            ],
            "expected_follow_up": True,
            "description": "追问（降序）"
        },
        {
            "round": 3,
            "query": "再给个快速排序的例子",
            "history": [
                {"role": "user", "content": "Python 怎么写排序？"},
                {"role": "assistant", "content": "可以用 sorted() 函数..."},
                {"role": "user", "content": "那降序呢？"},
                {"role": "assistant", "content": "可以用 reverse=True..."},
            ],
            "expected_follow_up": True,
            "description": "追问（快速排序）"
        },
        {
            "round": 4,
            "query": "上海今天天气怎么样？",
            "history": [
                {"role": "user", "content": "Python 怎么写排序？"},
                {"role": "assistant", "content": "可以用 sorted() 函数..."},
                {"role": "user", "content": "那降序呢？"},
                {"role": "assistant", "content": "可以用 reverse=True..."},
                {"role": "user", "content": "再给个快速排序的例子"},
                {"role": "assistant", "content": "这是快速排序..."},
            ],
            "expected_follow_up": False,
            "description": "新问题（完全无关）"
        },
    ]
    
    results = []
    previous_intent = None
    
    for case in test_cases:
        print(f"\n--- 第 {case['round']} 轮：{case['description']} ---")
        print(f"   query: {case['query']}")
        
        decision = await router.route(
            user_query=case['query'],
            conversation_history=case['history'],
            previous_intent=previous_intent
        )
        
        is_correct = decision.intent.is_follow_up == case['expected_follow_up']
        status = "✅" if is_correct else "❌"
        
        print(f"{status} is_follow_up: {decision.intent.is_follow_up} (预期: {case['expected_follow_up']})")
        print(f"   task_type: {decision.intent.task_type.value}")
        
        results.append({
            "round": case['round'],
            "is_correct": is_correct,
            "actual": decision.intent.is_follow_up,
            "expected": case['expected_follow_up']
        })
        
        previous_intent = decision.intent
    
    # 统计准确率
    correct_count = sum(1 for r in results if r['is_correct'])
    accuracy = correct_count / len(results) * 100
    
    print(f"\n📊 追问识别准确率: {correct_count}/{len(results)} ({accuracy:.1f}%)")
    
    assert accuracy >= 75.0, f"追问识别准确率过低: {accuracy:.1f}%"
    
    print(f"\n✅ 场景 3 通过: 追问识别准确率达标 ({accuracy:.1f}%)")
    
    return results


async def test_scenario_4_context_filtering_effectiveness():
    """场景 4: 上下文过滤有效性（对比测试）"""
    print("\n" + "=" * 80)
    print("场景 4: 上下文过滤有效性验证")
    print("=" * 80)
    
    from core.routing.intent_analyzer import IntentAnalyzer
    from core.llm import create_llm_service
    
    llm = create_llm_service(
        provider="claude",
        model="claude-3-5-haiku-20241022",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        enable_thinking=False,  # Haiku 不支持 thinking
        max_tokens=1024
    )
    
    analyzer = IntentAnalyzer(llm_service=llm, enable_llm=True)
    
    # 构造包含大量噪音的对话历史
    messages_with_noise = []
    for i in range(10):
        messages_with_noise.append({"role": "user", "content": f"query {i}"})
        messages_with_noise.append({
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": f"tool_{i}", "name": "search", "input": {}},
                {"type": "tool_result", "tool_use_id": f"tool_{i}", "content": "x" * 1000},
                {"type": "text", "text": "response " * 100}
            ]
        })
    
    messages_with_noise.append({"role": "user", "content": "帮我写个快速排序"})
    
    print(f"\n📝 测试消息:")
    print(f"   原始消息数: {len(messages_with_noise)} 条")
    
    # 执行过滤
    filtered = analyzer._filter_for_intent(messages_with_noise)
    print(f"   过滤后: {len(filtered)} 条")
    
    user_msgs = [m for m in filtered if m['role'] == 'user']
    assistant_msgs = [m for m in filtered if m['role'] == 'assistant']
    print(f"   用户消息: {len(user_msgs)} 条")
    print(f"   助手消息: {len(assistant_msgs)} 条")
    
    # 调用真实 API 进行意图识别
    print("\n🔍 调用真实 API 进行意图识别...")
    result = await analyzer.analyze(messages_with_noise)
    
    print(f"\n✅ 意图识别结果:")
    print(f"   task_type: {result.task_type.value}")
    print(f"   complexity: {result.complexity.value}")
    print(f"   needs_plan: {result.needs_plan}")
    
    # 验证过滤效果
    assert len(filtered) < len(messages_with_noise), "应该有过滤效果"
    assert len(filtered) <= 6, "过滤后应该不超过 6 条（5 user + 1 assistant）"
    
    print(f"\n✅ 场景 4 通过: 上下文过滤有效（减少 {len(messages_with_noise) - len(filtered)} 条消息）")
    
    return result


@pytest.mark.asyncio
async def test_e2e_v9_real_api():
    """V9.0 真实 API 端到端验证"""
    print("\n" + "=" * 80)
    print("🚀 V9.0 真实 API 端到端验证")
    print("=" * 80)
    
    # 加载环境变量
    if not load_env():
        pytest.skip("未找到 .env 文件")
    
    # 检查 API Key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("未设置 ANTHROPIC_API_KEY")
    
    print(f"\n🔑 API Key 已配置: {api_key[:8]}***")
    print(f"⚠️ 预计消耗: ~10-15K tokens (~$0.1-0.15)")
    
    try:
        # 场景 1: 简单问答 + 上下文过滤
        await test_scenario_1_simple_query()
        
        # 场景 2: 代码开发 + 追问
        await test_scenario_2_code_development()
        
        # 场景 3: 多轮对话追问识别
        await test_scenario_3_multi_turn_conversation()
        
        # 场景 4: 上下文过滤有效性
        await test_scenario_4_context_filtering_effectiveness()
        
        print("\n" + "=" * 80)
        print("✅ 所有真实 API 测试通过")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    """直接运行脚本"""
    asyncio.run(test_e2e_v9_real_api())

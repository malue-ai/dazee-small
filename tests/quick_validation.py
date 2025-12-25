"""
快速验证多调用方式支持

测试三个典型场景：
1. 简单查询 → Direct Tool Call
2. 配置生成 → Code Execution
3. 多工具编排 → Programmatic Tool Calling
"""

import os
import sys
import asyncio
from datetime import datetime

# 将项目根目录添加到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from core.agent import SimpleAgent


async def main():
    print("=" * 60)
    print("🚀 多调用方式快速验证")
    print("=" * 60)
    print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # 检查 API Key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("❌ 未设置 ANTHROPIC_API_KEY")
        print("请设置环境变量: export ANTHROPIC_API_KEY='your_key'")
        return
    
    print("✅ ANTHROPIC_API_KEY 已设置\n")
    
    # 初始化 Agent
    print("📦 初始化 SimpleAgent...")
    agent = SimpleAgent(verbose=True)
    print("✅ Agent 初始化完成\n")
    
    # ===== 场景 1: 简单查询 =====
    print("\n" + "=" * 60)
    print("📝 场景 1: 简单查询 → 预期 Direct Tool Call")
    print("=" * 60)
    
    query1 = "今天深圳天气怎么样？"
    print(f"👤 Query: {query1}\n")
    
    try:
        result1 = await agent.run(query1)
        print(f"\n📊 Result:")
        print(f"   Status: {result1['status']}")
        print(f"   Turns: {result1['turns']}")
        print(f"   Invocation Stats: {result1['invocation_stats']}")
        
        # 验证
        stats1 = result1['invocation_stats']
        if stats1.get('direct', 0) > 0:
            print(f"   ✅ 符合预期：使用了 Direct Tool Call")
        else:
            print(f"   ⚠️  与预期不同：未使用 Direct Tool Call")
            print(f"   实际使用的方式: {[k for k, v in stats1.items() if v > 0]}")
    except Exception as e:
        print(f"❌ 场景 1 执行失败: {e}")
        import traceback
        traceback.print_exc()
    
    # ===== 场景 2: 配置生成 =====
    print("\n\n" + "=" * 60)
    print("📝 场景 2: 配置生成 → 预期 Code Execution")
    print("=" * 60)
    
    query2 = "创建产品介绍 PPT"
    print(f"👤 Query: {query2}\n")
    print("⚠️  注意: 此场景需要真实的 SLIDESPEAK_API_KEY")
    print("     如果没有，Agent 会使用其他方式响应\n")
    
    try:
        result2 = await agent.run(query2)
        print(f"\n📊 Result:")
        print(f"   Status: {result2['status']}")
        print(f"   Turns: {result2['turns']}")
        print(f"   Invocation Stats: {result2['invocation_stats']}")
        
        # 验证
        stats2 = result2['invocation_stats']
        if stats2.get('code_execution', 0) > 0:
            print(f"   ✅ 符合预期：使用了 Code Execution")
        else:
            print(f"   ⚠️  与预期不同：未使用 Code Execution")
            print(f"   实际使用的方式: {[k for k, v in stats2.items() if v > 0]}")
    except Exception as e:
        print(f"❌ 场景 2 执行失败: {e}")
        import traceback
        traceback.print_exc()
    
    # ===== 场景 3: 多工具编排 =====
    print("\n\n" + "=" * 60)
    print("📝 场景 3: 多工具编排 → 预期 Programmatic Tool Calling")
    print("=" * 60)
    
    query3 = "研究 AI Agent 技术并生成报告"
    print(f"👤 Query: {query3}\n")
    print("⚠️  注意: Claude 会根据具体情况决定是否使用 Programmatic Tool Calling")
    print("     也可能使用多次 Direct Tool Call 或 Code Execution\n")
    
    try:
        result3 = await agent.run(query3)
        print(f"\n📊 Result:")
        print(f"   Status: {result3['status']}")
        print(f"   Turns: {result3['turns']}")
        print(f"   Invocation Stats: {result3['invocation_stats']}")
        
        # 验证
        stats3 = result3['invocation_stats']
        if stats3.get('programmatic', 0) > 0:
            print(f"   ✅ 使用了 Programmatic Tool Calling")
        elif stats3.get('code_execution', 0) > 0:
            print(f"   ✅ 使用了 Code Execution（合理的替代方式）")
        elif stats3.get('direct', 0) > 1:
            print(f"   ✅ 使用了多次 Direct Tool Call（合理的替代方式）")
        else:
            print(f"   ⚠️  实际使用的方式: {[k for k, v in stats3.items() if v > 0]}")
    except Exception as e:
        print(f"❌ 场景 3 执行失败: {e}")
        import traceback
        traceback.print_exc()
    
    # ===== 总结 =====
    print("\n\n" + "=" * 60)
    print("📊 验证总结")
    print("=" * 60)
    print("\n✅ 验证完成！")
    print("\n📝 说明:")
    print("   • 实际调用方式由 Claude 根据系统提示词智能决策")
    print("   • 不同场景可能因上下文不同而选择不同的方式")
    print("   • 关键是系统能够识别和统计所有调用方式")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())


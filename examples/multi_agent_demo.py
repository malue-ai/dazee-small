"""
Multi-Agent 并行调度示例

演示如何使用 AgentManager 实现多 Agent 协作

Author: 刘屹
Date: 2025-12-26
"""

import asyncio
from core.agent_manager import create_agent_manager


async def demo_basic_parallel():
    """
    示例 1: 基础并行执行
    
    场景: 同时优化 CSS 和编写测试
    """
    print("\n" + "="*70)
    print("示例 1: 基础并行执行")
    print("="*70)
    
    manager = create_agent_manager()
    
    # 执行任务
    result = await manager.execute_task(
        "优化导航栏CSS样式，同时补充登录页面的单元测试",
        strategy="parallel"
    )
    
    # 查看结果
    print(f"\n结果: {result.get_summary()}")
    
    return result


async def demo_sequential_with_dependencies():
    """
    示例 2: 串行执行 (有依赖关系)
    
    场景: 先重构代码，再补充测试
    """
    print("\n" + "="*70)
    print("示例 2: 串行执行 (有依赖关系)")
    print("="*70)
    
    manager = create_agent_manager()
    
    # 执行任务
    result = await manager.execute_task(
        "重构用户认证模块，然后为重构后的代码补充单元测试",
        strategy="sequential"
    )
    
    # 查看结果
    print(f"\n结果: {result.get_summary()}")
    
    return result


async def demo_complex_task():
    """
    示例 3: 复杂任务 (自动拆解)
    
    场景: 多个独立任务 + 依赖任务
    """
    print("\n" + "="*70)
    print("示例 3: 复杂任务 (自动拆解)")
    print("="*70)
    
    manager = create_agent_manager()
    
    # 复杂任务
    result = await manager.execute_task(
        """
        请完成以下任务:
        1. 重构用户认证模块，提取密码验证逻辑
        2. 优化登录页面的CSS样式，使用现代化设计
        3. 为重构后的认证模块补充完整的单元测试
        """,
        strategy="auto"  # 自动选择最优策略
    )
    
    # 查看结果
    print(f"\n结果: {result.get_summary()}")
    
    return result


async def demo_manual_agent_creation():
    """
    示例 4: 手动创建 Agent 并控制执行
    
    场景: 更精细的控制
    """
    print("\n" + "="*70)
    print("示例 4: 手动创建 Agent 并控制执行")
    print("="*70)
    
    manager = create_agent_manager()
    
    # 1. 创建专业 Agent
    css_agent = await manager.create_agent("agent-css-1", "css")
    test_agent = await manager.create_agent("agent-test-1", "test")
    refactor_agent = await manager.create_agent("agent-refactor-1", "refactor")
    
    print(f"\n创建了 {len(manager.list_agents())} 个 Agent")
    
    # 2. 并行执行任务
    print("\n开始并行执行...")
    
    results = await asyncio.gather(
        manager.start_agent("agent-css-1", "优化导航栏CSS"),
        manager.start_agent("agent-refactor-1", "重构认证模块"),
        return_exceptions=True
    )
    
    print("\n并行任务完成:")
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"  任务 {i+1}: 失败 - {result}")
        else:
            print(f"  任务 {i+1}: 成功")
    
    # 3. 串行执行依赖任务
    print("\n等待依赖任务完成后，执行测试...")
    
    test_result = await manager.start_agent("agent-test-1", "为认证模块补充测试")
    
    print(f"  测试任务: 成功")
    
    # 4. 查看状态
    status = manager.get_status()
    
    print(f"\n系统状态:")
    print(f"  总 Agent 数: {len(status['agents'])}")
    print(f"  完成任务数: {status['stats']['completed_tasks']}")
    print(f"  健康状态: {status['health']}")
    
    return status


async def demo_event_monitoring():
    """
    示例 5: 事件监听与监控
    
    场景: 实时监控 Agent 状态
    """
    print("\n" + "="*70)
    print("示例 5: 事件监听与监控")
    print("="*70)
    
    manager = create_agent_manager()
    
    # 注册事件监听器
    async def on_agent_created(data):
        print(f"  📢 事件: Agent 创建 - {data['agent_id']} ({data['specialization']})")
    
    async def on_agent_started(data):
        print(f"  📢 事件: Agent 启动 - {data['agent_id']}: {data['task']}")
    
    async def on_agent_completed(data):
        print(f"  📢 事件: Agent 完成 - {data['agent_id']}")
    
    manager.on("agent.created", on_agent_created)
    manager.on("agent.started", on_agent_started)
    manager.on("agent.completed", on_agent_completed)
    
    # 执行任务 (会触发事件)
    print("\n开始执行任务 (监听事件)...\n")
    
    result = await manager.execute_task(
        "优化CSS样式，同时补充单元测试",
        strategy="parallel"
    )
    
    print(f"\n结果: {result.get_summary()}")
    
    return result


async def demo_error_handling():
    """
    示例 6: 错误处理与重试
    
    场景: 任务失败的处理
    """
    print("\n" + "="*70)
    print("示例 6: 错误处理与重试")
    print("="*70)
    
    manager = create_agent_manager(config={'max_retries': 3})
    
    # 创建 Agent
    agent = await manager.create_agent("agent-1", "general")
    
    print("\n尝试执行可能失败的任务...")
    
    try:
        # 模拟失败场景
        # 实际使用中，任务可能因各种原因失败
        result = await manager.start_agent("agent-1", "执行一个复杂任务")
        print(f"  ✅ 任务成功")
    except Exception as e:
        print(f"  ❌ 任务失败: {e}")
        print(f"  🔄 可以实施重试策略...")
    
    return None


async def main():
    """
    主函数: 运行所有示例
    """
    print("\n" + "🚀" * 35)
    print("Multi-Agent 并行调度示例集合")
    print("🚀" * 35)
    
    # 运行所有示例
    demos = [
        demo_basic_parallel,
        demo_sequential_with_dependencies,
        demo_complex_task,
        demo_manual_agent_creation,
        demo_event_monitoring,
        demo_error_handling
    ]
    
    for demo in demos:
        try:
            await demo()
            await asyncio.sleep(1)  # 间隔
        except Exception as e:
            print(f"\n❌ 示例执行失败: {demo.__name__} - {e}")
    
    print("\n" + "="*70)
    print("✅ 所有示例执行完成")
    print("="*70)


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())
    
    
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 预期输出示例
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
============================================================
示例 1: 基础并行执行
============================================================

✅ AgentManager 初始化完成 (最大 Agent 数: 10)

============================================================
📋 任务: 优化导航栏CSS样式，同时补充登录页面的单元测试
============================================================

1️⃣ 任务分析与拆解...
   拆解为 2 个子任务:
   - task-1: 优化CSS样式 [css]
   - task-2: 补充单元测试 [test]

2️⃣ 创建专业 Agent...
   ✅ 创建 agent-css-1 (css)
   ✅ 创建 agent-test-1 (test)

3️⃣ 开始执行 (策略: parallel)...

   🔧 [agent-css-1] 执行: 优化CSS样式
   🔧 [agent-test-1] 执行: 补充单元测试
   ✅ [agent-css-1] 完成: 优化CSS样式 (1.0s)
   ✅ [agent-test-1] 完成: 补充单元测试 (1.0s)

============================================================
✅ 完成 2/2 任务,总耗时 1.2秒
============================================================
"""




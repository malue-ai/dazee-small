"""
Agent 创建性能基准测试

测试目的：验证 "clone 模式 vs 直接创建" 的性能差异
文档声称：clone 可节省 50-100ms

测试场景：
A. 从头创建 Agent（使用 AgentFactory，不使用预加载原型）
B. clone_for_session（registry.get_agent 使用，复用 tool_executor）
C. clone（agent_pool.acquire 使用，创建新 tool_executor）
"""

import asyncio
import time
import statistics
from typing import List, Dict, Any

# 设置环境变量（必须在导入其他模块之前）
import os
from pathlib import Path

# 加载 .env 文件
from dotenv import load_dotenv
env_file = Path(__file__).parent.parent / ".env.development"
load_dotenv(env_file)
os.environ.setdefault("ENV", "development")


async def run_benchmark():
    """运行性能基准测试"""
    
    # 导入依赖（在设置环境变量后）
    from services.agent_registry import get_agent_registry
    from infra.pools import get_agent_pool
    from core.events import create_event_manager, get_memory_storage
    from core.agent import AgentFactory
    
    print("=" * 60)
    print("Agent 创建性能基准测试")
    print("=" * 60)
    
    # 初始化
    registry = get_agent_registry()
    agent_pool = get_agent_pool()
    
    # 预加载（这是共享的准备工作）
    print("\n[0] 预加载...")
    start = time.perf_counter()
    await registry.preload_all()
    await agent_pool.preload_all()
    preload_time = (time.perf_counter() - start) * 1000
    print(f"    预加载总耗时: {preload_time:.2f}ms")
    
    # 测试参数
    agent_id = "dazee_agent"
    iterations = 5  # 减少迭代次数，因为从头创建很慢
    
    print(f"\n    测试 Agent: {agent_id}")
    print(f"    迭代次数: {iterations}")
    
    # 获取配置（用于从头创建）
    config = registry._configs[agent_id]
    
    # 创建测试用的 event_manager
    def create_test_event_manager():
        return create_event_manager(get_memory_storage())
    
    # ==================== 测试 A: 从头创建 (AgentFactory) ====================
    print("\n" + "-" * 60)
    print("测试 A: 从头创建 (AgentFactory.from_schema)")
    print("        这是【无预加载】时每次请求的真实耗时")
    print("-" * 60)
    
    from_scratch_times: List[float] = []
    
    for i in range(iterations):
        event_manager = create_test_event_manager()
        
        start = time.perf_counter()
        # 使用 AgentFactory 从头创建（模拟无预加载的情况）
        # 获取系统提示词（使用 MEDIUM 复杂度）
        from core.agent.types import Complexity
        system_prompt = config.prompt_cache.get_system_prompt(Complexity.MEDIUM) if config.prompt_cache else config.full_prompt
        agent = AgentFactory.from_schema(
            schema=config.prompt_cache.agent_schema,
            system_prompt=system_prompt,
            prompt_cache=config.prompt_cache,
            event_manager=event_manager,
            conversation_service=None,
            apis_config=None
        )
        elapsed = (time.perf_counter() - start) * 1000
        from_scratch_times.append(elapsed)
        
        print(f"    第 {i+1} 次: {elapsed:.2f}ms")
    
    print(f"\n    平均: {statistics.mean(from_scratch_times):.2f}ms")
    print(f"    中位数: {statistics.median(from_scratch_times):.2f}ms")
    if len(from_scratch_times) > 1:
        print(f"    标准差: {statistics.stdev(from_scratch_times):.2f}ms")
    
    # ==================== 测试 B: clone_for_session ====================
    print("\n" + "-" * 60)
    print("测试 B: clone_for_session (registry.get_agent)")
    print("        复用 tool_executor，速度最快但可能有并发问题")
    print("-" * 60)
    
    clone_session_times: List[float] = []
    
    for i in range(iterations):
        event_manager = create_test_event_manager()
        
        start = time.perf_counter()
        agent = await registry.get_agent(
            agent_id=agent_id,
            event_manager=event_manager,
            conversation_service=None
        )
        elapsed = (time.perf_counter() - start) * 1000
        clone_session_times.append(elapsed)
        
        print(f"    第 {i+1} 次: {elapsed:.2f}ms")
    
    print(f"\n    平均: {statistics.mean(clone_session_times):.2f}ms")
    print(f"    中位数: {statistics.median(clone_session_times):.2f}ms")
    if len(clone_session_times) > 1:
        print(f"    标准差: {statistics.stdev(clone_session_times):.2f}ms")
    
    # ==================== 测试 C: clone (独立 tool_executor) ====================
    print("\n" + "-" * 60)
    print("测试 C: clone (agent_pool.acquire)")
    print("        创建独立 tool_executor，更安全但稍慢")
    print("-" * 60)
    
    clone_times: List[float] = []
    
    for i in range(iterations):
        event_manager = create_test_event_manager()
        
        start = time.perf_counter()
        agent = await agent_pool.acquire(
            agent_id=agent_id,
            event_manager=event_manager,
            conversation_service=None
        )
        elapsed = (time.perf_counter() - start) * 1000
        clone_times.append(elapsed)
        
        # 释放 Agent
        await agent_pool.release(agent_id)
        
        print(f"    第 {i+1} 次: {elapsed:.2f}ms")
    
    print(f"\n    平均: {statistics.mean(clone_times):.2f}ms")
    print(f"    中位数: {statistics.median(clone_times):.2f}ms")
    if len(clone_times) > 1:
        print(f"    标准差: {statistics.stdev(clone_times):.2f}ms")
    
    # ==================== 结果对比 ====================
    print("\n" + "=" * 60)
    print("结果对比")
    print("=" * 60)
    
    scratch_avg = statistics.mean(from_scratch_times)
    session_avg = statistics.mean(clone_session_times)
    clone_avg = statistics.mean(clone_times)
    
    print(f"\n    A. 从头创建:         {scratch_avg:.2f}ms")
    print(f"    B. clone_for_session: {session_avg:.2f}ms")
    print(f"    C. clone:             {clone_avg:.2f}ms")
    
    print("\n" + "-" * 60)
    print("优化效果")
    print("-" * 60)
    
    saving_b = scratch_avg - session_avg
    saving_c = scratch_avg - clone_avg
    
    print(f"\n    clone_for_session 节省: {saving_b:.2f}ms ({saving_b/scratch_avg*100:.1f}%)")
    print(f"    clone 节省:             {saving_c:.2f}ms ({saving_c/scratch_avg*100:.1f}%)")
    
    print("\n" + "-" * 60)
    print("结论")
    print("-" * 60)
    
    if saving_c >= 30:
        print(f"\n    ✅ clone 模式有效，节省约 {saving_c:.0f}ms")
        if 40 <= saving_c <= 120:
            print(f"    📊 文档声称 50-100ms：基本符合")
        else:
            print(f"    📊 文档声称 50-100ms：数值{'偏低' if saving_c > 120 else '偏高'}")
    elif saving_c >= 5:
        print(f"\n    ⚠️ clone 模式略有效果，节省 {saving_c:.0f}ms")
        print(f"    📊 文档声称 50-100ms：夸大了")
    else:
        print(f"\n    ❌ clone 模式效果不明显（{saving_c:.2f}ms）")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(run_benchmark())

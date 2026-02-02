"""
端到端测试：部署态 vs 运行态 clone_for_session 验证

测试目标：
1. 验证部署态原型创建正确性
2. 验证运行态浅克隆性能和正确性
3. 验证单智能体和多智能体的一致性
4. 验证组件复用和状态重置

调用路径：
- 部署态: AgentRegistry.preload_all() → _create_agent_prototype()
- 运行态 (单): AgentRegistry.get_agent() → prototype.clone_for_session()
- 运行态 (多): ChatService._get_multi_agent_orchestrator() → prototype.clone_for_session()
"""

import asyncio
import time
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestResult:
    """测试结果收集器"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []
    
    def add(self, name: str, passed: bool, message: str = "", duration_ms: float = 0):
        status = "✅ PASS" if passed else "❌ FAIL"
        self.results.append({
            "name": name,
            "passed": passed,
            "message": message,
            "duration_ms": duration_ms,
        })
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        print(f"{status} | {name} | {message} | {duration_ms:.2f}ms")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"测试结果: {self.passed}/{total} 通过")
        if self.failed > 0:
            print("失败的测试:")
            for r in self.results:
                if not r["passed"]:
                    print(f"  - {r['name']}: {r['message']}")
        return self.failed == 0


async def test_simple_agent_clone():
    """测试 1: SimpleAgent.clone_for_session()"""
    results = TestResult()
    print("\n" + "="*60)
    print("测试 1: SimpleAgent.clone_for_session()")
    print("="*60)
    
    from core.agent.simple import SimpleAgent
    from core.events import create_event_manager, get_memory_storage
    from core.schemas import DEFAULT_AGENT_SCHEMA
    
    # 创建事件管理器
    storage = get_memory_storage()
    event_manager = create_event_manager(storage)
    
    # 1.1 创建原型
    start = time.perf_counter()
    prototype = SimpleAgent(
        model="claude-sonnet-4-5-20250929",
        max_turns=10,
        event_manager=event_manager,
        schema=DEFAULT_AGENT_SCHEMA,
    )
    prototype._is_prototype = True
    prototype_time = (time.perf_counter() - start) * 1000
    
    results.add(
        "1.1 原型创建",
        prototype is not None,
        f"SimpleAgent 原型",
        prototype_time
    )
    
    # 1.2 浅克隆
    start = time.perf_counter()
    clone = prototype.clone_for_session(
        event_manager=event_manager,
        workspace_dir="/tmp/test_workspace_1",
        conversation_service=None
    )
    clone_time = (time.perf_counter() - start) * 1000
    
    results.add(
        "1.2 浅克隆",
        clone is not None,
        f"clone_for_session()",
        clone_time
    )
    
    # 1.3 验证性能提升
    is_faster = clone_time < prototype_time * 0.5  # 克隆应该快于原型创建50%
    results.add(
        "1.3 性能提升",
        is_faster,
        f"克隆 {clone_time:.2f}ms vs 原型 {prototype_time:.2f}ms",
        0
    )
    
    # 1.4 验证组件复用（同一引用）
    same_llm = clone.llm is prototype.llm
    same_schema = clone.schema is prototype.schema
    same_capability_registry = clone.capability_registry is prototype.capability_registry
    
    results.add(
        "1.4 LLM 复用",
        same_llm,
        f"clone.llm is prototype.llm = {same_llm}",
        0
    )
    results.add(
        "1.5 Schema 复用",
        same_schema,
        f"clone.schema is prototype.schema = {same_schema}",
        0
    )
    results.add(
        "1.6 CapabilityRegistry 复用",
        same_capability_registry,
        f"clone.capability_registry is prototype.capability_registry = {same_capability_registry}",
        0
    )
    
    # 1.7 验证状态重置（新实例）
    different_workspace = clone.workspace_dir == "/tmp/test_workspace_1"
    results.add(
        "1.7 workspace_dir 绑定",
        different_workspace,
        f"clone.workspace_dir = {clone.workspace_dir}",
        0
    )
    
    # 1.8 多次克隆性能
    clone_times = []
    for i in range(5):
        start = time.perf_counter()
        c = prototype.clone_for_session(
            event_manager=event_manager,
            workspace_dir=f"/tmp/test_workspace_{i}",
            conversation_service=None
        )
        clone_times.append((time.perf_counter() - start) * 1000)
    
    avg_clone_time = sum(clone_times) / len(clone_times)
    results.add(
        "1.8 多次克隆平均",
        avg_clone_time < 10,  # 应该小于 10ms
        f"5次克隆平均 {avg_clone_time:.2f}ms",
        avg_clone_time
    )
    
    return results


async def test_multi_agent_clone():
    """测试 2: MultiAgentOrchestrator.clone_for_session()"""
    results = TestResult()
    print("\n" + "="*60)
    print("测试 2: MultiAgentOrchestrator.clone_for_session()")
    print("="*60)
    
    from core.agent.multi import MultiAgentOrchestrator
    from core.agent.multi.models import MultiAgentConfig
    
    # 2.1 创建原型
    start = time.perf_counter()
    config = MultiAgentConfig(
        config_id="test_config",
        name="Test Multi-Agent",
    )
    prototype = MultiAgentOrchestrator(
        config=config,
        enable_checkpoints=True,
        enable_lead_agent=True,
    )
    prototype._is_prototype = True
    prototype_time = (time.perf_counter() - start) * 1000
    
    results.add(
        "2.1 原型创建",
        prototype is not None,
        f"MultiAgentOrchestrator 原型",
        prototype_time
    )
    
    # 2.2 验证 LeadAgent 和 Critic
    has_lead_agent = prototype.lead_agent is not None
    results.add(
        "2.2 LeadAgent 存在",
        has_lead_agent,
        f"prototype.lead_agent = {type(prototype.lead_agent).__name__ if has_lead_agent else None}",
        0
    )
    
    # 2.3 浅克隆
    start = time.perf_counter()
    clone = prototype.clone_for_session(
        event_manager=None,
        workspace_dir="/tmp/multi_test_workspace_1",
        conversation_service=None
    )
    clone_time = (time.perf_counter() - start) * 1000
    
    results.add(
        "2.3 浅克隆",
        clone is not None,
        f"clone_for_session()",
        clone_time
    )
    
    # 2.4 验证性能提升
    is_faster = clone_time < prototype_time * 0.5
    results.add(
        "2.4 性能提升",
        is_faster or clone_time < 20,  # 克隆应该很快
        f"克隆 {clone_time:.2f}ms vs 原型 {prototype_time:.2f}ms",
        0
    )
    
    # 2.5 验证组件复用
    same_config = clone.config is prototype.config
    same_lead_agent = clone.lead_agent is prototype.lead_agent
    same_critic = clone.critic is prototype.critic
    same_worker_model = clone.worker_model == prototype.worker_model
    
    results.add(
        "2.5 Config 复用",
        same_config,
        f"clone.config is prototype.config = {same_config}",
        0
    )
    results.add(
        "2.6 LeadAgent 复用",
        same_lead_agent,
        f"clone.lead_agent is prototype.lead_agent = {same_lead_agent}",
        0
    )
    results.add(
        "2.7 Critic 复用",
        same_critic,
        f"clone.critic is prototype.critic = {same_critic}",
        0
    )
    results.add(
        "2.8 worker_model 复用",
        same_worker_model,
        f"clone.worker_model = {clone.worker_model}",
        0
    )
    
    # 2.9 验证状态重置
    different_workspace = clone.workspace_dir == "/tmp/multi_test_workspace_1"
    is_state_none = clone._state is None
    is_plan_none = clone.plan is None
    
    results.add(
        "2.9 workspace_dir 绑定",
        different_workspace,
        f"clone.workspace_dir = {clone.workspace_dir}",
        0
    )
    results.add(
        "2.10 _state 重置",
        is_state_none,
        f"clone._state = {clone._state}",
        0
    )
    results.add(
        "2.11 plan 重置",
        is_plan_none,
        f"clone.plan = {clone.plan}",
        0
    )
    
    # 2.12 验证 _is_prototype 标记
    is_not_prototype = not getattr(clone, '_is_prototype', True)
    results.add(
        "2.12 非原型标记",
        is_not_prototype,
        f"clone._is_prototype = {getattr(clone, '_is_prototype', 'N/A')}",
        0
    )
    
    # 2.13 多次克隆性能
    clone_times = []
    for i in range(5):
        start = time.perf_counter()
        c = prototype.clone_for_session(
            event_manager=None,
            workspace_dir=f"/tmp/multi_test_workspace_{i}",
            conversation_service=None
        )
        clone_times.append((time.perf_counter() - start) * 1000)
    
    avg_clone_time = sum(clone_times) / len(clone_times)
    results.add(
        "2.13 多次克隆平均",
        avg_clone_time < 20,  # 应该小于 20ms
        f"5次克隆平均 {avg_clone_time:.2f}ms",
        avg_clone_time
    )
    
    return results


async def test_agent_registry_flow():
    """测试 3: AgentRegistry 完整流程"""
    results = TestResult()
    print("\n" + "="*60)
    print("测试 3: AgentRegistry 完整流程")
    print("="*60)
    
    try:
        from services.agent_registry import AgentRegistry, get_agent_registry
        from core.events import create_event_manager, get_memory_storage
        
        # 创建事件管理器
        storage = get_memory_storage()
        event_manager = create_event_manager(storage)
        
        # 3.1 获取 Registry
        registry = get_agent_registry()
        results.add(
            "3.1 获取 Registry",
            registry is not None,
            f"AgentRegistry 实例",
            0
        )
        
        # 3.2 预加载（部署态）
        start = time.perf_counter()
        count = await registry.preload_all(force_refresh=False)
        preload_time = (time.perf_counter() - start) * 1000
        
        results.add(
            "3.2 预加载",
            count >= 0,
            f"加载 {count} 个实例",
            preload_time
        )
        
        # 3.3 检查原型缓存
        prototype_count = len(registry._agent_prototypes)
        results.add(
            "3.3 原型缓存",
            prototype_count >= 0,
            f"{prototype_count} 个原型",
            0
        )
        
        # 3.4 获取 Agent（运行态）- 测试浅克隆
        if count > 0:
            agents = registry.list_agents()
            if agents:
                test_agent_id = agents[0]["agent_id"]
                
                # 首次获取
                start = time.perf_counter()
                agent1 = await registry.get_agent(
                    agent_id=test_agent_id,
                    event_manager=event_manager,
                    workspace_dir="/tmp/test_run_1"
                )
                first_get_time = (time.perf_counter() - start) * 1000
                
                results.add(
                    "3.4 首次获取 Agent",
                    agent1 is not None,
                    f"agent_id={test_agent_id}",
                    first_get_time
                )
                
                # 二次获取（应该使用浅克隆）
                start = time.perf_counter()
                agent2 = await registry.get_agent(
                    agent_id=test_agent_id,
                    event_manager=event_manager,
                    workspace_dir="/tmp/test_run_2"
                )
                second_get_time = (time.perf_counter() - start) * 1000
                
                results.add(
                    "3.5 二次获取 Agent",
                    agent2 is not None,
                    f"浅克隆",
                    second_get_time
                )
                
                # 验证是不同实例
                is_different = agent1 is not agent2
                results.add(
                    "3.6 不同实例",
                    is_different,
                    f"agent1 is not agent2 = {is_different}",
                    0
                )
                
                # 验证 workspace_dir 不同
                different_workspace = agent1.workspace_dir != agent2.workspace_dir
                results.add(
                    "3.7 workspace_dir 隔离",
                    different_workspace,
                    f"{agent1.workspace_dir} vs {agent2.workspace_dir}",
                    0
                )
                
                # 验证 LLM 复用（同一引用）
                same_llm = agent1.llm is agent2.llm
                results.add(
                    "3.8 LLM 复用",
                    same_llm,
                    f"agent1.llm is agent2.llm = {same_llm}",
                    0
                )
        else:
            results.add(
                "3.4-3.8 跳过",
                True,
                "无可用实例",
                0
            )
        
    except Exception as e:
        results.add(
            "3.X 异常",
            False,
            f"错误: {str(e)}",
            0
        )
    
    return results


async def test_chat_service_multi_agent():
    """测试 4: ChatService 多智能体原型复用"""
    results = TestResult()
    print("\n" + "="*60)
    print("测试 4: ChatService 多智能体原型复用")
    print("="*60)
    
    try:
        from services.chat_service import ChatService
        
        # 4.1 创建 ChatService
        service = ChatService(enable_routing=True)
        
        results.add(
            "4.1 创建 ChatService",
            service is not None,
            "enable_routing=True",
            0
        )
        
        # 4.2 验证初始状态
        prototype_none = service._multi_agent_prototype is None
        results.add(
            "4.2 初始原型为 None",
            prototype_none,
            f"_multi_agent_prototype = {service._multi_agent_prototype}",
            0
        )
        
        # 4.3 首次获取（创建原型）
        start = time.perf_counter()
        orchestrator1 = service._get_multi_agent_orchestrator("/tmp/chat_test_1")
        first_time = (time.perf_counter() - start) * 1000
        
        results.add(
            "4.3 首次获取",
            orchestrator1 is not None,
            "创建原型 + 浅克隆",
            first_time
        )
        
        # 4.4 验证原型已创建
        prototype_exists = service._multi_agent_prototype is not None
        results.add(
            "4.4 原型已创建",
            prototype_exists,
            f"_multi_agent_prototype 类型: {type(service._multi_agent_prototype).__name__}",
            0
        )
        
        # 4.5 二次获取（纯浅克隆）
        start = time.perf_counter()
        orchestrator2 = service._get_multi_agent_orchestrator("/tmp/chat_test_2")
        second_time = (time.perf_counter() - start) * 1000
        
        results.add(
            "4.5 二次获取",
            orchestrator2 is not None,
            "纯浅克隆",
            second_time
        )
        
        # 4.6 性能对比
        is_faster = second_time < first_time * 0.5 or second_time < 20
        results.add(
            "4.6 性能提升",
            is_faster,
            f"二次 {second_time:.2f}ms vs 首次 {first_time:.2f}ms",
            0
        )
        
        # 4.7 验证是不同实例
        is_different = orchestrator1 is not orchestrator2
        results.add(
            "4.7 不同实例",
            is_different,
            f"orchestrator1 is not orchestrator2 = {is_different}",
            0
        )
        
        # 4.8 验证组件复用
        same_lead = orchestrator1.lead_agent is orchestrator2.lead_agent
        results.add(
            "4.8 LeadAgent 复用",
            same_lead,
            f"orchestrator1.lead_agent is orchestrator2.lead_agent = {same_lead}",
            0
        )
        
        # 4.9 验证 workspace 隔离
        different_workspace = orchestrator1.workspace_dir != orchestrator2.workspace_dir
        results.add(
            "4.9 workspace 隔离",
            different_workspace,
            f"{orchestrator1.workspace_dir} vs {orchestrator2.workspace_dir}",
            0
        )
        
        # 4.10 多次获取性能
        times = []
        for i in range(5):
            start = time.perf_counter()
            o = service._get_multi_agent_orchestrator(f"/tmp/chat_test_{i+3}")
            times.append((time.perf_counter() - start) * 1000)
        
        avg_time = sum(times) / len(times)
        results.add(
            "4.10 多次获取平均",
            avg_time < 20,
            f"5次平均 {avg_time:.2f}ms",
            avg_time
        )
        
    except Exception as e:
        import traceback
        results.add(
            "4.X 异常",
            False,
            f"错误: {str(e)}\n{traceback.format_exc()}",
            0
        )
    
    return results


async def test_performance_comparison():
    """测试 5: 性能对比总结"""
    results = TestResult()
    print("\n" + "="*60)
    print("测试 5: 性能对比总结")
    print("="*60)
    
    from core.agent.simple import SimpleAgent
    from core.agent.multi import MultiAgentOrchestrator
    from core.agent.multi.models import MultiAgentConfig
    from core.events import create_event_manager, get_memory_storage
    from core.schemas import DEFAULT_AGENT_SCHEMA
    
    storage = get_memory_storage()
    event_manager = create_event_manager(storage)
    
    # SimpleAgent 对比
    print("\n--- SimpleAgent ---")
    
    # 完整创建
    simple_create_times = []
    for _ in range(3):
        start = time.perf_counter()
        agent = SimpleAgent(
            model="claude-sonnet-4-5-20250929",
            max_turns=10,
            event_manager=event_manager,
            schema=DEFAULT_AGENT_SCHEMA,
        )
        simple_create_times.append((time.perf_counter() - start) * 1000)
    
    simple_avg_create = sum(simple_create_times) / len(simple_create_times)
    
    # 浅克隆
    prototype = SimpleAgent(
        model="claude-sonnet-4-5-20250929",
        max_turns=10,
        event_manager=event_manager,
        schema=DEFAULT_AGENT_SCHEMA,
    )
    prototype._is_prototype = True
    
    simple_clone_times = []
    for i in range(10):
        start = time.perf_counter()
        clone = prototype.clone_for_session(
            event_manager=event_manager,
            workspace_dir=f"/tmp/perf_{i}",
            conversation_service=None
        )
        simple_clone_times.append((time.perf_counter() - start) * 1000)
    
    simple_avg_clone = sum(simple_clone_times) / len(simple_clone_times)
    simple_improvement = ((simple_avg_create - simple_avg_clone) / simple_avg_create) * 100
    
    results.add(
        "5.1 SimpleAgent 完整创建",
        True,
        f"平均 {simple_avg_create:.2f}ms",
        simple_avg_create
    )
    results.add(
        "5.2 SimpleAgent 浅克隆",
        simple_avg_clone < simple_avg_create,
        f"平均 {simple_avg_clone:.2f}ms",
        simple_avg_clone
    )
    results.add(
        "5.3 SimpleAgent 提升",
        simple_improvement > 50,
        f"{simple_improvement:.1f}% 性能提升",
        0
    )
    
    # MultiAgent 对比
    print("\n--- MultiAgentOrchestrator ---")
    
    config = MultiAgentConfig(config_id="perf_test", name="Perf Test")
    
    multi_create_times = []
    for _ in range(3):
        start = time.perf_counter()
        orchestrator = MultiAgentOrchestrator(
            config=config,
            enable_checkpoints=True,
            enable_lead_agent=True,
        )
        multi_create_times.append((time.perf_counter() - start) * 1000)
    
    multi_avg_create = sum(multi_create_times) / len(multi_create_times)
    
    multi_prototype = MultiAgentOrchestrator(
        config=config,
        enable_checkpoints=True,
        enable_lead_agent=True,
    )
    multi_prototype._is_prototype = True
    
    multi_clone_times = []
    for i in range(10):
        start = time.perf_counter()
        clone = multi_prototype.clone_for_session(
            event_manager=None,
            workspace_dir=f"/tmp/multi_perf_{i}",
            conversation_service=None
        )
        multi_clone_times.append((time.perf_counter() - start) * 1000)
    
    multi_avg_clone = sum(multi_clone_times) / len(multi_clone_times)
    multi_improvement = ((multi_avg_create - multi_avg_clone) / multi_avg_create) * 100 if multi_avg_create > 0 else 0
    
    results.add(
        "5.4 MultiAgent 完整创建",
        True,
        f"平均 {multi_avg_create:.2f}ms",
        multi_avg_create
    )
    results.add(
        "5.5 MultiAgent 浅克隆",
        multi_avg_clone < multi_avg_create or multi_avg_clone < 20,
        f"平均 {multi_avg_clone:.2f}ms",
        multi_avg_clone
    )
    results.add(
        "5.6 MultiAgent 提升",
        multi_improvement > 30 or multi_avg_clone < 10,
        f"{multi_improvement:.1f}% 性能提升",
        0
    )
    
    # 总结
    print("\n--- 性能总结 ---")
    print(f"SimpleAgent:  创建 {simple_avg_create:.2f}ms → 克隆 {simple_avg_clone:.2f}ms ({simple_improvement:.1f}% ↑)")
    print(f"MultiAgent:   创建 {multi_avg_create:.2f}ms → 克隆 {multi_avg_clone:.2f}ms ({multi_improvement:.1f}% ↑)")
    
    return results


async def main():
    """运行所有测试"""
    print("="*60)
    print("端到端测试: clone_for_session 验证")
    print("="*60)
    
    all_results = []
    
    # 测试 1: SimpleAgent
    r1 = await test_simple_agent_clone()
    all_results.append(r1)
    
    # 测试 2: MultiAgentOrchestrator
    r2 = await test_multi_agent_clone()
    all_results.append(r2)
    
    # 测试 3: AgentRegistry
    r3 = await test_agent_registry_flow()
    all_results.append(r3)
    
    # 测试 4: ChatService
    r4 = await test_chat_service_multi_agent()
    all_results.append(r4)
    
    # 测试 5: 性能对比
    r5 = await test_performance_comparison()
    all_results.append(r5)
    
    # 总结
    print("\n" + "="*60)
    print("总体测试结果")
    print("="*60)
    
    total_passed = sum(r.passed for r in all_results)
    total_failed = sum(r.failed for r in all_results)
    total = total_passed + total_failed
    
    print(f"总计: {total_passed}/{total} 通过, {total_failed} 失败")
    
    if total_failed > 0:
        print("\n失败的测试:")
        for r in all_results:
            for item in r.results:
                if not item["passed"]:
                    print(f"  ❌ {item['name']}: {item['message']}")
    
    return total_failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)

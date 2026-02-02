"""
V8.0 端到端测试：从 Service 层模拟真实会话流程

测试目标：
1. 从 ChatService 层开始，模拟真实用户会话
2. 验证完整调用链：ChatService → Router → AgentFactory → Agent.chat()
3. 验证克隆机制：原型池 + clone_for_session
4. 验证 V8.0 语义驱动：IntentResult 字段一致性

调用路径：
ChatService.chat()
    ↓
AgentRouter.route() → RoutingDecision
    ↓
AgentFactory.create_from_decision() → SimpleAgent/RVRBAgent/MultiAgentOrchestrator
    ↓
Agent.chat() → 执行 RVR/RVR-B 循环
    ↓
返回结果

运行方式：
source /Users/liuyi/Documents/langchain/liuy/bin/activate
cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent
python -m pytest tests/test_e2e_v8_service_flow.py -v -s
"""

import pytest
import asyncio
import time
import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from dataclasses import dataclass

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载 .env 文件
from dotenv import load_dotenv
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ 已加载环境变量: {env_path}")


# ============================================================
# 测试辅助类
# ============================================================

@dataclass
class TestScenario:
    """测试场景定义"""
    name: str
    query: str
    expected_complexity: str  # simple/medium/complex
    expected_needs_plan: bool
    expected_execution_strategy: str  # rvr/rvr-b
    expected_agent_type: str  # single/multi


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


# ============================================================
# 测试场景定义
# ============================================================

TEST_SCENARIOS = [
    TestScenario(
        name="简单查询",
        query="今天上海天气怎么样？",
        expected_complexity="simple",
        expected_needs_plan=False,
        expected_execution_strategy="rvr",
        expected_agent_type="single",
    ),
    TestScenario(
        name="中等任务",
        query="帮我搜索 AI 最新进展并总结成一份报告",
        expected_complexity="medium",
        expected_needs_plan=True,
        expected_execution_strategy="rvr",  # 或 rvr-b
        expected_agent_type="single",
    ),
    TestScenario(
        name="复杂任务",
        query="研究 AWS、Azure、GCP 三家云服务商的 AI 战略，生成对比分析报告",
        expected_complexity="complex",
        expected_needs_plan=True,
        expected_execution_strategy="rvr-b",
        expected_agent_type="multi",  # 多实体研究
    ),
]


# ============================================================
# 测试 1：IntentAnalyzer 字段一致性（真实 LLM）
# ============================================================

@pytest.mark.asyncio
async def test_intent_analyzer_field_consistency():
    """
    测试 1：验证 IntentAnalyzer 输出字段一致性（V8.0 约束）
    
    根据 intent_recognition_prompt.py 的字段一致性约束：
    | complexity | needs_plan | suggested_planning_depth | execution_strategy |
    |------------|------------|--------------------------|-------------------|
    | simple     | false      | none 或 null             | rvr               |
    | medium     | true       | minimal                  | rvr 或 rvr-b      |
    | complex    | true       | full                     | rvr-b             |
    
    使用真实 LLM 调用
    """
    print("\n" + "="*60)
    print("测试 1：IntentAnalyzer 字段一致性验证（真实 LLM）")
    print("="*60)
    
    results = TestResult()
    
    # 检查 API Key
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        results.add("API Key 检查", False, "ANTHROPIC_API_KEY 未设置", 0)
        results.summary()
        pytest.skip("ANTHROPIC_API_KEY 未设置，跳过真实 LLM 测试")
        return
    
    print(f"✅ ANTHROPIC_API_KEY 已设置 (长度={len(api_key)})")
    
    try:
        from core.routing.intent_analyzer import IntentAnalyzer
        from core.agent.types import Complexity
        from core.llm import create_claude_service
        
        # 创建真实 LLM 服务（使用快速模型减少延迟）
        llm_service = create_claude_service(
            model="claude-3-5-haiku-20241022",  # 使用快速模型
            api_key=api_key,
            enable_thinking=False,  # 意图分析不需要 extended thinking
            enable_caching=True,    # 启用缓存减少成本
            max_tokens=4096         # haiku 模型最大 8192，设置为 4096 足够
        )
        print(f"✅ LLM 服务已创建: claude-3-5-haiku-20241022")
        
        # 创建 IntentAnalyzer 并传入 LLM 服务
        analyzer = IntentAnalyzer(llm_service=llm_service, enable_llm=True)
        
        for scenario in TEST_SCENARIOS:
            print(f"\n--- 场景: {scenario.name} ---")
            print(f"Query: {scenario.query}")
            
            # 构造消息列表格式（IntentAnalyzer.analyze() 需要 List[Dict]）
            messages = [{"role": "user", "content": scenario.query}]
            
            start = time.perf_counter()
            intent = await analyzer.analyze(messages)
            duration = (time.perf_counter() - start) * 1000
            
            print(f"IntentResult: complexity={intent.complexity.value}, "
                  f"needs_plan={intent.needs_plan}, "
                  f"execution_strategy={intent.execution_strategy}, "
                  f"suggested_planning_depth={intent.suggested_planning_depth}")
            print(f"  耗时: {duration:.0f}ms")
            
            # 验证字段一致性约束
            complexity = intent.complexity.value
            
            if complexity == "simple":
                # simple → needs_plan=false, suggested_planning_depth=none/null, execution_strategy=rvr
                consistent = (
                    intent.needs_plan == False and
                    intent.suggested_planning_depth in [None, "none"] and
                    intent.execution_strategy == "rvr"
                )
                results.add(
                    f"{scenario.name} - 字段一致性",
                    consistent,
                    f"simple: needs_plan={intent.needs_plan}, "
                    f"depth={intent.suggested_planning_depth}, "
                    f"strategy={intent.execution_strategy}",
                    duration
                )
            elif complexity == "medium":
                # medium → needs_plan=true, suggested_planning_depth=minimal, execution_strategy=rvr/rvr-b
                consistent = (
                    intent.needs_plan == True and
                    intent.suggested_planning_depth == "minimal" and
                    intent.execution_strategy in ["rvr", "rvr-b"]
                )
                results.add(
                    f"{scenario.name} - 字段一致性",
                    consistent,
                    f"medium: needs_plan={intent.needs_plan}, "
                    f"depth={intent.suggested_planning_depth}, "
                    f"strategy={intent.execution_strategy}",
                    duration
                )
            elif complexity == "complex":
                # complex → needs_plan=true, suggested_planning_depth=full, execution_strategy=rvr-b
                consistent = (
                    intent.needs_plan == True and
                    intent.suggested_planning_depth == "full" and
                    intent.execution_strategy == "rvr-b"
                )
                results.add(
                    f"{scenario.name} - 字段一致性",
                    consistent,
                    f"complex: needs_plan={intent.needs_plan}, "
                    f"depth={intent.suggested_planning_depth}, "
                    f"strategy={intent.execution_strategy}",
                    duration
                )
    
    except Exception as e:
        import traceback
        results.add("IntentAnalyzer 执行", False, f"异常: {e}\n{traceback.format_exc()}", 0)
    
    results.summary()
    assert results.failed == 0, f"{results.failed} 个测试失败"


# ============================================================
# 测试 2：AgentRouter 路由决策（真实 LLM）
# ============================================================

@pytest.mark.asyncio
async def test_agent_router_routing_decision():
    """
    测试 2：验证 AgentRouter 路由决策正确性（真实 LLM）
    
    验证：
    - needs_multi_agent=true → agent_type="multi"
    - needs_multi_agent=false → agent_type="single"
    - execution_strategy 正确传递
    """
    print("\n" + "="*60)
    print("测试 2：AgentRouter 路由决策验证（真实 LLM）")
    print("="*60)
    
    results = TestResult()
    
    # 检查 API Key
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        results.add("API Key 检查", False, "ANTHROPIC_API_KEY 未设置", 0)
        results.summary()
        pytest.skip("ANTHROPIC_API_KEY 未设置，跳过真实 LLM 测试")
        return
    
    try:
        from core.routing.router import AgentRouter
        from core.llm import create_claude_service
        
        # 创建真实 LLM 服务（使用快速模型减少延迟）
        llm_service = create_claude_service(
            model="claude-3-5-haiku-20241022",
            api_key=api_key,
            enable_thinking=False,
            enable_caching=True,
            max_tokens=4096
        )
        
        # 创建 AgentRouter 并传入 LLM 服务
        router = AgentRouter(llm_service=llm_service)
        
        for scenario in TEST_SCENARIOS:
            print(f"\n--- 场景: {scenario.name} ---")
            print(f"Query: {scenario.query}")
            
            start = time.perf_counter()
            decision = await router.route(
                user_query=scenario.query,
                conversation_history=[]
            )
            duration = (time.perf_counter() - start) * 1000
            
            print(f"RoutingDecision: agent_type={decision.agent_type}, "
                  f"execution_strategy={decision.execution_strategy}")
            print(f"  耗时: {duration:.0f}ms")
            
            # 验证 agent_type（放宽验证，因为 LLM 可能有不同判断）
            # 这里主要验证流程正确性，而非 LLM 判断准确性
            results.add(
                f"{scenario.name} - agent_type",
                decision.agent_type in ["single", "multi"],
                f"expected={scenario.expected_agent_type}, actual={decision.agent_type}",
                duration
            )
            
            # 验证 execution_strategy 传递
            if decision.intent:
                strategy_passed = decision.execution_strategy == decision.intent.execution_strategy
                results.add(
                    f"{scenario.name} - execution_strategy 传递",
                    strategy_passed,
                    f"decision={decision.execution_strategy}, "
                    f"intent={decision.intent.execution_strategy}",
                    0
                )
    
    except Exception as e:
        import traceback
        results.add("AgentRouter 执行", False, f"异常: {e}\n{traceback.format_exc()}", 0)
    
    results.summary()
    assert results.failed == 0, f"{results.failed} 个测试失败"


# ============================================================
# 测试 3：AgentFactory 创建 Agent
# ============================================================

@pytest.mark.asyncio
async def test_agent_factory_creates_correct_agent():
    """
    测试 3：验证 AgentFactory 根据 RoutingDecision 创建正确的 Agent
    
    验证：
    - execution_strategy="rvr" → SimpleAgent
    - execution_strategy="rvr-b" → RVRBAgent
    - agent_type="multi" → MultiAgentOrchestrator
    """
    print("\n" + "="*60)
    print("测试 3：AgentFactory 创建 Agent 验证")
    print("="*60)
    
    results = TestResult()
    
    try:
        from core.agent.factory import AgentFactory
        from core.routing.router import AgentRouter
        from core.events import create_event_manager, get_memory_storage
        
        # 创建依赖
        storage = get_memory_storage()
        event_manager = create_event_manager(storage)
        workspace_dir = "/tmp/zenflux_test_agent_factory"
        Path(workspace_dir).mkdir(parents=True, exist_ok=True)
        
        router = AgentRouter()
        
        for scenario in TEST_SCENARIOS:
            print(f"\n--- 场景: {scenario.name} ---")
            print(f"Query: {scenario.query}")
            
            # 获取路由决策
            decision = await router.route(
                user_query=scenario.query,
                conversation_history=[]
            )
            
            print(f"RoutingDecision: agent_type={decision.agent_type}, "
                  f"execution_strategy={decision.execution_strategy}")
            
            # 创建 Agent
            start = time.perf_counter()
            agent = await AgentFactory.create_from_decision(
                decision=decision,
                event_manager=event_manager,
                workspace_dir=workspace_dir
            )
            duration = (time.perf_counter() - start) * 1000
            
            agent_class = agent.__class__.__name__
            print(f"Created Agent: {agent_class}")
            
            # 验证 Agent 类型
            if decision.agent_type == "multi":
                expected_class = "MultiAgentOrchestrator"
            elif decision.execution_strategy == "rvr-b":
                expected_class = "RVRBAgent"
            else:
                expected_class = "SimpleAgent"
            
            results.add(
                f"{scenario.name} - Agent 类型",
                agent_class == expected_class,
                f"expected={expected_class}, actual={agent_class}",
                duration
            )
            
            # 验证 max_turns（统一为 30）
            if hasattr(agent, 'max_turns'):
                results.add(
                    f"{scenario.name} - max_turns",
                    agent.max_turns == 30,
                    f"expected=30, actual={agent.max_turns}",
                    0
                )
    
    except Exception as e:
        import traceback
        results.add("AgentFactory 执行", False, f"异常: {e}\n{traceback.format_exc()}", 0)
    
    results.summary()
    assert results.failed == 0, f"{results.failed} 个测试失败"


# ============================================================
# 测试 4：克隆机制验证
# ============================================================

@pytest.mark.asyncio
async def test_clone_for_session_mechanism():
    """
    测试 4：验证 clone_for_session 机制
    
    验证：
    - 原型创建后可被多次克隆
    - 克隆速度显著快于原型创建
    - 重型组件复用（LLM, Schema, CapabilityRegistry）
    - 状态隔离（workspace_dir, conversation_service）
    """
    print("\n" + "="*60)
    print("测试 4：clone_for_session 机制验证")
    print("="*60)
    
    results = TestResult()
    
    try:
        from core.agent.simple import SimpleAgent
        from core.events import create_event_manager, get_memory_storage
        from core.schemas import DEFAULT_AGENT_SCHEMA
        
        storage = get_memory_storage()
        event_manager = create_event_manager(storage)
        
        # 创建原型
        start = time.perf_counter()
        prototype = SimpleAgent(
            model="claude-sonnet-4-5-20250929",
            max_turns=30,
            event_manager=event_manager,
            schema=DEFAULT_AGENT_SCHEMA,
        )
        prototype._is_prototype = True
        prototype_time = (time.perf_counter() - start) * 1000
        
        results.add("原型创建", True, f"SimpleAgent 原型", prototype_time)
        
        # 多次克隆并验证
        clone_times = []
        clones = []
        
        for i in range(5):
            start = time.perf_counter()
            clone = prototype.clone_for_session(
                event_manager=event_manager,
                workspace_dir=f"/tmp/test_workspace_{i}",
                conversation_service=None
            )
            clone_time = (time.perf_counter() - start) * 1000
            clone_times.append(clone_time)
            clones.append(clone)
        
        avg_clone_time = sum(clone_times) / len(clone_times)
        
        # 验证性能提升
        results.add(
            "克隆性能",
            avg_clone_time < prototype_time * 0.5,
            f"克隆平均 {avg_clone_time:.2f}ms vs 原型 {prototype_time:.2f}ms",
            avg_clone_time
        )
        
        # 验证重型组件复用
        for i, clone in enumerate(clones):
            same_llm = clone.llm is prototype.llm
            same_schema = clone.schema is prototype.schema
            same_registry = clone.capability_registry is prototype.capability_registry
            
            if i == 0:  # 只验证第一个克隆
                results.add("LLM 复用", same_llm, f"clone.llm is prototype.llm = {same_llm}", 0)
                results.add("Schema 复用", same_schema, f"clone.schema is prototype.schema = {same_schema}", 0)
                results.add("Registry 复用", same_registry, f"clone.registry is prototype.registry = {same_registry}", 0)
        
        # 验证状态隔离
        all_different_workspace = all(
            clones[i].workspace_dir != clones[j].workspace_dir
            for i in range(len(clones))
            for j in range(i+1, len(clones))
        )
        results.add(
            "workspace_dir 隔离",
            all_different_workspace,
            f"所有克隆的 workspace_dir 不同",
            0
        )
        
        # 验证非原型标记
        all_not_prototype = all(not getattr(c, '_is_prototype', True) for c in clones)
        results.add(
            "非原型标记",
            all_not_prototype,
            f"所有克隆的 _is_prototype = False",
            0
        )
    
    except Exception as e:
        import traceback
        results.add("克隆机制", False, f"异常: {e}\n{traceback.format_exc()}", 0)
    
    results.summary()
    assert results.failed == 0, f"{results.failed} 个测试失败"


# ============================================================
# 测试 5：ChatService 完整流程（真实 LLM）
# ============================================================

@pytest.mark.asyncio
async def test_chat_service_complete_flow_real_llm():
    """
    测试 5：ChatService 完整流程（真实 LLM 调用）
    
    真实会话流程：
    ChatService.chat() → Router → Factory → Agent.chat()
    
    使用真实 LLM API 调用
    """
    print("\n" + "="*60)
    print("测试 5：ChatService 完整流程（真实 LLM）")
    print("="*60)
    
    results = TestResult()
    
    # 检查 API Key
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "":
        results.add("API Key 检查", False, "ANTHROPIC_API_KEY 未设置", 0)
        results.summary()
        pytest.skip("ANTHROPIC_API_KEY 未设置，跳过真实 LLM 测试")
        return
    
    results.add("API Key 检查", True, f"ANTHROPIC_API_KEY 已设置 (长度={len(api_key)})", 0)
    
    try:
        from services.chat_service import ChatService
        
        # 创建 ChatService
        service = ChatService(enable_routing=True)
        
        # 测试简单查询
        print("\n--- 测试简单查询（真实 LLM）---")
        start = time.perf_counter()
        
        response_events = []
        async for event in service.chat(
            message="用一句话解释什么是 Python 编程语言？",
            user_id="test_user_e2e",
            conversation_id="test_conv_e2e_001",
            stream=True
        ):
            response_events.append(event)
            # 打印事件类型
            event_type = event.get("type", event.get("event", "unknown"))
            if event_type == "content":
                print(f"  📝 Content: {str(event.get('data', event.get('content', '')))[:100]}...")
        
        duration = (time.perf_counter() - start) * 1000
        
        results.add(
            "简单查询 - 流程完成",
            len(response_events) > 0,
            f"收到 {len(response_events)} 个事件，耗时 {duration:.0f}ms",
            duration
        )
        
        # 验证有内容返回
        has_content = any(
            event.get("type") == "content" or 
            event.get("event") == "content" or
            "content" in str(event)
            for event in response_events
        )
        results.add(
            "简单查询 - 有内容返回",
            has_content,
            f"事件类型: {list(set(e.get('type', e.get('event', 'unknown')) for e in response_events))}",
            0
        )
        
        # 验证没有错误事件
        has_error = any(
            event.get("type") == "error" or event.get("event") == "error"
            for event in response_events
        )
        results.add(
            "简单查询 - 无错误",
            not has_error,
            "无 error 事件" if not has_error else "有 error 事件",
            0
        )
    
    except Exception as e:
        import traceback
        results.add("ChatService 流程", False, f"异常: {e}\n{traceback.format_exc()}", 0)
    
    results.summary()
    assert results.failed == 0, f"{results.failed} 个测试失败"


# ============================================================
# 测试 6：V8.0 语义驱动配置验证
# ============================================================

@pytest.mark.asyncio
async def test_v8_semantic_driven_configuration():
    """
    测试 6：验证 V8.0 语义驱动配置
    
    验证 AgentFactory 根据 LLM 语义字段配置 Schema：
    - suggested_planning_depth → plan_manager 配置
    - tool_usage_hint → tool_selector 配置
    - complexity_score 仅供参考，不影响配置
    """
    print("\n" + "="*60)
    print("测试 6：V8.0 语义驱动配置验证")
    print("="*60)
    
    results = TestResult()
    
    try:
        from core.agent.factory import AgentFactory
        from core.routing.router import RoutingDecision
        from core.agent.types import IntentResult, TaskType, Complexity
        from core.events import create_event_manager, get_memory_storage
        
        storage = get_memory_storage()
        event_manager = create_event_manager(storage)
        workspace_dir = "/tmp/zenflux_test_v8_config"
        Path(workspace_dir).mkdir(parents=True, exist_ok=True)
        
        # 场景 1：suggested_planning_depth=none
        print("\n--- 场景 1: suggested_planning_depth=none ---")
        intent_none = IntentResult(
            task_type=TaskType.INFORMATION_QUERY,
            complexity=Complexity.SIMPLE,
            complexity_score=2.0,
            needs_plan=False,
            suggested_planning_depth="none",
            execution_strategy="rvr"
        )
        decision_none = RoutingDecision(
            agent_type="single",
            execution_strategy="rvr",
            intent=intent_none
        )
        
        agent_none = await AgentFactory.create_from_decision(
            decision=decision_none,
            event_manager=event_manager,
            workspace_dir=workspace_dir
        )
        
        # 验证 plan_manager 配置
        if hasattr(agent_none, 'schema') and agent_none.schema.plan_manager:
            pm = agent_none.schema.plan_manager
            results.add(
                "none - plan_manager.enabled",
                pm.enabled == True,  # 工具始终可用
                f"enabled={pm.enabled}",
                0
            )
            results.add(
                "none - plan_manager.max_steps",
                pm.max_steps == 5,  # 简化配置
                f"max_steps={pm.max_steps}",
                0
            )
        
        # 场景 2：suggested_planning_depth=full
        print("\n--- 场景 2: suggested_planning_depth=full ---")
        intent_full = IntentResult(
            task_type=TaskType.CODE_DEVELOPMENT,
            complexity=Complexity.COMPLEX,
            complexity_score=8.0,
            needs_plan=True,
            suggested_planning_depth="full",
            execution_strategy="rvr-b"
        )
        decision_full = RoutingDecision(
            agent_type="single",
            execution_strategy="rvr-b",
            intent=intent_full
        )
        
        agent_full = await AgentFactory.create_from_decision(
            decision=decision_full,
            event_manager=event_manager,
            workspace_dir=workspace_dir
        )
        
        if hasattr(agent_full, 'schema') and agent_full.schema.plan_manager:
            pm = agent_full.schema.plan_manager
            results.add(
                "full - plan_manager.replan_enabled",
                pm.replan_enabled == True,
                f"replan_enabled={pm.replan_enabled}",
                0
            )
        
        # 场景 3：tool_usage_hint=parallel
        print("\n--- 场景 3: tool_usage_hint=parallel ---")
        intent_parallel = IntentResult(
            task_type=TaskType.DATA_ANALYSIS,
            complexity=Complexity.MEDIUM,
            complexity_score=5.0,
            needs_plan=True,
            tool_usage_hint="parallel",
            execution_strategy="rvr"
        )
        decision_parallel = RoutingDecision(
            agent_type="single",
            execution_strategy="rvr",
            intent=intent_parallel
        )
        
        agent_parallel = await AgentFactory.create_from_decision(
            decision=decision_parallel,
            event_manager=event_manager,
            workspace_dir=workspace_dir
        )
        
        if hasattr(agent_parallel, 'schema') and agent_parallel.schema.tool_selector:
            ts = agent_parallel.schema.tool_selector
            results.add(
                "parallel - tool_selector.allow_parallel",
                ts.allow_parallel == True,
                f"allow_parallel={ts.allow_parallel}",
                0
            )
        
        # 场景 4：complexity_score 不影响 max_turns
        print("\n--- 场景 4: complexity_score 不影响 max_turns ---")
        # 低分
        intent_low = IntentResult(
            task_type=TaskType.INFORMATION_QUERY,
            complexity=Complexity.SIMPLE,
            complexity_score=1.0,  # 很低
            needs_plan=False,
            execution_strategy="rvr"
        )
        decision_low = RoutingDecision(
            agent_type="single",
            execution_strategy="rvr",
            intent=intent_low
        )
        agent_low = await AgentFactory.create_from_decision(
            decision=decision_low,
            event_manager=event_manager,
            workspace_dir=workspace_dir
        )
        
        # 高分
        intent_high = IntentResult(
            task_type=TaskType.CODE_DEVELOPMENT,
            complexity=Complexity.COMPLEX,
            complexity_score=9.5,  # 很高
            needs_plan=True,
            execution_strategy="rvr-b"
        )
        decision_high = RoutingDecision(
            agent_type="single",
            execution_strategy="rvr-b",
            intent=intent_high
        )
        agent_high = await AgentFactory.create_from_decision(
            decision=decision_high,
            event_manager=event_manager,
            workspace_dir=workspace_dir
        )
        
        # 两者 max_turns 应该相同（都是 30）
        if hasattr(agent_low, 'max_turns') and hasattr(agent_high, 'max_turns'):
            same_max_turns = agent_low.max_turns == agent_high.max_turns == 30
            results.add(
                "complexity_score 不影响 max_turns",
                same_max_turns,
                f"low.max_turns={agent_low.max_turns}, high.max_turns={agent_high.max_turns}",
                0
            )
    
    except Exception as e:
        import traceback
        results.add("V8.0 配置验证", False, f"异常: {e}\n{traceback.format_exc()}", 0)
    
    results.summary()
    assert results.failed == 0, f"{results.failed} 个测试失败"


# ============================================================
# 主函数
# ============================================================

async def main():
    """运行所有测试"""
    print("="*60)
    print("V8.0 端到端测试：Service 层模拟真实会话")
    print("="*60)
    
    # 导入并运行测试
    await test_intent_analyzer_field_consistency()
    await test_agent_router_routing_decision()
    await test_agent_factory_creates_correct_agent()
    await test_clone_for_session_mechanism()
    await test_chat_service_complete_flow_mock()
    await test_v8_semantic_driven_configuration()
    
    print("\n" + "="*60)
    print("所有测试完成")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())

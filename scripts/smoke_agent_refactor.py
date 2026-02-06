#!/usr/bin/env python3
"""
Agent 重构集成测试脚本

测试项目：
1. 模块导入
2. Executor 注册表
3. Factory 创建 Agent
4. Agent 基本属性
5. 多智能体组件导入

使用方式：
    python scripts/smoke_agent_refactor.py
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置必需的环境变量（如果未配置）
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/test"
if "ANTHROPIC_API_KEY" not in os.environ:
    os.environ["ANTHROPIC_API_KEY"] = "test-key-for-import-only"


def test_module_imports():
    """测试模块导入"""
    print("\n=== 测试 1: 模块导入 ===")
    
    # 核心模块
    from core.agent import Agent, AgentState
    print(f"  ✅ Agent: {Agent}")
    print(f"  ✅ AgentState: {AgentState}")
    
    # 统一 Agent 类（已移除废弃别名）
    print(f"  ✅ Agent: {Agent} (统一实现类)")
    
    # 多智能体
    from core.agent import MultiAgentOrchestrator
    print(f"  ✅ MultiAgentOrchestrator: {MultiAgentOrchestrator}")
    
    # Factory
    from core.agent import AgentFactory, get_available_strategies
    print(f"  ✅ AgentFactory: {AgentFactory}")
    print(f"  ✅ get_available_strategies: {get_available_strategies}")
    
    # Models
    from core.agent import ExecutionMode, AgentConfig, MultiAgentConfig
    print(f"  ✅ ExecutionMode: {ExecutionMode}")
    print(f"  ✅ AgentConfig: {AgentConfig}")
    print(f"  ✅ MultiAgentConfig: {MultiAgentConfig}")
    
    print("  ✅ 模块导入测试通过")


def test_executor_registry():
    """测试 Executor 注册表"""
    print("\n=== 测试 2: Executor 注册表 ===")
    
    from core.agent import get_available_strategies
    from core.agent.factory import _get_executor_registry
    
    strategies = get_available_strategies()
    print(f"  可用策略: {strategies}")
    
    registry = _get_executor_registry()
    print(f"  注册表: {list(registry.keys())}")
    
    # 验证必需的策略
    required = ["rvr", "rvr-b", "sequential", "parallel", "hierarchical"]
    for s in required:
        if s in registry:
            print(f"    ✅ {s}: {registry[s].__name__}")
        else:
            print(f"    ❌ {s}: 缺失")
    
    print("  ✅ Executor 注册表测试通过")


def test_execution_module():
    """测试 execution 模块"""
    print("\n=== 测试 3: execution 模块 ===")
    
    from core.agent.execution import (
        ExecutorProtocol,
        ExecutorConfig,
        ExecutionContext,
        RVRExecutor,
        RVRBExecutor,
        MultiAgentExecutor,
        SequentialMultiExecutor,
        ParallelMultiExecutor,
        HierarchicalMultiExecutor,
    )
    
    print(f"  ✅ ExecutorProtocol: {ExecutorProtocol}")
    print(f"  ✅ ExecutorConfig: {ExecutorConfig}")
    print(f"  ✅ ExecutionContext: {ExecutionContext}")
    
    # 单智能体 Executor
    rvr = RVRExecutor()
    print(f"  ✅ RVRExecutor: name={rvr.name}, backtrack={rvr.supports_backtrack()}")
    
    rvrb = RVRBExecutor()
    print(f"  ✅ RVRBExecutor: name={rvrb.name}, backtrack={rvrb.supports_backtrack()}")
    
    # 多智能体 Executor
    seq = SequentialMultiExecutor()
    print(f"  ✅ SequentialMultiExecutor: name={seq.name}")
    
    par = ParallelMultiExecutor()
    print(f"  ✅ ParallelMultiExecutor: name={par.name}")
    
    hier = HierarchicalMultiExecutor()
    print(f"  ✅ HierarchicalMultiExecutor: name={hier.name}")
    
    print("  ✅ execution 模块测试通过")


def test_components_module():
    """测试 components 模块"""
    print("\n=== 测试 4: components 模块 ===")
    
    from core.agent.components import (
        Checkpoint,
        CheckpointManager,
        LeadAgent,
        SubTask,
        TaskDecompositionPlan,
        CriticAgent,
    )
    
    print(f"  ✅ Checkpoint: {Checkpoint}")
    print(f"  ✅ CheckpointManager: {CheckpointManager}")
    print(f"  ✅ LeadAgent: {LeadAgent}")
    print(f"  ✅ SubTask: {SubTask}")
    print(f"  ✅ TaskDecompositionPlan: {TaskDecompositionPlan}")
    print(f"  ✅ CriticAgent: {CriticAgent}")
    
    print("  ✅ components 模块测试通过")


def test_models_module():
    """测试 models 模块"""
    print("\n=== 测试 5: models 模块 ===")
    
    from core.agent.models import (
        ExecutionMode,
        AgentRole,
        AgentConfig,
        MultiAgentConfig,
        OrchestratorConfig,
        WorkerConfig,
        CriticConfig,
        TaskAssignment,
        AgentResult,
        SubagentResult,
        OrchestratorState,
        CriticAction,
        CriticConfidence,
        CriticResult,
    )
    
    print(f"  ✅ ExecutionMode: {list(ExecutionMode)}")
    print(f"  ✅ AgentRole: {list(AgentRole)}")
    print(f"  ✅ CriticAction: {list(CriticAction)}")
    print(f"  ✅ CriticConfidence: {list(CriticConfidence)}")
    
    # 创建示例配置
    config = AgentConfig(
        agent_id="test_agent",
        role=AgentRole.EXECUTOR,
        model="claude-sonnet-4-5-20250929",
    )
    print(f"  ✅ AgentConfig 创建成功: {config.agent_id}")
    
    multi_config = MultiAgentConfig(
        config_id="test_config",
        mode=ExecutionMode.SEQUENTIAL,
    )
    print(f"  ✅ MultiAgentConfig 创建成功: {multi_config.config_id}")
    
    print("  ✅ models 模块测试通过")


def test_errors_module():
    """测试 errors 模块"""
    print("\n=== 测试 6: errors 模块 ===")
    
    from core.agent.errors import (
        ErrorType,
        ErrorClassification,
        ErrorClassifier,
        create_error_tool_result,
        create_timeout_tool_results,
        create_fallback_tool_result,
    )
    
    print(f"  ✅ ErrorType: {list(ErrorType)}")
    print(f"  ✅ ErrorClassification: {ErrorClassification}")
    print(f"  ✅ ErrorClassifier: {ErrorClassifier}")
    
    # 测试错误分类
    try:
        raise ValueError("测试错误")
    except Exception as e:
        classification = ErrorClassifier.classify(e)
        print(f"  ✅ 错误分类: {classification.error_type.value} - {classification.user_message}")
    
    print("  ✅ errors 模块测试通过")


def test_no_circular_imports():
    """测试无循环导入"""
    print("\n=== 测试 7: 循环导入检查 ===")
    
    import importlib
    
    modules = [
        "core.agent",
        "core.agent.base",
        "core.agent.factory",
        "core.agent.models",
        "core.agent.execution._multi",  # V10.1: orchestrator 移到此处
        "core.agent.errors",
        "core.agent.execution",
        "core.agent.components",
        "core.agent.context",
        "core.agent.tools",
    ]
    
    for mod_name in modules:
        try:
            # 强制重新加载
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            importlib.import_module(mod_name)
            print(f"  ✅ {mod_name}")
        except ImportError as e:
            print(f"  ❌ {mod_name}: {e}")
    
    print("  ✅ 循环导入检查通过")


def main():
    """主测试入口"""
    print("=" * 60)
    print("Agent 重构集成测试")
    print("=" * 60)
    
    tests = [
        test_module_imports,
        test_executor_registry,
        test_execution_module,
        test_components_module,
        test_models_module,
        test_errors_module,
        test_no_circular_imports,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"\n❌ 测试失败: {test.__name__}")
            print(f"   错误: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

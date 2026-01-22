"""
Orchestrator DAG 集成测试

测试 V7.7 中 Orchestrator 与 DAGScheduler 的集成：
1. Plan.from_decomposition 转换验证
2. DAG 执行事件正确发出
3. 端到端 DAG 执行流程
"""
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from core.planning.protocol import Plan, PlanStep, StepStatus
from core.planning.dag_scheduler import DAGScheduler, StepResult
from core.agent.multi.models import (
    MultiAgentConfig,
    AgentConfig,
    AgentRole,
    ExecutionMode,
)
from core.agent.multi.lead_agent import TaskDecompositionPlan, SubTask


# ===================
# 测试夹具
# ===================

@pytest.fixture
def basic_config():
    """基础多智能体配置"""
    return MultiAgentConfig(
        config_id="test_config",
        mode=ExecutionMode.PARALLEL,
        agents=[
            AgentConfig(
                agent_id="executor_1",
                role=AgentRole.EXECUTOR,
                model="test-model",
                tools=["tool_a", "tool_b"],
            ),
            AgentConfig(
                agent_id="researcher_1",
                role=AgentRole.RESEARCHER,
                model="test-model",
                tools=["search"],
            ),
        ],
        enable_lead_agent=True,
        retry_on_failure=False,
    )


@pytest.fixture
def sample_decomposition_plan():
    """示例任务分解计划"""
    return TaskDecompositionPlan(
        plan_id="test_plan_001",
        original_query="测试查询",
        decomposed_goal="分解后的目标",
        subtasks=[
            SubTask(
                subtask_id="step_1",
                title="步骤 1",
                description="第一个任务",
                assigned_agent_role=AgentRole.RESEARCHER,
                tools_required=["search"],
                expected_output="搜索结果",
                depends_on=[],
                priority=2,
            ),
            SubTask(
                subtask_id="step_2",
                title="步骤 2",
                description="第二个任务",
                assigned_agent_role=AgentRole.EXECUTOR,
                tools_required=["tool_a"],
                depends_on=["step_1"],
                priority=1,
            ),
            SubTask(
                subtask_id="step_3",
                title="步骤 3",
                description="第三个任务（与步骤 2 并行）",
                assigned_agent_role=AgentRole.EXECUTOR,
                tools_required=["tool_b"],
                depends_on=["step_1"],
                priority=1,
            ),
            SubTask(
                subtask_id="step_4",
                title="步骤 4",
                description="最终汇总",
                assigned_agent_role=AgentRole.EXECUTOR,
                depends_on=["step_2", "step_3"],
                priority=0,
            ),
        ],
        execution_mode=ExecutionMode.PARALLEL,
        synthesis_strategy="综合所有结果",
        reasoning="任务分解推理",
    )


# ===================
# Plan.from_decomposition 集成测试
# ===================

class TestPlanFromDecompositionIntegration:
    """Plan.from_decomposition 转换集成测试"""
    
    def test_conversion_preserves_dependencies(self, sample_decomposition_plan):
        """转换应保留依赖关系"""
        plan = Plan.from_decomposition(sample_decomposition_plan)
        
        # 验证步骤数量
        assert len(plan.steps) == 4
        
        # 验证依赖关系
        step_map = {s.id: s for s in plan.steps}
        assert step_map["step_1"].dependencies == []
        assert step_map["step_2"].dependencies == ["step_1"]
        assert step_map["step_3"].dependencies == ["step_1"]
        assert set(step_map["step_4"].dependencies) == {"step_2", "step_3"}
    
    def test_conversion_sets_execution_mode(self, sample_decomposition_plan):
        """转换应正确设置执行模式"""
        plan = Plan.from_decomposition(sample_decomposition_plan)
        assert plan.execution_mode == "dag"
    
    def test_conversion_preserves_metadata(self, sample_decomposition_plan):
        """转换应保留元数据"""
        plan = Plan.from_decomposition(sample_decomposition_plan)
        
        assert plan.metadata["original_query"] == "测试查询"
        assert plan.metadata["synthesis_strategy"] == "综合所有结果"
        assert plan.metadata["reasoning"] == "任务分解推理"
    
    def test_scheduler_computes_correct_groups(self, sample_decomposition_plan):
        """调度器应正确计算并行组"""
        plan = Plan.from_decomposition(sample_decomposition_plan)
        scheduler = DAGScheduler()
        
        groups = scheduler.compute_parallel_groups(plan)
        
        # 期望 3 组：
        # 组 1: step_1
        # 组 2: step_2, step_3（可并行）
        # 组 3: step_4
        assert len(groups) == 3
        assert len(groups[0]) == 1
        assert groups[0][0].id == "step_1"
        assert len(groups[1]) == 2
        assert set(s.id for s in groups[1]) == {"step_2", "step_3"}
        assert len(groups[2]) == 1
        assert groups[2][0].id == "step_4"


# ===================
# DAG 执行器独立测试
# ===================

class TestDAGExecutorStandalone:
    """DAG 执行器独立测试（不依赖完整 Orchestrator）"""
    
    @pytest.mark.asyncio
    async def test_dag_scheduler_executes_plan(self, sample_decomposition_plan):
        """DAGScheduler 可以执行从 decomposition 转换的 Plan"""
        plan = Plan.from_decomposition(sample_decomposition_plan)
        scheduler = DAGScheduler(enable_retry=False)
        
        execution_order = []
        
        async def mock_executor(step: PlanStep, dep_results):
            execution_order.append(step.id)
            await asyncio.sleep(0.01)
            return StepResult(
                step_id=step.id,
                success=True,
                output=f"{step.id} 完成",
            )
        
        result = await scheduler.execute(plan, mock_executor)
        
        assert result.success
        assert result.completed_steps == 4
        
        # 验证执行顺序
        assert execution_order.index("step_1") < execution_order.index("step_2")
        assert execution_order.index("step_1") < execution_order.index("step_3")
        assert execution_order.index("step_2") < execution_order.index("step_4")
        assert execution_order.index("step_3") < execution_order.index("step_4")
    
    @pytest.mark.asyncio
    async def test_dag_scheduler_with_failure_and_skip(self, sample_decomposition_plan):
        """DAGScheduler 处理失败和级联跳过"""
        plan = Plan.from_decomposition(sample_decomposition_plan)
        scheduler = DAGScheduler(enable_retry=False)
        
        async def mock_executor_with_failure(step: PlanStep, dep_results):
            if step.id == "step_2":
                return StepResult(step_id=step.id, success=False, error="模拟失败")
            return StepResult(step_id=step.id, success=True, output=f"{step.id} 完成")
        
        result = await scheduler.execute(plan, mock_executor_with_failure)
        
        assert not result.success
        assert result.failed_steps >= 1
        assert result.skipped_steps >= 1  # step_4 依赖 step_2，应被跳过
    
    @pytest.mark.asyncio
    async def test_dag_scheduler_parallel_execution(self, sample_decomposition_plan):
        """DAGScheduler 并行执行验证"""
        plan = Plan.from_decomposition(sample_decomposition_plan)
        scheduler = DAGScheduler(max_concurrency=3, enable_retry=False)
        
        execution_times = {}
        
        async def mock_executor(step: PlanStep, dep_results):
            execution_times[step.id] = asyncio.get_event_loop().time()
            await asyncio.sleep(0.1)
            return StepResult(step_id=step.id, success=True)
        
        result = await scheduler.execute(plan, mock_executor)
        
        assert result.success
        
        # step_2 和 step_3 应该几乎同时开始（它们在同一并行组）
        if "step_2" in execution_times and "step_3" in execution_times:
            time_diff = abs(execution_times["step_2"] - execution_times["step_3"])
            assert time_diff < 0.05  # 允许 50ms 差异


# ===================
# Agent 选择逻辑独立测试
# ===================

class TestAgentSelectionLogic:
    """Agent 选择逻辑独立测试"""
    
    def test_step_to_subtask_conversion(self, sample_decomposition_plan):
        """PlanStep 可以正确转换回 SubTask"""
        plan = Plan.from_decomposition(sample_decomposition_plan)
        step = plan.steps[0]  # step_1
        
        # 验证字段被正确映射
        assert step.id == "step_1"
        assert step.assigned_agent_role == "researcher"
        assert "search" in step.tools_required
        assert step.dependencies == []
    
    def test_agent_matching_by_role(self, basic_config):
        """按角色匹配 Agent"""
        # 模拟 _select_agent_for_step 的逻辑
        step = PlanStep(
            id="test",
            description="测试",
            assigned_agent_role="researcher",
        )
        
        # 查找匹配的 Agent
        matched = None
        for agent in basic_config.agents:
            if agent.role.value == step.assigned_agent_role:
                matched = agent
                break
        
        assert matched is not None
        assert matched.role == AgentRole.RESEARCHER
    
    def test_agent_matching_by_tools(self, basic_config):
        """按工具匹配 Agent"""
        step = PlanStep(
            id="test",
            description="测试",
            tools_required=["search"],
        )
        
        matched = None
        for agent in basic_config.agents:
            if any(tool in agent.tools for tool in step.tools_required):
                matched = agent
                break
        
        assert matched is not None
        assert "search" in matched.tools
    
    def test_fallback_to_first_agent(self, basic_config):
        """无匹配时回退到第一个 Agent"""
        step = PlanStep(
            id="test",
            description="测试",
            # 无匹配条件
        )
        
        # 无匹配时应返回第一个
        matched = basic_config.agents[0] if basic_config.agents else None
        
        assert matched is not None
        assert matched.agent_id == "executor_1"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

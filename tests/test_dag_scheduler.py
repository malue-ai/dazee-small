"""
DAGScheduler 单元测试

测试 V7.7 新增的 DAG 调度器功能：
1. 并行组计算（拓扑分层）
2. 依赖结果注入
3. 分层执行
4. 失败重试和级联失败
"""
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock

from core.planning.protocol import Plan, PlanStep, StepStatus
from core.planning.dag_scheduler import (
    DAGScheduler,
    DAGExecutionResult,
    StepResult,
)


# ===================
# 测试数据工厂
# ===================

def create_plan_linear() -> Plan:
    """创建线性依赖的 Plan（A -> B -> C）"""
    return Plan(
        goal="线性测试",
        steps=[
            PlanStep(id="A", description="步骤 A"),
            PlanStep(id="B", description="步骤 B", dependencies=["A"]),
            PlanStep(id="C", description="步骤 C", dependencies=["B"]),
        ],
        execution_mode="dag"
    )


def create_plan_diamond() -> Plan:
    """创建钻石依赖的 Plan（A -> B, C -> D）"""
    return Plan(
        goal="钻石测试",
        steps=[
            PlanStep(id="A", description="步骤 A"),
            PlanStep(id="B", description="步骤 B", dependencies=["A"]),
            PlanStep(id="C", description="步骤 C", dependencies=["A"]),
            PlanStep(id="D", description="步骤 D", dependencies=["B", "C"]),
        ],
        execution_mode="dag"
    )


def create_plan_independent() -> Plan:
    """创建无依赖的 Plan（A, B, C 并行）"""
    return Plan(
        goal="并行测试",
        steps=[
            PlanStep(id="A", description="步骤 A"),
            PlanStep(id="B", description="步骤 B"),
            PlanStep(id="C", description="步骤 C"),
        ],
        execution_mode="dag"
    )


def create_plan_complex() -> Plan:
    """创建复杂依赖的 Plan"""
    #     A
    #    / \
    #   B   C
    #   |   |
    #   D   E
    #    \ /
    #     F
    return Plan(
        goal="复杂测试",
        steps=[
            PlanStep(id="A", description="步骤 A"),
            PlanStep(id="B", description="步骤 B", dependencies=["A"]),
            PlanStep(id="C", description="步骤 C", dependencies=["A"]),
            PlanStep(id="D", description="步骤 D", dependencies=["B"]),
            PlanStep(id="E", description="步骤 E", dependencies=["C"]),
            PlanStep(id="F", description="步骤 F", dependencies=["D", "E"]),
        ],
        execution_mode="dag"
    )


# ===================
# 并行组计算测试
# ===================

class TestComputeParallelGroups:
    """测试 compute_parallel_groups() 并行组计算"""
    
    def test_linear_dependency(self):
        """线性依赖（A->B->C）应产生 3 个单元素组"""
        scheduler = DAGScheduler()
        plan = create_plan_linear()
        
        groups = scheduler.compute_parallel_groups(plan)
        
        assert len(groups) == 3
        assert [g[0].id for g in groups] == ["A", "B", "C"]
    
    def test_diamond_dependency(self):
        """钻石依赖（A->B,C->D）应产生 3 组"""
        scheduler = DAGScheduler()
        plan = create_plan_diamond()
        
        groups = scheduler.compute_parallel_groups(plan)
        
        assert len(groups) == 3
        # 第一组：A
        assert len(groups[0]) == 1
        assert groups[0][0].id == "A"
        # 第二组：B, C（可并行）
        assert len(groups[1]) == 2
        assert set(s.id for s in groups[1]) == {"B", "C"}
        # 第三组：D
        assert len(groups[2]) == 1
        assert groups[2][0].id == "D"
    
    def test_independent_steps(self):
        """无依赖应产生 1 个包含所有步骤的组"""
        scheduler = DAGScheduler()
        plan = create_plan_independent()
        
        groups = scheduler.compute_parallel_groups(plan)
        
        assert len(groups) == 1
        assert len(groups[0]) == 3
        assert set(s.id for s in groups[0]) == {"A", "B", "C"}
    
    def test_complex_dependency(self):
        """复杂依赖应正确分层"""
        scheduler = DAGScheduler()
        plan = create_plan_complex()
        
        groups = scheduler.compute_parallel_groups(plan)
        
        assert len(groups) == 4
        # 第一组：A
        assert set(s.id for s in groups[0]) == {"A"}
        # 第二组：B, C
        assert set(s.id for s in groups[1]) == {"B", "C"}
        # 第三组：D, E
        assert set(s.id for s in groups[2]) == {"D", "E"}
        # 第四组：F
        assert set(s.id for s in groups[3]) == {"F"}
    
    def test_empty_plan(self):
        """空 Plan 应返回空列表"""
        scheduler = DAGScheduler()
        plan = Plan(goal="空测试", steps=[], execution_mode="dag")
        
        groups = scheduler.compute_parallel_groups(plan)
        
        assert groups == []
    
    def test_priority_ordering(self):
        """优先级高的步骤应排在前面"""
        scheduler = DAGScheduler()
        plan = Plan(
            goal="优先级测试",
            steps=[
                PlanStep(id="A", description="步骤 A", priority=1),
                PlanStep(id="B", description="步骤 B", priority=3),
                PlanStep(id="C", description="步骤 C", priority=2),
            ],
            execution_mode="dag"
        )
        
        groups = scheduler.compute_parallel_groups(plan)
        
        assert len(groups) == 1
        # 按优先级降序排列
        assert [s.id for s in groups[0]] == ["B", "C", "A"]


# ===================
# 依赖上下文注入测试
# ===================

class TestDependencyContextInjection:
    """测试 inject_dependency_context() 依赖结果注入"""
    
    def test_inject_single_dependency(self):
        """单个依赖的结果注入"""
        scheduler = DAGScheduler()
        step = PlanStep(id="B", description="步骤 B", dependencies=["A"])
        
        completed_results = {
            "A": StepResult(step_id="A", success=True, output="A 的输出结果")
        }
        
        scheduler.inject_dependency_context(step, completed_results)
        
        assert step.injected_context is not None
        assert "A 的输出结果" in step.injected_context
        assert "步骤 A 结果" in step.injected_context
    
    def test_inject_multiple_dependencies(self):
        """多个依赖的结果注入"""
        scheduler = DAGScheduler()
        step = PlanStep(id="D", description="步骤 D", dependencies=["B", "C"])
        
        completed_results = {
            "B": StepResult(step_id="B", success=True, output="B 的输出"),
            "C": StepResult(step_id="C", success=True, output="C 的输出"),
        }
        
        scheduler.inject_dependency_context(step, completed_results)
        
        assert step.injected_context is not None
        assert "B 的输出" in step.injected_context
        assert "C 的输出" in step.injected_context
    
    def test_inject_failed_dependency(self):
        """失败依赖的结果注入"""
        scheduler = DAGScheduler()
        step = PlanStep(id="B", description="步骤 B", dependencies=["A"])
        
        completed_results = {
            "A": StepResult(step_id="A", success=False, error="执行错误")
        }
        
        scheduler.inject_dependency_context(step, completed_results)
        
        assert step.injected_context is not None
        assert "失败" in step.injected_context
        assert "执行错误" in step.injected_context
    
    def test_no_dependencies(self):
        """无依赖时不注入上下文"""
        scheduler = DAGScheduler()
        step = PlanStep(id="A", description="步骤 A", dependencies=[])
        
        scheduler.inject_dependency_context(step, {})
        
        assert step.injected_context is None
    
    def test_context_length_limit(self):
        """上下文长度限制"""
        scheduler = DAGScheduler(context_max_length=100)
        step = PlanStep(id="B", description="步骤 B", dependencies=["A"])
        
        long_output = "x" * 500
        completed_results = {
            "A": StepResult(step_id="A", success=True, output=long_output)
        }
        
        scheduler.inject_dependency_context(step, completed_results)
        
        assert step.injected_context is not None
        assert "[截断]" in step.injected_context
        assert len(step.injected_context) < len(long_output)


# ===================
# DAG 执行测试
# ===================

class TestDAGExecution:
    """测试 DAGScheduler.execute() 分层执行"""
    
    @pytest.mark.asyncio
    async def test_execute_simple_plan(self):
        """简单 Plan 执行"""
        scheduler = DAGScheduler(enable_retry=False)
        plan = create_plan_linear()
        
        execution_order = []
        
        async def mock_executor(step, dep_results):
            execution_order.append(step.id)
            await asyncio.sleep(0.01)
            return StepResult(
                step_id=step.id,
                success=True,
                output=f"{step.id} 完成"
            )
        
        result = await scheduler.execute(plan, mock_executor)
        
        assert result.success
        assert result.completed_steps == 3
        assert result.failed_steps == 0
        assert execution_order == ["A", "B", "C"]
    
    @pytest.mark.asyncio
    async def test_execute_parallel_steps(self):
        """并行步骤执行"""
        scheduler = DAGScheduler(max_concurrency=3, enable_retry=False)
        plan = create_plan_independent()
        
        execution_times = {}
        
        async def mock_executor(step, dep_results):
            execution_times[step.id] = asyncio.get_event_loop().time()
            await asyncio.sleep(0.1)
            return StepResult(step_id=step.id, success=True)
        
        result = await scheduler.execute(plan, mock_executor)
        
        assert result.success
        # 验证并行执行（时间差应该很小）
        times = list(execution_times.values())
        max_diff = max(times) - min(times)
        assert max_diff < 0.05  # 允许 50ms 差异
    
    @pytest.mark.asyncio
    async def test_execute_with_failure(self):
        """执行失败处理"""
        scheduler = DAGScheduler(enable_retry=False)
        plan = create_plan_linear()
        
        async def mock_executor(step, dep_results):
            if step.id == "B":
                return StepResult(step_id=step.id, success=False, error="B 失败")
            return StepResult(step_id=step.id, success=True)
        
        result = await scheduler.execute(plan, mock_executor)
        
        assert not result.success
        assert result.failed_steps == 1
        assert result.skipped_steps == 1  # C 应该被跳过
    
    @pytest.mark.asyncio
    async def test_execute_with_retry(self):
        """失败重试机制"""
        scheduler = DAGScheduler(enable_retry=True, max_retries=2)
        plan = Plan(
            goal="重试测试",
            steps=[PlanStep(id="A", description="步骤 A")],
            execution_mode="dag"
        )
        
        attempt_count = 0
        
        async def mock_executor(step, dep_results):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                return StepResult(step_id=step.id, success=False, error="临时失败")
            return StepResult(step_id=step.id, success=True, output="成功")
        
        result = await scheduler.execute(plan, mock_executor)
        
        assert result.success
        assert attempt_count == 3  # 2 次重试 + 1 次成功
    
    @pytest.mark.asyncio
    async def test_cascade_failure(self):
        """级联失败（依赖失败导致跳过）"""
        scheduler = DAGScheduler(enable_retry=False)
        plan = create_plan_diamond()
        
        async def mock_executor(step, dep_results):
            if step.id == "B":
                return StepResult(step_id=step.id, success=False, error="B 失败")
            return StepResult(step_id=step.id, success=True)
        
        result = await scheduler.execute(plan, mock_executor)
        
        assert not result.success
        assert result.failed_steps == 1  # B 失败
        assert result.skipped_steps == 1  # D 被跳过（依赖 B）
        assert result.completed_steps == 2  # A 和 C 成功
    
    @pytest.mark.asyncio
    async def test_callbacks(self):
        """回调函数调用"""
        scheduler = DAGScheduler(enable_retry=False)
        plan = create_plan_linear()
        
        step_starts = []
        step_ends = []
        
        async def mock_executor(step, dep_results):
            return StepResult(step_id=step.id, success=True)
        
        def on_step_start(step):
            step_starts.append(step.id)
        
        def on_step_end(step, result):
            step_ends.append((step.id, result.success))
        
        result = await scheduler.execute(
            plan, mock_executor,
            on_step_start=on_step_start,
            on_step_end=on_step_end,
        )
        
        assert step_starts == ["A", "B", "C"]
        assert step_ends == [("A", True), ("B", True), ("C", True)]
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """超时处理"""
        scheduler = DAGScheduler(enable_retry=False)
        plan = Plan(
            goal="超时测试",
            steps=[PlanStep(id="A", description="步骤 A", max_time_seconds=1)],
            execution_mode="dag"
        )
        
        async def slow_executor(step, dep_results):
            await asyncio.sleep(5)  # 超时
            return StepResult(step_id=step.id, success=True)
        
        result = await scheduler.execute(plan, slow_executor)
        
        assert not result.success
        assert result.failed_steps == 1
        assert "超时" in result.step_results["A"].error


# ===================
# Plan.from_decomposition 测试
# ===================

class TestPlanFromDecomposition:
    """测试 Plan.from_decomposition() 转换方法"""
    
    def test_conversion(self):
        """基本转换测试"""
        from core.agent.multi.lead_agent import TaskDecompositionPlan, SubTask
        from core.agent.multi.models import AgentRole, ExecutionMode
        
        decomposition = TaskDecompositionPlan(
            plan_id="plan_123",
            original_query="测试查询",
            decomposed_goal="测试目标",
            subtasks=[
                SubTask(
                    subtask_id="task_1",
                    title="任务 1",
                    description="描述 1",
                    assigned_agent_role=AgentRole.EXECUTOR,
                    tools_required=["tool_a"],
                    expected_output="输出格式",
                    success_criteria=["标准 1"],
                    depends_on=[],
                    priority=1,
                    context="上下文",
                    constraints=["约束 1"],
                    max_time_seconds=60,
                ),
                SubTask(
                    subtask_id="task_2",
                    title="任务 2",
                    description="描述 2",
                    assigned_agent_role=AgentRole.RESEARCHER,
                    depends_on=["task_1"],
                    priority=2,
                ),
            ],
            execution_mode=ExecutionMode.PARALLEL,
            synthesis_strategy="综合策略",
            reasoning="推理过程",
            estimated_time_seconds=120,
        )
        
        plan = Plan.from_decomposition(decomposition)
        
        assert plan.plan_id == "plan_123"
        assert plan.goal == "测试目标"
        assert plan.execution_mode == "dag"
        assert len(plan.steps) == 2
        
        # 验证第一个步骤
        step1 = plan.steps[0]
        assert step1.id == "task_1"
        assert step1.description == "描述 1"
        assert step1.dependencies == []
        assert step1.assigned_agent_role == "executor"
        assert step1.tools_required == ["tool_a"]
        assert step1.priority == 1
        
        # 验证第二个步骤
        step2 = plan.steps[1]
        assert step2.id == "task_2"
        assert step2.dependencies == ["task_1"]
        assert step2.assigned_agent_role == "researcher"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

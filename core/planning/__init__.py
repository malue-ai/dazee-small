"""
ZenFlux Agent 规划模块

提供统一的 Plan 数据协议和存储层：
1. Plan 数据协议（混合方案）- 支持线性和DAG执行
2. Plan 存储层 - 持久化和检索
3. Plan 验证器 - 格式和依赖验证
4. DAG 调度器 - 多智能体并行调度（V7.7 新增）

架构原则：
- Plan 协议是单智能体和多智能体共享的数据结构
- 单智能体使用线性执行模式（linear）
- 多智能体使用DAG执行模式（dag）
- 执行逻辑各自独立，但数据结构统一

使用方式：
    from core.planning import Plan, PlanStep, PlanStorage, DAGScheduler

    # 创建Plan
    plan = Plan(
        goal="分析数据并生成报告",
        steps=[
            PlanStep(id="1", description="加载数据"),
            PlanStep(id="2", description="清洗数据", dependencies=["1"]),
            PlanStep(id="3", description="生成报告", dependencies=["2"]),
        ],
        execution_mode="dag"
    )

    # 使用 DAG 调度器执行
    scheduler = DAGScheduler(max_concurrency=5)
    result = await scheduler.execute(plan, executor=my_executor)

    # 存储Plan
    storage = PlanStorage()
    await storage.save(plan)
"""

from core.planning.dag_scheduler import (
    DAGExecutionResult,
    DAGScheduler,
    StepResult,
)
from core.planning.protocol import Plan, PlanStatus, PlanStep, StepStatus
from core.planning.storage import PlanStorage
from core.planning.validators import PlanValidator

__all__ = [
    # 数据协议
    "Plan",
    "PlanStep",
    "PlanStatus",
    "StepStatus",
    # 存储
    "PlanStorage",
    # 验证
    "PlanValidator",
    # DAG 调度器（V7.7）
    "DAGScheduler",
    "DAGExecutionResult",
    "StepResult",
]

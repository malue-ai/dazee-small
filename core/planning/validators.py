"""
Plan 验证器（Validators）

验证 Plan 的格式和依赖关系：
1. 格式验证（字段完整性）
2. 依赖验证（无循环依赖）
3. 执行顺序验证（拓扑排序可行）
"""

from typing import Dict, List, Optional, Set, Tuple

from core.planning.protocol import Plan, PlanStep
from logger import get_logger

logger = get_logger(__name__)


class PlanValidationError(Exception):
    """Plan 验证错误"""

    def __init__(self, message: str, errors: Optional[List[str]] = None):
        self.message = message
        self.errors = errors or []
        super().__init__(message)


class PlanValidator:  # UNUSED: no plan validation in execution path
    """
    Plan 验证器

    使用方式：
        validator = PlanValidator()

        # 验证 Plan
        is_valid, errors = validator.validate(plan)

        # 或直接抛出异常
        validator.validate_or_raise(plan)
    """

    def validate(self, plan: Plan) -> Tuple[bool, List[str]]:
        """
        验证 Plan

        Args:
            plan: Plan 对象

        Returns:
            Tuple[bool, List[str]]: (是否有效, 错误列表)
        """
        errors = []

        # 1. 基本字段验证
        if not plan.goal or not plan.goal.strip():
            errors.append("Plan 目标不能为空")

        if not plan.steps:
            errors.append("Plan 必须包含至少一个步骤")

        # 2. 步骤验证
        step_ids = set()
        for step in plan.steps:
            # 步骤ID唯一性
            if step.id in step_ids:
                errors.append(f"步骤ID重复: {step.id}")
            step_ids.add(step.id)

            # 步骤描述不能为空
            if not step.description or not step.description.strip():
                errors.append(f"步骤 {step.id} 描述不能为空")

        # 3. 依赖验证
        dep_errors = self._validate_dependencies(plan.steps)
        errors.extend(dep_errors)

        # 4. 循环依赖检测
        has_cycle, cycle_path = self._detect_cycle(plan.steps)
        if has_cycle:
            errors.append(f"存在循环依赖: {' -> '.join(cycle_path)}")

        is_valid = len(errors) == 0

        if is_valid:
            logger.debug(f"✅ Plan 验证通过: {plan.plan_id}")
        else:
            logger.warning(f"❌ Plan 验证失败: {errors}")

        return is_valid, errors

    def validate_or_raise(self, plan: Plan) -> None:
        """
        验证 Plan，失败时抛出异常

        Args:
            plan: Plan 对象

        Raises:
            PlanValidationError: 验证失败时抛出
        """
        is_valid, errors = self.validate(plan)

        if not is_valid:
            raise PlanValidationError(f"Plan 验证失败: {len(errors)} 个错误", errors=errors)

    def _validate_dependencies(self, steps: List[PlanStep]) -> List[str]:
        """
        验证步骤依赖

        Args:
            steps: 步骤列表

        Returns:
            List[str]: 错误列表
        """
        errors = []
        step_ids = {step.id for step in steps}

        for step in steps:
            for dep_id in step.dependencies:
                # 依赖的步骤必须存在
                if dep_id not in step_ids:
                    errors.append(f"步骤 {step.id} 依赖的步骤不存在: {dep_id}")

                # 不能依赖自己
                if dep_id == step.id:
                    errors.append(f"步骤 {step.id} 不能依赖自己")

        return errors

    def _detect_cycle(self, steps: List[PlanStep]) -> Tuple[bool, List[str]]:
        """
        检测循环依赖（使用DFS）

        Args:
            steps: 步骤列表

        Returns:
            Tuple[bool, List[str]]: (是否有循环, 循环路径)
        """
        # 构建邻接表
        graph: Dict[str, List[str]] = {}
        for step in steps:
            graph[step.id] = step.dependencies.copy()

        # DFS 检测循环
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {step.id: WHITE for step in steps}
        parent: Dict[str, Optional[str]] = {step.id: None for step in steps}

        def dfs(node: str, path: List[str]) -> Tuple[bool, List[str]]:
            color[node] = GRAY
            path.append(node)

            for neighbor in graph.get(node, []):
                if neighbor not in color:
                    continue

                if color[neighbor] == GRAY:
                    # 找到循环
                    cycle_start = path.index(neighbor)
                    return True, path[cycle_start:] + [neighbor]

                if color[neighbor] == WHITE:
                    has_cycle, cycle_path = dfs(neighbor, path.copy())
                    if has_cycle:
                        return True, cycle_path

            color[node] = BLACK
            return False, []

        for step in steps:
            if color[step.id] == WHITE:
                has_cycle, cycle_path = dfs(step.id, [])
                if has_cycle:
                    return True, cycle_path

        return False, []

    def get_execution_order(self, plan: Plan) -> List[str]:
        """
        获取执行顺序（拓扑排序）

        Args:
            plan: Plan 对象

        Returns:
            List[str]: 步骤ID的执行顺序

        Raises:
            PlanValidationError: 存在循环依赖时抛出
        """
        # 检查循环依赖
        has_cycle, cycle_path = self._detect_cycle(plan.steps)
        if has_cycle:
            raise PlanValidationError(
                f"无法确定执行顺序：存在循环依赖", errors=[f"循环: {' -> '.join(cycle_path)}"]
            )

        # 拓扑排序
        step_map = {step.id: step for step in plan.steps}
        in_degree: Dict[str, int] = {step.id: len(step.dependencies) for step in plan.steps}

        # 初始化队列（入度为0的节点）
        queue = [sid for sid, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            # 取出入度为0的节点
            node = queue.pop(0)
            result.append(node)

            # 更新依赖此节点的其他节点的入度
            for step in plan.steps:
                if node in step.dependencies:
                    in_degree[step.id] -= 1
                    if in_degree[step.id] == 0:
                        queue.append(step.id)

        return result

    def get_parallel_groups(self, plan: Plan) -> List[List[str]]:
        """
        获取可并行执行的步骤组

        用于多智能体DAG执行

        Args:
            plan: Plan 对象

        Returns:
            List[List[str]]: 并行组列表，每组内的步骤可同时执行
        """
        step_map = {step.id: step for step in plan.steps}
        completed: Set[str] = set()
        groups: List[List[str]] = []

        while len(completed) < len(plan.steps):
            # 找出可执行的步骤
            ready = []
            for step in plan.steps:
                if step.id in completed:
                    continue

                # 所有依赖都已完成
                if all(dep in completed for dep in step.dependencies):
                    ready.append(step.id)

            if not ready:
                # 理论上不应该发生（除非有循环依赖）
                break

            groups.append(ready)
            completed.update(ready)

        return groups

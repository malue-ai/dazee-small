"""
依赖图

管理子任务之间的依赖关系，支持拓扑排序

功能：
- 构建依赖图
- 拓扑排序
- 获取可执行任务（无阻塞依赖）
- 检测循环依赖
"""

from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional
from collections import defaultdict, deque

from logger import get_logger
from ..fsm.states import SubTaskState, SubTaskStatus

logger = get_logger("dependency_graph")


class CyclicDependencyError(Exception):
    """循环依赖错误"""
    
    def __init__(self, cycle: List[str]):
        self.cycle = cycle
        super().__init__(f"检测到循环依赖: {' -> '.join(cycle)}")


@dataclass
class DependencyNode:
    """依赖图节点"""
    task_id: str
    sub_task: SubTaskState
    dependencies: Set[str] = field(default_factory=set)  # 该任务依赖的任务
    dependents: Set[str] = field(default_factory=set)    # 依赖该任务的任务


class DependencyGraph:
    """
    依赖图
    
    管理子任务之间的依赖关系
    
    使用示例：
        graph = DependencyGraph()
        
        # 添加任务
        for sub_task in sub_tasks:
            graph.add_task(sub_task)
        
        # 获取可执行任务
        runnable = graph.get_runnable_tasks()
        
        # 标记完成
        graph.mark_completed("task-1")
    """
    
    def __init__(self):
        """初始化依赖图"""
        self._nodes: Dict[str, DependencyNode] = {}
        self._completed: Set[str] = set()
        self._failed: Set[str] = set()
        
        logger.debug("依赖图初始化完成")
    
    def add_task(self, sub_task: SubTaskState):
        """
        添加任务到图中
        
        Args:
            sub_task: 子任务
        """
        node = DependencyNode(
            task_id=sub_task.id,
            sub_task=sub_task,
            dependencies=set(sub_task.dependencies)
        )
        
        self._nodes[sub_task.id] = node
        
        # 更新依赖关系（双向）
        for dep_id in sub_task.dependencies:
            if dep_id in self._nodes:
                self._nodes[dep_id].dependents.add(sub_task.id)
        
        # 更新已有节点的 dependents
        for existing_id, existing_node in self._nodes.items():
            if sub_task.id in existing_node.dependencies:
                node.dependents.add(existing_id)
        
        logger.debug(f"任务 {sub_task.id} 已添加到依赖图")
    
    def add_tasks(self, sub_tasks: List[SubTaskState]):
        """批量添加任务"""
        for st in sub_tasks:
            self.add_task(st)
        
        # 验证依赖有效性
        self._validate_dependencies()
    
    def _validate_dependencies(self):
        """验证依赖有效性"""
        all_ids = set(self._nodes.keys())
        
        for node in self._nodes.values():
            invalid_deps = node.dependencies - all_ids
            if invalid_deps:
                logger.warning(
                    f"任务 {node.task_id} 存在无效依赖: {invalid_deps}"
                )
                # 移除无效依赖
                node.dependencies -= invalid_deps
    
    def topological_sort(self) -> List[str]:
        """
        拓扑排序
        
        Returns:
            任务 ID 的拓扑排序列表
            
        Raises:
            CyclicDependencyError: 存在循环依赖
        """
        # Kahn's algorithm
        in_degree = {node_id: len(node.dependencies) for node_id, node in self._nodes.items()}
        queue = deque([node_id for node_id, degree in in_degree.items() if degree == 0])
        result = []
        
        while queue:
            node_id = queue.popleft()
            result.append(node_id)
            
            node = self._nodes[node_id]
            for dependent_id in node.dependents:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)
        
        # 检查是否所有节点都被处理
        if len(result) != len(self._nodes):
            # 存在循环依赖
            cycle = self._find_cycle()
            raise CyclicDependencyError(cycle)
        
        return result
    
    def _find_cycle(self) -> List[str]:
        """查找循环依赖"""
        # DFS 查找环
        visited = set()
        rec_stack = set()
        path = []
        
        def dfs(node_id: str) -> Optional[List[str]]:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)
            
            node = self._nodes.get(node_id)
            if node:
                for dependent_id in node.dependents:
                    if dependent_id not in visited:
                        cycle = dfs(dependent_id)
                        if cycle:
                            return cycle
                    elif dependent_id in rec_stack:
                        # 找到环
                        cycle_start = path.index(dependent_id)
                        return path[cycle_start:] + [dependent_id]
            
            path.pop()
            rec_stack.remove(node_id)
            return None
        
        for node_id in self._nodes:
            if node_id not in visited:
                cycle = dfs(node_id)
                if cycle:
                    return cycle
        
        return []
    
    def get_runnable_tasks(self) -> List[SubTaskState]:
        """
        获取可执行的任务（所有依赖都已完成）
        
        Returns:
            可执行的子任务列表
        """
        runnable = []
        
        for node in self._nodes.values():
            # 跳过已完成或失败的任务
            if node.task_id in self._completed or node.task_id in self._failed:
                continue
            
            # 跳过正在运行的任务
            if node.sub_task.status == SubTaskStatus.RUNNING:
                continue
            
            # 检查所有依赖是否已完成
            deps_satisfied = all(
                dep_id in self._completed
                for dep_id in node.dependencies
            )
            
            # 检查是否有失败的依赖
            has_failed_dep = any(
                dep_id in self._failed
                for dep_id in node.dependencies
            )
            
            if deps_satisfied and not has_failed_dep:
                runnable.append(node.sub_task)
        
        return runnable
    
    def mark_completed(self, task_id: str):
        """标记任务完成"""
        self._completed.add(task_id)
        
        if task_id in self._nodes:
            self._nodes[task_id].sub_task.status = SubTaskStatus.COMPLETED
        
        logger.debug(f"任务 {task_id} 标记为完成")
    
    def mark_failed(self, task_id: str):
        """标记任务失败"""
        self._failed.add(task_id)
        
        if task_id in self._nodes:
            self._nodes[task_id].sub_task.status = SubTaskStatus.FAILED
        
        logger.debug(f"任务 {task_id} 标记为失败")
    
    def get_parallelizable_groups(self) -> List[List[str]]:
        """
        获取可并行执行的任务组
        
        基于拓扑排序，将同一层级的任务分为一组
        """
        try:
            sorted_ids = self.topological_sort()
        except CyclicDependencyError:
            logger.error("存在循环依赖，无法计算并行组")
            return [[node_id] for node_id in self._nodes.keys()]
        
        groups = []
        current_group = []
        processed = set()
        
        for task_id in sorted_ids:
            node = self._nodes[task_id]
            
            # 检查依赖是否都在之前的组中
            deps_in_previous = all(
                dep_id in processed
                for dep_id in node.dependencies
            )
            
            if deps_in_previous or not node.dependencies:
                current_group.append(task_id)
            else:
                # 开始新组
                if current_group:
                    groups.append(current_group)
                    processed.update(current_group)
                current_group = [task_id]
        
        # 添加最后一组
        if current_group:
            groups.append(current_group)
        
        return groups
    
    def get_task(self, task_id: str) -> Optional[SubTaskState]:
        """获取任务"""
        node = self._nodes.get(task_id)
        return node.sub_task if node else None
    
    def get_all_tasks(self) -> List[SubTaskState]:
        """获取所有任务"""
        return [node.sub_task for node in self._nodes.values()]
    
    def is_all_completed(self) -> bool:
        """检查是否所有任务都已完成"""
        return len(self._completed) == len(self._nodes)
    
    def has_failed(self) -> bool:
        """检查是否有失败的任务"""
        return len(self._failed) > 0
    
    def get_status(self) -> Dict:
        """获取图状态"""
        return {
            "total_tasks": len(self._nodes),
            "completed": len(self._completed),
            "failed": len(self._failed),
            "pending": len(self._nodes) - len(self._completed) - len(self._failed),
            "completed_ids": list(self._completed),
            "failed_ids": list(self._failed),
        }


def create_dependency_graph() -> DependencyGraph:
    """创建依赖图"""
    return DependencyGraph()

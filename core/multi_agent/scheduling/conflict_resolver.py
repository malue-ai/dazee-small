"""
并行安全与冲突管理

负责检测和解决 Multi-Agent 并行执行时的资源冲突

功能：
- 文件级资源锁
- 冲突检测（文件、资源、语义）
- 自动降级策略（并行 → 串行）
- 冲突事件上报

设计原则：
- 轻量级：内存锁表，无外部依赖
- 可扩展：预留语义冲突检测接口
- 容错优先：检测到冲突时自动串行化，而不是失败
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional
from enum import Enum

from logger import get_logger

logger = get_logger("conflict_resolver")


class ConflictType(str, Enum):
    """冲突类型"""
    FILE = "file"              # 文件冲突：多个 Worker 修改同一文件
    RESOURCE = "resource"      # 资源冲突：多个 Worker 使用同一外部资源
    SEMANTIC = "semantic"      # 语义冲突：任务间有逻辑冲突（预留）


class ResolutionStrategy(str, Enum):
    """冲突解决策略"""
    SEQUENTIAL = "sequential"  # 串行化：添加依赖关系
    WAIT = "wait"              # 等待：等待资源释放
    SKIP = "skip"              # 跳过：跳过冲突任务
    ASK_HUMAN = "ask_human"    # 人工介入（预留）


@dataclass
class Conflict:
    """冲突信息"""
    type: ConflictType
    resource: str                    # 冲突资源（文件路径/资源 ID）
    task_ids: List[str]              # 冲突任务 ID 列表
    severity: str = "medium"         # high | medium | low
    description: Optional[str] = None
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class ResourceLock:
    """资源锁"""
    resource: str
    owner_task_id: str
    acquired_at: datetime
    expires_at: Optional[datetime] = None


class ConflictResolver:
    """
    冲突解决器
    
    核心功能：
    1. 文件锁管理（避免同时修改同一文件）
    2. 冲突检测（分析任务间的资源冲突）
    3. 自动解决（串行化/等待/跳过）
    
    使用示例：
        resolver = ConflictResolver()
        
        # 获取锁
        if resolver.acquire_lock("task-1", "src/auth.py"):
            # 执行任务
            ...
            # 释放锁
            resolver.release_lock("src/auth.py")
        
        # 检测冲突
        conflicts = resolver.detect_conflicts(sub_tasks)
        if conflicts:
            # 应用解决策略
            resolver.resolve_conflicts(conflicts)
    """
    
    def __init__(self, default_lock_timeout: int = 300):
        """
        初始化冲突解决器
        
        Args:
            default_lock_timeout: 默认锁超时时间（秒）
        """
        self.default_lock_timeout = default_lock_timeout
        
        # 资源锁表：{resource_path: ResourceLock}
        self.locks: Dict[str, ResourceLock] = {}
        
        # 任务资源映射：{task_id: Set[resource_path]}
        self.task_resources: Dict[str, Set[str]] = {}
        
        logger.info(f"ConflictResolver 初始化完成 (lock_timeout={default_lock_timeout}s)")
    
    # ==================== 资源锁管理 ====================
    
    def acquire_lock(
        self,
        task_id: str,
        resource: str,
        timeout: Optional[int] = None
    ) -> bool:
        """
        获取资源锁
        
        Args:
            task_id: 任务 ID
            resource: 资源路径（文件路径或资源 ID）
            timeout: 锁超时时间（秒），None 则使用默认值
            
        Returns:
            True: 获取成功
            False: 资源被占用
        """
        timeout = timeout or self.default_lock_timeout
        
        # 检查是否已被占用
        if resource in self.locks:
            existing_lock = self.locks[resource]
            
            # 检查是否超时
            if existing_lock.expires_at and datetime.now() > existing_lock.expires_at:
                # 超时，强制释放
                logger.warning(
                    f"资源锁超时，强制释放: resource={resource}, "
                    f"owner={existing_lock.owner_task_id}"
                )
                self.release_lock(resource)
            else:
                # 仍被占用
                logger.debug(
                    f"资源锁获取失败（被占用）: resource={resource}, "
                    f"owner={existing_lock.owner_task_id}, requester={task_id}"
                )
                return False
        
        # 获取锁
        expires_at = datetime.now() + timedelta(seconds=timeout)
        self.locks[resource] = ResourceLock(
            resource=resource,
            owner_task_id=task_id,
            acquired_at=datetime.now(),
            expires_at=expires_at
        )
        
        # 记录任务资源映射
        if task_id not in self.task_resources:
            self.task_resources[task_id] = set()
        self.task_resources[task_id].add(resource)
        
        logger.debug(f"资源锁获取成功: resource={resource}, owner={task_id}")
        return True
    
    def release_lock(self, resource: str) -> bool:
        """
        释放资源锁
        
        Args:
            resource: 资源路径
            
        Returns:
            True: 释放成功
            False: 资源未被锁定
        """
        if resource not in self.locks:
            logger.warning(f"资源锁不存在，无法释放: resource={resource}")
            return False
        
        lock = self.locks[resource]
        owner_task_id = lock.owner_task_id
        
        # 从锁表中移除
        del self.locks[resource]
        
        # 从任务资源映射中移除
        if owner_task_id in self.task_resources:
            self.task_resources[owner_task_id].discard(resource)
            if not self.task_resources[owner_task_id]:
                del self.task_resources[owner_task_id]
        
        logger.debug(f"资源锁释放成功: resource={resource}, owner={owner_task_id}")
        return True
    
    def release_task_locks(self, task_id: str) -> int:
        """
        释放任务持有的所有锁
        
        Args:
            task_id: 任务 ID
            
        Returns:
            释放的锁数量
        """
        if task_id not in self.task_resources:
            return 0
        
        resources = list(self.task_resources[task_id])
        count = 0
        
        for resource in resources:
            if self.release_lock(resource):
                count += 1
        
        logger.debug(f"释放任务所有锁: task_id={task_id}, count={count}")
        return count
    
    # ==================== 冲突检测 ====================
    
    def detect_conflicts(self, sub_tasks: List) -> List[Conflict]:
        """
        检测任务间的冲突
        
        Args:
            sub_tasks: 子任务列表（SubTaskState 对象）
            
        Returns:
            冲突列表
        """
        conflicts = []
        
        # 1. 检测文件冲突
        file_conflicts = self._detect_file_conflicts(sub_tasks)
        conflicts.extend(file_conflicts)
        
        # 2. 检测资源冲突（预留）
        # resource_conflicts = self._detect_resource_conflicts(sub_tasks)
        # conflicts.extend(resource_conflicts)
        
        # 3. 检测语义冲突（预留）
        # semantic_conflicts = self._detect_semantic_conflicts(sub_tasks)
        # conflicts.extend(semantic_conflicts)
        
        if conflicts:
            logger.info(f"检测到 {len(conflicts)} 个冲突")
            for conflict in conflicts:
                logger.info(
                    f"  - {conflict.type.value} 冲突: resource={conflict.resource}, "
                    f"tasks={conflict.task_ids}"
                )
        
        return conflicts
    
    def _detect_file_conflicts(self, sub_tasks: List) -> List[Conflict]:
        """
        检测文件冲突
        
        策略：
        - 提取每个任务的目标文件（从 metadata.files_scope 或启发式分析）
        - 检查是否有多个任务操作同一文件
        """
        conflicts = []
        
        # 文件使用映射：{file_path: [task_ids]}
        file_usage: Dict[str, List[str]] = {}
        
        for sub_task in sub_tasks:
            task_id = sub_task.id if hasattr(sub_task, 'id') else str(sub_task)
            
            # 尝试从 metadata 中获取文件列表
            files = []
            if hasattr(sub_task, 'metadata') and isinstance(sub_task.metadata, dict):
                files = sub_task.metadata.get('files_scope', [])
            
            # 如果没有显式声明，尝试从 action 中启发式提取
            if not files and hasattr(sub_task, 'action'):
                files = self._extract_files_from_action(sub_task.action)
            
            # 记录文件使用
            for file_path in files:
                if file_path not in file_usage:
                    file_usage[file_path] = []
                file_usage[file_path].append(task_id)
        
        # 检测冲突：同一文件被多个任务使用
        for file_path, task_ids in file_usage.items():
            if len(task_ids) > 1:
                conflicts.append(Conflict(
                    type=ConflictType.FILE,
                    resource=file_path,
                    task_ids=task_ids,
                    severity="high",
                    description=f"多个任务尝试操作同一文件: {file_path}"
                ))
        
        return conflicts
    
    def _extract_files_from_action(self, action: str) -> List[str]:
        """
        从任务描述中启发式提取文件路径
        
        简单实现：查找常见文件扩展名
        """
        import re
        
        # 匹配常见文件路径模式
        patterns = [
            r'\b[\w/\-\.]+\.(py|js|ts|tsx|jsx|java|go|rs|cpp|c|h)\b',
            r'\b(src|tests?|core|lib|utils)/[\w/\-\.]+\b'
        ]
        
        files = []
        for pattern in patterns:
            matches = re.findall(pattern, action)
            files.extend(matches)
        
        return list(set(files))
    
    # ==================== 冲突解决 ====================
    
    def resolve_conflicts(
        self,
        conflicts: List[Conflict],
        strategy: ResolutionStrategy = ResolutionStrategy.SEQUENTIAL
    ) -> Dict[str, List[str]]:
        """
        解决冲突
        
        Args:
            conflicts: 冲突列表
            strategy: 解决策略
            
        Returns:
            解决方案：{task_id: [dependent_task_ids]}（新增的依赖关系）
        """
        dependencies = {}
        
        for conflict in conflicts:
            if strategy == ResolutionStrategy.SEQUENTIAL:
                # 串行化：让后续任务依赖第一个任务
                task_ids = conflict.task_ids
                if len(task_ids) >= 2:
                    first_task = task_ids[0]
                    for task_id in task_ids[1:]:
                        if task_id not in dependencies:
                            dependencies[task_id] = []
                        dependencies[task_id].append(first_task)
                    
                    logger.info(
                        f"应用串行化策略: {conflict.type.value} 冲突, "
                        f"resource={conflict.resource}, "
                        f"{task_ids[1:]} 依赖 {first_task}"
                    )
        
        return dependencies
    
    # ==================== 工具方法 ====================
    
    def get_active_locks(self) -> List[ResourceLock]:
        """获取所有活跃的锁"""
        return list(self.locks.values())
    
    def is_locked(self, resource: str) -> bool:
        """检查资源是否被锁定"""
        return resource in self.locks
    
    def get_lock_owner(self, resource: str) -> Optional[str]:
        """获取资源锁的持有者"""
        if resource in self.locks:
            return self.locks[resource].owner_task_id
        return None
    
    def cleanup_expired_locks(self) -> int:
        """清理过期的锁"""
        now = datetime.now()
        expired = [
            resource
            for resource, lock in self.locks.items()
            if lock.expires_at and now > lock.expires_at
        ]
        
        for resource in expired:
            self.release_lock(resource)
        
        if expired:
            logger.info(f"清理过期锁: {len(expired)} 个")
        
        return len(expired)

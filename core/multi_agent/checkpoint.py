"""
Checkpoint Manager - 检查点恢复机制

职责：
- 定期保存执行状态检查点
- 支持从检查点恢复执行
- 减少失败时的重试成本

设计原则：
- 参考 Anthropic 实践：Durable execution + 检查点恢复
- 支持长时间工作流的容错
- 失败时从检查点恢复，而非从头开始

使用示例：
    manager = CheckpointManager(storage_dir="/path/to/checkpoints")

    # 保存检查点
    checkpoint_id = await manager.save_checkpoint(
        orchestrator_state=state,
        worker_results=results
    )

    # 恢复检查点
    state, results = await manager.restore_from_checkpoint(checkpoint_id)
"""

import asyncio
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import aiofiles
from pydantic import BaseModel

from logger import get_logger

logger = get_logger(__name__)


class CheckpointType(str, Enum):
    """检查点类型"""

    AUTO = "auto"  # 自动检查点（定期保存）
    MANUAL = "manual"  # 手动检查点
    ERROR = "error"  # 错误时保存
    PHASE = "phase"  # 阶段完成时保存


class CheckpointMetadata(BaseModel):
    """检查点元数据"""

    checkpoint_id: str
    task_id: str
    session_id: str
    checkpoint_type: CheckpointType
    created_at: datetime
    phase: str  # 当前阶段（decomposing/scheduling/executing/aggregating）
    progress: float  # 进度（0-1）
    description: Optional[str] = None


class Checkpoint(BaseModel):
    """检查点数据"""

    metadata: CheckpointMetadata
    orchestrator_state: Dict[str, Any]  # OrchestratorState 序列化
    worker_results: List[Dict[str, Any]]  # AgentResult 列表序列化
    context: Dict[str, Any] = {}  # 额外上下文


class CheckpointManager:
    """
    检查点管理器

    支持：
    - 定期自动保存检查点
    - 手动保存检查点
    - 从检查点恢复执行
    - 检查点清理（过期检查点）
    """

    def __init__(
        self,
        storage_dir: str = ".checkpoints",
        auto_cleanup: bool = True,
        max_checkpoints_per_task: int = 5,
        checkpoint_ttl_hours: int = 24,
    ):
        """
        初始化检查点管理器

        Args:
            storage_dir: 检查点存储目录
            auto_cleanup: 是否自动清理过期检查点
            max_checkpoints_per_task: 每个任务保留的最大检查点数
            checkpoint_ttl_hours: 检查点 TTL（小时）
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.auto_cleanup = auto_cleanup
        self.max_checkpoints_per_task = max_checkpoints_per_task
        self.checkpoint_ttl_hours = checkpoint_ttl_hours

        logger.info(f"✅ CheckpointManager 初始化: storage={storage_dir}")

    async def save_checkpoint(
        self,
        task_id: str,
        session_id: str,
        orchestrator_state: Dict[str, Any],
        worker_results: List[Dict[str, Any]],
        checkpoint_type: CheckpointType = CheckpointType.AUTO,
        phase: str = "executing",
        progress: float = 0.0,
        description: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        保存检查点

        Args:
            task_id: 任务 ID
            session_id: 会话 ID
            orchestrator_state: Orchestrator 状态
            worker_results: Worker 结果列表
            checkpoint_type: 检查点类型
            phase: 当前阶段
            progress: 进度（0-1）
            description: 描述
            context: 额外上下文

        Returns:
            检查点 ID
        """
        # 生成检查点 ID
        checkpoint_id = str(uuid4())

        # 创建元数据
        metadata = CheckpointMetadata(
            checkpoint_id=checkpoint_id,
            task_id=task_id,
            session_id=session_id,
            checkpoint_type=checkpoint_type,
            created_at=datetime.now(),
            phase=phase,
            progress=progress,
            description=description,
        )

        # 创建检查点
        checkpoint = Checkpoint(
            metadata=metadata,
            orchestrator_state=orchestrator_state,
            worker_results=worker_results,
            context=context or {},
        )

        # 保存到文件（异步）
        checkpoint_file = self._get_checkpoint_path(task_id, checkpoint_id)
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

        content = json.dumps(
            checkpoint.model_dump(mode="json"), indent=2, ensure_ascii=False, default=str
        )
        async with aiofiles.open(checkpoint_file, "w", encoding="utf-8") as f:
            await f.write(content)

        logger.info(
            f"💾 检查点已保存: {checkpoint_id} "
            f"(task={task_id}, phase={phase}, progress={progress:.1%})"
        )

        # 自动清理旧检查点
        if self.auto_cleanup:
            await self._cleanup_old_checkpoints(task_id)

        return checkpoint_id

    async def restore_from_checkpoint(
        self, checkpoint_id: str, task_id: Optional[str] = None
    ) -> Tuple[CheckpointMetadata, Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
        """
        从检查点恢复

        Args:
            checkpoint_id: 检查点 ID
            task_id: 任务 ID（如果提供，用于定位检查点）

        Returns:
            (metadata, orchestrator_state, worker_results, context)

        Raises:
            FileNotFoundError: 检查点不存在
        """
        # 查找检查点文件
        if task_id:
            checkpoint_file = self._get_checkpoint_path(task_id, checkpoint_id)
        else:
            # 搜索所有任务目录
            checkpoint_file = await self._find_checkpoint_async(checkpoint_id)

        if not checkpoint_file or not checkpoint_file.exists():
            raise FileNotFoundError(f"检查点不存在: {checkpoint_id}")

        # 加载检查点（异步）
        async with aiofiles.open(checkpoint_file, "r", encoding="utf-8") as f:
            content = await f.read()
            data = json.loads(content)

        checkpoint = Checkpoint(**data)

        logger.info(
            f"🔄 检查点已恢复: {checkpoint_id} "
            f"(task={checkpoint.metadata.task_id}, "
            f"phase={checkpoint.metadata.phase}, "
            f"progress={checkpoint.metadata.progress:.1%})"
        )

        return (
            checkpoint.metadata,
            checkpoint.orchestrator_state,
            checkpoint.worker_results,
            checkpoint.context,
        )

    async def list_checkpoints(self, task_id: str) -> List[CheckpointMetadata]:
        """
        列出任务的所有检查点

        Args:
            task_id: 任务 ID

        Returns:
            检查点元数据列表（按时间倒序）
        """
        task_dir = self.storage_dir / task_id
        if not task_dir.exists():
            return []

        checkpoints = []
        # 使用 asyncio.to_thread 包装同步的 glob 操作
        checkpoint_files = await asyncio.to_thread(list, task_dir.glob("*.json"))
        for checkpoint_file in checkpoint_files:
            try:
                async with aiofiles.open(checkpoint_file, "r", encoding="utf-8") as f:
                    content = await f.read()
                    data = json.loads(content)
                checkpoint = Checkpoint(**data)
                checkpoints.append(checkpoint.metadata)
            except Exception as e:
                logger.warning(f"⚠️ 加载检查点失败: {checkpoint_file}, error={e}")

        # 按时间倒序排序
        checkpoints.sort(key=lambda x: x.created_at, reverse=True)

        return checkpoints

    async def get_latest_checkpoint(self, task_id: str) -> Optional[str]:
        """
        获取任务的最新检查点 ID

        Args:
            task_id: 任务 ID

        Returns:
            最新的检查点 ID，如果没有返回 None
        """
        checkpoints = await self.list_checkpoints(task_id)
        if checkpoints:
            return checkpoints[0].checkpoint_id
        return None

    async def delete_checkpoint(self, task_id: str, checkpoint_id: str):
        """
        删除检查点

        Args:
            task_id: 任务 ID
            checkpoint_id: 检查点 ID
        """
        checkpoint_file = self._get_checkpoint_path(task_id, checkpoint_id)
        if checkpoint_file.exists():
            checkpoint_file.unlink()
            logger.info(f"🗑️ 检查点已删除: {checkpoint_id}")

    async def _cleanup_old_checkpoints(self, task_id: str):
        """
        清理旧检查点

        保留策略：
        - 每个任务最多保留 max_checkpoints_per_task 个
        - 超过 TTL 的检查点自动删除

        Args:
            task_id: 任务 ID
        """
        checkpoints = await self.list_checkpoints(task_id)

        if len(checkpoints) <= self.max_checkpoints_per_task:
            return

        # 删除最旧的检查点
        for checkpoint in checkpoints[self.max_checkpoints_per_task :]:
            await self.delete_checkpoint(task_id, checkpoint.checkpoint_id)

    def _get_checkpoint_path(self, task_id: str, checkpoint_id: str) -> Path:
        """获取检查点文件路径"""
        return self.storage_dir / task_id / f"{checkpoint_id}.json"

    async def _find_checkpoint_async(self, checkpoint_id: str) -> Optional[Path]:
        """异步在所有任务目录中查找检查点"""
        # 使用 asyncio.to_thread 包装同步的目录遍历
        task_dirs = await asyncio.to_thread(list, self.storage_dir.iterdir())
        for task_dir in task_dirs:
            if task_dir.is_dir():
                checkpoint_file = task_dir / f"{checkpoint_id}.json"
                if checkpoint_file.exists():
                    return checkpoint_file
        return None


# ============================================================
# 工厂函数
# ============================================================


def create_checkpoint_manager(storage_dir: str = ".checkpoints") -> CheckpointManager:
    """
    创建检查点管理器

    Args:
        storage_dir: 检查点存储目录

    Returns:
        CheckpointManager 实例
    """
    return CheckpointManager(storage_dir=storage_dir)

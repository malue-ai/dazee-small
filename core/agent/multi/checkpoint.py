"""
多智能体检查点系统（Checkpointing）

灵感来源：Anthropic Multi-Agent Research System
- 支持长时间运行的工作流
- 失败时从检查点恢复，而非从头开始
- 持久化 Agent 状态到磁盘

设计原则：
1. 定期自动保存检查点（每个 Agent 完成后）
2. 故障恢复：从最后一个成功的检查点继续
3. 检查点包含完整的执行状态（已完成的 Agent、中间结果、上下文）
"""

import asyncio
import json
import aiofiles
from logger import get_logger
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from core.agent.multi.models import (
    AgentResult,
    ExecutionMode,
    OrchestratorState,
    TaskAssignment,
)

logger = get_logger(__name__)


class Checkpoint(BaseModel):
    """检查点数据结构"""
    checkpoint_id: str = Field(..., description="检查点唯一标识")
    session_id: str = Field(..., description="会话 ID")
    orchestrator_state_id: str = Field(..., description="编排器状态 ID")
    
    # 执行进度
    mode: ExecutionMode = Field(..., description="执行模式")
    completed_agents: List[str] = Field(default_factory=list, description="已完成的 Agent")
    pending_agents: List[str] = Field(default_factory=list, description="待执行的 Agent")
    current_agent: Optional[str] = Field(None, description="当前执行的 Agent")
    
    # 中间结果（关键！）
    agent_results: List[AgentResult] = Field(default_factory=list, description="Agent 结果")
    task_assignments: List[TaskAssignment] = Field(default_factory=list, description="任务分配")
    
    # 上下文（串行模式需要）
    last_output: Optional[str] = Field(None, description="最后一个 Agent 的输出")
    accumulated_context: Dict[str, Any] = Field(default_factory=dict, description="累积的上下文")
    
    # 统计
    total_turns: int = Field(0, description="已使用的总轮次")
    total_tokens: int = Field(0, description="已使用的总 Token")
    
    # 元数据
    created_at: datetime = Field(default_factory=datetime.now)
    reason: str = Field("auto", description="检查点原因: auto/manual/error")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class CheckpointManager:
    """
    检查点管理器
    
    职责：
    1. 创建检查点（自动/手动）
    2. 加载检查点
    3. 恢复执行状态
    4. 清理过期检查点
    
    使用方式：
        manager = CheckpointManager(storage_path="data/checkpoints")
        
        # 保存检查点
        await manager.save_checkpoint(state)
        
        # 从检查点恢复
        checkpoint = await manager.load_latest_checkpoint(session_id)
        if checkpoint:
            state = manager.restore_state(checkpoint)
    """
    
    def __init__(
        self,
        storage_path: str = "data/checkpoints",
        auto_save: bool = True,
        retention_days: int = 7
    ):
        """
        初始化检查点管理器
        
        Args:
            storage_path: 检查点存储路径
            auto_save: 是否自动保存检查点
            retention_days: 检查点保留天数
        """
        self.storage_path = Path(storage_path)
        self.auto_save = auto_save
        self.retention_days = retention_days
        
        # 确保存储目录存在
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"✅ CheckpointManager 初始化: path={self.storage_path}")
    
    # ===================
    # 保存检查点
    # ===================
    
    async def save_checkpoint(
        self,
        state: OrchestratorState,
        reason: str = "auto",
        last_output: Optional[str] = None
    ) -> Checkpoint:
        """
        保存检查点
        
        Args:
            state: 编排器状态
            reason: 检查点原因（auto/manual/error）
            last_output: 最后一个 Agent 的输出
            
        Returns:
            Checkpoint: 检查点对象
        """
        checkpoint = Checkpoint(
            checkpoint_id=str(uuid4()),
            session_id=state.session_id,
            orchestrator_state_id=state.state_id,
            mode=state.mode,
            completed_agents=state.completed_agents.copy(),
            pending_agents=state.pending_agents.copy(),
            current_agent=state.current_agent,
            agent_results=state.agent_results.copy(),
            task_assignments=state.task_assignments.copy(),
            last_output=last_output,
            total_turns=state.total_turns,
            reason=reason,
        )
        
        # 持久化到磁盘
        await self._persist_checkpoint(checkpoint)
        
        logger.info(
            f"💾 保存检查点: {checkpoint.checkpoint_id} "
            f"(session={state.session_id}, reason={reason}, "
            f"completed={len(checkpoint.completed_agents)}/{len(checkpoint.completed_agents) + len(checkpoint.pending_agents)})"
        )
        
        return checkpoint
    
    async def save_checkpoint_on_agent_completion(
        self,
        state: OrchestratorState,
        agent_id: str,
        result: AgentResult
    ) -> Checkpoint:
        """
        在 Agent 完成后自动保存检查点（关键点！）
        
        这是 Anthropic 设计的核心：每个子任务完成后保存状态
        """
        if not self.auto_save:
            return None
        
        return await self.save_checkpoint(
            state=state,
            reason=f"agent_completed:{agent_id}",
            last_output=result.output
        )
    
    async def save_checkpoint_on_error(
        self,
        state: OrchestratorState,
        error: Exception
    ) -> Checkpoint:
        """
        在发生错误时保存检查点
        
        即使失败，也保存当前进度，方便调试和恢复
        """
        return await self.save_checkpoint(
            state=state,
            reason=f"error:{type(error).__name__}"
        )
    
    # ===================
    # 加载检查点
    # ===================
    
    async def load_latest_checkpoint(
        self,
        session_id: str
    ) -> Optional[Checkpoint]:
        """
        加载最新的检查点
        
        Args:
            session_id: 会话 ID
            
        Returns:
            Checkpoint: 最新的检查点（如果存在）
        """
        checkpoints = await self._load_session_checkpoints(session_id)
        
        if not checkpoints:
            return None
        
        # 按创建时间倒序排序
        checkpoints.sort(key=lambda c: c.created_at, reverse=True)
        
        latest = checkpoints[0]
        logger.info(
            f"📂 加载最新检查点: {latest.checkpoint_id} "
            f"(completed={len(latest.completed_agents)}, pending={len(latest.pending_agents)})"
        )
        
        return latest
    
    async def load_checkpoint(
        self,
        checkpoint_id: str
    ) -> Optional[Checkpoint]:
        """
        加载指定的检查点（异步）
        
        Args:
            checkpoint_id: 检查点 ID
            
        Returns:
            Checkpoint: 检查点对象
        """
        file_path = self._get_checkpoint_path(checkpoint_id)
        
        if not file_path.exists():
            return None
        
        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)
            
            checkpoint = Checkpoint(**data)
            return checkpoint
        except Exception as e:
            logger.error(f"❌ 加载检查点失败 {checkpoint_id}: {e}")
            return None
    
    async def list_checkpoints(
        self,
        session_id: str
    ) -> List[Checkpoint]:
        """
        列出会话的所有检查点
        
        Args:
            session_id: 会话 ID
            
        Returns:
            List[Checkpoint]: 检查点列表
        """
        return await self._load_session_checkpoints(session_id)
    
    # ===================
    # 恢复状态
    # ===================
    
    def restore_state(
        self,
        checkpoint: Checkpoint
    ) -> OrchestratorState:
        """
        从检查点恢复编排器状态
        
        Args:
            checkpoint: 检查点对象
            
        Returns:
            OrchestratorState: 恢复的状态
        """
        state = OrchestratorState(
            state_id=checkpoint.orchestrator_state_id,
            session_id=checkpoint.session_id,
            config_id="restored",  # 需要从外部传入完整配置
            mode=checkpoint.mode,
            status="resumed",  # 标记为恢复状态
            current_agent=checkpoint.current_agent,
            completed_agents=checkpoint.completed_agents.copy(),
            pending_agents=checkpoint.pending_agents.copy(),
            task_assignments=checkpoint.task_assignments.copy(),
            agent_results=checkpoint.agent_results.copy(),
            total_turns=checkpoint.total_turns,
            started_at=checkpoint.created_at,
        )
        
        logger.info(
            f"🔄 从检查点恢复状态: {checkpoint.checkpoint_id} "
            f"→ 将继续执行 {len(state.pending_agents)} 个待处理 Agent"
        )
        
        return state
    
    def can_resume(
        self,
        checkpoint: Checkpoint
    ) -> bool:
        """
        检查是否可以从检查点恢复
        
        Args:
            checkpoint: 检查点对象
            
        Returns:
            bool: 是否可以恢复
        """
        # 检查是否还有待处理的 Agent
        if not checkpoint.pending_agents:
            logger.warning(f"⚠️ 检查点 {checkpoint.checkpoint_id} 已完成，无法恢复")
            return False
        
        # 检查检查点是否过期
        age_hours = (datetime.now() - checkpoint.created_at).total_seconds() / 3600
        if age_hours > 24:
            logger.warning(
                f"⚠️ 检查点 {checkpoint.checkpoint_id} 已过期 "
                f"({age_hours:.1f} 小时)"
            )
            return False
        
        return True
    
    # ===================
    # 清理
    # ===================
    
    async def cleanup_old_checkpoints(self) -> int:
        """
        清理过期的检查点（异步）
        
        Returns:
            int: 清理的数量
        """
        deleted = 0
        
        # 使用 asyncio.to_thread 包装同步的 glob 操作
        file_paths = await asyncio.to_thread(list, self.storage_path.glob("*.json"))
        for file_path in file_paths:
            try:
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    data = json.loads(content)
                
                created_at = datetime.fromisoformat(data["created_at"])
                age_days = (datetime.now() - created_at).days
                
                if age_days > self.retention_days:
                    await asyncio.to_thread(file_path.unlink)
                    deleted += 1
            except Exception as e:
                logger.error(f"清理检查点失败 {file_path}: {e}")
        
        if deleted > 0:
            logger.info(f"🧹 清理了 {deleted} 个过期检查点")
        
        return deleted
    
    # ===================
    # 内部方法
    # ===================
    
    def _get_checkpoint_path(self, checkpoint_id: str) -> Path:
        """获取检查点文件路径"""
        return self.storage_path / f"{checkpoint_id}.json"
    
    async def _persist_checkpoint(self, checkpoint: Checkpoint) -> None:
        """持久化检查点到磁盘（异步）"""
        file_path = self._get_checkpoint_path(checkpoint.checkpoint_id)
        
        data = checkpoint.model_dump(mode="json")
        content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(content)
    
    async def _load_session_checkpoints(
        self,
        session_id: str
    ) -> List[Checkpoint]:
        """加载会话的所有检查点（异步）"""
        checkpoints = []
        
        # 使用 asyncio.to_thread 包装同步的 glob 操作
        file_paths = await asyncio.to_thread(list, self.storage_path.glob("*.json"))
        for file_path in file_paths:
            try:
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    data = json.loads(content)
                
                if data.get("session_id") == session_id:
                    checkpoint = Checkpoint(**data)
                    checkpoints.append(checkpoint)
            except Exception as e:
                logger.error(f"加载检查点失败 {file_path}: {e}")
        
        return checkpoints

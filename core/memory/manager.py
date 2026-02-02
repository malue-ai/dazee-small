"""
Memory Manager - 统一记忆管理器

职责：
- 整合各层记忆（Working、User、System）
- 提供统一的内存访问接口
- 管理记忆的生命周期

设计原则：
- 统一入口：所有记忆通过 Manager 访问
- 按需加载：只在需要时创建子记忆
- 可扩展：支持添加新的记忆类型
"""

from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from logger import get_logger

from .working import WorkingMemory, create_working_memory
from .user import (
    EpisodicMemory, create_episodic_memory,
    PreferenceMemory, create_preference_memory,
    E2BMemory, create_e2b_memory,  # E2B 现在是用户级记忆
    PlanMemory, create_plan_memory  # 🆕 任务计划持久化
)
from .system import SkillMemory, create_skill_memory, CacheMemory, create_cache_memory

logger = get_logger("memory.manager")


class MemoryManager:
    """
    统一记忆管理器
    
    整合三层记忆：
    - Working Memory（会话级短期记忆）
    - User Memory（用户级长期记忆）
    - System Memory（系统级全局记忆）
    
    Args:
        user_id: 用户 ID（用于隔离用户级记忆）
        storage_dir: 存储目录（用于持久化）
    """
    
    def __init__(
        self,
        user_id: Optional[str] = None,
        storage_dir: Optional[str] = None
    ):
        self.user_id = user_id
        self.storage_dir = storage_dir
        
        # === 会话级记忆 ===
        self.working = create_working_memory()
        
        # === 用户级记忆 ===
        # E2B 沙箱记忆（用户的云端计算环境）
        self.e2b = create_e2b_memory(user_id=user_id)
        
        # 用户经验和偏好（按需创建）
        self._episodic: Optional[EpisodicMemory] = None
        self._preference: Optional[PreferenceMemory] = None
        self._plan: Optional[PlanMemory] = None  # 🆕 任务计划持久化
        
        # === 系统级记忆（单例）===
        self._skill: Optional[SkillMemory] = None
        self._cache: Optional[CacheMemory] = None
    
    # ==================== 用户级记忆（懒加载）====================
    
    @property
    def episodic(self) -> EpisodicMemory:
        """获取用户历史经验记忆（懒加载）"""
        if self._episodic is None:
            self._episodic = create_episodic_memory(
                user_id=self.user_id,
                storage_dir=self.storage_dir
            )
        return self._episodic
    
    @property
    def preference(self) -> PreferenceMemory:
        """获取用户偏好记忆（懒加载）"""
        if self._preference is None:
            self._preference = create_preference_memory(
                user_id=self.user_id,
                storage_dir=self.storage_dir
            )
        return self._preference
    
    @property
    def plan(self) -> PlanMemory:
        """
        获取任务计划记忆（懒加载）
        
        🆕 V4.3 新增：支持跨 Session 任务计划持久化
        
        用途：
        - 保存任务计划（首次 Session）
        - 恢复任务进度（后续 Session）
        - 生成进度摘要（自动注入 Prompt）
        """
        if self._plan is None:
            self._plan = create_plan_memory(
                user_id=self.user_id,
                storage_dir=self.storage_dir
            )
        return self._plan
    
    # ==================== 系统级记忆（懒加载）====================
    
    @property
    def skill(self) -> SkillMemory:
        """获取 Skill 缓存（懒加载）"""
        if self._skill is None:
            self._skill = create_skill_memory()
        return self._skill
    
    @property
    def cache(self) -> CacheMemory:
        """获取系统缓存（懒加载）"""
        if self._cache is None:
            self._cache = create_cache_memory()
        return self._cache
    
    # ==================== 生命周期管理 ====================
    
    def start_task(self, task_id: str, user_intent: str) -> None:
        """
        开始新任务
        
        Args:
            task_id: 任务 ID
            user_intent: 用户意图
        """
        self.working.clear()
        self.working.update_metadata("task_id", task_id)
        self.working.update_metadata("user_intent", user_intent)
        self.working.update_metadata("start_time", datetime.now().isoformat())
        
        if self.user_id:
            self.working.update_metadata("user_id", self.user_id)
        
        logger.debug(f"[MemoryManager] 开始任务: task_id={task_id}")
    
    async def end_task(self, result: Any, save_to_episodic: bool = True) -> None:
        """
        结束任务（异步版本）
        
        Args:
            result: 任务结果
            save_to_episodic: 是否保存到用户历史
        """
        task_id = self.working.get_metadata("task_id", "unknown")
        user_intent = self.working.get_metadata("user_intent", "")
        
        if save_to_episodic:
            # 确保 episodic 已初始化
            episodic = self.episodic
            if not episodic._initialized:
                await episodic.initialize()
            
            await episodic.add_episode(
                task_id=task_id,
                user_intent=user_intent,
                result=result,
                metadata=self.working.metadata.copy()
            )
        
        logger.debug(f"[MemoryManager] 结束任务: task_id={task_id}")
    
    def clear_session(self) -> None:
        """清空会话级记忆（保留持久沙箱）"""
        self.working.clear()
        self.e2b.clear_temporary()  # 只清除临时沙箱
    
    async def clear_all(self) -> None:
        """清空所有记忆（异步版本，慎用）"""
        self.working.clear()
        self.e2b.clear_all()  # 清除所有沙箱（包括持久）
        
        if self._episodic:
            await self._episodic.clear()
        if self._preference:
            await self._preference.clear()
        if self._plan:
            await self._plan.clear()  # 🆕 清除任务计划
        if self._skill:
            await self._skill.clear()
        if self._cache:
            self._cache.clear()  # CacheMemory.clear() 仍然是同步的
    
    # ==================== 上下文生成 ====================
    
    def get_context_for_llm(self, include_episodic: bool = False) -> Dict[str, Any]:
        """
        为 LLM 准备上下文
        
        Args:
            include_episodic: 是否包含历史经验
            
        Returns:
            上下文字典
        """
        context = {
            "messages": self.working.get_messages(),
            "tool_history": self.working.get_tool_history(),
            "metadata": self.working.metadata
        }
        
        # E2B 上下文
        e2b_context = self.e2b.get_context_for_llm()
        if e2b_context:
            context["e2b_context"] = e2b_context
        
        # 历史经验
        if include_episodic:
            user_intent = self.working.get_metadata("user_intent", "")
            if user_intent:
                similar = self.episodic.get_similar_episodes(user_intent, top_k=2)
                context["similar_episodes"] = similar
        
        return context
    
    # ==================== 用户切换 ====================
    
    def switch_user(self, user_id: str) -> None:
        """
        切换用户
        
        会清空用户级记忆缓存，下次访问时重新加载
        
        Args:
            user_id: 新用户 ID
        """
        self.user_id = user_id
        self._episodic = None
        self._preference = None
        logger.debug(f"[MemoryManager] 切换用户: user_id={user_id}")
    
    # ==================== 状态查询 ====================
    
    def summary(self) -> str:
        """获取摘要信息"""
        return (
            f"MemoryManager("
            f"user_id={self.user_id}, "
            f"working={self.working.summary()}, "
            f"e2b={'active' if self.e2b.has_active_session() else 'none'}, "
            f"episodic={'loaded' if self._episodic else 'not_loaded'}, "
            f"plan={'loaded' if self._plan else 'not_loaded'}, "
            f"skill={'loaded' if self._skill else 'not_loaded'})"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "user_id": self.user_id,
            "storage_dir": self.storage_dir,
            "working": self.working.to_dict(),
            "e2b": self.e2b.to_dict(),
            "episodic_loaded": self._episodic is not None,
            "preference_loaded": self._preference is not None,
            "plan_loaded": self._plan is not None,  # 🆕
            "skill_loaded": self._skill is not None,
            "cache_loaded": self._cache is not None
        }


# ==================== 工厂函数 ====================

def create_memory_manager(
    user_id: Optional[str] = None,
    storage_dir: Optional[str] = None
) -> MemoryManager:
    """
    创建 MemoryManager 实例
    
    Args:
        user_id: 用户 ID（用于隔离用户级记忆）
        storage_dir: 存储目录（用于持久化）
        
    Returns:
        配置好的 MemoryManager 实例
    """
    return MemoryManager(user_id=user_id, storage_dir=storage_dir)


def create_user_memory_manager(
    user_id: str,
    storage_dir: Optional[str] = None
) -> MemoryManager:
    """
    创建用户专属的 MemoryManager
    
    Args:
        user_id: 用户 ID（必填）
        storage_dir: 存储目录
        
    Returns:
        配置好的 MemoryManager 实例
    """
    if not user_id:
        raise ValueError("user_id 不能为空")
    
    return MemoryManager(user_id=user_id, storage_dir=storage_dir)


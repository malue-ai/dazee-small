"""
Plan 存储层（Storage）

提供 Plan 的持久化存储和检索功能：
1. 内存缓存（快速访问）
2. 文件持久化（跨Session）
3. 会话级索引

支持：
- 按 plan_id 查询
- 按 conversation_id 查询
- 按 user_id 查询
"""

import asyncio

from utils.app_paths import get_user_data_dir
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import aiofiles

from core.planning.protocol import Plan, PlanStatus
from logger import get_logger

logger = get_logger(__name__)


class PlanStorage:  # UNUSED: plans stored in Conversation.metadata.plan via PlanTodoTool
    """
    Plan 存储层

    使用方式：
        storage = PlanStorage(storage_path="data/plans")

        # 保存Plan
        await storage.save(plan)

        # 获取Plan
        plan = await storage.get(plan_id)

        # 按会话查询
        plans = await storage.get_by_conversation(conversation_id)
    """

    def __init__(self, storage_path: str = "", retention_days: int = 30):
        """
        初始化存储层

        Args:
            storage_path: 持久化存储路径
            retention_days: 数据保留天数

        注意：需要调用 await initialize() 完成异步初始化
        """
        self.storage_path = Path(storage_path) if storage_path else get_user_data_dir() / "data" / "plans"
        self.retention_days = retention_days

        # 确保存储目录存在
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # 内存缓存
        self._cache: Dict[str, Plan] = {}

        # 索引
        self._conversation_index: Dict[str, List[str]] = {}  # conversation_id -> [plan_id]
        self._user_index: Dict[str, List[str]] = {}  # user_id -> [plan_id]

        # 初始化标记
        self._initialized: bool = False

    async def initialize(self) -> None:
        """
        异步初始化：加载现有数据

        使用方式：
            storage = PlanStorage()
            await storage.initialize()
        """
        if self._initialized:
            return

        await self._load_all_async()
        self._initialized = True

    # ===================
    # 基本操作
    # ===================

    async def save(self, plan: Plan) -> None:
        """
        保存 Plan

        Args:
            plan: Plan 对象
        """
        # 更新缓存
        self._cache[plan.plan_id] = plan

        # 更新索引
        if plan.conversation_id:
            if plan.conversation_id not in self._conversation_index:
                self._conversation_index[plan.conversation_id] = []
            if plan.plan_id not in self._conversation_index[plan.conversation_id]:
                self._conversation_index[plan.conversation_id].append(plan.plan_id)

        if plan.user_id:
            if plan.user_id not in self._user_index:
                self._user_index[plan.user_id] = []
            if plan.plan_id not in self._user_index[plan.user_id]:
                self._user_index[plan.user_id].append(plan.plan_id)

        # 持久化到文件
        await self._persist(plan)

        logger.debug(f"💾 保存 Plan: {plan.plan_id}")

    async def get(self, plan_id: str) -> Optional[Plan]:
        """
        获取 Plan

        Args:
            plan_id: Plan ID

        Returns:
            Plan: Plan 对象（如果存在）
        """
        return self._cache.get(plan_id)

    async def delete(self, plan_id: str) -> bool:
        """
        删除 Plan

        Args:
            plan_id: Plan ID

        Returns:
            bool: 是否删除成功
        """
        if plan_id not in self._cache:
            return False

        plan = self._cache[plan_id]

        # 从索引中移除
        if plan.conversation_id and plan.conversation_id in self._conversation_index:
            self._conversation_index[plan.conversation_id] = [
                pid for pid in self._conversation_index[plan.conversation_id] if pid != plan_id
            ]

        if plan.user_id and plan.user_id in self._user_index:
            self._user_index[plan.user_id] = [
                pid for pid in self._user_index[plan.user_id] if pid != plan_id
            ]

        # 从缓存中移除
        del self._cache[plan_id]

        # 删除文件
        file_path = self._get_file_path(plan_id)
        if file_path.exists():
            file_path.unlink()

        logger.debug(f"🗑️ 删除 Plan: {plan_id}")
        return True

    async def update(self, plan: Plan) -> None:
        """
        更新 Plan

        Args:
            plan: Plan 对象
        """
        plan.updated_at = datetime.now()
        await self.save(plan)

    # ===================
    # 查询操作
    # ===================

    async def get_by_conversation(
        self, conversation_id: str, status: Optional[PlanStatus] = None
    ) -> List[Plan]:
        """
        按会话ID查询 Plan

        Args:
            conversation_id: 会话ID
            status: 状态筛选

        Returns:
            List[Plan]: Plan 列表
        """
        plan_ids = self._conversation_index.get(conversation_id, [])
        plans = [self._cache[pid] for pid in plan_ids if pid in self._cache]

        if status:
            plans = [p for p in plans if p.status == status]

        # 按创建时间倒序
        plans.sort(key=lambda p: p.created_at, reverse=True)

        return plans

    async def get_by_user(self, user_id: str, limit: int = 20) -> List[Plan]:
        """
        按用户ID查询 Plan

        Args:
            user_id: 用户ID
            limit: 返回数量限制

        Returns:
            List[Plan]: Plan 列表
        """
        plan_ids = self._user_index.get(user_id, [])
        plans = [self._cache[pid] for pid in plan_ids if pid in self._cache]

        # 按创建时间倒序
        plans.sort(key=lambda p: p.created_at, reverse=True)

        return plans[:limit]

    async def get_active_plans(self, conversation_id: Optional[str] = None) -> List[Plan]:
        """
        获取活跃的 Plan（PENDING 或 IN_PROGRESS）

        Args:
            conversation_id: 可选的会话ID筛选

        Returns:
            List[Plan]: 活跃的 Plan 列表
        """
        if conversation_id:
            plans = await self.get_by_conversation(conversation_id)
        else:
            plans = list(self._cache.values())

        return [p for p in plans if p.status in [PlanStatus.PENDING, PlanStatus.IN_PROGRESS]]

    # ===================
    # 统计信息
    # ===================

    def get_statistics(self) -> Dict:
        """获取统计信息"""
        plans = list(self._cache.values())

        by_status = {}
        for status in PlanStatus:
            by_status[status.value] = sum(1 for p in plans if p.status == status)

        return {
            "total_plans": len(plans),
            "by_status": by_status,
            "conversations_with_plans": len(self._conversation_index),
            "users_with_plans": len(self._user_index),
        }

    # ===================
    # 清理
    # ===================

    async def cleanup_old_plans(self) -> int:
        """
        清理过期的 Plan

        Returns:
            int: 清理的数量
        """
        cutoff = datetime.now() - timedelta(days=self.retention_days)

        deleted = 0
        for plan_id, plan in list(self._cache.items()):
            # 只清理已完成或失败的过期Plan
            if plan.status in [PlanStatus.COMPLETED, PlanStatus.FAILED, PlanStatus.CANCELLED]:
                if plan.updated_at < cutoff:
                    await self.delete(plan_id)
                    deleted += 1

        if deleted > 0:
            logger.info(f"🧹 清理了 {deleted} 个过期 Plan")

        return deleted

    # ===================
    # 内部方法
    # ===================

    def _get_file_path(self, plan_id: str) -> Path:
        """获取 Plan 文件路径"""
        return self.storage_path / f"{plan_id}.json"

    async def _persist(self, plan: Plan) -> None:
        """持久化 Plan 到文件（异步）"""
        file_path = self._get_file_path(plan.plan_id)

        data = plan.model_dump(mode="json")
        content = json.dumps(data, ensure_ascii=False, indent=2, default=str)

        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(content)

    async def _load_all_async(self) -> None:
        """异步加载所有 Plan 到内存"""
        # 使用 asyncio.to_thread 包装同步的 glob 操作
        file_paths = await asyncio.to_thread(list, self.storage_path.glob("*.json"))
        for file_path in file_paths:
            try:
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    data = json.loads(content)

                plan = Plan(**data)
                self._cache[plan.plan_id] = plan

                # 重建索引
                if plan.conversation_id:
                    if plan.conversation_id not in self._conversation_index:
                        self._conversation_index[plan.conversation_id] = []
                    self._conversation_index[plan.conversation_id].append(plan.plan_id)

                if plan.user_id:
                    if plan.user_id not in self._user_index:
                        self._user_index[plan.user_id] = []
                    self._user_index[plan.user_id].append(plan.plan_id)

            except Exception as e:
                logger.error(f"加载 Plan 失败 {file_path}: {e}")

        logger.info(f"📂 加载了 {len(self._cache)} 个 Plan")

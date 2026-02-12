"""
Episodic Memory - 用户历史经验

职责：
- 存储用户的历史会话记录
- 存储成功/失败的经验
- 支持按 user_id 隔离

设计原则：
- 长期记忆：持久化到文件/数据库
- 用户隔离：每个用户独立的经验库
- 可检索：支持相似度检索历史经验
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from logger import get_logger

from ..base import BaseScopedMemory, MemoryConfig, MemoryScope, StorageBackend

logger = get_logger("memory.user.episodic")


class EpisodicMemory(BaseScopedMemory):
    """
    情节记忆 - 用户长期任务历史

    存储内容：
    - 历史会话记录
    - 成功/失败的经验
    - 质量评估数据

    使用方式：
        memory = EpisodicMemory(user_id="user_123", storage_path="data/episodes.json")
        await memory.initialize()  # 必须调用以加载数据

    Args:
        user_id: 用户 ID（用于隔离数据）
        storage_path: 存储路径（file 后端使用）
    """

    def __init__(self, user_id: Optional[str] = None, storage_path: Optional[str] = None):
        config = MemoryConfig(
            scope=MemoryScope.USER,
            backend=StorageBackend.FILE if storage_path else StorageBackend.MEMORY,
            storage_path=storage_path,
        )
        super().__init__(scope_id=user_id, config=config)

        self.user_id = user_id
        self.storage_path = Path(storage_path) if storage_path else None
        self.episodes: List[Dict[str, Any]] = []
        self._initialized: bool = False

    async def initialize(self) -> None:
        """
        异步初始化：加载持久化数据

        使用方式：
            memory = EpisodicMemory(...)
            await memory.initialize()
        """
        if self._initialized:
            return

        if self.storage_path and self.storage_path.exists():
            await self._load_async()

        self._initialized = True
        logger.debug(f"[EpisodicMemory] 初始化完成: user_id={self.user_id}")

    async def add_episode(
        self,
        task_id: str,
        user_intent: str,
        result: Any,
        quality_score: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        添加一个历史情节（异步版本）

        Args:
            task_id: 任务 ID（原 session_id）
            user_intent: 用户意图
            result: 任务结果
            quality_score: 质量评分（可选）
            metadata: 额外元数据
        """
        episode = {
            "task_id": task_id,
            "user_id": self.user_id,
            "user_intent": user_intent,
            "result": result,
            "quality_score": quality_score,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
        }
        self.episodes.append(episode)

        # 自动持久化
        if self.storage_path:
            await self._save()

        logger.debug(f"[EpisodicMemory] 添加情节: task_id={task_id}, user_id={self.user_id}")

    def get_episodes(
        self, last_n: Optional[int] = None, min_quality: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        获取历史情节

        Args:
            last_n: 只返回最近 N 条
            min_quality: 最低质量阈值
        """
        episodes = self.episodes

        # 过滤质量阈值
        if min_quality is not None:
            episodes = [
                e
                for e in episodes
                if e.get("quality_score") is not None and e.get("quality_score") >= min_quality
            ]

        # 返回最近 N 个
        if last_n:
            return episodes[-last_n:]
        return episodes

    def get_similar_episodes(self, user_intent: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        获取相似的历史情节（简单实现：基于关键词匹配）

        未来可以使用 embedding 进行语义相似度检索

        Args:
            user_intent: 用户意图
            top_k: 返回最相似的 K 个
        """
        scored_episodes = []
        intent_words = set(user_intent.lower().split())

        for episode in self.episodes:
            episode_words = set(episode["user_intent"].lower().split())
            overlap = len(intent_words & episode_words)
            if overlap > 0:
                scored_episodes.append((overlap, episode))

        # 按相似度排序
        scored_episodes.sort(reverse=True, key=lambda x: x[0])
        return [e[1] for e in scored_episodes[:top_k]]

    def search_by_metadata(self, key: str, value: Any) -> List[Dict[str, Any]]:
        """
        按元数据搜索情节

        Args:
            key: 元数据 key
            value: 元数据 value
        """
        return [e for e in self.episodes if e.get("metadata", {}).get(key) == value]

    async def clear(self) -> None:
        """清空所有情节（异步版本）"""
        self.episodes.clear()
        if self.storage_path:
            await self._save()

    async def _save(self) -> None:
        """异步持久化到文件"""
        if not self.storage_path:
            return

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self.storage_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(self.episodes, ensure_ascii=False, indent=2))

    async def _load_async(self) -> None:
        """异步从文件加载"""
        if not self.storage_path or not self.storage_path.exists():
            return

        try:
            async with aiofiles.open(self.storage_path, "r", encoding="utf-8") as f:
                content = await f.read()
                self.episodes = json.loads(content)
        except Exception as e:
            logger.warning(f"[EpisodicMemory] 加载失败: {e}")
            self.episodes = []

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        base = super().to_dict()
        base.update(
            {
                "user_id": self.user_id,
                "episodes_count": len(self.episodes),
                "storage_path": str(self.storage_path) if self.storage_path else None,
            }
        )
        return base


def create_episodic_memory(
    user_id: Optional[str] = None, storage_dir: Optional[str] = None
) -> EpisodicMemory:
    """
    创建 EpisodicMemory 实例

    注意：创建后需要调用 await memory.initialize() 完成异步初始化

    Args:
        user_id: 用户 ID（用于隔离数据）
        storage_dir: 存储目录（自动生成文件名）

    Returns:
        EpisodicMemory 实例（需要调用 initialize() 加载数据）
    """
    storage_path = None
    if storage_dir:
        if user_id:
            storage_path = str(Path(storage_dir) / "users" / user_id / "episodic.json")
        else:
            storage_path = str(Path(storage_dir) / "episodic.json")

    return EpisodicMemory(user_id=user_id, storage_path=storage_path)


async def create_episodic_memory_async(
    user_id: Optional[str] = None, storage_dir: Optional[str] = None
) -> EpisodicMemory:
    """
    创建并初始化 EpisodicMemory 实例（异步版本）

    Args:
        user_id: 用户 ID（用于隔离数据）
        storage_dir: 存储目录（自动生成文件名）

    Returns:
        已初始化的 EpisodicMemory 实例
    """
    memory = create_episodic_memory(user_id=user_id, storage_dir=storage_dir)
    await memory.initialize()
    return memory

"""
Preference Memory - 用户偏好记忆（预留）

职责：
- 存储用户的个人偏好
- 存储用户的常用设置
- 支持学习用户行为

设计原则：
- 长期记忆：持久化到文件/数据库
- 用户隔离：每个用户独立的偏好库
- 可更新：支持增量学习用户偏好
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from logger import get_logger

from ..base import BaseScopedMemory, MemoryConfig, MemoryScope, StorageBackend

logger = get_logger("memory.user.preference")


class PreferenceMemory(BaseScopedMemory):
    """
    用户偏好记忆（预留）

    存储内容：
    - 用户偏好设置
    - 常用工具/操作
    - 输出风格偏好

    使用方式：
        memory = PreferenceMemory(user_id="user_123", storage_path="data/pref.json")
        await memory.initialize()  # 必须调用以加载数据

    Args:
        user_id: 用户 ID
        storage_path: 存储路径
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
        self.preferences: Dict[str, Any] = {}
        self._initialized: bool = False

    async def initialize(self) -> None:
        """
        异步初始化：加载持久化数据

        使用方式：
            memory = PreferenceMemory(...)
            await memory.initialize()
        """
        if self._initialized:
            return

        if self.storage_path and self.storage_path.exists():
            await self._load_async()

        self._initialized = True
        logger.debug(f"[PreferenceMemory] 初始化完成: user_id={self.user_id}")

    async def set_preference(self, key: str, value: Any) -> None:
        """
        设置偏好（异步版本）

        Args:
            key: 偏好 key
            value: 偏好值
        """
        self.preferences[key] = {"value": value, "updated_at": datetime.now().isoformat()}

        if self.storage_path:
            await self._save()

    def get_preference(self, key: str, default: Any = None) -> Any:
        """
        获取偏好

        Args:
            key: 偏好 key
            default: 默认值
        """
        pref = self.preferences.get(key)
        if pref:
            return pref.get("value", default)
        return default

    def get_all_preferences(self) -> Dict[str, Any]:
        """获取所有偏好"""
        return {k: v.get("value") for k, v in self.preferences.items()}

    async def delete_preference(self, key: str) -> None:
        """删除偏好（异步版本）"""
        if key in self.preferences:
            del self.preferences[key]
            if self.storage_path:
                await self._save()

    async def clear(self) -> None:
        """清空所有偏好（异步版本）"""
        self.preferences.clear()
        if self.storage_path:
            await self._save()

    async def _save(self) -> None:
        """异步持久化到文件"""
        if not self.storage_path:
            return

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self.storage_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(self.preferences, ensure_ascii=False, indent=2))

    async def _load_async(self) -> None:
        """异步从文件加载"""
        if not self.storage_path or not self.storage_path.exists():
            return

        try:
            async with aiofiles.open(self.storage_path, "r", encoding="utf-8") as f:
                content = await f.read()
                self.preferences = json.loads(content)
        except Exception as e:
            logger.warning(f"[PreferenceMemory] 加载失败: {e}")
            self.preferences = {}

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        base = super().to_dict()
        base.update({"user_id": self.user_id, "preferences_count": len(self.preferences)})
        return base


def create_preference_memory(
    user_id: Optional[str] = None, storage_dir: Optional[str] = None
) -> PreferenceMemory:
    """
    创建 PreferenceMemory 实例

    注意：创建后需要调用 await memory.initialize() 完成异步初始化

    Args:
        user_id: 用户 ID
        storage_dir: 存储目录

    Returns:
        PreferenceMemory 实例（需要调用 initialize() 加载数据）
    """
    storage_path = None
    if storage_dir:
        if user_id:
            storage_path = str(Path(storage_dir) / "users" / user_id / "preference.json")
        else:
            storage_path = str(Path(storage_dir) / "preference.json")

    return PreferenceMemory(user_id=user_id, storage_path=storage_path)


async def create_preference_memory_async(
    user_id: Optional[str] = None, storage_dir: Optional[str] = None
) -> PreferenceMemory:
    """
    创建并初始化 PreferenceMemory 实例（异步版本）

    Args:
        user_id: 用户 ID
        storage_dir: 存储目录

    Returns:
        已初始化的 PreferenceMemory 实例
    """
    memory = create_preference_memory(user_id=user_id, storage_dir=storage_dir)
    await memory.initialize()
    return memory

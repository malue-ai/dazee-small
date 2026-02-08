"""
策略库存储后端抽象

V9.4 新增

支持：
- FileStorage: 文件存储（默认，向后兼容）
- DatabaseStorage: 数据库存储（PostgreSQL/SQLite）
"""

import json
import os
from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from logger import get_logger
from utils.app_paths import get_instance_playbooks_dir

logger = get_logger("playbook_storage")


class PlaybookStorageBackend(ABC):
    """
    策略库存储后端抽象接口
    """

    @abstractmethod
    async def save(self, entry_id: str, data: Dict[str, Any]) -> None:
        """保存策略"""
        pass

    @abstractmethod
    async def load(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """加载策略"""
        pass

    @abstractmethod
    async def delete(self, entry_id: str) -> bool:
        """删除策略"""
        pass

    @abstractmethod
    async def list_all(self) -> List[Dict[str, Any]]:
        """列出所有策略"""
        pass

    @abstractmethod
    async def save_index(self, index: Dict[str, Any]) -> None:
        """保存索引"""
        pass

    @abstractmethod
    async def load_index(self) -> Dict[str, Any]:
        """加载索引"""
        pass


class FileStorage(PlaybookStorageBackend):
    """
    文件存储后端（默认，向后兼容）

    存储结构：
    - storage_path/
      - index.json
      - {id}.json
    """

    def __init__(self, storage_path: str = "", instance_name: str = ""):
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            import os
            _inst = instance_name or os.environ["AGENT_INSTANCE"]
            self.storage_path = get_instance_playbooks_dir(_inst)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 FileStorage 初始化: path={storage_path}")

    async def save(self, entry_id: str, data: Dict[str, Any]) -> None:
        """保存策略到文件"""
        entry_file = self.storage_path / f"{entry_id}.json"
        async with aiofiles.open(entry_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))

    async def load(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """从文件加载策略"""
        entry_file = self.storage_path / f"{entry_id}.json"
        if not entry_file.exists():
            return None

        async with aiofiles.open(entry_file, "r", encoding="utf-8") as f:
            content = await f.read()
            return json.loads(content)

    async def delete(self, entry_id: str) -> bool:
        """删除策略文件"""
        entry_file = self.storage_path / f"{entry_id}.json"
        if entry_file.exists():
            entry_file.unlink()
            return True
        return False

    async def list_all(self) -> List[Dict[str, Any]]:
        """列出所有策略"""
        entries = []
        index = await self.load_index()

        for entry_id in index.get("entries", []):
            data = await self.load(entry_id)
            if data:
                entries.append(data)

        return entries

    async def save_index(self, index: Dict[str, Any]) -> None:
        """保存索引"""
        index_file = self.storage_path / "index.json"
        async with aiofiles.open(index_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(index, ensure_ascii=False, indent=2))

    async def load_index(self) -> Dict[str, Any]:
        """加载索引"""
        index_file = self.storage_path / "index.json"
        if not index_file.exists():
            return {"entries": [], "updated_at": datetime.now().isoformat()}

        async with aiofiles.open(index_file, "r", encoding="utf-8") as f:
            content = await f.read()
            return json.loads(content)


class DatabaseStorage(PlaybookStorageBackend):
    """
    数据库存储后端

    使用 SQLAlchemy 异步会话
    """

    def __init__(self):
        self._session_factory = None
        logger.info("🗄️ DatabaseStorage 初始化")

    async def _get_session(self):
        """获取数据库会话"""
        if self._session_factory is None:
            try:
                from infra.database import AsyncSessionLocal

                self._session_factory = AsyncSessionLocal
            except ImportError:
                # TODO: 迁移到 local_store
                raise NotImplementedError("数据库模块已删除，DatabaseStorage 功能已禁用")

        return self._session_factory()

    async def save(self, entry_id: str, data: Dict[str, Any]) -> None:
        """保存策略到数据库"""
        try:
            from infra.database.crud.continuous_learning import create_playbook, get_playbook
            from infra.database.models.continuous_learning import PlaybookStatus
        except ImportError:
            # TODO: 迁移到 local_store
            raise NotImplementedError("数据库模块已删除，DatabaseStorage.save() 功能已禁用")

        async with await self._get_session() as session:
            # 检查是否存在
            existing = await get_playbook(session, entry_id)

            if existing:
                # 更新
                for key, value in data.items():
                    if key == "status" and isinstance(value, str):
                        value = PlaybookStatus(value)
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                existing.updated_at = datetime.now()
                await session.commit()
            else:
                # 创建
                status = data.get("status", "draft")
                if isinstance(status, str):
                    status = PlaybookStatus(status)

                await create_playbook(
                    session=session,
                    name=data.get("name", ""),
                    description=data.get("description", ""),
                    trigger=data.get("trigger", {}),
                    strategy=data.get("strategy", {}),
                    tool_sequence=data.get("tool_sequence", []),
                    quality_metrics=data.get("quality_metrics", {}),
                    source=data.get("source", "auto"),
                    source_session_id=data.get("source_session_id"),
                )

    async def load(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """从数据库加载策略"""
        try:
            from infra.database.crud.continuous_learning import get_playbook
        except ImportError:
            # TODO: 迁移到 local_store
            raise NotImplementedError("数据库模块已删除，DatabaseStorage.load() 功能已禁用")

        async with await self._get_session() as session:
            record = await get_playbook(session, entry_id)
            if not record:
                return None

            return {
                "id": record.id,
                "name": record.name,
                "description": record.description,
                "trigger": record.trigger,
                "strategy": record.strategy,
                "tool_sequence": record.tool_sequence,
                "quality_metrics": record.quality_metrics,
                "status": record.status.value if hasattr(record.status, "value") else record.status,
                "source": record.source,
                "source_session_id": record.source_session_id,
                "reviewed_by": record.reviewed_by,
                "review_notes": record.review_notes,
                "usage_count": record.usage_count,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            }

    async def delete(self, entry_id: str) -> bool:
        """从数据库删除策略"""
        try:
            from infra.database.crud.continuous_learning import delete_playbook
        except ImportError:
            # TODO: 迁移到 local_store
            raise NotImplementedError("数据库模块已删除，DatabaseStorage.delete() 功能已禁用")

        async with await self._get_session() as session:
            return await delete_playbook(session, entry_id)

    async def list_all(self) -> List[Dict[str, Any]]:
        """列出所有策略"""
        try:
            from infra.database.crud.continuous_learning import list_playbooks
        except ImportError:
            # TODO: 迁移到 local_store
            raise NotImplementedError("数据库模块已删除，DatabaseStorage.list_all() 功能已禁用")

        async with await self._get_session() as session:
            records = await list_playbooks(session)
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "description": r.description,
                    "trigger": r.trigger,
                    "strategy": r.strategy,
                    "tool_sequence": r.tool_sequence,
                    "quality_metrics": r.quality_metrics,
                    "status": r.status.value if hasattr(r.status, "value") else r.status,
                    "source": r.source,
                    "source_session_id": r.source_session_id,
                    "usage_count": r.usage_count,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in records
            ]

    async def save_index(self, index: Dict[str, Any]) -> None:
        """数据库模式不需要单独的索引"""
        pass

    async def load_index(self) -> Dict[str, Any]:
        """数据库模式从表中动态生成索引"""
        try:
            from infra.database.crud.continuous_learning import get_learning_stats
            from infra.database.models.continuous_learning import PlaybookStatus
        except ImportError:
            # TODO: 迁移到 local_store
            raise NotImplementedError("数据库模块已删除，DatabaseStorage.load_index() 功能已禁用")

        async with await self._get_session() as session:
            stats = await get_learning_stats(session)

            return {
                "entries": [],  # 数据库模式不需要
                "updated_at": datetime.now().isoformat(),
                "stats": stats.get("playbooks", {}),
            }


def create_storage_backend(
    backend_type: str = None, storage_path: str = ""
) -> PlaybookStorageBackend:
    """
    创建存储后端

    Args:
        backend_type: 存储类型 ("file" | "database")，默认从环境变量读取
        storage_path: 文件存储路径（仅文件模式）

    Returns:
        PlaybookStorageBackend 实例
    """
    if backend_type is None:
        backend_type = os.getenv("PLAYBOOK_STORAGE_BACKEND", "file")

    if backend_type == "database":
        return DatabaseStorage()
    else:
        return FileStorage(storage_path)

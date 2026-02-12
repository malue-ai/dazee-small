"""
策略库文件存储后端

V8.0 新增
V10.0 重构：删除不可用的 DatabaseStorage，简化为纯文件存储

存储结构：
- storage_path/
  - index.json
  - {id}.json
"""

import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from logger import get_logger
from utils.app_paths import get_instance_playbooks_dir

logger = get_logger("playbook_storage")


class PlaybookStorageBackend(ABC):
    """策略库存储后端抽象接口"""

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
    文件存储后端

    存储结构：
    - storage_path/
      - index.json
      - {id}.json
    """

    def __init__(self, storage_path: str = ""):
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            instance_name = os.getenv("AGENT_INSTANCE", "default")
            self.storage_path = get_instance_playbooks_dir(instance_name)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 FileStorage 初始化: path={self.storage_path}")

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


def create_storage_backend(storage_path: str = "") -> PlaybookStorageBackend:
    """
    创建文件存储后端

    Args:
        storage_path: 存储路径，为空时使用实例隔离路径

    Returns:
        FileStorage 实例
    """
    return FileStorage(storage_path)

"""
本地文件存储
"""

import aiofiles
from pathlib import Path
from typing import BinaryIO, Optional

from infra.storage.base import StorageBackend
from utils.app_paths import get_instance_storage_dir


class LocalStorage(StorageBackend):
    """本地文件系统存储"""

    def __init__(self, base_dir: str = "", instance_name: str = ""):
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            import os
            _inst = instance_name or os.getenv("AGENT_INSTANCE", "default")
            self.base_dir = get_instance_storage_dir(_inst)
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_full_path(self, path: str) -> Path:
        """获取完整路径"""
        return self.base_dir / path
    
    async def save(
        self,
        file: BinaryIO,
        path: str,
        content_type: Optional[str] = None
    ) -> str:
        """保存文件到本地"""
        full_path = self._get_full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 读取文件内容
        content = file.read() if hasattr(file, 'read') else file
        
        # 异步写入
        async with aiofiles.open(full_path, 'wb') as f:
            await f.write(content)
        
        return str(full_path)
    
    async def get(self, path: str) -> bytes:
        """获取文件内容"""
        full_path = self._get_full_path(path)
        
        async with aiofiles.open(full_path, 'rb') as f:
            return await f.read()
    
    async def delete(self, path: str) -> bool:
        """删除文件"""
        full_path = self._get_full_path(path)
        
        if full_path.exists():
            full_path.unlink()
            return True
        return False
    
    async def exists(self, path: str) -> bool:
        """检查文件是否存在"""
        return self._get_full_path(path).exists()
    
    def get_url(self, path: str, expires_in: int = 3600) -> str:
        """
        获取文件访问 URL
        
        本地存储返回文件路径，实际访问需要通过 API 路由
        """
        return f"/api/v1/files/{path}"


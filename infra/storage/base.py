"""
存储后端抽象基类
"""

from abc import ABC, abstractmethod
from typing import BinaryIO, Optional
from pathlib import Path


class StorageBackend(ABC):
    """
    存储后端抽象基类
    
    定义统一的文件存储接口，具体实现可以是本地文件系统、S3、OSS 等
    """
    
    @abstractmethod
    async def save(
        self,
        file: BinaryIO,
        path: str,
        content_type: Optional[str] = None
    ) -> str:
        """
        保存文件
        
        Args:
            file: 文件对象
            path: 存储路径
            content_type: 文件类型
            
        Returns:
            存储后的路径或 URL
        """
        pass
    
    @abstractmethod
    async def get(self, path: str) -> bytes:
        """
        获取文件内容
        
        Args:
            path: 文件路径
            
        Returns:
            文件内容
        """
        pass
    
    @abstractmethod
    async def delete(self, path: str) -> bool:
        """
        删除文件
        
        Args:
            path: 文件路径
            
        Returns:
            是否删除成功
        """
        pass
    
    @abstractmethod
    async def exists(self, path: str) -> bool:
        """
        检查文件是否存在
        
        Args:
            path: 文件路径
            
        Returns:
            是否存在
        """
        pass
    
    @abstractmethod
    def get_url(self, path: str, expires_in: int = 3600) -> str:
        """
        获取文件访问 URL
        
        Args:
            path: 文件路径
            expires_in: URL 过期时间（秒）
            
        Returns:
            访问 URL
        """
        pass


"""
文件存储模块

提供统一的文件存储抽象，支持：
- LocalStorage: 本地文件系统（开发环境）
- S3Storage: AWS S3（生产环境，待实现）
- OSSStorage: 阿里云 OSS（国内云，待实现）
"""

from infra.storage.base import StorageBackend
from infra.storage.local import LocalStorage

__all__ = [
    "StorageBackend",
    "LocalStorage",
]

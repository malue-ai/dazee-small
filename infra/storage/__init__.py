"""
存储模块

提供文件存储抽象：
- LocalStorage: 本地文件系统
- S3Storage: S3 / MinIO
"""

from infra.storage.base import StorageBackend
from infra.storage.local import LocalStorage

__all__ = [
    "StorageBackend",
    "LocalStorage",
]


"""
本地知识检索模块

Level 1: FTS5 全文搜索
Level 2: 可选 sqlite-vec 语义搜索
"""

from core.knowledge.file_indexer import FileIndexer
from core.knowledge.local_search import LocalKnowledgeManager

__all__ = [
    "LocalKnowledgeManager",
    "FileIndexer",
]

"""
知识服务 — KnowledgeService

管理 LocalKnowledgeManager 的生命周期：
- 单例初始化（从实例配置读取参数）
- 提供全局访问入口
- 初始化时自动索引配置的目录

使用方式：
    from services.knowledge_service import get_knowledge_manager

    km = await get_knowledge_manager()
    results = await km.search("我的文档")
"""

from pathlib import Path
from typing import Optional

from logger import get_logger

logger = get_logger("services.knowledge")

# Global singleton
_knowledge_manager = None
_file_indexer = None


async def get_knowledge_manager():
    """
    Get the global LocalKnowledgeManager singleton.

    Lazily initializes from instance config on first call.

    Returns:
        Initialized LocalKnowledgeManager
    """
    global _knowledge_manager

    if _knowledge_manager is None:
        _knowledge_manager = await _create_knowledge_manager()

    return _knowledge_manager


async def get_file_indexer():
    """
    Get the global FileIndexer singleton.

    Returns:
        Initialized FileIndexer
    """
    global _file_indexer

    if _file_indexer is None:
        from core.knowledge.file_indexer import FileIndexer

        km = await get_knowledge_manager()
        _file_indexer = FileIndexer(km)

    return _file_indexer


async def index_configured_directories() -> int:
    """
    Index all directories configured in instance config.

    Called during app startup or on-demand.

    Returns:
        Total number of files indexed
    """
    config = _load_knowledge_config()
    directories = config.get("directories", [])

    if not directories:
        logger.debug("No knowledge directories configured, skipping indexing")
        return 0

    indexer = await get_file_indexer()
    total = 0

    for dir_path in directories:
        path = Path(dir_path).expanduser().resolve()
        if not path.exists():
            logger.warning(f"Knowledge directory not found: {path}")
            continue

        count = await indexer.index_directory(path)
        total += count
        logger.info(f"Indexed {count} files from {path}")

    return total


async def shutdown():
    """Clean up knowledge service resources."""
    global _knowledge_manager, _file_indexer
    _knowledge_manager = None
    _file_indexer = None


# ==================== Internal ====================


async def _create_knowledge_manager():
    """
    Create and initialize LocalKnowledgeManager from instance config.

    Reads knowledge config from the active instance:
    - enabled: bool
    - semantic_enabled: bool
    - embedding_provider: str
    - embedding_model: str | None
    """
    from core.knowledge.local_search import LocalKnowledgeManager

    config = _load_knowledge_config()

    if not config.get("enabled", True):
        logger.info("Knowledge module disabled in config")
        km = LocalKnowledgeManager(
            fts5_enabled=True,
            semantic_enabled=False,
        )
        await km.initialize()
        return km

    semantic_enabled = config.get("semantic_enabled", False)
    embedding_provider = config.get("embedding_provider", "auto")
    embedding_model = config.get("embedding_model") or None

    km = LocalKnowledgeManager(
        fts5_enabled=True,
        semantic_enabled=semantic_enabled,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
    )

    await km.initialize()

    stats = await km.get_stats()
    logger.info(
        f"Knowledge manager initialized: "
        f"fts5={stats['fts5_enabled']}, "
        f"semantic={stats['semantic_enabled']}, "
        f"docs={stats['total_docs']}"
    )

    return km


def _load_knowledge_config() -> dict:
    """
    Load knowledge config from active instance's config.yaml.

    Reads AGENT_INSTANCE env var to locate the instance directory,
    then parses the knowledge section from config.yaml.

    Returns:
        Knowledge config dict (defaults if not found)
    """
    import os

    import yaml

    instance_name = os.getenv("AGENT_INSTANCE", "")
    if not instance_name:
        return {"enabled": True, "semantic_enabled": False}

    try:
        config_path = Path(f"instances/{instance_name}/config.yaml")
        if not config_path.exists():
            return {"enabled": True, "semantic_enabled": False}

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        return config.get("knowledge", {})

    except Exception as e:
        logger.debug(f"Failed to load knowledge config: {e}")
        return {"enabled": True, "semantic_enabled": False}

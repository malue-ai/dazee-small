"""
SQLite 数据库管理模块

提供数据库初始化、连接管理和基础操作
"""

import aiosqlite
import json
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_path: str = "workspace/database/zenflux.db"):
        """
        初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    async def init_database(self):
        """初始化数据库表结构"""
        async with aiosqlite.connect(self.db_path) as db:
            # 创建用户表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT,
                    email TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            
            # 创建对话表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT DEFAULT '新对话',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            
            # 创建消息表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            """)
            
            # 创建索引
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_user_id 
                ON conversations(user_id)
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id 
                ON messages(conversation_id)
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_created_at 
                ON messages(created_at)
            """)
            
            await db.commit()
            logger.info(f"数据库初始化完成: {self.db_path}")
    
    def get_connection(self) -> aiosqlite.Connection:
        """
        获取数据库连接
        
        注意：返回的是未启动的连接对象，需要配合 async with 使用
        
        Returns:
            数据库连接对象
        """
        return aiosqlite.connect(self.db_path)


# 全局数据库管理器实例
db_manager = DatabaseManager()


async def init_db():
    """初始化数据库（启动时调用）"""
    await db_manager.init_database()


def serialize_metadata(metadata: Optional[dict]) -> str:
    """序列化元数据为 JSON 字符串"""
    if metadata is None:
        return "{}"
    return json.dumps(metadata, ensure_ascii=False)


def deserialize_metadata(metadata_str: str) -> dict:
    """反序列化 JSON 字符串为元数据字典"""
    try:
        return json.loads(metadata_str)
    except (json.JSONDecodeError, TypeError):
        return {}


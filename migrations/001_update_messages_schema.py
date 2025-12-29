"""
数据库迁移脚本：更新 messages 表结构

变更内容：
1. id: INTEGER → TEXT (UUID)
2. 新增字段: status (TEXT)
3. 新增字段: score (REAL)
4. 新增字段: step_index (INTEGER)
"""

import aiosqlite
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "workspace/database/zenflux.db"


async def migrate():
    """执行数据库迁移"""
    db_path = Path(DB_PATH)
    
    if not db_path.exists():
        logger.info("数据库不存在，无需迁移")
        return
    
    logger.info(f"开始迁移数据库: {DB_PATH}")
    
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. 检查是否已经迁移过（检查字段是否存在）
        cursor = await db.execute("PRAGMA table_info(messages)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if "status" in column_names:
            logger.info("✅ 数据库已经是最新版本，无需迁移")
            return
        
        logger.info("开始迁移 messages 表...")
        
        # 2. 备份旧表
        await db.execute("ALTER TABLE messages RENAME TO messages_old")
        logger.info("✅ 旧表已备份为 messages_old")
        
        # 3. 创建新表结构
        await db.execute("""
            CREATE TABLE messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT,
                score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)
        logger.info("✅ 新表结构已创建")
        
        # 4. 迁移数据（id 从自增整数转换为 UUID）
        cursor = await db.execute("SELECT * FROM messages_old")
        old_messages = await cursor.fetchall()
        
        if old_messages:
            from uuid import uuid4
            
            for row in old_messages:
                old_id = row[0]
                conversation_id = row[1]
                role = row[2]
                content = row[3]
                created_at = row[4]
                metadata = row[5] if len(row) > 5 else '{}'
                
                # 生成新的 UUID
                new_id = f"msg_{uuid4().hex[:24]}"
                
                await db.execute(
                    """
                    INSERT INTO messages 
                    (id, conversation_id, role, content, status, score, created_at, metadata)
                    VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)
                    """,
                    (new_id, conversation_id, role, content, created_at, metadata)
                )
            
            logger.info(f"✅ 已迁移 {len(old_messages)} 条消息")
        
        # 5. 重新创建索引
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_conversation_id 
            ON messages(conversation_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_created_at 
            ON messages(created_at)
        """)
        logger.info("✅ 索引已重建")
        
        await db.commit()
        
        logger.info("✅ 数据库迁移完成！")
        logger.info("提示：旧数据仍保留在 messages_old 表中，确认无误后可手动删除")
        logger.info("删除命令：DROP TABLE messages_old;")


async def rollback():
    """回滚迁移（如果出错）"""
    logger.warning("开始回滚迁移...")
    
    async with aiosqlite.connect(DB_PATH) as db:
        # 检查是否有备份表
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages_old'"
        )
        if not await cursor.fetchone():
            logger.error("❌ 未找到备份表 messages_old，无法回滚")
            return
        
        # 删除新表
        await db.execute("DROP TABLE IF EXISTS messages")
        
        # 恢复旧表
        await db.execute("ALTER TABLE messages_old RENAME TO messages")
        
        await db.commit()
        
        logger.info("✅ 回滚完成，已恢复到旧版本")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        asyncio.run(rollback())
    else:
        asyncio.run(migrate())


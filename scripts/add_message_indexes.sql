-- ============================================================
-- 消息会话管理框架 - 数据库索引优化脚本
-- ============================================================
-- 
-- 用途：添加缺失的复合索引，优化分页查询性能
-- 
-- 执行方式：
--   psql -h <host> -U <user> -d <database> -f scripts/add_message_indexes.sql
-- 
-- 或使用 Python：
--   python scripts/add_message_indexes.py
-- ============================================================

-- ============================================================
-- 1. 消息表复合索引（分页查询必需）
-- ============================================================
-- 用途：优化基于 conversation_id 和 created_at 的分页查询
-- 查询场景：WHERE conversation_id = ? AND created_at < ? ORDER BY created_at DESC

CREATE INDEX IF NOT EXISTS idx_messages_conv_created 
ON messages(conversation_id, created_at ASC);

-- ============================================================
-- 2. 对话表复合索引（对话列表查询优化）
-- ============================================================
-- 用途：优化用户对话列表查询
-- 查询场景：WHERE user_id = ? ORDER BY updated_at DESC

CREATE INDEX IF NOT EXISTS idx_conversations_user_updated 
ON conversations(user_id, updated_at DESC);

-- ============================================================
-- 3. 消息表 status 索引（可选，用于查询流式消息）
-- ============================================================
-- 用途：优化查询未完成的流式消息（用于后台清理任务）
-- 查询场景：WHERE status = 'streaming' AND created_at < ?

-- PostgreSQL 支持部分索引
CREATE INDEX IF NOT EXISTS idx_messages_status 
ON messages(status) 
WHERE status = 'streaming';

-- SQLite 不支持部分索引，使用普通索引
-- CREATE INDEX IF NOT EXISTS idx_messages_status 
-- ON messages(status);

-- ============================================================
-- 4. 验证索引创建
-- ============================================================

-- 查询所有索引
-- SELECT indexname, indexdef 
-- FROM pg_indexes 
-- WHERE tablename IN ('messages', 'conversations')
-- ORDER BY tablename, indexname;

-- ============================================================
-- 完成
-- ============================================================

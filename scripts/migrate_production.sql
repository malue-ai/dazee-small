-- ============================================================================
-- Production 数据库迁移脚本
-- 同步 STAGING -> PRODUCTION 表结构
-- 执行前请备份数据库！
-- ============================================================================

-- 开始事务
BEGIN;

-- ============================================================================
-- 1. 创建 fc_function_pool 表（PRODUCTION 缺失）
-- ============================================================================
CREATE TABLE IF NOT EXISTS fc_function_pool (
    id VARCHAR(64) PRIMARY KEY,
    function_name VARCHAR(128) NOT NULL,
    http_trigger_url VARCHAR(512) NULL,
    session_id VARCHAR(128) NULL,
    status INTEGER NOT NULL DEFAULT 0,
    conversation_id VARCHAR(64) NULL,
    user_id VARCHAR(64) NULL,
    oss_bucket_path VARCHAR(256) NULL,
    oss_mount_dir VARCHAR(256) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    allocated_at TIMESTAMP NULL,
    session_expire_at TIMESTAMP NULL,
    last_active_at TIMESTAMP NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);

-- fc_function_pool 索引
CREATE UNIQUE INDEX IF NOT EXISTS ix_fc_function_pool_function_name ON fc_function_pool(function_name);
CREATE INDEX IF NOT EXISTS ix_fc_function_pool_status ON fc_function_pool(status);
CREATE INDEX IF NOT EXISTS ix_fc_function_pool_session_id ON fc_function_pool(session_id);
CREATE INDEX IF NOT EXISTS ix_fc_function_pool_conversation_id ON fc_function_pool(conversation_id);
CREATE INDEX IF NOT EXISTS ix_fc_pool_conversation ON fc_function_pool(conversation_id);
CREATE INDEX IF NOT EXISTS ix_fc_pool_status_created ON fc_function_pool(status, created_at);

-- ============================================================================
-- 2. sandboxes 表添加缺失的列
-- ============================================================================
ALTER TABLE sandboxes 
ADD COLUMN IF NOT EXISTS active_project_path VARCHAR(256) NULL;

ALTER TABLE sandboxes 
ADD COLUMN IF NOT EXISTS active_project_stack VARCHAR(32) NULL;

-- ============================================================================
-- 3. users 表：修改 updated_at 允许 NULL（可选，取决于业务需求）
-- ============================================================================
-- 注意：如果 production 有数据且 updated_at 有 NOT NULL 约束，需要先确保所有行都有值
-- ALTER TABLE users ALTER COLUMN updated_at DROP NOT NULL;

-- ============================================================================
-- 4. messages 表：status 列类型不一致（varchar(32) vs text）
-- ============================================================================
-- 注意：varchar(32) -> text 是兼容的，通常不需要修改
-- 如果要统一为 text，可以执行：
-- ALTER TABLE messages ALTER COLUMN status TYPE TEXT;

-- ============================================================================
-- 5. 添加缺失的索引
-- ============================================================================

-- conversations 表索引
CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations(status);
CREATE INDEX IF NOT EXISTS ix_conversations_updated_at ON conversations(updated_at);

-- messages 表索引
CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status);
CREATE INDEX IF NOT EXISTS ix_messages_created_at ON messages(created_at);

-- ============================================================================
-- 6. 可选：同步 users 表索引（根据实际需求）
-- ============================================================================
-- STAGING 有 ix_users_email，PRODUCTION 有 ix_users_username
-- 如果两边都需要，可以添加缺失的：
-- CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);  -- 如果有 email 列
-- CREATE INDEX IF NOT EXISTS ix_users_username ON users(username);

-- 提交事务
COMMIT;

-- ============================================================================
-- 验证：执行后检查表结构
-- ============================================================================
-- \d fc_function_pool
-- \d sandboxes
-- \d messages
-- \d conversations

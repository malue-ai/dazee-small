# 消息会话框架端到端测试

本目录包含消息会话管理框架的端到端测试脚本，用于验证在真实数据库和 Redis 环境下的功能。

## 测试文件

1. **test_connectivity.py** - 服务器连通性测试
   - PostgreSQL 连接测试
   - Redis 连接测试（支持 TLS）
   - 数据库表结构验证

2. **test_schema_io.py** - Schema IO 读写测试
   - User 表 CRUD 操作
   - Conversation 表 CRUD 操作
   - Message 表 CRUD 操作（包括状态流转和 metadata 深度合并）
   - Redis Streams 操作

3. **test_e2e_flow.py** - 端到端流程测试
   - 阶段一：占位消息创建
   - 流式传输模拟
   - 阶段二：最终消息更新
   - 完整流程验证

4. **fixtures.py** - 测试数据和工具函数
   - Mock 数据生成函数
   - 测试数据清理函数

## 运行测试

### 部署环境

支持两种部署环境：

1. **本地测试环境**（默认，`DEPLOYMENT_ENV=local`）：使用本地 Redis，便于开发和验证
2. **AWS 生产部署环境**（`DEPLOYMENT_ENV=aws`）：使用 AWS MemoryDB，生产环境部署

> 📖 **详细配置说明**：请参考 [CONFIG_GUIDE.md](./CONFIG_GUIDE.md)

### 前置条件

1. 确保已安装所有依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. **本地测试环境**需要本地 Redis：
   ```bash
   # 方式1：使用 Homebrew
   brew install redis
   brew services start redis
   
   # 方式2：使用 Docker
   docker run -d --name redis-test -p 6379:6379 redis:7-alpine
   
   # 方式3：使用启动脚本（自动检测并启动）
   bash tests/e2e_message_session/start_local_redis.sh
   ```

### 运行测试

#### 方式1：使用测试脚本（推荐）

```bash
# 本地测试模式（默认，使用本地 Redis）
bash tests/e2e_message_session/run_tests.sh

# 部署发布模式（使用 AWS MemoryDB）
TEST_MODE=production bash tests/e2e_message_session/run_tests.sh
```

#### 方式2：运行单个测试

```bash
# 本地测试环境
DEPLOYMENT_ENV=local python tests/e2e_message_session/test_connectivity.py
DEPLOYMENT_ENV=local python tests/e2e_message_session/test_schema_io.py
DEPLOYMENT_ENV=local python tests/e2e_message_session/test_e2e_flow.py

# AWS 生产部署环境
DEPLOYMENT_ENV=aws python tests/e2e_message_session/test_connectivity.py
DEPLOYMENT_ENV=aws python tests/e2e_message_session/test_schema_io.py
DEPLOYMENT_ENV=aws python tests/e2e_message_session/test_e2e_flow.py
```

### 配置说明

部署环境配置由 `config.py` 管理，通过环境变量 `DEPLOYMENT_ENV` 控制：

- `DEPLOYMENT_ENV=local` 或 `development`（默认）：使用本地 Redis (`redis://localhost:6379/0`)
- `DEPLOYMENT_ENV=aws` 或 `production`：使用 AWS MemoryDB（带 TLS）

## 测试环境配置

测试脚本中已配置以下连接信息：

- **PostgreSQL**:
  - Host: `zen0-backend-staging-postgresql.cz0gu26m8g6c.ap-southeast-1.rds.amazonaws.com`
  - Database: `zen0_staging_pg`

- **Redis (MemoryDB)**:
  - Host: `clustercfg.zen0-backend-staging-memorydb.w9tdej.memorydb.ap-southeast-1.amazonaws.com`
  - TLS: 启用

## 测试数据

所有测试数据使用 `test_e2e_` 前缀，便于识别和清理。

测试完成后会自动清理测试数据，但如果测试中断，可能需要手动清理。

## 注意事项

1. **安全性**：测试脚本中包含敏感信息（密码），生产环境应使用环境变量或配置文件
2. **隔离性**：每个测试使用独立的测试数据，避免相互影响
3. **幂等性**：测试可以重复运行，不会因为数据已存在而失败
4. **清理**：测试后会自动清理测试数据，避免污染生产数据

## 故障排查

### PostgreSQL 连接失败

- 检查网络连接
- 验证数据库连接信息
- 确认数据库表已创建

### Redis 连接失败

- 检查 TLS 配置是否正确
- 验证 Redis URL 格式（使用 `rediss://` 前缀）
- 确认 Redis 服务可访问

### 测试数据清理失败

- 检查外键约束
- 手动删除测试数据（使用 `test_e2e_` 前缀查找）

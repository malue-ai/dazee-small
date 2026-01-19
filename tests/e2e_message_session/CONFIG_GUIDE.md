# 部署环境配置指南

## 概述

系统支持两种部署环境，用于不同的使用场景：

1. **本地测试环境**（`DEPLOYMENT_ENV=local` 或 `development`）：使用本地 Redis，便于开发和快速验证
2. **AWS 生产部署环境**（`DEPLOYMENT_ENV=aws` 或 `production`）：使用 AWS MemoryDB，生产环境部署

## 配置管理

配置由 `config.py` 统一管理，通过环境变量 `DEPLOYMENT_ENV` 控制：

```bash
# 本地测试环境（默认）
export DEPLOYMENT_ENV=local  # 或 development
# 使用 redis://localhost:6379/0

# AWS 生产部署环境
export DEPLOYMENT_ENV=aws  # 或 production
# 使用 AWS MemoryDB（带 TLS）
```

## 本地测试环境

### 适用场景

- 开发环境验证
- 功能测试
- 快速迭代

### 前置条件

1. **安装 Redis**：
   ```bash
   # macOS
   brew install redis
   brew services start redis
   
   # 或使用 Docker
   docker run -d --name redis-test -p 6379:6379 redis:7-alpine
   ```

2. **验证 Redis 运行**：
   ```bash
   redis-cli ping
   # 应返回: PONG
   ```

### 运行测试

```bash
# 方式1：使用测试脚本（推荐）
bash tests/e2e_message_session/run_tests.sh

# 方式2：直接运行（默认就是本地环境）
DEPLOYMENT_ENV=local python tests/e2e_message_session/test_connectivity.py
DEPLOYMENT_ENV=local python tests/e2e_message_session/test_schema_io.py
DEPLOYMENT_ENV=local python tests/e2e_message_session/test_e2e_flow.py
```

## AWS 生产部署环境

### 适用场景

- 生产环境验证
- 部署前测试
- AWS 环境集成测试

### 前置条件

1. **网络连接**：确保可以访问 AWS MemoryDB（可能需要 VPN）
2. **TLS 配置**：Redis 客户端已正确配置 TLS（在 `infra/cache/redis.py` 中）

### 运行测试

```bash
# 使用测试脚本
DEPLOYMENT_ENV=aws bash tests/e2e_message_session/run_tests.sh

# 或直接运行
DEPLOYMENT_ENV=aws python tests/e2e_message_session/test_connectivity.py
DEPLOYMENT_ENV=aws python tests/e2e_message_session/test_schema_io.py
DEPLOYMENT_ENV=aws python tests/e2e_message_session/test_e2e_flow.py
```

## 配置详情

### PostgreSQL 配置

两种模式使用相同的 PostgreSQL 配置（AWS RDS）：

```python
DATABASE_URL = (
    "postgresql+asyncpg://postgres:924Ff8O5kfEWOvzj3nN1ricrWVTIHSy8@"
    "zen0-backend-staging-postgresql.cz0gu26m8g6c.ap-southeast-1.rds.amazonaws.com:5432/"
    "zen0_staging_pg"
)
```

### Redis 配置

#### 本地测试环境

```python
REDIS_URL = "redis://localhost:6379/0"
# 无 TLS，无认证
```

#### AWS 生产部署环境

```python
REDIS_URL = (
    "rediss://agentuser:y05EtW8goYEBOpMYB52lPh8qHnRZggcc@"
    "clustercfg.zen0-backend-staging-memorydb.w9tdej.memorydb.ap-southeast-1.amazonaws.com:6379"
)
# 带 TLS（rediss://），需要认证
```

## 环境变量

测试脚本会自动设置以下环境变量：

- `DATABASE_URL`: PostgreSQL 连接字符串
- `REDIS_URL`: Redis 连接字符串

这些环境变量会在导入 `config.py` 时自动设置，确保所有测试使用一致的配置。

## 故障排查

### 本地 Redis 连接失败

```bash
# 检查 Redis 是否运行
redis-cli ping

# 如果未运行，启动 Redis
brew services start redis
# 或
docker start redis-test
```

### AWS MemoryDB 连接失败

1. **检查网络连接**：
   ```bash
   telnet clustercfg.zen0-backend-staging-memorydb.w9tdej.memorydb.ap-southeast-1.amazonaws.com 6379
   ```

2. **检查 VPN**：确保已连接到 AWS VPN

3. **检查 TLS 配置**：查看 `infra/cache/redis.py` 中的 TLS 设置

4. **使用本地模式**：如果网络问题无法解决，先使用本地模式验证功能

## 最佳实践

1. **开发阶段**：使用本地测试模式，快速迭代
2. **部署前**：使用部署发布模式，验证生产配置
3. **CI/CD**：根据环境自动选择模式
4. **文档同步**：确保配置变更及时更新文档

## 配置迁移

从本地测试环境切换到 AWS 生产部署环境：

```bash
# 1. 确保网络连接正常（VPN）
# 2. 设置环境变量
export DEPLOYMENT_ENV=aws

# 3. 运行测试
bash tests/e2e_message_session/run_tests.sh
```

从 AWS 生产部署环境切换回本地测试环境：

```bash
# 1. 确保本地 Redis 运行
redis-cli ping

# 2. 设置环境变量（或不设置，默认就是 local）
export DEPLOYMENT_ENV=local

# 3. 运行测试
bash tests/e2e_message_session/run_tests.sh
```

## 在应用代码中使用

在应用代码中，可以通过环境变量来区分部署环境：

```python
import os

DEPLOYMENT_ENV = os.getenv("DEPLOYMENT_ENV", "local")

if DEPLOYMENT_ENV in ("local", "development"):
    # 本地测试环境配置
    REDIS_URL = "redis://localhost:6379/0"
elif DEPLOYMENT_ENV in ("aws", "production"):
    # AWS 生产部署环境配置
    REDIS_URL = os.getenv("REDIS_URL")  # 从环境变量或 Secrets Manager 读取
```

## 部署环境变量设置

### 本地开发/测试环境

在 `.env` 文件中设置：
```bash
DEPLOYMENT_ENV=local
REDIS_URL=redis://localhost:6379/0
```

### AWS 生产部署环境

在 AWS ECS Task Definition 或 Kubernetes ConfigMap/Secret 中设置：
```bash
DEPLOYMENT_ENV=aws
REDIS_URL=rediss://agentuser:password@clustercfg.zen0-backend-staging-memorydb.w9tdej.memorydb.ap-southeast-1.amazonaws.com:6379
```

或者使用 AWS Secrets Manager：
```python
import boto3

secrets_client = boto3.client('secretsmanager')
secret = secrets_client.get_secret_value(SecretId='zenflux/redis')
redis_config = json.loads(secret['SecretString'])
```

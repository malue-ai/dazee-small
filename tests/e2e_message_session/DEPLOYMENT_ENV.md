# 部署环境配置说明

## 概述

系统支持两种部署环境，用于不同的使用场景：

1. **本地测试环境**：用于本地开发、测试和验证
2. **AWS 生产部署环境**：用于 AWS 生产环境部署

## 环境变量

通过 `DEPLOYMENT_ENV` 环境变量来区分部署环境：

```bash
# 本地测试环境
export DEPLOYMENT_ENV=local
# 或
export DEPLOYMENT_ENV=development

# AWS 生产部署环境
export DEPLOYMENT_ENV=aws
# 或
export DEPLOYMENT_ENV=production
```

## 配置差异

### 本地测试环境

- **Redis**: `redis://localhost:6379/0`（本地 Redis，无 TLS）
- **用途**: 本地开发、功能测试、快速验证
- **前置条件**: 需要本地 Redis 运行

### AWS 生产部署环境

- **Redis**: AWS MemoryDB（带 TLS，需要认证）
- **用途**: 生产环境部署
- **前置条件**: 
  - 需要 VPN 连接到 AWS 网络
  - 需要正确的 TLS 配置
  - 需要认证信息

## 在应用代码中使用

### 方式1：通过环境变量

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

### 方式2：使用配置类

```python
from tests.e2e_message_session.config import DeploymentConfig

if DeploymentConfig.is_local_env():
    # 本地测试环境逻辑
    pass
elif DeploymentConfig.is_aws_env():
    # AWS 生产部署环境逻辑
    pass
```

## 部署配置示例

### 本地开发环境（.env 文件）

```bash
DEPLOYMENT_ENV=local
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/db
REDIS_URL=redis://localhost:6379/0
```

### AWS 生产环境（ECS Task Definition / Kubernetes）

```bash
DEPLOYMENT_ENV=aws
DATABASE_URL=postgresql+asyncpg://user:pass@rds-endpoint:5432/db
REDIS_URL=rediss://user:pass@memorydb-endpoint:6379
```

或使用 AWS Secrets Manager：

```python
import boto3
import json

secrets_client = boto3.client('secretsmanager')
secret = secrets_client.get_secret_value(SecretId='zenflux/redis')
redis_config = json.loads(secret['SecretString'])

REDIS_URL = redis_config['url']
```

## 测试脚本使用

### 本地测试环境

```bash
# 默认就是本地环境
bash tests/e2e_message_session/run_tests.sh

# 或显式指定
DEPLOYMENT_ENV=local bash tests/e2e_message_session/run_tests.sh
```

### AWS 生产部署环境

```bash
# 需要 VPN 连接
DEPLOYMENT_ENV=aws bash tests/e2e_message_session/run_tests.sh
```

## 注意事项

1. **环境变量优先级**: 环境变量 `DEPLOYMENT_ENV` 会覆盖默认值
2. **向后兼容**: 为了兼容旧代码，`TestConfig` 仍然可用，但建议使用 `DeploymentConfig`
3. **配置安全**: 生产环境的敏感信息（如密码）应使用 Secrets Manager 或环境变量，不要硬编码
4. **网络要求**: AWS 生产环境需要 VPN 连接才能访问 MemoryDB

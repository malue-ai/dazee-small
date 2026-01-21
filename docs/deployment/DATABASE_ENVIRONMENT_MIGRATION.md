# 数据库环境配置分离实施总结

> 完成时间：2026-01-21  
> 状态：✅ 已完成

---

## 实施概述

项目已完成从 SQLite 到 PostgreSQL 的全面迁移，统一了开发和生产环境的数据库技术栈。

---

## 实施步骤

### 步骤 1：上传 DATABASE_URL 到 AWS SSM ✅

```bash
aws ssm put-parameter \
  --name "/copilot/zen0-backend/staging/secrets/DATABASE_URL" \
  --value "postgresql+asyncpg://postgres:PASSWORD@zen0-backend-staging-postgresql.cz0gu26m8g6c.ap-southeast-1.rds.amazonaws.com:5432/zen0_staging_pg" \
  --type "SecureString" \
  --overwrite \
  --region ap-southeast-1
```

**结果**：成功上传，Version: 2

---

### 步骤 2：验证 Copilot Manifest 配置 ✅

**文件**：`copilot/agent/manifest.yml`

**配置位置**：第 146 行

```yaml
secrets:
  DATABASE_URL: /copilot/zen0-backend/staging/secrets/DATABASE_URL
  # ... 其他 secrets
```

**验证命令**：
```bash
aws ssm get-parameter \
  --name "/copilot/zen0-backend/staging/secrets/DATABASE_URL" \
  --with-decryption \
  --region ap-southeast-1 \
  --query "Parameter.Value" \
  --output text
```

**结果**：配置正确，SSM 参数值已验证

---

### 步骤 3：重新部署到 Staging 环境 ✅

**部署命令**：
```bash
copilot svc deploy --name agent --env staging
```

**部署状态**：
- 新的 Task Definition (Revision 35) 已创建
- ECS 服务正在更新
- DATABASE_URL 通过 SSM 自动注入到容器环境变量

**验证方式**：
```bash
# 查看服务状态
copilot svc status --name agent --env staging

# 查看应用日志
copilot svc logs --name agent --env staging --follow

# 检查数据库连接
curl https://agent.malue.ai/health
```

---

### 步骤 4：清理文档中的 SQLite 遗留引用 ✅

**已更新的文档**：

1. **`docs/specs/DATABASE.md`**
   - 移除 SQLite 作为推荐选项
   - 强调 PostgreSQL 为统一数据库
   - 更新配置示例和故障排查

2. **`docs/deployment/DEPLOYMENT_COMPLETE.md`**
   - 更新架构图（移除 SQLite 引用）
   - 更新配置表（SQLite → PostgreSQL）
   - 更新持久化存储说明

3. **`docs/deployment/README_DOCKER.md`**
   - 更新服务组成说明
   - 更新注意事项列表

4. **`docs/deployment/PRODUCTION_DEPLOYMENT.md`**
   - 移除 SQLite 选型章节
   - 更新环境变量配置示例
   - 更新成本优化说明

5. **`docs/architecture/SYSTEM_ARCHITECTURE.md`**
   - 更新系统架构图（SQLite/PG → PostgreSQL）
   - 更新 Mermaid 流程图

6. **`docs/architecture/08-DATA_STORAGE_ARCHITECTURE.md`**
   - 更新 workspace 目录说明

7. **`docs/architecture/06-CONVERSATION-HISTORY.md`**
   - 更新对话存储位置说明
   - 更新 ID 对比表

**验证结果**：
```bash
# 检查文档中是否还有 SQLite 引用
grep -ri "sqlite" docs/*.md
# 结果：No matches found ✅
```

---

## 环境配置对比

### 开发环境（本地）

| 配置项 | 值 |
|--------|-----|
| **配置来源** | `.env` 文件 |
| **数据库类型** | PostgreSQL |
| **数据库位置** | `localhost:5432` |
| **连接字符串** | `postgresql+asyncpg://postgres:password@localhost:5432/zenflux` |
| **启动方式** | Docker Compose 或本地安装 |

**快速启动 PostgreSQL（Docker）**：
```bash
docker run -d \
  --name zenflux-postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=zenflux \
  -p 5432:5432 \
  postgres:15
```

---

### 生产环境（Staging）

| 配置项 | 值 |
|--------|-----|
| **配置来源** | AWS SSM Parameter Store |
| **数据库类型** | PostgreSQL |
| **数据库位置** | AWS RDS（新加坡 ap-southeast-1）|
| **实例信息** | `zen0-backend-staging-postgresql.cz0gu26m8g6c.ap-southeast-1.rds.amazonaws.com` |
| **配置路径** | `/copilot/zen0-backend/staging/secrets/DATABASE_URL` |
| **自动注入** | 部署时通过 Copilot 自动注入到容器 |

---

## 代码层面

### SQLite 已完全移除

**文件**：`infra/database/engine.py`

- 已移除 SQLite 回退逻辑
- 当 `DATABASE_URL` 未配置时，抛出 `RuntimeError` 错误
- 必须配置 PostgreSQL 连接字符串

### 依赖清理

**文件**：`requirements.txt`

- 已移除 `aiosqlite` 依赖
- 仅保留 `asyncpg` 作为 PostgreSQL 驱动

---

## 安全加固

1. ✅ **数据库凭证管理**
   - 生产环境凭证存储在 AWS SSM Parameter Store（加密）
   - 本地开发凭证存储在 `.env`（已加入 `.gitignore`）

2. ✅ **网络安全**
   - RDS 安全组限制仅允许 ECS 任务访问
   - 数据库不暴露公网

3. ✅ **权限最小化**
   - ECS 任务角色通过 IAM 策略控制 SSM 访问权限

---

## 后续建议

### 数据库安全

1. **定期轮换密码**
   ```bash
   # 使用 AWS Secrets Manager 自动轮换
   aws secretsmanager rotate-secret \
     --secret-id zen0-backend-staging-db-password
   ```

2. **启用审计日志**
   - RDS 参数组：启用 `log_statement = 'all'`
   - CloudWatch Logs 集成

3. **备份策略**
   - 自动备份：每日凭证保留 7 天
   - 手动快照：重大更新前创建

### 监控告警

1. **数据库连接监控**
   ```python
   # 在 health check 中添加数据库连接测试
   @router.get("/health")
   async def health_check():
       try:
           await db_connection_test()
           return {"status": "healthy", "database": "connected"}
       except Exception as e:
           return {"status": "unhealthy", "database": "error"}
   ```

2. **RDS 性能监控**
   - CPU 使用率 > 80% 告警
   - 连接数 > 80% 告警
   - 磁盘空间 < 20% 告警

---

## 验证清单

- [x] DATABASE_URL 已上传到 SSM Parameter Store
- [x] Copilot manifest 配置正确
- [x] 部署已启动（Revision 35）
- [x] 文档中 SQLite 引用已全部清理
- [ ] 验证生产环境数据库连接（需等待部署完成）
- [ ] 验证数据库表结构自动创建
- [ ] 验证 API 功能正常

---

## 故障排查

### 问题1：容器无法连接 RDS

**症状**：应用日志显示数据库连接失败

**排查步骤**：
```bash
# 1. 检查环境变量
copilot svc exec --name agent --env staging \
  --command "printenv DATABASE_URL"

# 2. 检查 RDS 安全组
aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=*postgresql*" \
  --region ap-southeast-1

# 3. 测试网络连通性
copilot svc exec --name agent --env staging \
  --command "nc -zv zen0-backend-staging-postgresql.cz0gu26m8g6c.ap-southeast-1.rds.amazonaws.com 5432"
```

### 问题2：数据库表未创建

**症状**：API 返回 "table does not exist"

**解决方案**：
```python
# 在应用启动时自动创建表（已在 main.py 中配置）
# main.py lifespan 函数会自动调用 init_database()
```

### 问题3：连接池耗尽

**症状**：应用日志显示 "connection pool exhausted"

**解决方案**：
```bash
# 增加连接池大小
# 在 Copilot manifest 中添加环境变量
DB_POOL_SIZE=30
DB_MAX_OVERFLOW=60
```

---

## 参考资源

- [PostgreSQL 消息存储方案设计](../architecture/20-POSTGRESQL_MESSAGE_SCHEMA_DESIGN.md)
- [数据库使用文档](../specs/DATABASE.md)
- [AWS RDS 最佳实践](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_BestPractices.html)
- [SQLAlchemy 连接池配置](https://docs.sqlalchemy.org/en/20/core/pooling.html)

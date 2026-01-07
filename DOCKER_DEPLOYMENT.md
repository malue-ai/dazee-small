# 🐳 Zenflux Agent Docker 部署指南

## 快速开始（5 分钟部署）

### 1. 准备环境

确保服务器已安装：
- Docker 20.10+
- Docker Compose 2.0+

```bash
# 检查 Docker 版本
docker --version
docker compose version

# 如果没有安装，使用以下命令安装
curl -fsSL https://get.docker.com | sh
```

### 2. 克隆项目

```bash
# 克隆代码
git clone <your-repo-url> zenflux_agent
cd zenflux_agent
```

### 3. 配置环境变量

```bash
# 复制示例配置
cp .env.example .env

# 编辑配置文件，填入你的 API Keys
vim .env  # 或使用 nano
```

**必须配置的环境变量：**

```bash
# Claude API Key（必需）
ANTHROPIC_API_KEY=sk-ant-xxxxx

# E2B Sandbox API Key（必需）
E2B_API_KEY=e2b_xxxxx

# 数据库密码（建议修改）
DB_PASSWORD=your_secure_password_here

# Redis 密码（可选，生产环境建议设置）
REDIS_PASSWORD=your_redis_password
```

### 4. 启动服务

```bash
# 构建并启动所有服务
docker compose up -d

# 查看日志
docker compose logs -f

# 查看服务状态
docker compose ps
```

### 5. 验证部署

```bash
# 检查后端健康状态
curl http://localhost:8000/health

# 访问前端
open http://localhost:3000

# 访问 API 文档
open http://localhost:8000/docs
```

---

## 📦 服务说明

### 服务列表

| 服务 | 端口 | 说明 |
|------|------|------|
| backend | 8000 | FastAPI 后端服务 |
| frontend | 3000 | Vue 3 前端界面 |
| redis | 6379 | Session 和 SSE 管理 |
| postgres | 5432 | 主数据库 |

### 服务依赖关系

```
frontend (Nginx)
    ↓
backend (FastAPI)
    ↓
  ├─→ redis
  └─→ postgres
```

---

## 🛠️ 常用命令

### 启动和停止

```bash
# 启动所有服务
docker compose up -d

# 停止所有服务
docker compose down

# 停止并删除数据卷（⚠️ 会清空数据库）
docker compose down -v

# 重启单个服务
docker compose restart backend
docker compose restart frontend
```

### 查看日志

```bash
# 查看所有服务日志
docker compose logs -f

# 查看特定服务日志
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f postgres

# 查看最近 100 行日志
docker compose logs --tail=100 backend
```

### 进入容器

```bash
# 进入后端容器
docker compose exec backend bash

# 进入 PostgreSQL 容器
docker compose exec postgres psql -U zenflux -d zenflux

# 进入 Redis 容器
docker compose exec redis redis-cli
```

### 更新部署

```bash
# 拉取最新代码
git pull

# 重新构建镜像
docker compose build --no-cache

# 重启服务
docker compose up -d

# 查看运行状态
docker compose ps
```

---

## 🔧 数据库管理

### 运行数据库迁移

```bash
# 方式 1：在宿主机运行（需要 Python 环境）
python migrations/001_update_messages_schema.py

# 方式 2：在容器内运行
docker compose exec backend python migrations/001_update_messages_schema.py
```

### 数据备份

```bash
# 备份 PostgreSQL 数据库
docker compose exec postgres pg_dump -U zenflux zenflux > backup_$(date +%Y%m%d).sql

# 恢复数据库
docker compose exec -T postgres psql -U zenflux zenflux < backup_20240101.sql
```

### 清空数据

```bash
# 清空 Redis 缓存
docker compose exec redis redis-cli FLUSHALL

# 重置数据库（⚠️ 慎用）
docker compose down -v
docker compose up -d
```

---

## 📊 监控和调试

### 查看资源使用情况

```bash
# 查看容器资源使用
docker stats

# 查看特定容器资源
docker stats zenflux-backend zenflux-frontend
```

### 健康检查

```bash
# 检查所有服务健康状态
docker compose ps

# 手动测试后端健康检查
curl http://localhost:8000/health

# 测试 Redis 连接
docker compose exec redis redis-cli ping

# 测试 PostgreSQL 连接
docker compose exec postgres pg_isready -U zenflux
```

### 调试模式

```bash
# 在 .env 中启用调试模式
DEBUG_MODE=true
LOG_LEVEL=DEBUG

# 重启后端服务
docker compose restart backend

# 查看详细日志
docker compose logs -f backend
```

---

## 🔐 安全配置（生产环境）

### 1. 修改默认密码

```bash
# 在 .env 中设置强密码
DB_PASSWORD=使用强密码！@#$
REDIS_PASSWORD=使用强密码！@#$
```

### 2. 限制 CORS 域名

修改 `main.py` 中的 CORS 配置：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://yourdomain.com",
        "https://www.yourdomain.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 3. 使用 HTTPS

```bash
# 使用 Nginx 反向代理 + Let's Encrypt
# 或使用 Caddy（自动 HTTPS）
```

### 4. 限制端口访问

```yaml
# 在 docker-compose.yml 中移除不必要的端口映射
# 例如，只暴露前端端口，后端通过内网访问
services:
  backend:
    # ports:
    #   - "8000:8000"  # 不直接暴露
    expose:
      - "8000"  # 仅内网可访问
```

---

## 🚀 性能优化

### 1. 调整资源限制

编辑 `docker-compose.yml`：

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

### 2. Redis 持久化优化

```yaml
redis:
  command: >
    redis-server
    --requirepass ${REDIS_PASSWORD}
    --maxmemory 512mb
    --maxmemory-policy allkeys-lru
    --save 300 10
    --appendonly yes
    --appendfsync everysec
```

### 3. PostgreSQL 性能调优

```bash
# 进入容器编辑配置
docker compose exec postgres vi /var/lib/postgresql/data/postgresql.conf

# 调整参数（根据服务器规格）
shared_buffers = 256MB
effective_cache_size = 1GB
max_connections = 100
```

---

## 🐛 常见问题

### 问题 1：后端启动失败

```bash
# 查看详细错误日志
docker compose logs backend

# 常见原因：
# 1. 环境变量未配置
# 2. 数据库连接失败
# 3. 端口被占用
```

### 问题 2：前端无法连接后端

```bash
# 检查网络
docker network ls
docker network inspect zenflux_zenflux-network

# 检查前端 Nginx 配置
docker compose exec frontend cat /etc/nginx/conf.d/default.conf
```

### 问题 3：数据库连接失败

```bash
# 检查 PostgreSQL 是否启动
docker compose ps postgres

# 查看 PostgreSQL 日志
docker compose logs postgres

# 手动测试连接
docker compose exec backend python -c "
from infra.database import engine
import asyncio
asyncio.run(engine.connect())
"
```

### 问题 4：Redis 连接失败

```bash
# 检查 Redis 是否运行
docker compose exec redis redis-cli ping

# 如果设置了密码
docker compose exec redis redis-cli -a your_password ping
```

### 问题 5：磁盘空间不足

```bash
# 清理未使用的 Docker 资源
docker system prune -a --volumes

# 查看磁盘使用情况
docker system df
```

---

## 📝 维护建议

### 定期任务

```bash
# 每周备份数据库
0 2 * * 0 docker compose exec postgres pg_dump -U zenflux zenflux > /backup/zenflux_$(date +\%Y\%m\%d).sql

# 每月清理旧日志
0 3 1 * * find /path/to/logs -name "*.log.*" -mtime +30 -delete

# 每季度更新镜像
docker compose pull
docker compose up -d
```

### 监控指标

- CPU 和内存使用率
- 数据库连接数
- Redis 内存使用
- API 响应时间
- 错误日志数量

---

## 📞 获取帮助

如果遇到问题：

1. 查看日志：`docker compose logs -f`
2. 检查健康状态：`docker compose ps`
3. 阅读文档：`/docs/*.md`
4. 提交 Issue：[GitHub Issues]

---

## 🎉 部署成功！

现在你的 Zenflux Agent 已经在 Docker 中运行了！

- 🌐 前端地址：http://localhost:3000
- 🔌 API 地址：http://localhost:8000
- 📚 API 文档：http://localhost:8000/docs

Happy Coding! 🚀


# 🚀 Zenflux Agent 快速开始

## Docker 部署（推荐，3 分钟完成）

### 一键部署

```bash
# 1. 克隆项目
git clone <your-repo-url> zenflux_agent
cd zenflux_agent

# 2. 配置环境变量
cp env.template .env
vim .env  # 填入你的 API Keys

# 3. 一键启动
./deploy.sh
```

### 手动部署

```bash
# 1. 配置环境变量
cp env.template .env
vim .env

# 2. 启动服务
docker compose up -d

# 3. 查看日志
docker compose logs -f

# 4. 访问服务
# 前端: http://localhost:3000
# 后端: http://localhost:8000
# API 文档: http://localhost:8000/docs
```

### 必需的配置

在 `.env` 文件中配置以下内容：

```bash
# Claude API Key（必需）
ANTHROPIC_API_KEY=sk-ant-xxxxx

# E2B Sandbox API Key（必需）
E2B_API_KEY=e2b_xxxxx

# 数据库密码（建议修改）
DB_PASSWORD=your_secure_password
```

---

## 本地开发部署

### 前置要求

- Python 3.10+
- Node.js 18+
- Redis（可选，用于 SSE）
- PostgreSQL（可选，可用 SQLite）

### 后端启动

```bash
# 1. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp env.template .env
vim .env

# 4. 启动服务
python main.py
```

### 前端启动

```bash
# 1. 进入前端目录
cd frontend

# 2. 安装依赖
npm install

# 3. 启动开发服务器
npm run dev

# 4. 访问 http://localhost:5173
```

---

## 常用命令

### Docker 命令

```bash
# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f backend
docker compose logs -f frontend

# 重启服务
docker compose restart backend

# 停止服务
docker compose down

# 停止并删除数据
docker compose down -v
```

### 数据库操作

```bash
# 进入数据库
docker compose exec postgres psql -U zenflux -d zenflux

# 备份数据
docker compose exec postgres pg_dump -U zenflux zenflux > backup.sql

# 恢复数据
docker compose exec -T postgres psql -U zenflux zenflux < backup.sql
```

### 清理和更新

```bash
# 更新代码
git pull

# 重新构建
docker compose build --no-cache

# 重启服务
docker compose up -d

# 清理未使用的资源
docker system prune -a
```

---

## 验证部署

### 检查后端

```bash
# 健康检查
curl http://localhost:8000/health

# 预期响应
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00",
  "active_sessions": 0
}
```

### 检查前端

访问 http://localhost:3000，你应该看到聊天界面。

### 检查 API 文档

访问 http://localhost:8000/docs，你应该看到 Swagger UI。

---

## 故障排查

### 问题：后端启动失败

```bash
# 查看详细日志
docker compose logs backend

# 常见原因：
# 1. API Key 未配置
# 2. 数据库连接失败
# 3. 端口被占用
```

### 问题：前端无法连接后端

```bash
# 检查后端是否运行
curl http://localhost:8000/health

# 检查网络
docker network inspect zenflux_zenflux-network
```

### 问题：数据库连接失败

```bash
# 检查 PostgreSQL 状态
docker compose ps postgres

# 查看日志
docker compose logs postgres

# 重启数据库
docker compose restart postgres
```

---

## 获取帮助

- 📖 详细文档：[DOCKER_DEPLOYMENT.md](./DOCKER_DEPLOYMENT.md)
- 🏗️ 架构文档：[docs/00-ARCHITECTURE-OVERVIEW.md](./docs/00-ARCHITECTURE-OVERVIEW.md)
- 🐛 问题反馈：[GitHub Issues]

---

## 下一步

部署成功后，你可以：

1. 📝 阅读 [API 文档](http://localhost:8000/docs)
2. 🎨 访问 [前端界面](http://localhost:3000)
3. 🧪 运行测试：`docker compose exec backend pytest`
4. 📊 查看监控：`docker stats`

Happy Coding! 🎉


# 🐳 Docker 部署指南

## 快速开始

```bash
# 1. 配置环境变量
cp env.template .env
vim .env  # 填入 ANTHROPIC_API_KEY 和 E2B_API_KEY

# 2. 一键部署
./deploy.sh

# 3. 访问服务
open http://localhost:8010/docs
```

## 常用命令

```bash
# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f
docker compose logs -f backend  # 只看后端

# 重启服务
docker compose restart

# 停止服务
docker compose down

# 停止并删除数据
docker compose down -v

# 进入容器
docker compose exec backend bash

# 重新构建
docker compose build --no-cache
docker compose up -d
```

## 配置说明

### 服务组成

- **backend**: FastAPI 后端 (端口 8010)
- **redis**: Redis 缓存 (端口 6379)
- **数据库**: PostgreSQL (Docker Compose 自动启动)

### 环境变量 (.env)

必需：
- `ANTHROPIC_API_KEY` - Claude API Key
- `E2B_API_KEY` - E2B Sandbox API Key

可选：
- `REDIS_PASSWORD` - Redis 密码
- `LOG_LEVEL` - 日志级别 (默认 INFO)

### 数据持久化

以下目录会被挂载到容器：
- `workspace/` - 工作空间数据
- `logs/` - 日志文件
- `config/` - 配置文件

## 外网访问

服务默认监听 `0.0.0.0:8010`，可以从外部访问：

```bash
# 查看本机 IP
ifconfig | grep "inet "

# 从其他设备访问
# http://你的IP:8010
```

## 故障排查

### 镜像拉取失败

配置 Docker 镜像加速：

1. 打开 Docker Desktop → Settings → Docker Engine
2. 添加配置：

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://dockerproxy.com"
  ]
}
```

3. 点击 Apply & Restart

### 服务启动失败

```bash
# 查看详细日志
docker compose logs backend

# 常见问题：
# 1. API Key 未配置
# 2. 端口被占用
# 3. 内存不足
```

## 服务器部署

```bash
# 1. 上传代码
scp -r zenflux_agent ubuntu@server-ip:~/

# 2. SSH 登录
ssh ubuntu@server-ip

# 3. 配置并部署
cd zenflux_agent
cp env.template .env
vim .env  # 填入 API Keys
./deploy.sh

# 4. 访问
# http://server-ip:8010
```

## 注意事项

- ✅ 使用阿里云镜像（国内快）
- ✅ 使用清华 pip 源（依赖安装快）
- ✅ Python 3.11（稳定可靠）
- ✅ PostgreSQL 数据库（Docker Compose 自动配置）
- ✅ 监听 0.0.0.0（外网可访问）

## 技术支持

详细文档：
- `DOCKER_DEPLOYMENT.md` - 完整部署文档
- `QUICK_START.md` - 快速开始指南
- `docs/` - 架构和 API 文档


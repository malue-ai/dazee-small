# Zenflux Agent - Production 环境部署指南

## 概述

Production 环境使用 **Load Balanced Web Service** 类型，但仅提供内网 gRPC 服务，不配置公网域名。

### 服务架构

```
zen0-backend (应用)
├── staging (环境)
│   └── agent (服务) ← Load Balanced Web Service（公网 HTTP + gRPC）
│
└── production (环境)
    ├── backend (服务) ← Go 后端
    └── agent (服务) ← Load Balanced Web Service（仅内网 gRPC，不配置公网域名）
```

### 网络架构

```
┌─────────────────────────────────────────────────────────────┐
│                    VPC (私有网络)                            │
│                                                             │
│  ┌─────────────────┐      NLB / Service Connect  ┌──────────────────────┐
│  │  zen0-backend   │ ────────────────────────────│  agent               │
│  │  (Go 后端)      │      内网 gRPC 调用          │  Load Balanced Web   │
│  │  Port: 8000     │                             │  Port: 50051         │
│  └─────────────────┘                             │  1 vCPU + 2GB        │
│         │                                        └──────────────────────┘
│         │ ALB (公网)                                      │
│         ▼                                                │
│  ┌─────────────────┐                                     │
│  │  用户请求       │      内网访问地址:                   │
│  │  api.dazee.ai   │      agent.production.zen0-backend.local:50051
│  └─────────────────┘                                     │
└─────────────────────────────────────────────────────────────┘
```

### 配置对比

| 配置项 | Staging | Production |
|--------|---------|------------|
| 服务名 | agent | agent |
| 服务类型 | Load Balanced Web Service | Load Balanced Web Service |
| 网络暴露 | 公网 ALB + 内网 NLB | 仅内网 NLB（不配置公网域名） |
| gRPC 端口 | 50051 (NLB) | 50051 (NLB) |
| HTTP 端口 | 80 (ALB) | 80（仅健康检查，无公网域名） |
| 域名 | agent.malue.ai | 无（内网 DNS） |
| CPU | 0.5 vCPU | 1 vCPU |
| Memory | 1 GB | 2 GB |
| 副本数 | 1-3 | 2-10 |
| Container Insights | false | true |
| 日志级别 | DEBUG | INFO |

---

## 快速开始

### 1. 初始化 Secrets

```bash
# 交互式初始化（推荐）
./deploy/aws/production/secrets.sh init --interactive

# 或从文件初始化
./deploy/aws/production/secrets.sh export-template > secrets.production.env
# 编辑 secrets.production.env 填入实际值
./deploy/aws/production/secrets.sh init --from-env secrets.production.env
```

### 2. 验证 Secrets

```bash
./deploy/aws/production/secrets.sh verify
```

### 3. 部署服务

```bash
# 完整部署（首次）
./deploy/aws/production/production.sh deploy

# 仅部署服务（环境已存在）
./deploy/aws/production/production.sh deploy --svc-only
```

### 4. 查看状态

```bash
./deploy/aws/production/production.sh status
```

---

## 命令参考

### production.sh

```bash
# 部署
./deploy/aws/production/production.sh deploy [选项]
  --env-only          仅创建环境
  --svc-only          仅部署服务
  --skip-checks       跳过前置检查
  --skip-health       跳过健康检查
  --skip-confirm      跳过确认（CI/CD 使用）

# 回滚
./deploy/aws/production/production.sh rollback [--to-version <tag>]

# 状态
./deploy/aws/production/production.sh status

# 日志
./deploy/aws/production/production.sh logs [--follow] [--since 10m]

# 清理
./deploy/aws/production/production.sh clean
```

### secrets.sh

```bash
# 初始化
./deploy/aws/production/secrets.sh init [--interactive|--from-env <文件>]

# 创建/更新
./deploy/aws/production/secrets.sh create <名称> <值>
./deploy/aws/production/secrets.sh update <名称> <值>

# 查看
./deploy/aws/production/secrets.sh list
./deploy/aws/production/secrets.sh show <名称>
./deploy/aws/production/secrets.sh verify

# 删除
./deploy/aws/production/secrets.sh delete [--force]

# 导出模板
./deploy/aws/production/secrets.sh export-template
```

---

## Secrets 配置

Production 环境需要以下 Secrets（存储在 SSM Parameter Store）：

### 必需

| SSM 名称 | 映射到环境变量 | 说明 |
|----------|---------------|------|
| `DATABASE_URL` | `DATABASE_URL` | PostgreSQL 连接字符串 |
| `MEMORYDB_HOST` | `REDIS_HOST` | MemoryDB 主机地址 |
| `ANTHROPIC_API_KEY` | `ANTHROPIC_API_KEY` | Anthropic API 密钥 |

### 可选

| SSM 名称 | 映射到环境变量 | 说明 |
|----------|---------------|------|
| `MEMORYDB_PORT` | `REDIS_PORT` | MemoryDB 端口（默认 6379） |
| `MEMORYDB_PASSWORD` | `REDIS_PASSWORD` | MemoryDB 密码 |
| `E2B_API_KEY` | `E2B_API_KEY` | E2B 代码执行 API 密钥 |
| `RAGIE_API_KEY` | `RAGIE_API_KEY` | Ragie RAG API 密钥 |
| `TAVILY_API_KEY` | `TAVILY_API_KEY` | Tavily 搜索 API 密钥 |
| `EXA_API_KEY` | `EXA_API_KEY` | Exa 搜索 API 密钥 |
| `SLIDESPEAK_API_KEY` | `SLIDESPEAK_API_KEY` | SlideSpeak PPT 生成 API 密钥 |
| `AWS_ACCESS_KEY_ID` | `AWS_ACCESS_KEY_ID` | AWS Access Key（S3 访问） |
| `AWS_SECRET_ACCESS_KEY` | `AWS_SECRET_ACCESS_KEY` | AWS Secret Key（S3 访问） |

> **注意**：应用代码使用 `REDIS_*` 环境变量，manifest 中将 `MEMORYDB_*` secrets 映射到 `REDIS_*`

---

## 其他服务调用方式

部署完成后，其他服务可通过 NLB 或 Service Connect 访问 agent gRPC 服务。

### Go 客户端

```go
import "google.golang.org/grpc"

conn, err := grpc.Dial(
    "agent.production.zen0-backend.local:50051",
    grpc.WithInsecure(), // VPC 内部通信，无需 TLS
)
if err != nil {
    log.Fatalf("连接失败: %v", err)
}
defer conn.Close()

client := pb.NewAgentServiceClient(conn)
```

### Python 客户端

```python
import grpc

channel = grpc.insecure_channel(
    "agent.production.zen0-backend.local:50051"
)
stub = agent_pb2_grpc.AgentServiceStub(channel)
```

---

## 故障排查

### 1. 部署失败

```bash
# 查看日志
./deploy/aws/production/production.sh logs --since 30m

# 清理后重试
./deploy/aws/production/production.sh clean
./deploy/aws/production/production.sh deploy
```

### 2. Secrets 问题

```bash
# 验证 secrets
./deploy/aws/production/secrets.sh verify

# 查看具体值
./deploy/aws/production/secrets.sh show ANTHROPIC_API_KEY
```

### 3. 服务无法访问

```bash
# 检查 ECS 任务状态
./deploy/aws/production/production.sh status

# 查看实时日志
./deploy/aws/production/production.sh logs --follow
```

### 4. 回滚到之前版本

```bash
# 查看可用版本并选择回滚
./deploy/aws/production/production.sh rollback

# 或指定版本
./deploy/aws/production/production.sh rollback --to-version 20260101-120000
```

---

## 成本估算

| 资源 | 配置 | 月成本 |
|------|------|--------|
| ECS Fargate | 1 vCPU, 2GB × 2 实例 | ~$60 |
| NLB | gRPC 流量 | ~$20 |
| CloudWatch Logs | 10GB | ~$5 |
| **总计** | | **~$85/月** |

---

## 注意事项

1. **Production 环境 7×24 运行**，不提供 start/stop 命令
2. **所有操作需要确认**，输入 `PRODUCTION` 确认
3. **内网访问**：`agent.production.zen0-backend.local:50051`
4. **日志保留**：30 天
5. **自动扩缩容**：2-10 个实例
6. **统一服务名**：Staging 和 Production 都使用 `agent` 服务

---

## 相关文档

- [Staging 部署指南](../staging/README.md)
- [AWS Copilot 官方文档](https://aws.github.io/copilot-cli/)
- [项目架构文档](../../../docs/00-ARCHITECTURE-OVERVIEW.md)

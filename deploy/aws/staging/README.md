# Zenflux Agent - AWS ECS Fargate 部署指南

## 📋 目录

- [快速开始](#快速开始)
- [前置要求](#前置要求)
- [部署流程](#部署流程)
- [常用命令](#常用命令)
- [故障排查](#故障排查)

---

## 🚀 快速开始

```bash
# 1. 申请 SSL 证书
./deploy/aws/staging/setup-certificate.sh request

# 2. 等待证书验证完成（5-30 分钟）
./deploy/aws/staging/setup-certificate.sh status

# 3. 部署应用
./deploy/aws/staging/staging.sh deploy

# 4. 查看状态
./deploy/aws/staging/staging.sh status
```

---

## 📦 前置要求

### 1. 安装工具

```bash
# macOS
brew install awscli copilot-cli jq docker

# 验证安装
aws --version
copilot --version
jq --version
docker --version
```

### 2. 配置 AWS 凭证

```bash
aws configure
# 输入 Access Key ID 和 Secret Access Key
# Region: ap-southeast-1
```

### 3. 准备环境变量

确保项目根目录有 `.env` 文件（参考 `env.template`）：

```bash
cp env.template .env
# 编辑 .env 填入真实的 API Keys
```

---

## 🏗️ 部署流程

### 步骤 1: 申请 SSL 证书

```bash
./deploy/aws/staging/setup-certificate.sh request
```

**输出示例：**
```
📋 申请 SSL 证书
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ℹ️  域名: agent.malue.ai
ℹ️  区域: ap-southeast-1

✅ 证书申请成功: arn:aws:acm:ap-southeast-1:xxx:certificate/xxx

⚠️  重要：需要完成 DNS 验证

请在您的 DNS 提供商添加以下 CNAME 记录:
  类型: CNAME
  名称: _xxx.agent.malue.ai
  值: _xxx.acm-validations.aws.
```

### 步骤 2: 添加 DNS 验证记录

在您的 DNS 提供商（如 Cloudflare、阿里云等）添加上述 CNAME 记录。

### 步骤 3: 等待证书验证

```bash
# 查看证书状态
./deploy/aws/staging/setup-certificate.sh status

# 状态为 ISSUED 时可以继续部署
```

### 步骤 4: 部署应用

```bash
# 完整部署（环境 + 服务）
./deploy/aws/staging/staging.sh deploy

# 仅部署服务（环境已存在）
./deploy/aws/staging/staging.sh deploy --svc-only

# 跳过健康检查（调试时使用）
./deploy/aws/staging/staging.sh deploy --skip-health
```

**部署过程：**
1. 检查依赖工具
2. 初始化 Copilot 应用
3. 部署环境（VPC、EFS、安全组等）
4. 构建 Docker 镜像
5. 推送到 ECR
6. 部署 ECS 服务
7. 运行数据库迁移
8. 健康检查

**预计时间：** 25-35 分钟

---

## 🎮 常用命令

### 查看状态

```bash
# 查看环境和服务状态
./deploy/aws/staging/staging.sh status
```

### 查看日志

```bash
# 查看最近 10 分钟日志
./deploy/aws/staging/staging.sh logs

# 实时跟踪日志
./deploy/aws/staging/staging.sh logs --follow

# 查看最近 1 小时日志
./deploy/aws/staging/staging.sh logs --since 1h
```

### 启动/停止环境

```bash
# 停止环境（缩容到 0，保留配置）
./deploy/aws/staging/staging.sh stop --keep-service

# 启动环境（恢复运行）
./deploy/aws/staging/staging.sh start

# 完全删除环境
./deploy/aws/staging/staging.sh stop --force
```

### 清理失败资源

```bash
# 清理卡住的 CloudFormation Stack
./deploy/aws/staging/staging.sh clean
```

---

## 🏗️ 架构说明

### 部署架构

```
┌─────────────────────────────────────┐
│   ECS Fargate Task (0.5 vCPU, 1GB) │
│                                     │
│  ┌──────────────────────────────┐  │
│  │  Nginx (Port 80)             │  │
│  │  ├─ /        → Frontend      │  │
│  │  └─ /api/*   → Backend:8000  │  │
│  └──────────────────────────────┘  │
│  ┌──────────────────────────────┐  │
│  │  FastAPI (Port 8000)         │  │
│  └──────────────────────────────┘  │
└─────────────────────────────────────┘
         ↓ 持久化存储
    EFS (workspace, logs, config)
         ↓ 缓存
    ElastiCache Redis (复用)
```

### 网络配置

- **VPC**: `vpc-0c7d3d0bd0b1dcdce` (复用 zen0-backend)
- **公有子网**: 2 个（ap-southeast-1a, 1b）
- **私有子网**: 2 个（ap-southeast-1a, 1b）
- **ALB**: 复用 `zen0-b-Publi-NMnJaDU9XzTR`
- **域名**: `agent.malue.ai`

### 资源配置

- **CPU**: 0.5 vCPU
- **内存**: 1 GB
- **存储**: EFS (按使用量计费)
- **Redis**: 复用 `zen0-backend-staging-redis`
- **数据库**: PostgreSQL (RDS)

---

## 🔧 故障排查

### 1. 部署失败

```bash
# 查看详细日志
./deploy/aws/staging/staging.sh logs --since 30m

# 清理失败资源
./deploy/aws/staging/staging.sh clean

# 重新部署
./deploy/aws/staging/staging.sh deploy --force
```

### 2. 健康检查失败

```bash
# 查看服务日志
copilot svc logs --name backend --env staging --follow

# 检查容器状态
aws ecs describe-services \
  --cluster zen0-agent-staging \
  --services backend \
  --region ap-southeast-1
```

### 3. 环境变量问题

```bash
# 检查 SSM Parameter Store
aws ssm get-parameters-by-path \
  --path /copilot/zen0-agent/staging/secrets \
  --region ap-southeast-1

# 更新环境变量后重新部署
./deploy/aws/staging/staging.sh deploy --svc-only
```

### 4. 证书问题

```bash
# 查看证书状态
./deploy/aws/staging/setup-certificate.sh status

# 验证 DNS 记录
dig _xxx.agent.malue.ai CNAME
```

### 5. 数据库迁移失败

```bash
# 手动执行迁移
copilot svc exec \
  --name backend \
  --env staging \
  --command "python -c 'from infra.database import init_database; import asyncio; asyncio.run(init_database())'"
```

---

## 💰 成本估算

| 资源 | 配置 | 月成本 |
|------|------|--------|
| ECS Fargate | 0.5 vCPU, 1GB | ~$15 |
| EFS | 10GB | ~$3 |
| ALB | 共享 | $0 |
| Redis | 共享 | $0 |
| 数据传输 | 估算 | ~$5 |
| **总计** | | **~$23/月** |

---

## 📚 相关文档

- [AWS Copilot 官方文档](https://aws.github.io/copilot-cli/)
- [ECS Fargate 定价](https://aws.amazon.com/fargate/pricing/)
- [项目架构文档](../../../docs/00-ARCHITECTURE-OVERVIEW.md)

---

## 🆘 获取帮助

```bash
# 查看脚本帮助
./deploy/aws/staging/staging.sh --help

# 查看 Copilot 帮助
copilot --help
copilot svc deploy --help
```

---

## 📝 注意事项

1. **首次部署** 需要 25-35 分钟
2. **证书验证** 通常需要 5-30 分钟
3. **停止环境** 使用 `--keep-service` 可快速恢复
4. **环境变量** 修改后需要重新部署服务
5. **日志保留** 默认 30 天
6. **自动扩缩容** 支持 1-4 个实例

---

**最后更新**: 2026-01-08

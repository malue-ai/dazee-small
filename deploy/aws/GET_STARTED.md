# 🚀 Zenflux Agent - AWS 部署快速开始

## 📋 概述

本指南将帮助您在 **5 分钟内**了解如何将 Zenflux Agent 部署到 AWS ECS Fargate。

### 🏗️ 部署架构

Zenflux Agent 作为 **zen0-backend 应用的一个服务**部署到现有的 staging 环境：

```
zen0-backend (应用)
└─ staging (环境) ← 复用现有
    ├─ backend (服务) ← 已有的 Go 后端
    └─ agent (服务) ← 新增的 Python Agent
```

**复用的资源**：VPC、ALB、Redis、安全组
**新增的资源**：ECS 服务、EFS 存储

---

## ⚡ 快速开始

### 🚀 方式 1: HTTP 部署（推荐新手，无需证书）

```bash
# 一键部署，25-35 分钟
./deploy/aws/staging/staging.sh deploy
```

**就这么简单！** 部署完成后会显示访问地址。

---

### 🔒 方式 2: HTTPS 部署（需要自定义域名）

#### 1️⃣ 申请 SSL 证书

```bash
# 配置域名
export CUSTOM_DOMAIN=agent.malue.ai

# 申请证书
./deploy/aws/staging/staging.sh cert request
```

**输出示例：**
```
✅ 证书申请成功
⚠️  请添加 DNS CNAME 记录:
  名称: _xxx.agent.malue.ai
  值: _xxx.acm-validations.aws.
```

👉 **去您的 DNS 提供商添加这条记录**

#### 2️⃣ 等待证书验证（5-30 分钟）

```bash
./deploy/aws/staging/staging.sh cert status
```

**等待状态变为：**
```
✅ 证书已签发，可以部署
```

#### 3️⃣ 一键部署

```bash
./deploy/aws/staging/staging.sh deploy
```

**部署过程：**
- ✅ 检查依赖工具
- ✅ 初始化 Copilot 应用
- ✅ 部署环境（VPC、EFS、安全组）
- ✅ 构建 Docker 镜像
- ✅ 推送到 ECR
- ✅ 部署 ECS 服务
- ✅ 运行数据库迁移
- ✅ 健康检查

**预计时间：** 25-35 分钟 ☕

---

### 📚 更多部署模式

详见 [DEPLOYMENT_MODES.md](staging/DEPLOYMENT_MODES.md) 了解 HTTP 和 HTTPS 模式的详细对比。

---

## 🎉 部署完成！

访问您的应用（通过 ALB 默认域名 + 路径）：

| 服务 | URL |
|------|-----|
| 🌐 前端 | http://{ALB域名}/agent/ |
| 📚 API 文档 | http://{ALB域名}/agent/docs |
| ❤️ 健康检查 | http://{ALB域名}/agent/health |

**注意**：ALB 域名会在部署完成后显示，类似：
`zen0-b-Publi-NMnJaDU9XzTR-xxx.ap-southeast-1.elb.amazonaws.com`

---

## 📱 常用命令

```bash
# 查看状态
./deploy/aws/staging/staging.sh status

# 查看日志
./deploy/aws/staging/staging.sh logs --follow

# 停止环境（节省成本）
./deploy/aws/staging/staging.sh stop --keep-service

# 启动环境
./deploy/aws/staging/staging.sh start

# 更新部署
./deploy/aws/staging/staging.sh deploy --svc-only
```

---

## 📚 详细文档

| 文档 | 说明 |
|------|------|
| [DEPLOYMENT_SUMMARY.md](DEPLOYMENT_SUMMARY.md) | 完整部署总结 |
| [staging/README.md](staging/README.md) | 详细部署指南 |
| [staging/CHECKLIST.md](staging/CHECKLIST.md) | 部署检查清单 |
| [staging/QUICK_REFERENCE.md](staging/QUICK_REFERENCE.md) | 快速参考 |

---

## ⚠️ 前置要求

### 必需工具

```bash
# 安装（macOS）
brew install awscli copilot-cli jq docker

# 验证
aws --version
copilot --version
jq --version
docker info
```

### AWS 凭证

```bash
aws configure
# 输入 Access Key ID 和 Secret Access Key
# Region: ap-southeast-1
```

### 环境变量

确保 `.env` 文件已配置（参考 `env.template`）

---

## 💰 成本

| 资源 | 月成本 |
|------|--------|
| ECS Fargate (0.5 vCPU, 1GB) | ~$15 |
| EFS (10GB) | ~$3 |
| 数据传输 | ~$5 |
| **总计** | **~$23/月** |

**💡 提示**: 使用 `stop --keep-service` 可节省约 70% 成本

---

## 🆘 遇到问题？

### 1. 证书验证失败
```bash
# 检查 DNS 记录
dig _xxx.agent.malue.ai CNAME

# 等待 DNS 传播（最多 48 小时，通常 5-30 分钟）
```

### 2. 部署失败
```bash
# 查看日志
./deploy/aws/staging/staging.sh logs --since 30m

# 清理后重试
./deploy/aws/staging/staging.sh clean
./deploy/aws/staging/staging.sh deploy --force
```

### 3. 健康检查失败
```bash
# 实时查看日志
./deploy/aws/staging/staging.sh logs --follow

# 检查环境变量
copilot svc show --name backend --env staging
```

---

## 🎯 下一步

1. **配置域名 DNS**
   - 将 `agent.malue.ai` 指向 ALB

2. **测试功能**
   - 访问前端页面
   - 测试 API 接口
   - 上传文件测试

3. **监控和告警**
   - 查看 CloudWatch 日志
   - 配置告警规则

---

## 📞 获取帮助

```bash
# 查看脚本帮助
./deploy/aws/staging/staging.sh --help

# 查看 Copilot 帮助
copilot --help
```

---

**准备好了吗？开始部署吧！** 🚀

```bash
./deploy/aws/staging/setup-certificate.sh request
```

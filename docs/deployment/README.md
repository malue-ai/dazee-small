# 📦 Zenflux Agent 部署文档导航

欢迎查阅 Zenflux Agent V7 的部署文档！

---

## 📚 文档列表

### 🚀 主部署方案
**[PRODUCTION_DEPLOYMENT.md](./PRODUCTION_DEPLOYMENT.md)** - **⭐ 推荐阅读**

这是 **V7 完整生产部署方案**，包含：
- ✅ 架构全景图与模块结构
- ✅ 三种部署方案对比（Docker Compose / AWS ECS / Kubernetes）
- ✅ 基础设施配置（数据库、Redis、向量数据库、对象存储）
- ✅ 可观测性建设（分布式追踪、Prometheus、Grafana、告警）
- ✅ 安全加固（认证鉴权、限流、CORS）
- ✅ 性能优化（数据库、缓存、LLM 调用）
- ✅ 运维手册（健康检查、日志、备份、扩缩容）
- ✅ 故障应急预案

**适用场景**：生产环境、预发布环境、灰度环境

---

### 🐳 Docker 部署指南

#### [README_DOCKER.md](./README_DOCKER.md) - 快速开始
- 5 分钟快速部署
- 适用于开发/测试环境
- Docker Compose 单机部署

#### [DOCKER_DEPLOYMENT.md](./DOCKER_DEPLOYMENT.md) - 详细指南
- 完整的 Docker Compose 部署文档
- 包含运维命令、故障排查、性能优化
- 适用于小规模生产环境

---

### ☁️ AWS ECS 部署

#### [DEPLOYMENT_COMPLETE.md](./DEPLOYMENT_COMPLETE.md) - ECS Fargate 部署
- AWS ECS Fargate 单容器架构
- 一键部署脚本
- SSL 证书管理
- 成本优化方案（~$23/月）
- 适用于中小规模生产环境（< 10k QPS）

**相关文件**：
- `deploy/aws/staging/staging.sh` - 一键部署脚本
- `deploy/aws/staging/setup-certificate.sh` - SSL 证书管理
- `copilot/` - AWS Copilot 配置

---

## 🎯 快速导航

### 按使用场景选择

| 场景 | 推荐方案 | 文档 |
|------|---------|------|
| 本地开发 | Docker Compose | [README_DOCKER.md](./README_DOCKER.md) |
| 测试环境 | Docker Compose | [DOCKER_DEPLOYMENT.md](./DOCKER_DEPLOYMENT.md) |
| 小规模生产（< 1k QPS） | Docker Compose | [DOCKER_DEPLOYMENT.md](./DOCKER_DEPLOYMENT.md) |
| 中规模生产（< 10k QPS） | AWS ECS Fargate | [DEPLOYMENT_COMPLETE.md](./DEPLOYMENT_COMPLETE.md) |
| 大规模生产（> 10k QPS） | Kubernetes | [PRODUCTION_DEPLOYMENT.md](./PRODUCTION_DEPLOYMENT.md) Kubernetes 章节 |
| 企业级生产（> 100k QPS） | Kubernetes + 完整可观测性 | [PRODUCTION_DEPLOYMENT.md](./PRODUCTION_DEPLOYMENT.md) |

### 按技能栈选择

| 技能栈 | 推荐方案 | 复杂度 |
|--------|---------|--------|
| 熟悉 Docker | Docker Compose | ⭐ 低 |
| 熟悉 AWS | AWS ECS Fargate | ⭐⭐ 中 |
| 熟悉 Kubernetes | Kubernetes | ⭐⭐⭐ 高 |

---

## 📋 部署前准备

### 必需的 API Keys

无论选择哪种部署方案，都需要准备：

```bash
# Claude API Key（必需）
ANTHROPIC_API_KEY=sk-ant-xxxxx

# E2B Sandbox API Key（必需）
E2B_API_KEY=e2b_xxxxx
```

获取方式：
- Claude API: https://console.anthropic.com/
- E2B Sandbox: https://e2b.dev/

### 可选的 API Keys

```bash
# OpenAI（降级方案）
OPENAI_API_KEY=sk-xxxxx

# Google Gemini（降级方案）
GOOGLE_API_KEY=xxxxx

# Ragie（知识库，可选）
RAGIE_API_KEY=xxxxx
```

---

## 🚀 5 分钟快速开始

### Docker Compose（最简单）

```bash
# 1. 克隆代码
git clone <repo-url> zenflux_agent
cd zenflux_agent

# 2. 配置环境变量
cp env.template .env
vim .env  # 填入 ANTHROPIC_API_KEY 和 E2B_API_KEY

# 3. 启动服务
docker compose up -d

# 4. 访问服务
curl http://localhost:8000/health
open http://localhost:8000/docs
```

详见：[README_DOCKER.md](./README_DOCKER.md)

### AWS ECS Fargate

```bash
# 1. 申请 SSL 证书
./deploy/aws/staging/setup-certificate.sh request

# 2. 配置 DNS（添加 CNAME 记录）

# 3. 等待证书验证（5-30分钟）
./deploy/aws/staging/setup-certificate.sh status

# 4. 一键部署
./deploy/aws/staging/staging.sh deploy

# 5. 验证部署
curl https://agent.yourdomain.com/health
```

详见：[DEPLOYMENT_COMPLETE.md](./DEPLOYMENT_COMPLETE.md)

### Kubernetes

```bash
# 1. 创建 Secret
kubectl create secret generic zenflux-secrets \
  --from-literal=anthropic-api-key=$ANTHROPIC_API_KEY \
  --from-literal=e2b-api-key=$E2B_API_KEY \
  -n production

# 2. 应用配置
kubectl apply -f k8s/

# 3. 验证部署
kubectl get pods -n production
```

详见：[PRODUCTION_DEPLOYMENT.md](./PRODUCTION_DEPLOYMENT.md) Kubernetes 章节

---

## 📊 成本对比

| 方案 | 月成本（USD） | 适用规模 |
|------|--------------|---------|
| Docker Compose（自建） | ~$0 | < 1k QPS |
| AWS ECS Fargate | ~$23-71 | < 10k QPS |
| AWS ECS Fargate（优化） | ~$31 | < 10k QPS |
| Kubernetes（EKS） | ~$462 | > 10k QPS |
| Kubernetes（优化） | ~$200 | > 10k QPS |

---

## 🔧 运维工具

### 健康检查
```bash
# 简单健康检查
curl http://localhost:8000/health

# 就绪检查（含依赖）
curl http://localhost:8000/health/ready
```

### 日志查看
```bash
# Docker Compose
docker compose logs -f backend

# Kubernetes
kubectl logs -f deployment/zenflux-agent -n production
```

### Metrics 监控
```bash
# Prometheus Metrics
curl http://localhost:8000/metrics
```

---

## 📞 获取帮助

### 文档资源
- 📖 架构文档：`../architecture/00-ARCHITECTURE-OVERVIEW.md`
- 📖 API 文档：`../api/chat_api_specification.md`
- 📖 评估报告：`../reports/`

### 问题排查
1. 查看对应部署文档的"故障排查"章节
2. 查看日志输出
3. 检查环境变量配置
4. 查看健康检查端点

### 联系方式
- GitHub Issues: 提交 Bug 或功能请求
- 文档反馈: 改进建议

---

## 🎓 推荐阅读顺序

1. **新手**：
   - 先读 [README_DOCKER.md](./README_DOCKER.md)
   - 快速体验 Docker Compose 部署
   - 熟悉基本概念

2. **进阶**：
   - 读 [DOCKER_DEPLOYMENT.md](./DOCKER_DEPLOYMENT.md)
   - 了解完整的运维命令
   - 学习故障排查

3. **生产部署**：
   - 读 [PRODUCTION_DEPLOYMENT.md](./PRODUCTION_DEPLOYMENT.md)
   - 理解架构全景
   - 选择合适的部署方案
   - 配置可观测性

4. **AWS 用户**：
   - 读 [DEPLOYMENT_COMPLETE.md](./DEPLOYMENT_COMPLETE.md)
   - 快速上手 ECS Fargate
   - 了解成本优化

---

## ✅ 部署检查清单

在正式部署前，请确保：

- [ ] 已阅读对应的部署文档
- [ ] API Keys 已准备并验证
- [ ] 数据库方案已选择（SQLite/PostgreSQL）
- [ ] Redis 已配置
- [ ] 存储方案已确定（本地/S3/OSS）
- [ ] 日志收集已配置
- [ ] 监控告警已配置（生产环境）
- [ ] 备份策略已制定（生产环境）
- [ ] 应急预案已准备（生产环境）

---

## 🎉 开始部署

选择你的部署方案，开始部署 Zenflux Agent V7！

**祝部署顺利！** 🚀

---

*文档版本: V7.0*  
*最后更新: 2026-01-15*

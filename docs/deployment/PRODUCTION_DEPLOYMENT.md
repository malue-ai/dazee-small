# 🚀 Zenflux Agent V7 生产部署完整方案

> **版本**: V7.0 - 面向 99.9% SLA 的生产级部署方案  
> **更新日期**: 2026-01-15  
> **适用环境**: 生产环境、预发布环境、灰度环境

---

## 📋 目录

- [一、架构全景](#一架构全景)
- [二、部署方案对比](#二部署方案对比)
- [三、基础设施配置](#三基础设施配置)
- [四、部署流程](#四部署流程)
- [五、可观测性建设](#五可观测性建设)
- [六、安全加固](#六安全加固)
- [七、性能优化](#七性能优化)
- [八、运维手册](#八运维手册)
- [九、故障应急](#九故障应急)
- [附录](#附录)

---

## 一、架构全景

### 1.1 系统整体架构图

```mermaid
flowchart TB
    subgraph External[外部流量层]
        Client[客户端<br/>Web/App/API]
        CDN[CDN/WAF]
    end

    subgraph Gateway[网关层]
        LB[负载均衡<br/>ALB/Nginx]
        RateLimit[限流中间件]
        Auth[认证鉴权]
    end

    subgraph Protocol[协议层]
        FastAPI[FastAPI REST<br/>:8000]
        gRPC[gRPC Service<br/>:50051]
        SSE[SSE 流式响应]
    end

    subgraph AgentCore[智能体核心框架 V7]
        subgraph Router[路由层 core/routing/]
            IntentAnalyzer[IntentAnalyzer<br/>意图识别]
            AgentRouter[AgentRouter<br/>路由决策]
            ComplexityScorer[ComplexityScorer<br/>复杂度评分]
        end

        subgraph Agents[Agent 执行层]
            SimpleAgent[SimpleAgent<br/>单智能体 RVR循环]
            MultiAgent[MultiAgentOrchestrator<br/>多智能体 DAG编排]
        end

        subgraph Context[上下文工程]
            ContextManager[Context Manager<br/>上下文管理]
            Compaction[Context Compaction<br/>三层防护]
            PromptManager[Prompt Manager<br/>分层提示词]
        end

        subgraph Memory[记忆系统]
            WorkingMem[Working Memory<br/>会话级]
            Mem0Core[Mem0 Core<br/>长期记忆]
            UserPref[User Preference<br/>用户偏好]
        end

        subgraph Tools[工具能力层]
            ToolExecutor[Tool Executor<br/>工具执行器]
            SkillLoader[Skill Loader<br/>技能加载器]
            Capability[Capability Registry<br/>能力注册表]
        end

        subgraph Events[事件系统]
            EventDispatcher[Event Dispatcher<br/>事件分发]
            Broadcaster[Broadcaster<br/>消息广播]
        end
    end

    subgraph LLM[LLM 适配层]
        Claude[Claude Adaptor]
        OpenAI[OpenAI Adaptor]
        Gemini[Gemini Adaptor]
    end

    subgraph Resilience[容错层 infra/resilience/]
        CircuitBreaker[熔断器]
        Retry[重试策略]
        Fallback[降级策略]
        Timeout[超时控制]
    end

    subgraph Monitoring[监控层]
        ProdMonitor[Production Monitor<br/>生产监控]
        TokenAudit[Token Audit<br/>成本审计]
        FailureDetector[Failure Detector<br/>故障检测]
    end

    subgraph DataLayer[数据层]
        Redis[(Redis Cluster<br/>会话/缓存)]
        PG[(PostgreSQL<br/>主从架构)]
        VectorDB[(向量数据库<br/>Mem0存储)]
        OSS[(S3/OSS<br/>文件存储)]
    end

    subgraph ExternalAI[外部AI服务]
        Anthropic[Anthropic API]
        E2B[E2B Sandbox]
        Ragie[Ragie API]
    end

    subgraph Observability[可观测性]
        Prometheus[Prometheus]
        Jaeger[Jaeger Tracing]
        Grafana[Grafana]
        AlertManager[AlertManager]
    end

    Client --> CDN --> LB
    LB --> RateLimit --> Auth
    Auth --> FastAPI & gRPC
    FastAPI --> SSE
    FastAPI & gRPC --> Router
    
    Router --> Agents
    Agents --> Context
    Agents --> Memory
    Agents --> Tools
    Agents --> Events
    
    Agents --> LLM
    LLM --> Resilience
    Resilience --> Anthropic & E2B & Ragie
    
    AgentCore --> Monitoring
    Context --> Redis
    Memory --> VectorDB & Redis
    Tools --> OSS
    
    Monitoring -.->|metrics| Prometheus
    AgentCore -.->|traces| Jaeger
    Prometheus --> Grafana
    Prometheus --> AlertManager
```

### 1.2 V7 核心模块结构

```
zenflux_agent/
├── core/                           # 核心框架
│   ├── agent/                      # Agent 引擎
│   │   ├── factory.py              # ✅ Agent Factory 统一入口
│   │   ├── simple_agent.py         # ✅ SimpleAgent (RVR 循环)
│   │   ├── types.py                # Agent 类型定义
│   │   └── multi/                  # ✅ 多智能体框架 (独立)
│   │       ├── orchestrator.py     # 多智能体编排器
│   │       └── models.py           # 多智能体模型
│   │
│   ├── routing/                    # ✅ 共享路由层 (V5.1 剥离)
│   │   ├── intent_analyzer.py      # IntentAnalyzer (共享)
│   │   ├── router.py               # AgentRouter 路由决策
│   │   └── complexity_scorer.py    # 复杂度评分
│   │
│   ├── planning/                   # ✅ 共享 Plan 层 (V5.1 剥离)
│   │   ├── protocol.py             # Plan 数据协议
│   │   ├── storage.py              # Plan 持久化
│   │   └── validators.py           # Plan 验证器
│   │
│   ├── context/                    # 上下文工程
│   │   ├── compaction/             # ✅ 上下文压缩三层防护
│   │   ├── manager.py              # 上下文管理器
│   │   ├── prompt_manager.py       # Prompt 分层管理
│   │   └── ...
│   │
│   ├── memory/                     # 记忆系统 (三层)
│   │   ├── working.py              # WorkingMemory (会话级)
│   │   ├── user/                   # 用户级记忆
│   │   ├── system/                 # 系统级记忆
│   │   └── mem0/                   # Mem0 长期记忆
│   │
│   ├── tool/                       # 工具能力层
│   │   ├── executor.py             # ✅ 工具执行器
│   │   ├── loader.py               # 统一加载器
│   │   └── capability/             # 能力注册表
│   │
│   ├── llm/                        # LLM 适配层
│   │   ├── base.py                 # LLM 基类
│   │   ├── claude.py               # ✅ Claude 适配 (主力)
│   │   ├── openai.py               # OpenAI 适配
│   │   └── gemini.py               # Gemini 适配
│   │
│   ├── events/                     # 事件系统
│   │   ├── manager.py              # 事件管理器
│   │   ├── context_events.py       # 上下文事件 (V6.3)
│   │   └── adapters/               # 平台适配器
│   │
│   ├── output/                     # 输出格式化
│   │   ├── formatter.py            # 输出格式化器
│   │   └── validators.py           # 输出验证器
│   │
│   └── monitoring/                 # ✅ 监控系统
│       ├── production_monitor.py   # 生产监控
│       ├── failure_detector.py     # 故障检测
│       └── token_audit.py          # Token 审计 & 计费日志
│
├── services/                       # 业务逻辑层
│   ├── chat_service.py             # ✅ ChatService (集成 AgentRouter)
│   ├── agent_registry.py           # Agent 注册表
│   ├── session_service.py          # Session 管理
│   ├── conversation_service.py     # 对话历史
│   ├── redis_manager.py            # Redis 管理
│   └── ...
│
├── routers/                        # ✅ FastAPI 入口
│   ├── chat.py                     # 对话接口
│   ├── health.py                   # 健康检查
│   ├── agents.py                   # Agent 管理
│   └── ...
│
├── grpc_server/                    # ✅ gRPC 入口
│   ├── server.py                   # gRPC Server
│   ├── chat_service.py             # Chat Service gRPC
│   └── interceptors.py             # gRPC 拦截器
│
├── infra/                          # 基础设施
│   ├── database/                   # 数据库
│   │   ├── engine.py               # SQLAlchemy 引擎
│   │   └── models/                 # 数据模型
│   │
│   └── resilience/                 # ✅ 容错层
│       ├── circuit_breaker.py      # 熔断器
│       ├── retry.py                # 重试策略
│       ├── timeout.py              # 超时控制
│       ├── fallback.py             # 降级策略
│       └── config.py               # 容错配置加载
│
├── evaluation/                     # ✅ 评估系统 (Anthropic 方法论)
│   ├── harness.py                  # 评估工具
│   ├── graders/                    # 三层评分器
│   └── qos_config.py               # QoS 评估配置
│
├── instances/                      # 实例配置
│   └── {agent_name}/
│       ├── prompt.md               # 运营提示词
│       ├── config.yaml             # 实例配置
│       ├── skills/                 # 技能配置
│       └── prompt_results/         # 生成的场景化提示词
│
├── config/                         # 配置文件
│   ├── resilience.yaml             # ✅ 容错配置
│   ├── context_compaction.yaml     # 上下文压缩策略
│   ├── capabilities.yaml           # 工具能力配置
│   ├── routing_rules.yaml          # 路由规则
│   └── ...
│
├── tests/                          # 测试
│   ├── test_e2e_complete_flow.py   # ✅ E2E 测试（含 Token 审计）
│   ├── integration/                # 集成测试
│   └── unit/                       # 单元测试
│
├── main.py                         # ✅ FastAPI 主入口
├── logger.py                       # 日志配置
├── Dockerfile                      # 开发环境镜像
├── Dockerfile.production           # 生产环境镜像
├── docker-compose.yml              # Docker Compose 配置
└── .env                            # 环境变量配置
```

### 1.3 单智能体与多智能体独立原则

**核心架构决策**：

```mermaid
graph TB
    Request[用户请求] --> ChatService[ChatService 服务层]
    ChatService --> ContextLoader[历史上下文加载]
    ContextLoader --> AgentRouter[AgentRouter 路由层]
    
    AgentRouter --> IntentAnalyzer[IntentAnalyzer 共享模块]
    IntentAnalyzer --> Decision{复杂度判断}
    
    Decision -->|simple/medium| SingleAgent[SimpleAgent 单智能体]
    Decision -->|complex| MultiAgent[MultiAgentOrchestrator]
    
    subgraph SharedLayer[共享层 core/routing + core/planning]
        IntentAnalyzer
        PlanProtocol[Plan 数据协议]
        ComplexityScorer[复杂度评分器]
    end
    
    subgraph Independent[独立执行层 完全解耦]
        SingleAgent --> PlanTodo[plan_todo 工具 线性执行]
        MultiAgent --> TaskDecomposer[TaskDecomposer DAG执行]
    end
    
    PlanProtocol --> PlanTodo
    PlanProtocol --> TaskDecomposer
    
    SingleAgent --> LLM[Claude LLM]
    MultiAgent --> LLM
```

**关键约束**:
- `SimpleAgent` 不包含任何多智能体调用逻辑
- `MultiAgentOrchestrator` 不继承或调用 `SimpleAgent`
- 意图识别在路由层完成，两个框架是平级的
- 共享基础设施（LLM、工具、记忆、Plan 协议），但执行逻辑完全独立

---

## 二、部署方案对比

### 2.1 三种部署方案对比

| 维度 | Docker Compose | AWS ECS Fargate | Kubernetes |
|------|---------------|-----------------|------------|
| **适用场景** | 开发/测试/小规模生产 | 中等规模生产 | 大规模生产 |
| **部署复杂度** | ⭐ 低 | ⭐⭐ 中 | ⭐⭐⭐ 高 |
| **运维成本** | ⭐ 低 | ⭐⭐ 中 | ⭐⭐⭐ 高 |
| **弹性伸缩** | ❌ 不支持 | ✅ 自动 HPA | ✅ 自动 HPA + VPA |
| **高可用** | ❌ 单点 | ✅ 多 AZ | ✅ 多 AZ + 自愈 |
| **服务发现** | Docker Network | ALB + Target Group | Service + Ingress |
| **配置管理** | .env 文件 | SSM Parameter Store | ConfigMap + Secret |
| **日志收集** | 本地文件 | CloudWatch Logs | EFK/Loki Stack |
| **监控告警** | 手动配置 | CloudWatch Alarms | Prometheus + Grafana |
| **成本** | ~$0 (自建) | ~$20-50/月 | ~$50-200/月 |
| **故障恢复** | 手动重启 | 自动重启 | 自动重启 + 滚动更新 |

### 2.2 方案选择建议

#### 🌱 开发/测试环境
**推荐**: Docker Compose

```bash
# 快速启动
docker compose up -d

# 成本: 几乎为 0
# 维护: 简单直接
```

#### 🚀 中小规模生产 (< 10k QPS)
**推荐**: AWS ECS Fargate

优势：
- ✅ 无需管理服务器
- ✅ 按需付费，成本可控
- ✅ 集成 AWS 生态（ALB、RDS、ElastiCache）
- ✅ 自动扩缩容

成本估算：
- 0.5 vCPU, 1GB 内存：~$15/月
- EFS 10GB：~$3/月
- 数据传输：~$5/月
- **总计：~$23/月**

#### 🏢 大规模生产 (> 10k QPS)
**推荐**: Kubernetes (EKS/GKE/自建)

优势：
- ✅ 强大的编排能力
- ✅ 精细的资源控制
- ✅ 丰富的生态工具
- ✅ 多云/混合云部署

---

## 三、基础设施配置

### 3.1 数据库选型

#### SQLite (开发/小规模)
```yaml
# 适用场景: 
- 开发环境
- 单机部署
- QPS < 100

# 配置:
DATABASE_TYPE: sqlite
DATABASE_PATH: ./workspace/database/zenflux.db
```

#### PostgreSQL (生产环境)
```yaml
# 适用场景:
- 生产环境
- 多实例部署
- QPS > 100

# 主从配置:
PRIMARY_DB_URL: postgresql://user:pass@primary-host:5432/zenflux
REPLICA_DB_URL: postgresql://user:pass@replica-host:5432/zenflux

# 连接池:
DB_POOL_SIZE: 20
DB_MAX_OVERFLOW: 40
DB_POOL_TIMEOUT: 30
```

**PostgreSQL 部署方案**：

1. **AWS RDS PostgreSQL** (推荐)
   - 自动备份
   - 自动故障转移
   - 自动扩展存储
   - 成本：~$20-50/月（db.t3.micro）

2. **Docker PostgreSQL**
   ```bash
   docker run -d \
     --name postgres \
     -e POSTGRES_DB=zenflux \
     -e POSTGRES_USER=zenflux \
     -e POSTGRES_PASSWORD=secure_password \
     -v postgres_data:/var/lib/postgresql/data \
     -p 5432:5432 \
     postgres:16-alpine
   ```

### 3.2 Redis 配置

#### 单机 Redis (开发)
```yaml
REDIS_HOST: localhost
REDIS_PORT: 6379
REDIS_PASSWORD: optional
REDIS_DB: 0
```

#### Redis Cluster (生产)
```yaml
# AWS ElastiCache Redis
REDIS_CLUSTER_ENDPOINTS:
  - redis-001.cache.amazonaws.com:6379
  - redis-002.cache.amazonaws.com:6379
  - redis-003.cache.amazonaws.com:6379

# 连接池配置
REDIS_MAX_CONNECTIONS: 50
REDIS_SOCKET_TIMEOUT: 5
REDIS_SOCKET_CONNECT_TIMEOUT: 5
REDIS_RETRY_ON_TIMEOUT: true
```

**Redis 部署方案**：

1. **AWS ElastiCache Redis** (推荐)
   - 自动故障转移
   - 自动备份
   - 多 AZ 部署
   - 成本：~$15-40/月（cache.t3.micro）

2. **Docker Redis**
   ```bash
   docker run -d \
     --name redis \
     -p 6379:6379 \
     -v redis_data:/data \
     redis:7-alpine redis-server \
     --requirepass secure_password \
     --maxmemory 512mb \
     --maxmemory-policy allkeys-lru
   ```

### 3.3 向量数据库 (Mem0)

#### 自建 Qdrant (推荐)
```yaml
MEM0_VECTOR_STORE:
  provider: qdrant
  config:
    host: localhost
    port: 6333
    grpc_port: 6334
    collection_name: zenflux_memories
```

```bash
# Docker 部署
docker run -d \
  --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v qdrant_data:/qdrant/storage \
  qdrant/qdrant:latest
```

#### 托管方案
- **Qdrant Cloud**: $25/月起
- **Pinecone**: $70/月起
- **Weaviate Cloud**: $25/月起

### 3.4 对象存储

#### AWS S3
```yaml
STORAGE_TYPE: s3
AWS_S3_BUCKET: zenflux-files-prod
AWS_S3_REGION: ap-southeast-1
AWS_S3_ACCESS_KEY: your_access_key
AWS_S3_SECRET_KEY: your_secret_key
```

#### 阿里云 OSS
```yaml
STORAGE_TYPE: oss
ALIYUN_OSS_BUCKET: zenflux-files
ALIYUN_OSS_ENDPOINT: oss-cn-hangzhou.aliyuncs.com
ALIYUN_OSS_ACCESS_KEY_ID: your_key
ALIYUN_OSS_ACCESS_KEY_SECRET: your_secret
```

---

## 四、部署流程

### 4.1 Docker Compose 部署 (开发/测试)

#### 快速开始

```bash
# 1. 克隆代码
git clone <repo-url> zenflux_agent
cd zenflux_agent

# 2. 配置环境变量
cp env.template .env
vim .env  # 填入必要的 API Keys

# 3. 启动服务
docker compose up -d

# 4. 查看状态
docker compose ps
docker compose logs -f backend

# 5. 访问服务
curl http://localhost:8000/health
open http://localhost:8000/docs
```

#### 环境变量配置 (.env)

```bash
# ===== 核心 API Keys =====
ANTHROPIC_API_KEY=sk-ant-xxxxx    # Claude API Key (必需)
E2B_API_KEY=e2b_xxxxx              # E2B Sandbox (必需)

# ===== 数据库配置 =====
DATABASE_TYPE=sqlite               # 或 postgresql
DATABASE_PATH=./workspace/database/zenflux.db

# ===== Redis 配置 =====
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=optional

# ===== LLM 配置 =====
DEFAULT_LLM_MODEL=claude-sonnet-4-5-20250929
DEFAULT_LLM_TEMPERATURE=0.7
DEFAULT_LLM_MAX_TOKENS=8192

# ===== 日志配置 =====
LOG_LEVEL=INFO
LOG_FORMAT=json

# ===== gRPC 配置 (可选) =====
ENABLE_GRPC=false
GRPC_PORT=50051

# ===== 容错配置 =====
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT=60

# ===== Token 审计 =====
TOKEN_AUDIT_ENABLED=true
TOKEN_AUDIT_LOG_DIR=./logs/tokens
```

### 4.2 AWS ECS Fargate 部署 (生产)

详见 `docs/deployment/DEPLOYMENT_COMPLETE.md`

**关键步骤**：

1. **申请 SSL 证书**
   ```bash
   ./deploy/aws/staging/setup-certificate.sh request
   ```

2. **配置 DNS**
   - 添加 CNAME 记录到 Route53
   - 等待证书验证（5-30分钟）

3. **一键部署**
   ```bash
   ./deploy/aws/staging/staging.sh deploy
   ```

4. **验证部署**
   ```bash
   curl https://agent.yourdomain.com/health
   ```

**成本优化**：
```bash
# 非工作时间停止环境
./deploy/aws/staging/staging.sh stop --keep-service

# 可节省约 70% 的 ECS 成本
```

### 4.3 Kubernetes 部署 (大规模生产)

#### 准备工作

```bash
# 安装 kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"

# 安装 helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# 配置 kubeconfig
export KUBECONFIG=~/.kube/config
```

#### Kubernetes 配置文件

创建 `k8s/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: zenflux-agent
  namespace: production
  labels:
    app: zenflux-agent
    version: v7.0
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: zenflux-agent
  template:
    metadata:
      labels:
        app: zenflux-agent
        version: v7.0
    spec:
      containers:
      - name: backend
        image: your-registry/zenflux-agent:v7.0
        ports:
        - containerPort: 8000
          name: http
          protocol: TCP
        - containerPort: 50051
          name: grpc
          protocol: TCP
        env:
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: zenflux-secrets
              key: anthropic-api-key
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: zenflux-secrets
              key: database-url
        - name: REDIS_HOST
          value: redis-service
        envFrom:
        - configMapRef:
            name: zenflux-config
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 2000m
            memory: 4Gi
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3
        volumeMounts:
        - name: workspace
          mountPath: /app/workspace
        - name: logs
          mountPath: /app/logs
      volumes:
      - name: workspace
        persistentVolumeClaim:
          claimName: zenflux-workspace-pvc
      - name: logs
        persistentVolumeClaim:
          claimName: zenflux-logs-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: zenflux-service
  namespace: production
spec:
  type: ClusterIP
  selector:
    app: zenflux-agent
  ports:
  - name: http
    port: 8000
    targetPort: 8000
    protocol: TCP
  - name: grpc
    port: 50051
    targetPort: 50051
    protocol: TCP
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: zenflux-hpa
  namespace: production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: zenflux-agent
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
      - type: Percent
        value: 100
        periodSeconds: 30
      - type: Pods
        value: 2
        periodSeconds: 60
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: zenflux-pdb
  namespace: production
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: zenflux-agent
```

创建 `k8s/configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: zenflux-config
  namespace: production
data:
  LOG_LEVEL: "INFO"
  LOG_FORMAT: "json"
  DEFAULT_LLM_MODEL: "claude-sonnet-4-5-20250929"
  CIRCUIT_BREAKER_ENABLED: "true"
  TOKEN_AUDIT_ENABLED: "true"
  ENABLE_GRPC: "true"
```

创建 `k8s/ingress.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: zenflux-ingress
  namespace: production
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/rate-limit: "100"
spec:
  tls:
  - hosts:
    - agent.yourdomain.com
    secretName: zenflux-tls
  rules:
  - host: agent.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: zenflux-service
            port:
              number: 8000
```

#### 部署命令

```bash
# 1. 创建 namespace
kubectl create namespace production

# 2. 创建 Secret
kubectl create secret generic zenflux-secrets \
  --from-literal=anthropic-api-key=$ANTHROPIC_API_KEY \
  --from-literal=database-url=$DATABASE_URL \
  --from-literal=e2b-api-key=$E2B_API_KEY \
  -n production

# 3. 应用配置
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/ingress.yaml

# 4. 验证部署
kubectl get pods -n production
kubectl get svc -n production
kubectl get ingress -n production

# 5. 查看日志
kubectl logs -f deployment/zenflux-agent -n production

# 6. 查看 HPA 状态
kubectl get hpa -n production
```

---

## 五、可观测性建设

### 5.1 分布式追踪 (P0)

#### OpenTelemetry 集成

创建 `infra/tracing/otel.py`:

```python
"""OpenTelemetry 分布式追踪集成"""
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

def init_tracing(service_name: str = "zenflux-agent"):
    """初始化 OpenTelemetry 追踪"""
    
    # 配置 Resource
    resource = Resource(attributes={
        SERVICE_NAME: service_name,
        "deployment.environment": os.getenv("ENVIRONMENT", "production"),
        "service.version": os.getenv("VERSION", "v7.0"),
    })
    
    # 配置 TracerProvider
    provider = TracerProvider(resource=resource)
    
    # 配置 Jaeger Exporter
    jaeger_exporter = JaegerExporter(
        agent_host_name=os.getenv("JAEGER_HOST", "localhost"),
        agent_port=int(os.getenv("JAEGER_PORT", "6831")),
    )
    
    # 添加 BatchSpanProcessor
    provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
    
    # 设置全局 TracerProvider
    trace.set_tracer_provider(provider)
    
    print(f"✅ OpenTelemetry 追踪已初始化: {service_name}")

def get_tracer(name: str):
    """获取 Tracer 实例"""
    return trace.get_tracer(name)
```

#### FastAPI 中间件

创建 `infra/tracing/middleware.py`:

```python
"""FastAPI 追踪中间件"""
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

class TracingMiddleware(BaseHTTPMiddleware):
    """追踪中间件"""
    
    async def dispatch(self, request: Request, call_next):
        tracer = trace.get_tracer(__name__)
        
        # 提取 trace context
        trace_id = request.headers.get("X-Trace-ID")
        request_id = request.headers.get("X-Request-ID")
        
        # 创建 span
        with tracer.start_as_current_span(
            f"{request.method} {request.url.path}",
            kind=trace.SpanKind.SERVER
        ) as span:
            # 设置 span 属性
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("http.route", request.url.path)
            span.set_attribute("request.id", request_id or "")
            
            start_time = time.time()
            
            try:
                response = await call_next(request)
                
                # 设置响应属性
                span.set_attribute("http.status_code", response.status_code)
                
                if response.status_code >= 500:
                    span.set_status(Status(StatusCode.ERROR))
                else:
                    span.set_status(Status(StatusCode.OK))
                
                return response
            
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
            
            finally:
                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("http.duration_ms", duration_ms)
```

#### 在 main.py 中集成

```python
from infra.tracing.otel import init_tracing
from infra.tracing.middleware import TracingMiddleware

# 初始化追踪
if os.getenv("TRACING_ENABLED", "false").lower() == "true":
    init_tracing("zenflux-agent")
    app.add_middleware(TracingMiddleware)
```

### 5.2 Prometheus Metrics (P0)

#### Metrics 暴露

创建 `infra/metrics/prometheus.py`:

```python
"""Prometheus Metrics 采集"""
from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
import time

# 定义 Metrics

# 请求计数
request_count = Counter(
    'zenflux_request_total',
    'Total HTTP requests',
    ['method', 'path', 'status']
)

# 请求延迟
request_duration = Histogram(
    'zenflux_request_duration_seconds',
    'HTTP request latency',
    ['method', 'path'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

# Token 消耗
token_usage = Counter(
    'zenflux_llm_tokens_total',
    'Total LLM tokens consumed',
    ['type', 'model']  # type: input/output/thinking
)

# 熔断器状态
circuit_breaker_state = Gauge(
    'zenflux_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half_open)',
    ['service']
)

# 活跃会话数
active_sessions = Gauge(
    'zenflux_active_sessions',
    'Number of active sessions'
)

# Agent 执行轮次
agent_turns = Counter(
    'zenflux_agent_turns_total',
    'Total agent execution turns',
    ['agent_type', 'status']  # status: success/failed
)

# 应用信息
app_info = Info(
    'zenflux_app',
    'Application information'
)
app_info.info({
    'version': 'v7.0',
    'environment': 'production'
})

def metrics_endpoint():
    """Prometheus metrics 端点"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
```

#### Metrics 中间件

创建 `infra/metrics/middleware.py`:

```python
"""Prometheus Metrics 中间件"""
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from .prometheus import request_count, request_duration

class MetricsMiddleware(BaseHTTPMiddleware):
    """Metrics 收集中间件"""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        response = await call_next(request)
        
        duration = time.time() - start_time
        
        # 记录 metrics
        request_count.labels(
            method=request.method,
            path=request.url.path,
            status=response.status_code
        ).inc()
        
        request_duration.labels(
            method=request.method,
            path=request.url.path
        ).observe(duration)
        
        return response
```

#### 暴露 /metrics 端点

在 `routers/metrics.py`:

```python
from fastapi import APIRouter
from infra.metrics.prometheus import metrics_endpoint

router = APIRouter(tags=["Metrics"])

@router.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint"""
    return metrics_endpoint()
```

在 `main.py` 中注册：

```python
from routers.metrics import router as metrics_router
from infra.metrics.middleware import MetricsMiddleware

app.include_router(metrics_router)
app.add_middleware(MetricsMiddleware)
```

### 5.3 Grafana 看板

#### Prometheus 配置

`prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'zenflux-agent'
    static_configs:
      - targets: ['zenflux-service:8000']
    metrics_path: '/metrics'
```

#### Grafana Dashboard JSON

创建 `monitoring/grafana/zenflux-dashboard.json` (简化版):

```json
{
  "dashboard": {
    "title": "Zenflux Agent V7 - Production",
    "panels": [
      {
        "title": "Request Rate (QPS)",
        "targets": [
          {
            "expr": "rate(zenflux_request_total[1m])"
          }
        ]
      },
      {
        "title": "P95/P99 Latency",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(zenflux_request_duration_seconds_bucket[5m]))",
            "legendFormat": "P95"
          },
          {
            "expr": "histogram_quantile(0.99, rate(zenflux_request_duration_seconds_bucket[5m]))",
            "legendFormat": "P99"
          }
        ]
      },
      {
        "title": "Token Usage (per minute)",
        "targets": [
          {
            "expr": "rate(zenflux_llm_tokens_total{type='input'}[1m])",
            "legendFormat": "Input"
          },
          {
            "expr": "rate(zenflux_llm_tokens_total{type='output'}[1m])",
            "legendFormat": "Output"
          }
        ]
      },
      {
        "title": "Circuit Breaker State",
        "targets": [
          {
            "expr": "zenflux_circuit_breaker_state"
          }
        ]
      },
      {
        "title": "Active Sessions",
        "targets": [
          {
            "expr": "zenflux_active_sessions"
          }
        ]
      }
    ]
  }
}
```

### 5.4 告警规则

#### Prometheus Alert Rules

`prometheus-alerts.yml`:

```yaml
groups:
  - name: zenflux_alerts
    interval: 30s
    rules:
      # 高错误率告警
      - alert: HighErrorRate
        expr: |
          rate(zenflux_request_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }} over the last 5 minutes"
      
      # 高延迟告警
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95, rate(zenflux_request_duration_seconds_bucket[5m])) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High latency detected"
          description: "P95 latency is {{ $value }}s"
      
      # 熔断器打开告警
      - alert: CircuitBreakerOpen
        expr: |
          zenflux_circuit_breaker_state{service="claude"} == 1
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Circuit breaker opened for {{ $labels.service }}"
      
      # Token 消耗异常
      - alert: HighTokenUsage
        expr: |
          rate(zenflux_llm_tokens_total[5m]) > 10000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High token usage detected"
          description: "Token usage is {{ $value }} tokens/s"
```

---

## 六、安全加固

### 6.1 认证鉴权

#### API Key 认证

在 `routers/auth.py`:

```python
from fastapi import Header, HTTPException, status
import os

async def verify_api_key(x_api_key: str = Header(...)):
    """验证 API Key"""
    valid_keys = os.getenv("API_KEYS", "").split(",")
    
    if x_api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )
    
    return x_api_key
```

在需要认证的路由中使用：

```python
from fastapi import Depends
from routers.auth import verify_api_key

@router.post("/api/v1/chat")
async def chat(
    request: ChatRequest,
    api_key: str = Depends(verify_api_key)
):
    ...
```

### 6.2 限流策略

#### Redis Token Bucket 限流

创建 `infra/middleware/rate_limiter.py`:

```python
"""基于 Redis 的限流中间件"""
import time
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
import redis.asyncio as aioredis

class RateLimiter:
    """Token Bucket 限流器"""
    
    def __init__(
        self,
        redis_url: str,
        rate: int = 100,  # 每分钟请求数
        burst: int = 10    # 突发容量
    ):
        self.redis = aioredis.from_url(redis_url)
        self.rate = rate
        self.burst = burst
        self.period = 60  # 1分钟
    
    async def is_allowed(self, key: str) -> bool:
        """判断是否允许请求"""
        now = time.time()
        
        # Lua 脚本实现 Token Bucket
        lua_script = """
        local key = KEYS[1]
        local rate = tonumber(ARGV[1])
        local burst = tonumber(ARGV[2])
        local period = tonumber(ARGV[3])
        local now = tonumber(ARGV[4])
        
        local token_key = key .. ':tokens'
        local ts_key = key .. ':ts'
        
        local last_tokens = tonumber(redis.call('get', token_key)) or burst
        local last_ts = tonumber(redis.call('get', ts_key)) or now
        
        local delta = math.max(0, now - last_ts)
        local tokens = math.min(burst, last_tokens + (delta * rate / period))
        
        if tokens < 1 then
            return 0
        else
            redis.call('setex', token_key, period, tokens - 1)
            redis.call('setex', ts_key, period, now)
            return 1
        end
        """
        
        result = await self.redis.eval(
            lua_script,
            1,
            key,
            str(self.rate),
            str(self.burst),
            str(self.period),
            str(now)
        )
        
        return result == 1

class RateLimitMiddleware(BaseHTTPMiddleware):
    """限流中间件"""
    
    def __init__(self, app, redis_url: str, rate: int = 100):
        super().__init__(app)
        self.limiter = RateLimiter(redis_url, rate)
    
    async def dispatch(self, request: Request, call_next):
        # 按 user_id 或 IP 限流
        user_id = request.headers.get("X-User-ID")
        rate_limit_key = f"rate_limit:{user_id or request.client.host}"
        
        if not await self.limiter.is_allowed(rate_limit_key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded"
            )
        
        return await call_next(request)
```

在 `main.py` 中启用：

```python
from infra.middleware.rate_limiter import RateLimitMiddleware

if os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true":
    app.add_middleware(
        RateLimitMiddleware,
        redis_url=os.getenv("REDIS_URL"),
        rate=int(os.getenv("RATE_LIMIT_PER_MINUTE", "100"))
    )
```

### 6.3 CORS 配置

生产环境 CORS 配置：

```python
from fastapi.middleware.cors import CORSMiddleware

# 生产环境：严格限制
if os.getenv("ENVIRONMENT") == "production":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://yourdomain.com",
            "https://www.yourdomain.com"
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
        max_age=3600,
    )
else:
    # 开发环境：允许所有
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

### 6.4 敏感信息保护

#### 环境变量加密 (AWS SSM)

```bash
# 存储敏感信息到 AWS SSM Parameter Store
aws ssm put-parameter \
  --name "/zenflux/prod/anthropic-api-key" \
  --value "sk-ant-xxxxx" \
  --type "SecureString" \
  --key-id "alias/aws/ssm"

# 在应用启动时加载
aws ssm get-parameter \
  --name "/zenflux/prod/anthropic-api-key" \
  --with-decryption \
  --query "Parameter.Value" \
  --output text
```

#### Kubernetes Secret

```bash
# 创建 Secret
kubectl create secret generic zenflux-secrets \
  --from-literal=anthropic-api-key=$ANTHROPIC_API_KEY \
  --from-literal=database-url=$DATABASE_URL \
  -n production

# 加密存储（启用 EncryptionConfig）
kubectl create secret generic zenflux-secrets \
  --from-file=./secrets.yaml \
  --dry-run=client -o yaml | \
  kubeseal -o yaml > sealed-secret.yaml
```

---

## 七、性能优化

### 7.1 数据库优化

#### PostgreSQL 连接池

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,           # 连接池大小
    max_overflow=40,        # 最大溢出连接数
    pool_timeout=30,        # 获取连接超时
    pool_recycle=3600,      # 连接回收时间（1小时）
    pool_pre_ping=True,     # 连接前检查
    echo=False,
)

async_session_maker = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
```

#### 索引优化

```sql
-- 用户 ID 索引
CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);

-- 时间范围查询索引
CREATE INDEX idx_messages_created_at ON messages(created_at DESC);

-- 复合索引
CREATE INDEX idx_conversations_user_created ON conversations(user_id, created_at DESC);
```

### 7.2 Redis 缓存策略

#### 多级缓存

```python
from functools import wraps
import pickle

def multi_level_cache(ttl: int = 300):
    """多级缓存装饰器：内存 → Redis → 数据库"""
    
    # L1 内存缓存
    memory_cache = {}
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{args}:{kwargs}"
            
            # L1: 检查内存缓存
            if cache_key in memory_cache:
                return memory_cache[cache_key]
            
            # L2: 检查 Redis 缓存
            redis_value = await redis.get(cache_key)
            if redis_value:
                result = pickle.loads(redis_value)
                memory_cache[cache_key] = result
                return result
            
            # L3: 查询数据库
            result = await func(*args, **kwargs)
            
            # 写回缓存
            memory_cache[cache_key] = result
            await redis.setex(cache_key, ttl, pickle.dumps(result))
            
            return result
        
        return wrapper
    
    return decorator
```

### 7.3 LLM 调用优化

#### Prompt Caching

```python
# 在 Claude LLM 调用中启用 Prompt Caching
from anthropic import Anthropic

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

response = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=8192,
    system=[
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"}  # 缓存 system prompt
        }
    ],
    messages=messages
)
```

**节省成本**：
- 缓存命中：输入 Token 成本降低 90%
- 适用场景：system prompt、长文档、知识库

#### 批量处理

```python
# 使用 Anthropic Batch API (50% 折扣)
batch_requests = [
    {"model": "claude-sonnet-4-5-20250929", "messages": messages1},
    {"model": "claude-sonnet-4-5-20250929", "messages": messages2},
    # ... 更多请求
]

batch_response = await client.messages.batch.create(
    requests=batch_requests,
    processing_mode="async"  # 异步处理
)
```

### 7.4 上下文压缩

利用现有的 `core/context/compaction/` 三层防护：

1. **预防层**: Token 预算控制
2. **动态层**: 实时压缩
3. **兜底层**: 紧急截断

配置文件 `config/context_compaction.yaml`:

```yaml
context_compaction:
  enabled: true
  
  # 预防层
  prevention:
    max_input_tokens: 150000
    max_output_tokens: 8192
    reserve_buffer: 2000
  
  # 动态层
  dynamic:
    soft_limit: 100000
    hard_limit: 150000
    compression_strategy: "intelligent"  # intelligent / aggressive
  
  # 兜底层
  emergency:
    trigger_threshold: 180000
    keep_recent_messages: 10
    keep_system_prompt: true
```

---

## 八、运维手册

### 8.1 健康检查

#### 健康检查端点

`routers/health.py`:

```python
from fastapi import APIRouter, status
from typing import Dict, Any
import redis.asyncio as aioredis
from infra.database import engine

router = APIRouter(tags=["Health"])

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """简单健康检查（Liveness Probe）"""
    return {
        "status": "healthy",
        "service": "zenflux-agent",
        "version": "v7.0"
    }

@router.get("/health/ready")
async def readiness_check() -> Dict[str, Any]:
    """就绪检查（Readiness Probe）- 检查依赖"""
    checks = {}
    overall_healthy = True
    
    # 检查数据库
    try:
        async with engine.begin() as conn:
            await conn.execute("SELECT 1")
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {str(e)}"
        overall_healthy = False
    
    # 检查 Redis
    try:
        redis = aioredis.from_url(os.getenv("REDIS_URL"))
        await redis.ping()
        checks["redis"] = "healthy"
    except Exception as e:
        checks["redis"] = f"unhealthy: {str(e)}"
        overall_healthy = False
    
    # 检查 Claude API (可选)
    try:
        from core.llm.claude import ClaudeLLMService
        llm = ClaudeLLMService()
        # 简单的 API 可用性检查
        checks["claude_api"] = "healthy"
    except Exception as e:
        checks["claude_api"] = f"warning: {str(e)}"
        # Claude API 不可用不影响整体健康状态
    
    return {
        "status": "healthy" if overall_healthy else "unhealthy",
        "checks": checks
    }
```

### 8.2 日志管理

#### 日志配置

`logger.py`:

```python
import logging
import sys
import json
from datetime import datetime
from pathlib import Path

def setup_logging(
    level: str = "INFO",
    log_format: str = "json",  # json or text
    log_file: str = None
):
    """配置日志系统"""
    
    # 创建 logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper()))
    
    # 清除现有 handlers
    logger.handlers.clear()
    
    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    
    if log_format == "json":
        # JSON 格式（生产环境）
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                log_obj = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                }
                
                if record.exc_info:
                    log_obj["exception"] = self.formatException(record.exc_info)
                
                return json.dumps(log_obj)
        
        console_handler.setFormatter(JSONFormatter())
    else:
        # Text 格式（开发环境）
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    
    # File Handler (可选)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=100 * 1024 * 1024,  # 100MB
            backupCount=10
        )
        file_handler.setFormatter(
            JSONFormatter() if log_format == "json" else formatter
        )
        logger.addHandler(file_handler)
    
    return logger
```

#### 日志查询

```bash
# Kubernetes 日志
kubectl logs -f deployment/zenflux-agent -n production

# 查询最近 100 行
kubectl logs --tail=100 deployment/zenflux-agent -n production

# 查询特定时间范围
kubectl logs --since=1h deployment/zenflux-agent -n production

# 导出日志
kubectl logs deployment/zenflux-agent -n production > app.log

# 使用 stern 查看多个 Pod 日志
stern zenflux-agent -n production
```

### 8.3 数据备份

#### 数据库备份脚本

```bash
#!/bin/bash
# backup-database.sh

set -e

BACKUP_DIR="/backup/zenflux"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/zenflux_${DATE}.sql"

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份数据库
pg_dump -h $DB_HOST -U $DB_USER -d zenflux > $BACKUP_FILE

# 压缩备份
gzip $BACKUP_FILE

# 删除 7 天前的备份
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete

echo "✅ 备份完成: ${BACKUP_FILE}.gz"
```

#### 自动备份 (Cron)

```bash
# 每天凌晨 2 点备份
0 2 * * * /path/to/backup-database.sh >> /var/log/backup.log 2>&1
```

### 8.4 扩缩容策略

#### 手动扩容

```bash
# Docker Compose (手动增加副本)
docker compose up -d --scale backend=3

# Kubernetes
kubectl scale deployment zenflux-agent --replicas=5 -n production
```

#### 自动扩容 (HPA)

已在 Kubernetes 配置中定义 HPA，基于：
- CPU 使用率 > 70%
- 内存使用率 > 80%

#### 预热策略

```bash
# 扩容前预热新实例
kubectl set image deployment/zenflux-agent \
  backend=your-registry/zenflux-agent:v7.0 \
  --record -n production

# 滚动更新配置
kubectl patch deployment zenflux-agent -n production -p '{
  "spec": {
    "strategy": {
      "rollingUpdate": {
        "maxSurge": 1,
        "maxUnavailable": 0
      }
    }
  }
}'
```

### 8.5 版本更新流程

#### 蓝绿部署

```bash
# 1. 部署绿色环境
kubectl apply -f k8s/deployment-green.yaml

# 2. 验证绿色环境
kubectl get pods -l version=green -n production

# 3. 切换流量到绿色环境
kubectl patch service zenflux-service -n production -p '{
  "spec": {
    "selector": {
      "version": "green"
    }
  }
}'

# 4. 验证流量切换
curl https://agent.yourdomain.com/health

# 5. 清理蓝色环境
kubectl delete deployment zenflux-agent-blue -n production
```

#### 灰度发布 (Canary)

```bash
# 1. 部署 Canary 版本（10% 流量）
kubectl apply -f k8s/deployment-canary.yaml

# 2. 逐步增加流量
# 20%
kubectl scale deployment zenflux-agent-canary --replicas=2 -n production
# 50%
kubectl scale deployment zenflux-agent-canary --replicas=5 -n production
# 100%
kubectl scale deployment zenflux-agent-canary --replicas=10 -n production
kubectl delete deployment zenflux-agent-stable -n production
```

---

## 九、故障应急

### 9.1 常见故障处理

#### 问题 1：Pod 启动失败

```bash
# 查看 Pod 状态
kubectl get pods -n production

# 查看 Pod 事件
kubectl describe pod <pod-name> -n production

# 查看日志
kubectl logs <pod-name> -n production

# 常见原因：
# 1. 镜像拉取失败 → 检查镜像仓库凭证
# 2. 配置错误 → 检查 ConfigMap/Secret
# 3. 资源不足 → 检查节点资源
# 4. 健康检查失败 → 检查应用启动时间
```

#### 问题 2：数据库连接失败

```bash
# 测试数据库连接
kubectl run -it --rm debug --image=postgres:16 --restart=Never -- \
  psql -h postgres-service -U zenflux -d zenflux

# 检查数据库 Service
kubectl get svc postgres-service -n production

# 检查数据库 Pod
kubectl get pods -l app=postgres -n production

# 解决方案：
# 1. 检查数据库密码
# 2. 检查网络策略
# 3. 检查数据库是否正常运行
```

#### 问题 3：Redis 连接失败

```bash
# 测试 Redis 连接
kubectl run -it --rm debug --image=redis:7 --restart=Never -- \
  redis-cli -h redis-service ping

# 检查 Redis Service
kubectl get svc redis-service -n production

# 解决方案：
# 1. 检查 Redis 密码
# 2. 检查 Redis 是否正常运行
# 3. 检查网络连接
```

#### 问题 4：高延迟

```bash
# 查看 Prometheus metrics
curl http://zenflux-service:8000/metrics | grep request_duration

# 查看慢查询
kubectl logs -f deployment/zenflux-agent -n production | grep "slow"

# 排查思路：
# 1. 检查数据库连接池是否耗尽
# 2. 检查 LLM API 响应时间
# 3. 检查上下文大小是否超限
# 4. 检查是否触发熔断
```

#### 问题 5：Token 消耗异常

```bash
# 查看 Token 审计日志
kubectl exec -it deployment/zenflux-agent -n production -- \
  cat logs/tokens/<user_id>/$(date +%Y-%m-%d).jsonl | jq .

# 统计 Token 使用
cat logs/tokens/*/*.jsonl | jq '.tokens.total' | \
  awk '{sum+=$1} END {print "Total tokens:", sum}'

# 排查思路：
# 1. 检查是否有异常用户
# 2. 检查上下文是否过大
# 3. 检查是否启用 Prompt Caching
```

### 9.2 应急预案

#### Runbook: 服务完全不可用

1. **立即响应**（5分钟内）
   ```bash
   # 检查服务状态
   kubectl get pods -n production
   
   # 查看最近事件
   kubectl get events -n production --sort-by='.lastTimestamp'
   
   # 查看日志
   kubectl logs -f deployment/zenflux-agent -n production --tail=100
   ```

2. **快速降级**（10分钟内）
   ```bash
   # 回滚到上一个稳定版本
   kubectl rollout undo deployment/zenflux-agent -n production
   
   # 或者手动指定版本
   kubectl set image deployment/zenflux-agent \
     backend=your-registry/zenflux-agent:v6.3 \
     -n production
   ```

3. **通知干系人**
   - 发送告警通知
   - 更新状态页面
   - 通知客户（如果必要）

4. **根因分析**（事后）
   - 收集日志和 metrics
   - 分析故障原因
   - 制定改进措施

#### Runbook: Claude API 不可用

1. **自动降级**（熔断器触发）
   ```python
   # 已在 infra/resilience/fallback.py 中实现
   # 降级到 OpenAI/Gemini
   ```

2. **手动切换 LLM**
   ```bash
   # 更新 ConfigMap
   kubectl patch configmap zenflux-config -n production -p '{
     "data": {
       "DEFAULT_LLM_MODEL": "gpt-4-turbo"
     }
   }'
   
   # 重启 Pods 使配置生效
   kubectl rollout restart deployment/zenflux-agent -n production
   ```

3. **监控恢复状态**
   ```bash
   # 查看熔断器状态
   curl http://zenflux-service:8000/metrics | grep circuit_breaker_state
   ```

#### Runbook: 数据库故障

1. **切换到从库**（如果有主从架构）
   ```bash
   # 更新数据库连接字符串
   kubectl set env deployment/zenflux-agent \
     DATABASE_URL=postgresql://user:pass@replica-host:5432/zenflux \
     -n production
   ```

2. **启用只读模式**
   ```python
   # 在 main.py 中添加只读中间件
   @app.middleware("http")
   async def read_only_mode(request: Request, call_next):
       if request.method in ["POST", "PUT", "DELETE"]:
           return Response(
               status_code=503,
               content="Service temporarily in read-only mode"
           )
       return await call_next(request)
   ```

### 9.3 监控告警联系人

| 告警级别 | 联系人 | 响应时间 | 通知方式 |
|---------|--------|---------|---------|
| Critical | On-call Engineer | 5分钟 | 电话 + 短信 + 钉钉 |
| Warning | Team Lead | 15分钟 | 钉钉 + 邮件 |
| Info | 全体团队 | 1小时 | 邮件 |

---

## 十、附录

### 附录 A: 环境变量完整列表

#### 核心配置

| 变量名 | 必需 | 默认值 | 说明 |
|--------|-----|-------|------|
| `ANTHROPIC_API_KEY` | ✅ | - | Claude API Key |
| `E2B_API_KEY` | ✅ | - | E2B Sandbox API Key |
| `ENVIRONMENT` | ❌ | `development` | 运行环境 (development/staging/production) |
| `VERSION` | ❌ | `v7.0` | 应用版本号 |

#### 数据库配置

| 变量名 | 必需 | 默认值 | 说明 |
|--------|-----|-------|------|
| `DATABASE_TYPE` | ❌ | `sqlite` | 数据库类型 (sqlite/postgresql) |
| `DATABASE_URL` | ✅ (PG) | - | PostgreSQL 连接字符串 |
| `DATABASE_PATH` | ✅ (SQLite) | `./workspace/database/zenflux.db` | SQLite 数据库路径 |
| `DB_POOL_SIZE` | ❌ | `20` | 数据库连接池大小 |
| `DB_MAX_OVERFLOW` | ❌ | `40` | 最大溢出连接数 |

#### Redis 配置

| 变量名 | 必需 | 默认值 | 说明 |
|--------|-----|-------|------|
| `REDIS_HOST` | ✅ | `localhost` | Redis 主机 |
| `REDIS_PORT` | ❌ | `6379` | Redis 端口 |
| `REDIS_PASSWORD` | ❌ | - | Redis 密码 |
| `REDIS_DB` | ❌ | `0` | Redis 数据库编号 |
| `REDIS_MAX_CONNECTIONS` | ❌ | `50` | Redis 最大连接数 |

#### LLM 配置

| 变量名 | 必需 | 默认值 | 说明 |
|--------|-----|-------|------|
| `DEFAULT_LLM_MODEL` | ❌ | `claude-sonnet-4-5-20250929` | 默认 LLM 模型 |
| `DEFAULT_LLM_TEMPERATURE` | ❌ | `0.7` | 默认温度 |
| `DEFAULT_LLM_MAX_TOKENS` | ❌ | `8192` | 默认最大 Token 数 |
| `OPENAI_API_KEY` | ❌ | - | OpenAI API Key（降级用） |
| `GOOGLE_API_KEY` | ❌ | - | Gemini API Key（降级用） |

#### 日志配置

| 变量名 | 必需 | 默认值 | 说明 |
|--------|-----|-------|------|
| `LOG_LEVEL` | ❌ | `INFO` | 日志级别 (DEBUG/INFO/WARNING/ERROR) |
| `LOG_FORMAT` | ❌ | `json` | 日志格式 (json/text) |
| `LOG_FILE` | ❌ | - | 日志文件路径 |

#### 容错配置

| 变量名 | 必需 | 默认值 | 说明 |
|--------|-----|-------|------|
| `CIRCUIT_BREAKER_ENABLED` | ❌ | `true` | 是否启用熔断器 |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | ❌ | `5` | 熔断器失败阈值 |
| `CIRCUIT_BREAKER_TIMEOUT` | ❌ | `60` | 熔断器超时时间（秒） |
| `RETRY_MAX_ATTEMPTS` | ❌ | `3` | 最大重试次数 |
| `RETRY_BACKOFF_FACTOR` | ❌ | `2` | 重试退避因子 |

#### 监控配置

| 变量名 | 必需 | 默认值 | 说明 |
|--------|-----|-------|------|
| `TRACING_ENABLED` | ❌ | `false` | 是否启用分布式追踪 |
| `JAEGER_HOST` | ❌ | `localhost` | Jaeger Agent 主机 |
| `JAEGER_PORT` | ❌ | `6831` | Jaeger Agent 端口 |
| `METRICS_ENABLED` | ❌ | `true` | 是否启用 Metrics |
| `TOKEN_AUDIT_ENABLED` | ❌ | `true` | 是否启用 Token 审计 |
| `TOKEN_AUDIT_LOG_DIR` | ❌ | `./logs/tokens` | Token 审计日志目录 |

#### 限流配置

| 变量名 | 必需 | 默认值 | 说明 |
|--------|-----|-------|------|
| `RATE_LIMIT_ENABLED` | ❌ | `true` | 是否启用限流 |
| `RATE_LIMIT_PER_MINUTE` | ❌ | `100` | 每分钟请求数限制 |

#### gRPC 配置

| 变量名 | 必需 | 默认值 | 说明 |
|--------|-----|-------|------|
| `ENABLE_GRPC` | ❌ | `false` | 是否启用 gRPC 服务 |
| `GRPC_HOST` | ❌ | `0.0.0.0` | gRPC 监听主机 |
| `GRPC_PORT` | ❌ | `50051` | gRPC 监听端口 |
| `GRPC_MAX_WORKERS` | ❌ | `0` | gRPC 最大工作线程数（0=自动） |

### 附录 B: 配置文件索引

| 配置文件 | 用途 | 位置 |
|----------|------|------|
| `resilience.yaml` | 容错配置（熔断/重试/超时） | `config/resilience.yaml` |
| `context_compaction.yaml` | 上下文压缩策略 | `config/context_compaction.yaml` |
| `capabilities.yaml` | 工具能力配置 | `config/capabilities.yaml` |
| `routing_rules.yaml` | Agent 路由规则 | `config/routing_rules.yaml` |
| `llm_config/profiles.yaml` | LLM 配置 Profile | `config/llm_config/profiles.yaml` |
| `{instance}/config.yaml` | 实例配置 | `instances/{name}/config.yaml` |
| `{instance}/prompt.md` | 运营提示词 | `instances/{name}/prompt.md` |

### 附录 C: API 端点清单

#### 核心 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | Liveness 健康检查 |
| `/health/ready` | GET | Readiness 就绪检查 |
| `/metrics` | GET | Prometheus Metrics |
| `/api/v1/chat` | POST | 对话接口 |
| `/api/v1/chat/stream` | POST | 流式对话接口 |
| `/api/v1/agents` | GET | 获取 Agent 列表 |
| `/api/v1/conversations` | GET | 获取对话历史 |
| `/api/v1/files/upload` | POST | 文件上传 |
| `/api/v1/mem0/memories` | GET | 获取用户记忆 |

#### 管理 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/admin/sessions` | GET | 获取活跃会话 |
| `/admin/metrics` | GET | 系统指标 |
| `/admin/config/reload` | POST | 重新加载配置 |

### 附录 D: 部署检查清单

#### 部署前检查

- [ ] 环境变量已配置完整
- [ ] API Keys 已填写并验证
- [ ] 数据库连接已测试
- [ ] Redis 连接已测试
- [ ] 存储桶已创建并配置权限
- [ ] SSL 证书已申请并验证
- [ ] DNS 记录已配置
- [ ] 容错配置已启用
- [ ] 日志收集已配置
- [ ] 监控告警已配置

#### 部署后验证

- [ ] 健康检查端点正常
- [ ] API 接口可访问
- [ ] 对话功能正常
- [ ] 文件上传正常
- [ ] 日志正常输出
- [ ] Metrics 正常暴露
- [ ] 告警规则已生效
- [ ] 自动扩缩容测试通过
- [ ] 故障恢复测试通过
- [ ] 性能测试达标

### 附录 E: SLA 保障矩阵

| SLA 指标 | 目标 | 实现手段 |
|----------|------|----------|
| **可用性** | >= 99.9% (月度) | 多副本 + HPA + PDB + 自动故障转移 |
| **P95 延迟** | < 3s | 熔断 + 降级 + 缓存 + 连接池优化 |
| **P99 延迟** | < 10s | LLM 超时控制 + 上下文压缩 |
| **错误率** | < 0.1% | 重试策略 + 降级方案 + 数据校验 |
| **MTTR** | < 5min | 自动扩缩容 + 健康检查 + 告警 |
| **数据持久性** | 99.999% | 数据库主从 + 每日备份 + 跨 AZ |
| **RTO** | < 15min | 快速回滚 + 蓝绿部署 |
| **RPO** | < 1h | 实时同步 + 每小时增量备份 |

### 附录 F: 成本估算

#### AWS ECS Fargate 方案

| 资源 | 配置 | 月成本（USD） |
|------|------|---------------|
| **计算资源** | | |
| ECS Fargate | 0.5 vCPU, 1GB, 24/7 | $15 |
| Fargate Spot | 0.5 vCPU, 1GB, 24/7（节省 70%） | $5 |
| **存储** | | |
| EFS | 10GB + 访问费 | $3 |
| EBS Snapshot | 10GB 备份 | $0.5 |
| **网络** | | |
| ALB | 共享（无额外成本） | $0 |
| 数据传输 | 估算 100GB/月 | $5 |
| **数据库** | | |
| RDS PostgreSQL | db.t3.micro（主从） | $30 |
| ElastiCache Redis | cache.t3.micro | $15 |
| **监控** | | |
| CloudWatch Logs | 5GB/月 | $3 |
| CloudWatch Metrics | 标准指标 | $0 |
| **合计（标准）** | | **~$71/月** |
| **合计（优化）** | | **~$31/月**（使用 Spot + SQLite + 停用非工作时间） |

#### Kubernetes 方案

| 资源 | 配置 | 月成本（USD） |
|------|------|---------------|
| **计算资源** | | |
| EKS 控制平面 | 1 集群 | $73 |
| EC2 实例（节点） | t3.medium x 3（节省计划） | $60 |
| **存储** | | |
| EBS 卷 | 100GB gp3 | $8 |
| **网络** | | |
| ALB | 1 个 | $16 |
| 数据传输 | 估算 100GB/月 | $5 |
| **数据库** | | |
| RDS PostgreSQL | db.t3.medium（主从） | $100 |
| ElastiCache Redis Cluster | cache.r6g.large x 3 | $200 |
| **监控** | | |
| Prometheus + Grafana（自建） | 包含在计算成本 | $0 |
| **合计** | | **~$462/月** |

**成本优化建议**：
1. 使用 Spot 实例（节省 70%）
2. 启用 Savings Plans（节省 30-50%）
3. 非工作时间停止环境（节省 70%）
4. 使用预留实例（节省 40%）
5. 启用 S3 Intelligent-Tiering（自动优化存储成本）

---

## 🎉 总结

本文档提供了 Zenflux Agent V7 面向生产环境的完整部署方案，涵盖：

✅ **架构全景** - V7 核心架构与模块结构  
✅ **部署方案** - Docker Compose / AWS ECS / Kubernetes  
✅ **基础设施** - 数据库、Redis、向量数据库、对象存储  
✅ **可观测性** - 分布式追踪、Metrics、Grafana、告警  
✅ **安全加固** - 认证鉴权、限流、CORS、敏感信息保护  
✅ **性能优化** - 数据库优化、缓存策略、LLM 优化、上下文压缩  
✅ **运维手册** - 健康检查、日志管理、备份、扩缩容、版本更新  
✅ **故障应急** - 常见故障处理、应急预案、监控告警

**部署前请务必**：
1. 阅读完整文档
2. 完成部署前检查清单
3. 配置监控告警
4. 制定应急预案
5. 进行压力测试

**获取帮助**：
- 📚 完整文档：`docs/`
- 💬 问题反馈：GitHub Issues
- 📧 邮件支持：support@yourdomain.com

---

**祝部署顺利！🚀**

*文档版本: V7.0*  
*最后更新: 2026-01-15*

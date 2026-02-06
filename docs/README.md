# ZenFlux Agent 文档中心

> 本目录包含 ZenFlux Agent 的所有技术文档。

---

## 目录结构

```
docs/
├── architecture/       # 核心架构设计（3 个核心文档 + 4 个子目录）
│   ├── 00-ARCHITECTURE-OVERVIEW.md    # 架构概览（入门必读）
│   ├── SYSTEM_ARCHITECTURE.md         # 系统架构图
│   ├── AGENT_ARCHITECTURE_VISUAL.md   # Agent 架构可视化
│   ├── decisions/      # 架构决策记录（ADR）- 4 个文档
│   ├── features/       # 功能模块设计 - 25 个文档
│   ├── integrations/   # 外部集成方案 - 4 个文档
│   └── archived/       # 历史版本文档 - 11 个文档
├── api/                # API 规范（5 个文档）
├── specs/              # 技术规格（4 个文档）
├── guides/             # 使用指南（21 个文档）
├── deployment/         # 部署文档（7 个文档）
├── analysis/           # 分析文档（8 个文档）
├── reports/            # 实施报告（23 个文档）
├── troubleshooting/    # 问题排查（2 个文档）
├── use-cases/          # 使用场景（2 个文档）
├── hiring/             # 招聘面试题（5 个文档）
├── issues/             # 问题追踪（1 个文档）
└── internal/           # 内部文档（1 个文档）
```

**目录说明**：
- `architecture/` - 系统设计的核心，包含架构决策、功能设计、集成方案
- `api/` + `specs/` - 接口规范和技术规格，开发必读
- `guides/` - 实用指南，快速上手和集成参考
- `deployment/` - 部署运维相关
- `analysis/` + `reports/` - 分析报告和实施总结
- `troubleshooting/` - 常见问题解决方案
- `archived/` - 历史版本文档，仅供参考

---

## 快速导航

### 核心架构 (`architecture/`)

**入门必读**：
- [架构概览](architecture/00-ARCHITECTURE-OVERVIEW.md) - 系统整体架构
- [系统架构图](architecture/SYSTEM_ARCHITECTURE.md) - 架构可视化

**核心协议**：
| 文档 | 说明 |
|-----|------|
| [01-记忆协议](architecture/features/01-MEMORY-PROTOCOL.md) | 记忆系统设计 |
| [02-能力路由](architecture/features/02-CAPABILITY-ROUTING.md) | 工具选择与路由 |
| [03-事件协议](architecture/features/03-EVENT-PROTOCOL.md) | 事件驱动设计 |
| [05-多智能体编排](architecture/features/05-MULTI-AGENT-ORCHESTRATION.md) | 多 Agent 协作 |
| [06-对话历史](architecture/features/06-CONVERSATION-HISTORY.md) | 对话存储设计 |
| [消息会话架构](architecture/features/MESSAGE_SESSION_ARCHITECTURE.md) | 消息会话系统完整设计（v6.0） |

**架构决策** (`architecture/decisions/`)：
- [缓存架构决策](architecture/decisions/cache-architecture-decision.md)
- [上下文管理决策](architecture/decisions/context_management_decision.md)
- [分层原则](architecture/decisions/layering_principles.md)

---

### API 规范 (`api/`)

| 文档 | 说明 |
|-----|------|
| [Chat API](api/chat_api_specification.md) | 聊天接口规范 |
| [Message/Session API](api/message-session-api-specification.md) | 消息会话接口 |
| [SSE 规范](api/ZENO_SSE_SPEC.md) | 流式事件规范 |

---

### 技术规格 (`specs/`)

| 文档 | 说明 |
|-----|------|
| [Agent I/O 规范](specs/AGENT_IO_SPECIFICATION.md) | 智能体输入输出 |
| [数据库设计](specs/DATABASE.md) | 数据库 Schema |
| [文件存储系统](specs/FILE_STORAGE_SYSTEM.md) | 文件存储方案 |
| [工具注册规范](specs/TOOL_REGISTRATION_SPEC.md) | 工具注册协议 |

---

### 使用指南 (`guides/`)

**快速入门**：
- [工具参考](guides/tool_reference.md) - 可用工具列表
- [工具配置指南](guides/tool_configuration_guide.md) - 工具配置方法

**集成指南**：
- [MCP 集成清单](guides/MCP_INTEGRATION_CHECKLIST.md) - MCP 工具接入
- [E2B 快速开始](guides/E2B_QUICKSTART.md) - E2B 沙盒入门
- [E2B 集成](guides/E2B_INTEGRATION.md) - E2B 完整集成
- [gRPC 集成](guides/GRPC_INTEGRATION.md) - gRPC 服务集成
- [Mem0 指南](guides/MEM0_GUIDE.md) - 记忆增强集成

**测试指南**：
- [测试执行指南](guides/TEST_EXECUTION_GUIDE.md) - 测试运行方法

**高级主题**：
- [上下文压缩策略](guides/context_compression_strategy.md)
- [存储优化](guides/storage_optimization.md)
- [弹性使用指南](guides/resilience_usage.md)

---

### 部署文档 (`deployment/`)

| 文档 | 说明 |
|-----|------|
| [README](deployment/README.md) | 部署概览 |
| [Docker 部署](deployment/DOCKER_DEPLOYMENT.md) | Docker 容器部署 |
| [生产部署](deployment/PRODUCTION_DEPLOYMENT.md) | 生产环境部署 |
| [数据库迁移](deployment/DATABASE_ENVIRONMENT_MIGRATION.md) | 数据库环境迁移 |

---

### 分析与报告

**分析文档** (`analysis/`)：
- [Simple Agent 流程分析](analysis/SIMPLE_AGENT_FLOW_ANALYSIS.md)
- [Multi Agent 流程分析](analysis/MULTI_AGENT_FLOW_ANALYSIS.md)
- [性能优化指南](analysis/PERFORMANCE_OPTIMIZATION_GUIDE.md)
- [计费架构分析](analysis/BILLING_ARCHITECTURE_ANALYSIS.md)

**实施报告** (`reports/`)：
- [架构优化实施报告](reports/architecture_optimization_implementation_report.md)
- [E2E 流程审计报告](reports/E2E_FLOW_AUDIT_REPORT.md)
- [E2E 测试交付](reports/E2E_TEST_DELIVERY.md)
- [E2E 验证报告](reports/E2E_VALIDATION_REPORT.md)
- [综合验证报告](reports/COMPREHENSIVE_VALIDATION_REPORT.md)
- [验证摘要](reports/VALIDATION_SUMMARY.md)
- [V9.0 交付总结](reports/V9.0-DELIVERY-SUMMARY.md)
- [项目问题分析](reports/PROJECT_ISSUES_ANALYSIS.md)

---

### 问题排查 (`troubleshooting/`)

| 问题 | 文档 |
|-----|------|
| AWS NLB 超时 | [aws-nlb-timeout-fix.md](troubleshooting/aws-nlb-timeout-fix.md) |
| gRPC 上下文取消 | [grpc-context-canceled.md](troubleshooting/grpc-context-canceled.md) |

---

## 文档维护约定

1. **新功能**：在 `architecture/features/` 添加设计文档
2. **架构决策**：在 `architecture/decisions/` 记录 ADR
3. **API 变更**：更新 `api/` 下对应文档
4. **问题排查**：在 `troubleshooting/` 记录解决方案
5. **过时文档**：移动到 `architecture/archived/`

---

## 贡献指南

- 文档使用 Markdown 格式
- 文件名使用 `UPPER_CASE` 或 `kebab-case`
- 代码块必须可复制执行
- 保持文档与代码同步更新

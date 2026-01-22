# Workers 配置目录（高级功能）

> ⚠️ **大多数情况无需配置**：LeadAgent 会自动分解任务并分配 Worker，无需手动定义。

本目录用于**高级场景**下自定义 Multi-Agent Workers。

## 何时需要自定义 Workers？

| 场景 | 是否需要 | 说明 |
|------|---------|------|
| 普通多智能体任务 | ❌ 不需要 | LeadAgent 自动分解任务 |
| 固定领域专家角色 | ⚠️ 可选 | 如需固定"法律专家"、"财务专家"角色 |
| Worker 需要特殊模型 | ⚠️ 可选 | 如某 Worker 必须用 GPT-4o |
| Worker 需要特殊工具集 | ⚠️ 可选 | 如某 Worker 只能用特定 API |

## 极简配置（推荐）

在 `config.yaml` 中只需配置 `mode`：

```yaml
multi_agent:
  mode: "auto"  # disabled / auto / enabled
```

框架自动处理：
- **任务分解**：LeadAgent 分析任务并拆分子任务
- **Worker 创建**：根据子任务动态创建 Worker
- **并行调度**：DAGScheduler 自动处理依赖关系
- **质量评估**：Critic Agent 评估并触发重试

## 高级：自定义 Worker（可选）

如需自定义，创建 `worker_registry.yaml`：

```yaml
workers:
  - name: legal_expert
    description: "法律合规专家"
    model: "claude-sonnet-4-5-20250929"  # 覆盖默认模型
    capabilities:
      - knowledge_search
    prompt: |
      你是法律合规专家，专注于...
```

## 目录结构

```
workers/
├── README.md                 # 本说明
└── worker_registry.yaml      # Worker 注册表（可选）
```

## 参考

- 多智能体架构：`docs/architecture/00-ARCHITECTURE-OVERVIEW.md`
- LeadAgent 任务分解：`core/agent/multi/lead_agent.py`
- DAGScheduler 调度：`core/agent/multi/orchestrator.py`

# Workers 配置目录

本目录用于配置 **Multi-Agent Workers**，每个 Worker 是一个专业领域的 Agent。

## 目录结构

```
workers/
├── worker_registry.yaml    # Workers 注册表（推荐）
├── refactor/               # 重构专家
│   ├── prompt.md           # 系统提示词（必需）
│   └── config.yaml         # Worker 配置（可选）
├── css/                    # CSS 专家
│   └── prompt.md
└── test/                   # 测试专家
    └── prompt.md
```

## 配置方式

### 方式 1：worker_registry.yaml（推荐）

在 `worker_registry.yaml` 中声明所有 Workers：

```yaml
workers:
  - name: refactor
    specialization: refactor
    enabled: true
    description: "代码重构专家"
    capabilities:
      - file_operations
      - code_execution
```

### 方式 2：自动发现（兼容模式）

如果没有 `worker_registry.yaml`，系统会自动发现所有包含 `prompt.md` 的子目录。

## Worker 配置文件

### prompt.md（必需）

Worker 的系统提示词，定义其行为和能力：

```markdown
# 重构专家 Worker

你是一个代码重构专家...

## 核心职责
- ...

## 行为约束
- ✅ 只专注于重构
- ❌ 不要添加新功能
```

### config.yaml（可选）

Worker 的额外配置，可覆盖默认值：

```yaml
# 覆盖模型
model: "claude-sonnet-4-5-20250929"

# 覆盖最大轮次
max_turns: 10

# 自定义配置
custom:
  strict_mode: true
```

## 启用 Multi-Agent

在实例的 `config.yaml` 中启用：

```yaml
multi_agent:
  enabled: true
  max_concurrent_workers: 5
```

## 使用场景

Multi-Agent 适用于可并行化的复杂任务：

- ✅ "重构代码，同时优化 CSS 并补充测试"
- ✅ "分析 10 家公司的财报"
- ❌ 简单的单步任务
- ❌ 强依赖的串行任务

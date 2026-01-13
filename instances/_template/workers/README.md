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
    type: agent            # agent / skill / mcp / workflow / sandbox / subagent / human
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
  # 🆕 V6.0 mode 选项：
  #   - disabled: 禁用，始终使用 SimpleAgent（默认）
  #   - auto: 自动判断（基于任务复杂度和关键词）
  #   - enabled: 始终使用 Multi-Agent
  mode: "auto"  # 或 "enabled"
  
  # 最大并发 Worker 数
  max_parallel_workers: 5
  
  # 执行策略：auto | parallel | sequential
  execution_strategy: "auto"
```

## Worker 类型说明

| 类型 | 执行主体 | 适用场景 | 成本 | 延迟 |
|------|----------|----------|------|------|
| `agent` | 内置 Agent | 通用任务、需要深度推理 | 低 | 低 |
| `skill` | Claude + Skill | 专业任务、高质量输出 | 低 | 低 |
| `mcp` | 远程 MCP Server | 已有 MCP 服务 | 中 | 中 |
| `workflow` | Coze/Dify | 复杂流程、可视化配置 | 中 | 中 |
| `sandbox` | E2B/沙箱 | 代码执行、数据分析 | 中 | 中 |
| `subagent` | Claude 子智能体 | 上下文隔离、工具密集 | 低 | 低 |
| `human` | 人类专家 | 审核、决策、敏感处理 | 高 | 高 |

## 使用场景

Multi-Agent 适用于可并行化的复杂任务：

- ✅ "重构代码，同时优化 CSS 并补充测试"
- ✅ "分析 10 家公司的财报"
- ✅ "多维度分析市场趋势"
- ❌ 简单的单步任务
- ❌ 强依赖的串行任务

## 示例：添加新 Worker

### 1. 创建目录和提示词

```bash
mkdir workers/analyst
cat > workers/analyst/prompt.md << 'EOF'
# 数据分析专家

你是一个数据分析专家，专注于：
- 数据清洗和预处理
- 统计分析
- 可视化建议

## 输出规范
- 使用 Markdown 表格展示数据
- 提供关键洞察
- 建议下一步分析方向
EOF
```

### 2. 在 worker_registry.yaml 中注册

```yaml
workers:
  # ... 现有 Workers ...
  
  - name: analyst
    type: agent
    specialization: data_analysis
    enabled: true
    description: "数据分析专家"
    capabilities:
      - data_processing
      - visualization
```

### 3. 启用 Multi-Agent

```yaml
# config.yaml
multi_agent:
  mode: "auto"  # 或 "enabled"
```

## 调试 Workers

查看启动日志，会显示：
- Workers 加载状态
- 哪些 Workers 启用
- Multi-Agent 模式

```
2026-01-13 10:00:00 [INFO] Multi-Agent: 已启用 (mode=auto)
2026-01-13 10:00:00 [INFO] Workers: 3 个 (3 启用)
2026-01-13 10:00:00 [INFO]    • refactor (refactor)
2026-01-13 10:00:00 [INFO]    • css (css)
2026-01-13 10:00:00 [INFO]    • test (test)
```

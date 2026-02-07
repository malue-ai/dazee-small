# 智能体实例创建指南

> **设计理念**: LLM-First（大模型优先）— 充分信任大模型的语义理解和深度推理能力  
> **架构全景图**: 👉 [CONFIGURATION_GUIDE.md](./CONFIGURATION_GUIDE.md)

## 快速开始（3 步完成）

### Step 1: 复制模板

```bash
# 在 instances/ 目录下创建新实例
cp -r _template my_agent
```

### Step 2: 编写提示词

编辑 `my_agent/prompt.md`，按模板填写：

| 章节 | 必填 | 说明 |
|------|------|------|
| 角色定义 | ✅ | 描述智能体的身份和定位 |
| 核心能力 | ✅ | 用自然语言描述能力（LLM 自动语义推断） |
| 工作规则 | ⬜ | 特定的工作流程或限制 |
| 专属工具说明 | ⬜ | 对 MCP 工具的使用指导 |
| 输出风格 | ⬜ | 回复格式和语言风格 |
| 限制与边界 | ⬜ | 明确不应该做什么 |

### Step 3: 配置密钥

全局 API Key 已在项目根目录 `config.yaml` 中管理。
如果实例需要额外的环境变量，在 `config.yaml` 的 `env_vars` 段添加：

```yaml
# config.yaml
env_vars:
  CUSTOM_API_KEY: "xxx..."
```

## 启动智能体

```bash
# 在项目根目录运行
python scripts/instance_loader.py --instance my_agent
```

## 🆕 自动生成的 prompt_results 目录

首次启动时，框架会自动分析 `prompt.md` 并生成优化后的系统提示词：

```
my_agent/
├── prompt.md              # 运营编写的原始提示词
├── config.yaml            # 配置文件（含 env_vars 环境变量段）
└── prompt_results/        # 🆕 框架自动生成
    ├── README.md          # 使用说明
    ├── _metadata.json     # 元数据（哈希、时间戳）
    ├── agent_schema.yaml  # Agent 配置（组件、工具、参数）
    ├── intent_prompt.md   # 意图识别专用提示词
    ├── simple_prompt.md   # 简单任务提示词
    ├── medium_prompt.md   # 中等任务提示词
    └── complex_prompt.md  # 复杂任务提示词
```

### prompt_results 使用说明

| 文件 | 用途 | 可编辑 |
|------|------|--------|
| `agent_schema.yaml` | Agent 配置（组件、工具、参数） | ✅ 是 |
| `intent_prompt.md` | 意图识别专用提示词 | ✅ 是 |
| `simple_prompt.md` | 简单任务处理提示词 | ✅ 是 |
| `medium_prompt.md` | 中等任务处理提示词 | ✅ 是 |
| `complex_prompt.md` | 复杂任务处理提示词 | ✅ 是 |

**运营二次编辑**：
- 可以直接编辑任意 `.md` 或 `.yaml` 文件
- 系统会检测您的手动修改，下次更新时**不会覆盖**
- 如需强制重新生成，删除 `_metadata.json` 或使用 `--force-refresh`

**动态更新策略**：
- 修改 `prompt.md` 后，**未手动编辑的文件**会自动更新
- 您手动编辑的文件会被保护
- 如需全部重新生成，删除整个 `prompt_results/` 目录

## LLM 语义推断（LLM-First）

框架采用 **LLM-First** 设计理念，通过大模型深度语义理解来推断所需能力，而非简单的关键词匹配。

### 工作原理

```
用户输入: "你是一个数据分析师，能够处理 Excel 和进行数据可视化"

LLM 语义分析:
├─ 角色: 数据分析师
├─ 能力1: "处理 Excel" → 需要 Excel 读写能力
├─ 能力2: "数据可视化" → 需要图表生成能力
├─ 隐含需求: 可能需要代码执行分析
│
自动推断结果:
├─ xlsx: true
├─ code_execution: true
└─ plan_manager: true (数据分析通常需要多步骤)
```

### 语义推断 vs 关键词匹配

| 场景 | 关键词匹配 | LLM 语义推断 |
|------|-----------|-------------|
| "构造CRM系统" | 匹配"系统"→complex | 理解"构造"是 build 动作→complex ✅ |
| "系统怎么用?" | 匹配"系统"→complex ❌ | 理解是询问用法→simple ✅ |
| "不要做PPT" | 匹配"PPT"→启用 pptx ❌ | 理解否定语义→不启用 ✅ |

**示例**：在 `prompt.md` 中写"具备数据分析能力"，LLM 会语义理解并自动推断需要启用相关工具。

## 配置 MCP 工具

如果需要使用外部 MCP 工具（如 Dify 工作流），在 `config.yaml` 中声明：

```yaml
mcp_tools:
  - name: dify_workflow
    server_url: "https://api.dify.ai/mcp/server/xxx/mcp"
    server_name: "dify"
    auth_type: "bearer"
    auth_env: "DIFY_API_KEY"
```

实例独有的密钥在 `config.yaml` 的 `env_vars` 段配置：

```yaml
env_vars:
  DIFY_API_KEY: "app-xxx"
```

## 目录结构

```
my_agent/
├── prompt.md              # 核心！智能体定义（运营填写）
├── config.yaml            # 配置覆盖、MCP 工具声明和环境变量
├── prompt_results/        # 🆕 框架自动生成的优化提示词
│   ├── README.md          # 使用说明
│   ├── agent_schema.yaml  # Agent 配置
│   ├── intent_prompt.md   # 意图识别提示词
│   ├── simple_prompt.md   # 简单任务提示词
│   ├── medium_prompt.md   # 中等任务提示词
│   └── complex_prompt.md  # 复杂任务提示词
├── workers/               # Multi-Agent Workers 配置
│   ├── worker_registry.yaml
│   └── {worker_name}/prompt.md
├── skills/                # Claude Skills 配置
│   └── skill_registry.yaml
└── api_desc/              # REST API 描述文档
    └── {api_name}.md
```

## Multi-Agent 配置

在 `config.yaml` 中配置多智能体模式：

```yaml
multi_agent:
  # mode 选项：
  #   - disabled: 禁用（默认），始终使用 SimpleAgent
  #   - auto: 自动判断（基于 LLM 语义分析任务复杂度）
  #   - enabled: 始终使用 Multi-Agent
  mode: "disabled"
  
  # 最大并行 Worker 数
  max_parallel_workers: 5
```

## 常见问题

### Q: prompt_results 生成失败？

1. 检查 `ANTHROPIC_API_KEY` 是否配置正确
2. 检查网络连接
3. 查看日志中的错误信息
4. 尝试删除 `prompt_results/` 重新生成

### Q: 如何添加新能力？

在 `prompt.md` 的"核心能力"章节用自然语言描述即可，LLM 会自动语义推断所需工具。

### Q: 配置没生效？

检查优先级：`config.yaml` > LLM 推断 > 默认值。如果需要强制覆盖，在 `config.yaml` 中显式配置。

### Q: MCP 工具连接失败？

1. 检查 `config.yaml` 中的 `server_url` 是否正确
2. 检查 `config.yaml` 的 `env_vars` 段中密钥是否配置
3. 检查网络连接

### Q: 如何强制重新生成 prompt_results？

```bash
# 方式 1：删除元数据
rm instances/my_agent/prompt_results/_metadata.json

# 方式 2：删除整个目录
rm -rf instances/my_agent/prompt_results/

# 方式 3：使用命令行参数
python scripts/instance_loader.py --instance my_agent --force-refresh
```

### Q: 编辑了 prompt_results 中的文件，但想恢复自动生成？

删除对应文件（如 `simple_prompt.md`），下次启动时会重新生成。
